"""
Consumer loop for jobs pushed by node-service (see
node-service/src/queue/ingestionQueue.js). Runs as a separate asyncio task
alongside the ARQ worker (both started from app/worker.py's run()), reading
plain JSON payloads off a Redis list with BRPOP and handing them to the same
process_document() pipeline ARQ's cron sweeper also supervises for crash
recovery (see sweep_stuck_documents in app/worker.py).

This keeps the enqueue side (Node) decoupled from ARQ's Python-specific wire
format, while process_document() itself already guarantees documents.status
is set to 'failed' with an error_message on any pipeline exception — so this
loop doesn't need to duplicate that error handling, just keep running.
"""

import asyncio
import json
import logging
import time

import redis.asyncio as redis

from app.core.config import settings
from app.services.ingestion import process_document

logger = logging.getLogger("queue_consumer")

QUEUE_KEY = "ingestion:jobs"
BLOCK_TIMEOUT_SECONDS = 5


async def run_consumer_loop() -> None:
    client = redis.Redis(
        host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True
    )
    logger.info("Connected to Redis (%s:%s), listening on queue '%s'", settings.REDIS_HOST, settings.REDIS_PORT, QUEUE_KEY)

    while True:
        try:
            result = await client.brpop(QUEUE_KEY, timeout=BLOCK_TIMEOUT_SECONDS)
            if result is None:
                continue  # timed out waiting; loop again so the task stays cancellable

            _, raw_payload = result
            payload = json.loads(raw_payload)

            document_id = int(payload["document_id"])
            storage_path = payload["storage_path"]
            file_type = payload["file_type"]
            uploaded_at_ms = payload.get("uploaded_at_ms")

            logger.info(
                "Dequeued job from '%s': document_id=%s, file_type=%s, path='%s'",
                QUEUE_KEY,
                document_id,
                file_type,
                storage_path,
            )

            job_start = time.perf_counter()
            try:
                chunks_written = await process_document(
                    document_id, storage_path, file_type, uploaded_at_ms=uploaded_at_ms
                )
                elapsed = time.perf_counter() - job_start
                logger.info(
                    "Job completed successfully: document_id=%s (%d chunks created) in %.2fs",
                    document_id,
                    chunks_written,
                    elapsed,
                )

            except Exception as err:
                elapsed = time.perf_counter() - job_start
                logger.error(
                    "Job failed: document_id=%s after %.2fs (%s)",
                    document_id,
                    elapsed,
                    err,
                )

        except asyncio.CancelledError:
            logger.info("Queue consumer received cancellation signal, stopping loop")
            raise
        except Exception:
            logger.exception("Unexpected error in consumer loop, retrying in 1s...")
            await asyncio.sleep(1)

