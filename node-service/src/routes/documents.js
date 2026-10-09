const express = require("express");
const multer = require("multer");
const path = require("path");
const fs = require("fs/promises");
const crypto = require("crypto");

const { requireAuth } = require("../middleware/auth");
const { withUserContext } = require("../db/withUserContext");
const { validateUpload } = require("../utils/validateUpload");
const { ingestionQueue } = require("../queue/ingestionQueue");
const logger = require("../utils/logger");

const router = express.Router();

const MAX_UPLOAD_BYTES = Number(process.env.MAX_UPLOAD_SIZE_MB || 25) * 1024 * 1024;
const UPLOAD_DIR = process.env.UPLOAD_DIR || "/app/uploads";

// Buffer the upload in memory first (needed to inspect magic bytes before
// deciding whether to accept it at all); capped by MAX_UPLOAD_BYTES so a
// malicious huge upload can't exhaust memory before validation runs.
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: MAX_UPLOAD_BYTES },
});

router.use(requireAuth);

// POST /documents/upload
router.post("/upload", upload.single("file"), async (req, res) => {
  if (!req.file) {
    logger.warn(`Upload attempt with no file attachment by user_id=${req.user.id}`);
    return res.status(400).json({ error: "No file provided (expected form field 'file')" });
  }

  const rawSizeKb = (req.file.size / 1024).toFixed(1);
  logger.upload(
    `Received upload '${req.file.originalname}' (${rawSizeKb} KB) from user_id=${req.user.id}`
  );

  const validation = await validateUpload(req.file.buffer, req.file.originalname);
  if (!validation.ok) {
    logger.warn(
      `Upload rejected for '${req.file.originalname}': ${validation.reason}`
    );
    return res.status(415).json({ error: `Unsupported file: ${validation.reason}` });
  }

  logger.success(
    `Validated '${req.file.originalname}': type=${validation.file_type}, mime=${validation.mime_type}`
  );

  const storedName = `${crypto.randomUUID()}-${path.basename(req.file.originalname)}`;
  const storagePath = path.resolve(UPLOAD_DIR, storedName);

  try {
    await fs.mkdir(UPLOAD_DIR, { recursive: true });
    await fs.writeFile(storagePath, req.file.buffer);
    logger.upload(`Persisted file to disk: ${storagePath}`);

    const document = await withUserContext(req.user.id, async (client) => {
      const result = await client.query(
        `INSERT INTO documents
           (document_name, uploaded_by, size_bytes, file_type, mime_type, storage_path, status)
         VALUES ($1, $2, $3, $4, $5, $6, 'pending')
         RETURNING id, document_name, uploaded_at, size_bytes, file_type, mime_type, status`,
        [
          req.file.originalname,
          req.user.id,
          req.file.size,
          validation.file_type,
          validation.mime_type,
          storagePath,
        ]
      );
      const row = result.rows[0];
      if (row) {
        row.id = Number(row.id);
        row.size_bytes = Number(row.size_bytes);
      }
      return row;
    });

    logger.db(
      `Document row created: id=${document.id}, name='${document.document_name}', status='${document.status}'`
    );

    const uploadedAtMs = Date.now();
    await ingestionQueue.add("ingest", {
      document_id: Number(document.id),
      storage_path: storagePath,
      file_type: validation.file_type,
      uploaded_at_ms: uploadedAtMs,
    });

    logger.queue(
      `Enqueued job for worker: document_id=${document.id}, file_type=${validation.file_type} (upload_time: ${new Date(uploadedAtMs).toISOString()})`
    );


    return res.status(202).json({
      message: "Document uploaded and queued for processing",
      document,
    });
  } catch (err) {
    // Best-effort cleanup of the written file if the DB insert or enqueue failed.
    await fs.unlink(storagePath).catch(() => {});
    logger.error(`Upload error for '${req.file.originalname}':`, err);
    return res.status(500).json({ error: "Internal server error" });
  }
});

