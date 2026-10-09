import json
import logging
import time
from datetime import datetime
from pathlib import Path

from app.core.database import get_pool
from app.core.logger import Colors, log_pipeline_step
from app.services.chunker import chunk_sections
from app.services.embeddings import generate_embeddings_batch
from app.services.extractor import extract_text
from app.services.structure_parser import parse_document_structure
from app.services.validator import validate_chunks

logger = logging.getLogger("ingestion")


MAX_CHUNK_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 50


def _resolve_file_path(storage_path: str) -> str:
    """Ensures storage_path is resolved to an absolute, existing file path."""
    p = Path(storage_path)
    if p.is_file():
        return str(p.resolve())

    candidates = [
        Path.cwd() / storage_path,
        Path.cwd().parent / storage_path,
        Path.cwd().parent / "node-service" / storage_path,
        Path.cwd() / "node-service" / storage_path,
        Path.cwd() / "uploads" / p.name,
        Path.cwd().parent / "uploads" / p.name,
        Path.cwd().parent / "node-service" / "uploads" / p.name,
    ]
    for cand in candidates:
        if cand.is_file():
            return str(cand.resolve())
    return str(p.resolve())


async def process_document(
    document_id: int | str,
    storage_path: str,
    file_type: str,
    uploaded_at_ms: float | int | None = None,
) -> int:
    """Full pipeline for one document:
    1. Extract text with word boundary & cross-page stitching
    2. Parse document structure (headings, paragraphs, lists)
    3. Section-based token chunking
    4. Pre-embedding validation (empty, broken, duplicate, malformed)
    5. Generate vector embeddings via Ollama
    6. Persist chunks with full metadata to PostgreSQL (pgvector)
    """
    document_id = int(document_id)
    storage_path = _resolve_file_path(storage_path)

    pool = await get_pool()
    pipeline_start = time.perf_counter()

    # If uploaded_at_ms was not passed in Redis payload, fetch uploaded_at from DB
    if uploaded_at_ms is None:
        try:
            row = await pool.fetchrow("SELECT uploaded_at FROM documents WHERE id = $1", document_id)
            if row and row["uploaded_at"]:
                uploaded_at_ms = row["uploaded_at"].timestamp() * 1000.0
        except Exception:
            pass

    worker_start_epoch_ms = time.time() * 1000.0
    queue_wait_s = ((worker_start_epoch_ms - uploaded_at_ms) / 1000.0) if uploaded_at_ms else 0.0

    logger.info("Initializing ingestion pipeline for document_id=%s (type: %s)", document_id, file_type)

    await pool.execute(
        """
        UPDATE documents
        SET status = 'processing', processing_started_at = NOW()
        WHERE id = $1
        """,
        document_id,
    )
    logger.info("Updated status to 'processing' for document_id=%s", document_id)

    try:
        chunks_count = await _run_pipeline(
            pool,
            document_id,
            storage_path,
            file_type,
            uploaded_at_ms=uploaded_at_ms,
            queue_wait_s=queue_wait_s,
            worker_start_epoch_ms=worker_start_epoch_ms,
            pipeline_start=pipeline_start,
        )
        return chunks_count
    except Exception as err:
        total_time = time.perf_counter() - pipeline_start
        logger.exception(
            "Ingestion pipeline failed for document_id=%s after %.2fs: %s",
            document_id,
            total_time,
            err,
        )
        failure_metrics = {
            "uploaded_at_ms": uploaded_at_ms,
            "dequeued_at_ms": worker_start_epoch_ms,
            "failed_at_ms": time.time() * 1000.0,
            "queue_wait_duration_s": round(queue_wait_s, 4),
            "elapsed_before_failure_s": round(total_time, 4),
            "status": "failed",
            "error": str(err)[:500],
        }
        await pool.execute(
            "UPDATE documents SET status = 'failed', error_message = $2, metrics = $3::jsonb WHERE id = $1",
            document_id,
            str(err)[:1000],
            json.dumps(failure_metrics),
        )
        raise


