"""
Local embedding generation via Ollama's /api/embeddings endpoint.

This replaces the reference repo's OpenAI embeddings call
(app/services/vector_store.py: generate_embedding / generate_embeddings_batch),
which sent text to a third party. This version never leaves the Docker network.

Note: as of most Ollama versions, /api/embeddings handles one input per call
(no native batch endpoint like OpenAI's). We fan out concurrently with a
semaphore instead of relying on a batch API.
"""

import asyncio
import logging
import time

import httpx

from app.core.config import settings

logger = logging.getLogger("embeddings")

EMBED_CONCURRENCY_LIMIT = 5


async def generate_embedding(client: httpx.AsyncClient, text: str) -> list[float]:
    url = f"{settings.OLLAMA_HOST}/api/embeddings"
    try:
        response = await client.post(
            url,
            json={"model": settings.EMBEDDING_MODEL, "prompt": text},
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        embedding = data["embedding"]

        if len(embedding) != settings.EMBEDDING_DIMENSION:
            raise ValueError(
                f"Embedding dimension mismatch: got {len(embedding)}, "
                f"expected {settings.EMBEDDING_DIMENSION}. Check EMBEDDING_MODEL "
                f"matches the schema's VECTOR({settings.EMBEDDING_DIMENSION})."
            )
        return embedding
    except httpx.ConnectError:
        logger.error(
            "Cannot connect to Ollama at %s. Ensure Ollama is running and accessible.",
            settings.OLLAMA_HOST,
        )
        raise
    except httpx.HTTPStatusError as e:
        logger.error(
            "Ollama embedding request failed with HTTP %s: %s",
            e.response.status_code,
            e.response.text,
        )
        raise


async def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    count = len(texts)
    start_time = time.perf_counter()
    logger.info(
        "Requesting embeddings for %d chunks via Ollama (model: '%s', host: %s, concurrency=%d)",
        count,
        settings.EMBEDDING_MODEL,
        settings.OLLAMA_HOST,
        EMBED_CONCURRENCY_LIMIT,
    )

    semaphore = asyncio.Semaphore(EMBED_CONCURRENCY_LIMIT)

    async with httpx.AsyncClient() as client:

        async def _bounded(idx: int, text: str) -> list[float]:
            async with semaphore:
                emb = await generate_embedding(client, text)
                logger.debug("Generated embedding for chunk %d/%d (vector dim: %d)", idx + 1, count, len(emb))
                return emb

        results = await asyncio.gather(*[_bounded(i, t) for i, t in enumerate(texts)])

    elapsed = time.perf_counter() - start_time
    logger.info(
        "Generated %d embeddings in %.2fs (avg %.1f ms/chunk)",
        count,
        elapsed,
        (elapsed / count * 1000) if count else 0,
    )
    return results