// GET /documents/metrics — returns aggregate and per-document ingestion performance metrics
router.get("/metrics", async (req, res) => {
  const documents = await withUserContext(req.user.id, async (client) => {
    const result = await client.query(
      `SELECT id, document_name, uploaded_at, size_bytes, file_type, status, error_message, processing_started_at, metrics
       FROM documents
       ORDER BY id DESC`
    );
    return result.rows.map((row) => ({
      ...row,
      id: Number(row.id),
      size_bytes: Number(row.size_bytes),
    }));
  });

  const totalDocuments = documents.length;
  const completedDocs = documents.filter((d) => d.status === "completed");
  const failedDocs = documents.filter((d) => d.status === "failed");
  const pendingDocs = documents.filter((d) => d.status === "pending" || d.status === "processing");

  // Filter completed runs that have recorded timing metrics
  const runsWithMetrics = completedDocs.filter(
    (d) =>
      d.metrics &&
      typeof d.metrics === "object" &&
      (d.metrics.worker_pipeline_duration_s !== undefined || d.metrics.stage_timings !== undefined)
  );

  let totalChunks = 0;
  for (const doc of completedDocs) {
    if (doc.metrics && doc.metrics.chunks_count) {
      totalChunks += Number(doc.metrics.chunks_count);
    }
  }

  // Helper functions for stats
  const calcMedian = (arr) => {
    if (!arr || arr.length === 0) return null;
    const sorted = [...arr].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 !== 0
      ? sorted[mid]
      : Number(((sorted[mid - 1] + sorted[mid]) / 2).toFixed(4));
  };

  const calcAverage = (arr) => {
    if (!arr || arr.length === 0) return null;
    const sum = arr.reduce((acc, val) => acc + val, 0);
    return Number((sum / arr.length).toFixed(4));
  };

  const workerDurations = runsWithMetrics
    .map((d) => Number(d.metrics.worker_pipeline_duration_s))
    .filter((n) => Number.isFinite(n));

  const e2eDurations = runsWithMetrics
    .map((d) => Number(d.metrics.upload_to_completion_duration_s))
    .filter((n) => Number.isFinite(n));

  const queueWaitDurations = runsWithMetrics
    .map((d) => Number(d.metrics.queue_wait_duration_s))
    .filter((n) => Number.isFinite(n));

  const embeddingDurations = runsWithMetrics
    .map((d) => Number(d.metrics.stage_timings?.embedding_generation_s))
    .filter((n) => Number.isFinite(n));

  const dbDurations = runsWithMetrics
    .map((d) => Number(d.metrics.stage_timings?.database_persistence_s))
    .filter((n) => Number.isFinite(n));

  const extractionDurations = runsWithMetrics
    .map((d) => Number(d.metrics.stage_timings?.text_extraction_s))
    .filter((n) => Number.isFinite(n));

  const aggregates = {
    total_documents_processed: totalDocuments,
    total_completed: completedDocs.length,
    total_failed: failedDocs.length,
    total_pending: pendingDocs.length,
    total_chunks_generated: totalChunks,
    sufficient_data: runsWithMetrics.length > 0,
    metrics_recorded_runs_count: runsWithMetrics.length,
    worker_pipeline_duration: {
      average_s: calcAverage(workerDurations),
      median_s: calcMedian(workerDurations),
      min_s: workerDurations.length ? Math.min(...workerDurations) : null,
      max_s: workerDurations.length ? Math.max(...workerDurations) : null,
    },
    upload_to_completion_duration: {
      average_s: calcAverage(e2eDurations),
      median_s: calcMedian(e2eDurations),
      min_s: e2eDurations.length ? Math.min(...e2eDurations) : null,
      max_s: e2eDurations.length ? Math.max(...e2eDurations) : null,
    },
    queue_wait_duration: {
      average_s: calcAverage(queueWaitDurations),
      median_s: calcMedian(queueWaitDurations),
    },
    embedding_generation_duration: {
      average_s: calcAverage(embeddingDurations),
    },
    database_persistence_duration: {
      average_s: calcAverage(dbDurations),
    },
    text_extraction_duration: {
      average_s: calcAverage(extractionDurations),
    },
  };

  const history = documents.map((doc) => {
    const m = doc.metrics || {};
    return {
      document_id: doc.id,
      document_name: doc.document_name,
      file_type: doc.file_type,
      size_bytes: doc.size_bytes,
      status: doc.status,
      uploaded_at: doc.uploaded_at,
      error_message: doc.error_message,
      chunks_count: m.chunks_count || null,
      queue_wait_duration_s: m.queue_wait_duration_s ?? null,
      worker_pipeline_duration_s: m.worker_pipeline_duration_s ?? null,
      upload_to_completion_duration_s: m.upload_to_completion_duration_s ?? null,
      stage_timings: m.stage_timings || null,
      timestamps: m.timestamps || {
        uploaded_at_ms: m.uploaded_at_ms,
        dequeued_at_ms: m.dequeued_at_ms,
        completed_at_ms: m.completed_at_ms,
      },
    };
  });

  logger.info(`Metrics requested for user_id=${req.user.id}: ${runsWithMetrics.length} runs with telemetry`);
  return res.json({
    summary: aggregates,
    history,
  });
});

