"""
Worker entrypoint — directly modeled on the reference repo's
app/workers/arq_worker.py pattern, extended to also run the plain-Redis-list
consumer (see app/queue_consumer.py) that node-service actually enqueues to.

This answers the user's original requirement ("keep python process alive,
work on ETA, and decide whether to spawn new process and kill the previous
one on completion") the same way the reference repo solved it: not by
manually managing process spawn/kill, but by running a persistent worker
(bounded concurrency via EMBED_CONCURRENCY_LIMIT and asyncpg pool size, see
embeddings.py/database.py) plus a cron-style sweeper that reclaims jobs
stuck in 'processing' after a crash or restart. Docker's
`restart: unless-stopped` keeps the container itself alive; this module
manages job lifecycle inside it.

Two things run concurrently in this one process:
  1. `run_consumer_loop()` — the actual job processor, pulling from the
     Redis list node-service pushes to.
  2. An ARQ worker whose only job is the cron-scheduled `sweep_stuck_documents`
     — ARQ is used here purely for its reliable cron scheduling, not as the
     job queue itself (see queue_consumer.py's docstring for why).
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from arq import cron
from arq.connections import RedisSettings
from arq.worker import create_worker

from app.core.config import settings
from app.core.database import close_pool, get_pool, init_pool
from app.core.logger import log_banner, setup_colored_logging
from app.queue_consumer import run_consumer_loop

setup_colored_logging(level=logging.INFO)
logger = logging.getLogger("python_worker")


async def startup(ctx: dict) -> None:
    logger.info("ARQ cron supervisor started")


async def shutdown(ctx: dict) -> None:
    logger.info("ARQ cron supervisor shutting down")


async def sweep_stuck_documents(ctx: dict) -> None:
    """Cron task, mirrors the reference repo's sweep_stuck_jobs(): finds
    documents stuck in 'processing' for more than 10 minutes (a crash
    mid-ingestion, or a worker killed by its own resource limits) and marks
    them 'failed' so the client isn't left polling forever, and so the user
    can re-trigger ingestion.

    Measured from processing_started_at (set when the worker actually picks
    up the job in ingestion.py), not uploaded_at — a large scanned PDF can
    legitimately take several minutes of OCR, and uploaded_at includes
    whatever time it sat queued before a worker got to it. Using uploaded_at
    here would wrongly kill jobs that are still genuinely in progress.
    """
    sweeper_logger = logging.getLogger("sweeper")
    pool = await get_pool()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)

    result = await pool.execute(
        """
        UPDATE documents
        SET status = 'failed', error_message = 'Processing timed out or worker crashed'
        WHERE status = 'processing' AND processing_started_at < $1
        """,
        cutoff,
    )
    # asyncpg execute() returns a string like "UPDATE 3"
    if result and not result.endswith("UPDATE 0"):
        sweeper_logger.warning("Sweeper reclaimed stuck documents: %s", result)
    else:
        sweeper_logger.debug("Sweeper heartbeat: no stuck documents found")


class WorkerSettings:
    """ARQ runs with no job functions of its own — it's used only to drive
    the cron sweeper reliably. All actual document processing happens in
    run_consumer_loop(), run as a sibling asyncio task in run() below."""

    functions: list = []
    cron_jobs = [cron(sweep_stuck_documents, minute=set(range(0, 60, 5)))]

    redis_settings = RedisSettings(host=settings.REDIS_HOST, port=settings.REDIS_PORT)

    on_startup = startup
    on_shutdown = shutdown

    # Resource/concurrency caps
    max_jobs = 10
    job_timeout = 600  # seconds
    max_tries = 3
    retry_delay = 10


async def run() -> None:
    """Entrypoint: runs the ARQ cron-sweeper worker and the Redis-list
    consumer loop side by side in one process/container."""
    log_banner(
        "Python Ingestion & Chunking Worker",
        {
            "Status": "ONLINE & LISTENING",
            "Postgres DB": f"{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB} (user: {settings.WORKER_DB_USER})",
            "Redis Queue": f"{settings.REDIS_HOST}:{settings.REDIS_PORT} (key: ingestion:jobs)",
            "Ollama Host": f"{settings.OLLAMA_HOST}",
            "Embedding Model": f"{settings.EMBEDDING_MODEL} ({settings.EMBEDDING_DIMENSION}-dim)",
            "Cron Sweeper": "Every 5 mins (reclaims jobs stuck > 10m)",
        },
    )

    await init_pool()

    arq_worker = create_worker(WorkerSettings)

    try:
        await asyncio.gather(
            arq_worker.async_run(),
            run_consumer_loop(),
        )
    finally:
        logger.info("Worker shutdown initiated: closing resources")
        await arq_worker.close()
        await close_pool()
        logger.info("Worker shutdown completed successfully")


if __name__ == "__main__":
    asyncio.run(run())

