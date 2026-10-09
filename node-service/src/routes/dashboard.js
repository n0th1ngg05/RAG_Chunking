const express = require("express");
const router = express.Router();

router.get("/", (req, res) => {
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DocStack — Document Ingestion Performance Metrics</title>
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: #111827;
      --card-border: #1f2937;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --primary: #38bdf8;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --accent: #8b5cf6;
      --extract-color: #06b6d4;
      --parse-color: #3b82f6;
      --chunk-color: #ec4899;
      --val-color: #f59e0b;
      --embed-color: #10b981;
      --db-color: #a855f7;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background-color: var(--bg); color: var(--text); padding: 24px; min-height: 100vh; }
    .container { max-width: 1300px; margin: 0 auto; }
    
    header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; border-bottom: 1px solid var(--card-border); padding-bottom: 16px; flex-wrap: wrap; gap: 16px; }
    .title-group h1 { font-size: 24px; font-weight: 700; color: #fff; display: flex; align-items: center; gap: 10px; }
    .title-group p { font-size: 14px; color: var(--text-muted); margin-top: 4px; }
    .badge { font-size: 11px; padding: 3px 8px; border-radius: 999px; text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px; }
    .badge-live { background: rgba(16, 185, 129, 0.15); color: var(--success); border: 1px solid rgba(16, 185, 129, 0.3); }

    .auth-bar { display: flex; align-items: center; gap: 10px; }
    .auth-bar input { background: #1f2937; border: 1px solid #374151; color: #fff; padding: 8px 12px; border-radius: 6px; font-size: 13px; width: 280px; }
    .auth-bar button { background: #2563eb; color: #fff; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600; transition: 0.2s; }
    .auth-bar button:hover { background: #1d4ed8; }

    /* KPI Grid */
    .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .kpi-card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 10px; padding: 18px; display: flex; flex-direction: column; }
    .kpi-title { font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; font-weight: 600; }
    .kpi-val { font-size: 26px; font-weight: 700; color: #fff; }
    .kpi-sub { font-size: 12px; color: var(--text-muted); margin-top: 6px; }

    /* Comparison Section */
    .section-card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 10px; padding: 22px; margin-bottom: 24px; }
    .section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px; }
    .section-title { font-size: 17px; font-weight: 600; color: #fff; display: flex; align-items: center; gap: 8px; }

    /* Stage legend */
    .stage-legend { display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; margin-bottom: 16px; padding: 10px 14px; background: rgba(31, 41, 55, 0.4); border-radius: 8px; }
    .legend-item { display: flex; align-items: center; gap: 6px; }
    .legend-dot { width: 10px; height: 10px; border-radius: 3px; }

    /* Table */
    .table-container { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }
    th { padding: 12px; color: var(--text-muted); border-bottom: 1px solid var(--card-border); font-weight: 600; text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px; }
    td { padding: 14px 12px; border-bottom: 1px solid rgba(31, 41, 55, 0.7); vertical-align: middle; }
    tr:hover td { background-color: rgba(31, 41, 55, 0.3); }

    .status-badge { display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; text-transform: uppercase; }
    .status-completed { background: rgba(16, 185, 129, 0.2); color: #34d399; }
    .status-failed { background: rgba(239, 68, 68, 0.2); color: #f87171; }
    .status-pending { background: rgba(245, 158, 11, 0.2); color: #fbbf24; }

    /* Horizontal Stacked Duration Bar */
    .stage-bar-container { width: 100%; min-width: 220px; display: flex; flex-direction: column; gap: 4px; }
    .stacked-bar { display: flex; height: 16px; border-radius: 4px; overflow: hidden; background: #1f2937; }
    .bar-segment { height: 100%; transition: width 0.3s; position: relative; }
    .bar-labels { display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted); }

    .empty-state { text-align: center; padding: 48px 16px; color: var(--text-muted); }
    .empty-icon { font-size: 32px; margin-bottom: 12px; }

    .highlight-cell { font-weight: 600; color: #fff; }
    .dim-cell { color: var(--text-muted); }

    .reference-box { background: rgba(56, 189, 248, 0.05); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 8px; padding: 14px; margin-bottom: 20px; font-size: 13px; line-height: 1.5; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="title-group">
        <h1>DocStack Dashboard <span class="badge badge-live">Live Telemetry</span></h1>
        <p>Document Ingestion & Chunking Performance Analytics</p>
      </div>
      <div class="auth-bar">
        <input type="text" id="jwtToken" placeholder="Paste JWT Bearer Token (or Login)" />
        <button onclick="fetchMetrics()">Refresh Metrics</button>
      </div>
    </header>

    <div class="reference-box">
      <strong>Telemetry Engine:</strong> Live metrics are captured at sub-millisecond precision during execution and persisted permanently in PostgreSQL. Timestamps correlate Node.js upload arrival with Python worker execution stages.
    </div>

    <!-- Summary KPIs -->
    <div class="kpi-grid">
      <div class="kpi-card">
        <span class="kpi-title">Total Documents</span>
        <span class="kpi-val" id="kpiTotalDocs">--</span>
        <span class="kpi-sub" id="kpiStatusBreakdown">0 completed · 0 failed</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-title">Total Chunks</span>
        <span class="kpi-val" id="kpiTotalChunks" style="color: var(--primary);">--</span>
        <span class="kpi-sub">Vector embeddings stored</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-title">Avg Worker Duration</span>
        <span class="kpi-val" id="kpiAvgWorker">--</span>
        <span class="kpi-sub" id="kpiMedianWorker">Median: --</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-title">Avg Upload-to-Completion</span>
        <span class="kpi-val" id="kpiAvgE2E" style="color: #34d399;">--</span>
        <span class="kpi-sub" id="kpiMedianE2E">Median: --</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-title">Avg Queue Wait</span>
        <span class="kpi-val" id="kpiAvgQueue">--</span>
        <span class="kpi-sub">Redis hand-off latency</span>
      </div>
      <div class="kpi-card">
        <span class="kpi-title">Avg Embedding Time</span>
        <span class="kpi-val" id="kpiAvgEmbed" style="color: var(--embed-color);">--</span>
        <span class="kpi-sub">Ollama local inference</span>
      </div>
    </div>

    <!-- Per-Document Processing History & Horizontal Duration Breakdown -->
    <div class="section-card">
      <div class="section-header">
        <div class="section-title">
          <span>Per-Document Processing History & Stage Breakdown</span>
        </div>
      </div>

      <div class="stage-legend">
        <div class="legend-item"><div class="legend-dot" style="background: var(--extract-color);"></div> Text Extraction</div>
        <div class="legend-item"><div class="legend-dot" style="background: var(--parse-color);"></div> Structure Parsing</div>
        <div class="legend-item"><div class="legend-dot" style="background: var(--chunk-color);"></div> Section Chunking</div>
        <div class="legend-item"><div class="legend-dot" style="background: var(--val-color);"></div> Chunk Validation</div>
        <div class="legend-item"><div class="legend-dot" style="background: var(--embed-color);"></div> Embedding Generation</div>
        <div class="legend-item"><div class="legend-dot" style="background: var(--db-color);"></div> DB Persistence</div>
      </div>

      <div class="table-container">
        <table id="historyTable">
          <thead>
            <tr>
              <th>ID</th>
              <th>Document Name</th>
              <th>Format</th>
              <th>Size</th>
              <th>Chunks</th>
              <th>Status</th>
              <th>Queue Wait</th>
              <th>Worker Pipeline</th>
              <th>Upload-to-Done</th>
              <th style="min-width: 260px;">Stage-by-Stage Duration Breakdown</th>
            </tr>
          </thead>
          <tbody id="historyBody">
            <tr>
              <td colspan="10">
                <div class="empty-state">
                  <div class="empty-icon">⏳</div>
                  <p>Loading performance telemetry...</p>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    // Load stored token
    const storedToken = localStorage.getItem("docstack_token") || "";
    if (storedToken) {
      document.getElementById("jwtToken").value = storedToken;
    }

    async function fetchMetrics() {
      const tokenInput = document.getElementById("jwtToken").value.trim();
      if (tokenInput) {
        localStorage.setItem("docstack_token", tokenInput);
      }

      const headers = {};
      if (tokenInput) {
        headers["Authorization"] = "Bearer " + tokenInput;
      }

      try {
        const res = await fetch("/documents/metrics", { headers });
        if (res.status === 401) {
          showEmptyState("Authentication required. Please enter a valid JWT token above.");
          return;
        }
        if (!res.ok) {
          throw new Error("HTTP " + res.status);
        }

        const data = await res.json();
        renderDashboard(data);
      } catch (err) {
        console.error("Failed to load metrics:", err);
        showEmptyState("Could not retrieve metrics. Ensure the API service is running and token is valid.");
      }
    }

    function showEmptyState(msg) {
      document.getElementById("historyBody").innerHTML = \`
        <tr>
          <td colspan="10">
            <div class="empty-state">
              <div class="empty-icon">🔒</div>
              <p>\${msg}</p>
            </div>
          </td>
        </tr>
      \`;
    }

    function renderDashboard(data) {
      const s = data.summary;
      const h = data.history;

      // Update KPI cards
      document.getElementById("kpiTotalDocs").innerText = s.total_documents_processed || 0;
      document.getElementById("kpiStatusBreakdown").innerText = \`\${s.total_completed} completed · \${s.total_failed} failed\`;
      document.getElementById("kpiTotalChunks").innerText = s.total_chunks_generated || 0;

      if (s.sufficient_data) {
        document.getElementById("kpiAvgWorker").innerText = (s.worker_pipeline_duration.average_s !== null ? s.worker_pipeline_duration.average_s.toFixed(2) + "s" : "--");
        document.getElementById("kpiMedianWorker").innerText = "Median: " + (s.worker_pipeline_duration.median_s !== null ? s.worker_pipeline_duration.median_s.toFixed(2) + "s" : "--");

        document.getElementById("kpiAvgE2E").innerText = (s.upload_to_completion_duration.average_s !== null ? s.upload_to_completion_duration.average_s.toFixed(2) + "s" : "--");
        document.getElementById("kpiMedianE2E").innerText = "Median: " + (s.upload_to_completion_duration.median_s !== null ? s.upload_to_completion_duration.median_s.toFixed(2) + "s" : "--");

        document.getElementById("kpiAvgQueue").innerText = (s.queue_wait_duration.average_s !== null ? s.queue_wait_duration.average_s.toFixed(3) + "s" : "--");
        document.getElementById("kpiAvgEmbed").innerText = (s.embedding_generation_duration.average_s !== null ? s.embedding_generation_duration.average_s.toFixed(2) + "s" : "--");
      } else {
        document.getElementById("kpiAvgWorker").innerText = "--";
        document.getElementById("kpiMedianWorker").innerText = "Insufficient data";
        document.getElementById("kpiAvgE2E").innerText = "--";
        document.getElementById("kpiMedianE2E").innerText = "Insufficient data";
        document.getElementById("kpiAvgQueue").innerText = "--";
        document.getElementById("kpiAvgEmbed").innerText = "--";
      }

      // Render table rows
      if (!h || h.length === 0) {
        document.getElementById("historyBody").innerHTML = \`
          <tr>
            <td colspan="10">
              <div class="empty-state">
                <div class="empty-icon">📂</div>
                <p>No document processing records found.</p>
              </div>
            </td>
          </tr>
        \`;
        return;
      }

      const rows = h.map((doc) => {
        const sizeKb = (doc.size_bytes / 1024).toFixed(1) + " KB";
        const statusClass = "status-" + (doc.status || "pending");
        const queueWait = doc.queue_wait_duration_s !== null ? doc.queue_wait_duration_s.toFixed(3) + "s" : "--";
        const workerDur = doc.worker_pipeline_duration_s !== null ? doc.worker_pipeline_duration_s.toFixed(2) + "s" : "--";
        const e2eDur = doc.upload_to_completion_duration_s !== null ? doc.upload_to_completion_duration_s.toFixed(2) + "s" : "--";

        // Stage duration bars
        let barHtml = '<span class="dim-cell">No stage timings</span>';
        if (doc.stage_timings) {
          const st = doc.stage_timings;
          const ext = st.text_extraction_s || 0;
          const prs = st.structure_parsing_s || 0;
          const chk = st.section_chunking_s || 0;
          const val = st.chunk_validation_s || 0;
          const emb = st.embedding_generation_s || 0;
          const dbs = st.database_persistence_s || 0;
          const total = (ext + prs + chk + val + emb + dbs) || 1;

          const pExt = ((ext / total) * 100).toFixed(1);
          const pPrs = ((prs / total) * 100).toFixed(1);
          const pChk = ((chk / total) * 100).toFixed(1);
          const pVal = ((val / total) * 100).toFixed(1);
          const pEmb = ((emb / total) * 100).toFixed(1);
          const pDbs = ((dbs / total) * 100).toFixed(1);

          barHtml = \`
            <div class="stage-bar-container">
              <div class="stacked-bar">
                <div class="bar-segment" style="width: \${pExt}%; background: var(--extract-color);" title="Text Extraction: \${ext.toFixed(2)}s (\${pExt}%)"></div>
                <div class="bar-segment" style="width: \${pPrs}%; background: var(--parse-color);" title="Structure Parsing: \${prs.toFixed(2)}s (\${pPrs}%)"></div>
                <div class="bar-segment" style="width: \${pChk}%; background: var(--chunk-color);" title="Section Chunking: \${chk.toFixed(2)}s (\${pChk}%)"></div>
                <div class="bar-segment" style="width: \${pVal}%; background: var(--val-color);" title="Validation: \${val.toFixed(2)}s (\${pVal}%)"></div>
                <div class="bar-segment" style="width: \${pEmb}%; background: var(--embed-color);" title="Embedding Generation: \${emb.toFixed(2)}s (\${pEmb}%)"></div>
                <div class="bar-segment" style="width: \${pDbs}%; background: var(--db-color);" title="Database Persistence: \${dbs.toFixed(2)}s (\${pDbs}%)"></div>
              </div>
              <div class="bar-labels">
                <span>Ext: \${ext.toFixed(2)}s</span>
                <span>Embed: \${emb.toFixed(2)}s</span>
                <span>DB: \${dbs.toFixed(2)}s</span>
              </div>
            </div>
          \`;
        } else if (doc.status === "failed") {
          barHtml = \`<span style="color: var(--danger); font-size: 11px;">Failed: \${doc.error_message || 'Processing error'}</span>\`;
        }

        return \`
          <tr>
            <td class="dim-cell">#\${doc.document_id}</td>
            <td class="highlight-cell">\${doc.document_name}</td>
            <td><span class="badge" style="background:#1f2937; color:#cbd5e1;">\${doc.file_type}</span></td>
            <td>\${sizeKb}</td>
            <td class="highlight-cell">\${doc.chunks_count || '--'}</td>
            <td><span class="status-badge \${statusClass}">\${doc.status}</span></td>
            <td class="dim-cell">\${queueWait}</td>
            <td class="highlight-cell">\${workerDur}</td>
            <td style="color: #34d399; font-weight: 600;">\${e2eDur}</td>
            <td>\${barHtml}</td>
          </tr>
        \`;
      }).join("");

      document.getElementById("historyBody").innerHTML = rows;
    }

    // Auto-fetch on initial page load
    fetchMetrics();
  </script>
</body>
</html>`;

  res.setHeader("Content-Type", "text/html; charset=utf-8");
  return res.send(html);
});

module.exports = router;