async def _run_pipeline(
    pool,
    document_id: int,
    storage_path: str,
    file_type: str,
    uploaded_at_ms: float | None = None,
    queue_wait_s: float = 0.0,
    worker_start_epoch_ms: float = 0.0,
    pipeline_start: float = 0.0,
) -> int:

    # ---------------------------------------------------------
    # STAGE 1: Text Extraction & Cross-Page Word Stitching
    # ---------------------------------------------------------
    log_pipeline_step(1, 6, "TEXT EXTRACTION", document_id, f"source={file_type}")
    extract_start = time.perf_counter()
    pages = extract_text(storage_path, file_type)
    extract_time = time.perf_counter() - extract_start
    total_raw_chars = sum(len(text) for _, text in pages)
    logger.info(
        "Extracted %d pages (%d chars total) with word-boundary protection in %.2fs",
        len(pages),
        total_raw_chars,
        extract_time,
    )

    if not pages or total_raw_chars == 0:
        logger.warning("No extractable text found in document_id=%s", document_id)
        await pool.execute(
            "UPDATE documents SET status = 'failed', error_message = $2 WHERE id = $1",
            document_id,
            "No extractable text found in document",
        )
        return 0

    # ---------------------------------------------------------
    # STAGE 2: Document Structure Parsing
    # ---------------------------------------------------------
    log_pipeline_step(2, 6, "STRUCTURE PARSING", document_id, "headings, paragraphs & lists")
    parse_start = time.perf_counter()
    sections = parse_document_structure(pages)
    parse_time = time.perf_counter() - parse_start
    logger.info(
        "Identified %d document sections in %.2fs",
        len(sections),
        parse_time,
    )

    # ---------------------------------------------------------
    # STAGE 3: Section-Aware Token Chunking
    # ---------------------------------------------------------
    log_pipeline_step(3, 6, "SECTION CHUNKING", document_id, f"token_budget={MAX_CHUNK_TOKENS}")
    chunk_start = time.perf_counter()
    raw_chunks = chunk_sections(
        sections,
        max_tokens=MAX_CHUNK_TOKENS,
        overlap_tokens=CHUNK_OVERLAP_TOKENS,
    )
    chunk_time = time.perf_counter() - chunk_start
    logger.info(
        "Generated %d section-aware chunks in %.2fs",
        len(raw_chunks),
        chunk_time,
    )

    # ---------------------------------------------------------
    # STAGE 4: Pre-Embedding Validation & Deduplication
    # ---------------------------------------------------------
    log_pipeline_step(4, 6, "CHUNK VALIDATION", document_id, "filtering empty, broken & duplicate content")
    val_start = time.perf_counter()
    valid_chunks, val_summary = validate_chunks(raw_chunks, document_id)
    val_time = time.perf_counter() - val_start

    if not valid_chunks:
        logger.warning("No valid chunks survived validation for document_id=%s", document_id)
        await pool.execute(
            "UPDATE documents SET status = 'failed', error_message = $2 WHERE id = $1",
            document_id,
            "No valid chunks remained after validation",
        )
        return 0

    # ---------------------------------------------------------
    # STAGE 5: Vector Embeddings Generation
    # ---------------------------------------------------------
    log_pipeline_step(5, 6, "VECTOR EMBEDDINGS", document_id, f"{len(valid_chunks)} chunks via Ollama")
    embed_start = time.perf_counter()
    texts = [c.content for c in valid_chunks]
    embeddings = await generate_embeddings_batch(texts)
    embed_time = time.perf_counter() - embed_start

    # ---------------------------------------------------------
    # STAGE 6: Database Persistence with Rich Metadata & Metrics
    # ---------------------------------------------------------
    log_pipeline_step(6, 6, "DATABASE PERSISTENCE", document_id, "storing chunks & pgvector data")
    db_start = time.perf_counter()

    pipeline_duration_s = time.perf_counter() - pipeline_start
    now_epoch_ms = time.time() * 1000.0
    total_e2e_s = ((now_epoch_ms - uploaded_at_ms) / 1000.0) if uploaded_at_ms else pipeline_duration_s

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Clear any previous chunks for this document (re-ingestion case).
            deleted_result = await conn.execute(
                "DELETE FROM document_chunks WHERE document_id = $1", document_id
            )
            logger.debug("Cleaned up prior chunks: %s", deleted_result)

            for chunk, embedding in zip(valid_chunks, embeddings):
                embedding_literal = "[" + ",".join(str(x) for x in embedding) + "]"
                await conn.execute(
                    """
                    INSERT INTO document_chunks
                        (document_id, chunk_index, content, embedding, page_number, metadata)
                    VALUES ($1, $2, $3, $4::vector, $5, $6::jsonb)
                    """,
                    document_id,
                    chunk.chunk_index,
                    chunk.content,
                    embedding_literal,
                    chunk.page_number,
                    json.dumps(chunk.metadata),
                )

            db_time = time.perf_counter() - db_start

            # Calculate and store exact metrics dictionary
            metrics_payload = {
                "document_id": document_id,
                "file_type": file_type,
                "uploaded_at_ms": uploaded_at_ms,
                "dequeued_at_ms": worker_start_epoch_ms,
                "completed_at_ms": now_epoch_ms,
                "queue_wait_duration_s": round(queue_wait_s, 4),
                "worker_pipeline_duration_s": round(pipeline_duration_s, 4),
                "upload_to_completion_duration_s": round(total_e2e_s, 4),
                "stage_timings": {
                    "text_extraction_s": round(extract_time, 4),
                    "structure_parsing_s": round(parse_time, 4),
                    "section_chunking_s": round(chunk_time, 4),
                    "chunk_validation_s": round(val_time, 4),
                    "embedding_generation_s": round(embed_time, 4),
                    "database_persistence_s": round(db_time, 4),
                },
                "chunks_count": len(valid_chunks),
                "total_characters": total_raw_chars,
                "status": "completed",
            }

            await conn.execute(
                """
                UPDATE documents 
                SET status = 'completed', error_message = NULL, metrics = $2::jsonb 
                WHERE id = $1
                """,
                document_id,
                json.dumps(metrics_payload),
            )

    logger.info(
        "Database updated: inserted %d structured chunks with metadata in %.2fs",
        len(valid_chunks),
        db_time,
    )

    # ---------------------------------------------------------
    # END-TO-END TIMING: Upload -> Chunks & Embeddings Complete
    # ---------------------------------------------------------
    pipeline_duration_s = time.perf_counter() - pipeline_start
    now_epoch_ms = time.time() * 1000.0
    total_e2e_s = ((now_epoch_ms - uploaded_at_ms) / 1000.0) if uploaded_at_ms else pipeline_duration_s

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(
        f"\n{Colors.DIM}{now_str}{Colors.RESET} {Colors.BOLD}{Colors.BRIGHT_CYAN}[PY-WORKER]{Colors.RESET} >> "
        f"{Colors.BOLD}{Colors.BRIGHT_GREEN}TOTAL END-TO-END TIME for doc_id={document_id}: {total_e2e_s:.2f}s{Colors.RESET} "
        f"{Colors.DIM}(upload -> Redis queue: {queue_wait_s:.2f}s | worker pipeline: {pipeline_duration_s:.2f}s | {len(valid_chunks)} chunks embedded & stored){Colors.RESET}\n"
    )

    logger.info(
        "END-TO-END DURATION for doc_id=%s: %.2fs total (queue_wait=%.2fs, worker_pipeline=%.2fs, extract=%.2fs, parse=%.2fs, chunk=%.2fs, embed=%.2fs, db=%.2fs)",
        document_id,
        total_e2e_s,
        queue_wait_s,
        pipeline_duration_s,
        extract_time,
        parse_time,
        chunk_time,
        embed_time,
        db_time,
    )

    return len(valid_chunks)

