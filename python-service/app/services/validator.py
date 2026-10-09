"""
Pre-embedding chunk validation and sanitization.

Validates that every chunk is:
1. Non-empty and meaningful (token_count >= 4, char_count >= 15).
2. Word-intact (repairs trailing hyphens, checks for broken/shredded words).
3. Non-duplicate (deduplicates exact and near-identical chunks within the document).
4. Well-formed (filters out unprintable binary junk and OCR symbol noise).
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.services.chunker import MAX_CHUNK_TOKENS, StructuredChunk, count_tokens

logger = logging.getLogger("validator")


@dataclass
class ValidationSummary:
    total_input: int
    total_valid: int
    dropped_empty: int
    dropped_duplicates: int
    dropped_malformed: int
    repaired: int


def sanitize_chunk_text(text: str) -> str:
    """Repairs minor text defects without discarding the chunk."""
    cleaned = text.strip()

    # Clean unprintable control characters except newline and tab
    cleaned = "".join(ch for ch in cleaned if ch.isprintable() or ch in "\n\t")

    # Normalize excessive newlines (> 2) to standard paragraph breaks
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned.strip()


def has_broken_boundary(text: str) -> bool:
    """Detects boundary artifacts that would indicate a split word."""
    cleaned = text.strip()
    if not cleaned:
        return False

    body = re.sub(r"^\[[^\]\n]{1,120}\]\s*", "", cleaned).strip()
    if not body:
        return False

    # A dangling hyphen is the clearest signal of a page/chunk split word.
    if re.search(r"[A-Za-z0-9]-$", body):
        return True

    return False


def is_malformed_ocr_noise(text: str) -> bool:
    """Detects if text is OCR symbol garbage or corrupted binary."""
    if len(text) < 40:
        return False

    if text.count("\ufffd") >= 3:
        return True

    alpha_count = sum(1 for ch in text if ch.isalnum())
    alpha_ratio = alpha_count / len(text)

    # Less than 35% alphanumeric characters indicates pure noise/lines/symbols
    if alpha_ratio < 0.35:
        return True

    # Check for shredded single-character word syndrome: "e x p e r i e n c e"
    words = text.split()
    if len(words) >= 20:
        single_chars = sum(1 for w in words if len(w) == 1 and w.isalpha())
        if (single_chars / len(words)) > 0.40:
            return True

    return False


def is_near_duplicate(normalized: str, seen_texts: list[str]) -> bool:
    """Detects near-identical chunks while allowing intentional small overlaps."""
    for previous in seen_texts:
        if abs(len(previous) - len(normalized)) > max(80, int(len(normalized) * 0.15)):
            continue
        if SequenceMatcher(None, previous, normalized).ratio() >= 0.97:
            return True
    return False


def validate_chunks(
    chunks: list[StructuredChunk],
    document_id: int,
) -> tuple[list[StructuredChunk], ValidationSummary]:
    """Validates and filters chunks before passing them to Ollama for embedding.
    Surviving chunks are sequentially re-indexed starting from 0.
    """
    valid_chunks: list[StructuredChunk] = []
    seen_hashes: set[str] = set()
    seen_texts: list[str] = []

    dropped_empty = 0
    dropped_duplicates = 0
    dropped_malformed = 0
    repaired_count = 0

    for chunk in chunks:
        # 1. Sanitize text
        original_text = chunk.content
        cleaned_text = sanitize_chunk_text(original_text)
        if cleaned_text != original_text:
            repaired_count += 1
            chunk.content = cleaned_text
            chunk.char_count = len(cleaned_text)
            chunk.token_count = count_tokens(cleaned_text)

        # 2. Check for empty / trivial content
        if len(cleaned_text) < 15 or chunk.token_count < 4:
            logger.warning(
                "Dropped empty/trivial chunk #%d (tokens: %d, chars: %d, heading: '%s')",
                chunk.chunk_index,
                chunk.token_count,
                len(cleaned_text),
                chunk.section_heading,
            )
            dropped_empty += 1
            continue

        # 3. Check for malformed / OCR noise / broken boundaries
        if is_malformed_ocr_noise(cleaned_text) or has_broken_boundary(cleaned_text):
            logger.warning(
                "Dropped malformed or broken-boundary chunk #%d (heading: '%s', sample: '%.40s')",
                chunk.chunk_index,
                chunk.section_heading,
                cleaned_text,
            )
            dropped_malformed += 1
            continue

        if chunk.token_count > MAX_CHUNK_TOKENS:
            logger.warning(
                "Dropped over-limit chunk #%d (%d tokens > %d max, heading: '%s')",
                chunk.chunk_index,
                chunk.token_count,
                MAX_CHUNK_TOKENS,
                chunk.section_heading,
            )
            dropped_malformed += 1
            continue

        # 4. Check for duplicate content (SHA-256 of normalized text, plus near-duplicate guard)
        norm_key = re.sub(r"\s+", " ", cleaned_text.lower())
        content_hash = hashlib.sha256(norm_key.encode("utf-8")).hexdigest()
        if content_hash in seen_hashes or is_near_duplicate(norm_key, seen_texts):
            logger.warning(
                "Dropped duplicate chunk #%d (heading: '%s', sample: '%.40s')",
                chunk.chunk_index,
                chunk.section_heading,
                cleaned_text,
            )
            dropped_duplicates += 1
            continue

        seen_hashes.add(content_hash)
        seen_texts.append(norm_key)
        valid_chunks.append(chunk)

    # 5. Sequentially re-index surviving valid chunks (0, 1, 2, ... N-1)
    for idx, chunk in enumerate(valid_chunks):
        chunk.chunk_index = idx
        # Ensure complete metadata is populated
        chunk.metadata.update(
            {
                "document_id": document_id,
                "chunk_index": idx,
                "section_heading": chunk.section_heading,
                "page_number": chunk.page_number,
                "page_end": chunk.page_end,
                "token_count": chunk.token_count,
                "char_count": chunk.char_count,
                "has_list": chunk.has_list,
                "is_continuation": chunk.is_continuation,
            }
        )

    summary = ValidationSummary(
        total_input=len(chunks),
        total_valid=len(valid_chunks),
        dropped_empty=dropped_empty,
        dropped_duplicates=dropped_duplicates,
        dropped_malformed=dropped_malformed,
        repaired=repaired_count,
    )

    logger.info(
        "Validation complete for doc_id=%d: %d/%d valid chunks accepted (%d empty, %d dupes, %d noise dropped, %d repaired)",
        document_id,
        summary.total_valid,
        summary.total_input,
        summary.dropped_empty,
        summary.dropped_duplicates,
        summary.dropped_malformed,
        summary.repaired,
    )

    return valid_chunks, summary