// GET /documents/:id — status + metadata + metrics, RLS ensures only the owner can see it
router.get("/:id", async (req, res) => {
  const id = Number(req.params.id);
  if (!Number.isInteger(id)) {
    logger.warn(`Invalid document id requested: '${req.params.id}'`);
    return res.status(400).json({ error: "Invalid document id" });
  }

  const document = await withUserContext(req.user.id, async (client) => {
    const result = await client.query(
      `SELECT id, document_name, uploaded_at, size_bytes, file_type, mime_type, status, error_message, metrics
       FROM documents WHERE id = $1`,
      [id]
    );
    const row = result.rows[0];
    if (row) {
      row.id = Number(row.id);
      row.size_bytes = Number(row.size_bytes);
    }
    return row;
  });

  if (!document) {
    logger.warn(`Document id=${id} not found or not owned by user_id=${req.user.id}`);
    return res.status(404).json({ error: "Document not found" });
  }

  logger.info(
    `Fetched document id=${id}: status='${document.status}', file='${document.document_name}'`
  );
  return res.json({ document });
});

// GET /documents — list the current user's documents
router.get("/", async (req, res) => {
  const documents = await withUserContext(req.user.id, async (client) => {
    const result = await client.query(
      `SELECT id, document_name, uploaded_at, size_bytes, file_type, status
       FROM documents ORDER BY uploaded_at DESC LIMIT 100`
    );
    return result.rows.map((row) => ({
      ...row,
      id: Number(row.id),
      size_bytes: Number(row.size_bytes),
    }));
  });
  logger.info(`Listing documents for user_id=${req.user.id}: returned ${documents.length} items`);
  return res.json({ documents });
});

// GET /documents/:id/chunks — retrieve chunks for a completed document
router.get("/:id/chunks", async (req, res) => {
  const id = Number(req.params.id);
  if (!Number.isInteger(id)) {
    logger.warn(`Invalid document id requested for chunks: '${req.params.id}'`);
    return res.status(400).json({ error: "Invalid document id" });
  }

  const chunks = await withUserContext(req.user.id, async (client) => {
    const result = await client.query(
      `SELECT dc.id, dc.chunk_index, dc.content, dc.page_number, dc.metadata
       FROM document_chunks dc
       WHERE dc.document_id = $1
       ORDER BY dc.chunk_index`,
      [id]
    );
    return result.rows.map((row) => ({
      ...row,
      id: Number(row.id),
    }));
  });

  logger.success(`Retrieved ${chunks.length} chunks for document_id=${id}`);
  return res.json({ chunks });
});


module.exports = router;

