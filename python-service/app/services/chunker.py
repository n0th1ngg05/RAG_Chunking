"""
Section-aware, token-bounded document chunker.

Key features:
- Section cohesion: keeps related section content together in single chunks whenever possible.
- Token-based limits: counts exact BPE tokens (tiktoken) tailored for embedding models.
- Sentence-level overlap: overlap applies ONLY within overflowing sections and ALWAYS on
  whole sentence boundaries, never cutting through words or clauses.
- Rich structural metadata: attaches section headings, page numbers, list flags, and token counts.
"""

import logging
import re
from dataclasses import dataclass

import tiktoken

from app.services.structure_parser import DocumentSection

logger = logging.getLogger("chunker")

# Target token limits for nomic-embed-text (8192 max context, ~500 tokens ideal for retrieval)
MAX_CHUNK_TOKENS = 500
MIN_CHUNK_TOKENS = 20
CHUNK_OVERLAP_TOKENS = 50

# Fast BPE tokenizer
_tokenizer = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Returns exact token count for text."""
    if not text:
        return 0
    return len(_tokenizer.encode(text, disallowed_special=()))


def split_into_sentences(text: str) -> list[str]:
    """Splits text into complete sentences, never slicing words."""
    cleaned = text.strip()
    if not cleaned:
        return []
    # Split on sentence terminals followed by whitespace
    raw_sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    return [s.strip() for s in raw_sentences if s.strip()]


def split_by_word_boundaries(text: str, max_tokens: int) -> list[str]:
    """Splits oversized text into token-bounded pieces without truncating words."""
    words = re.findall(r"\S+", text.strip())
    if not words:
        return []

    pieces: list[str] = []
    current_words: list[str] = []

    for word in words:
        candidate_words = [*current_words, word]
        candidate = " ".join(candidate_words)

        if count_tokens(candidate) <= max_tokens:
            current_words = candidate_words
            continue

        if current_words:
            pieces.append(" ".join(current_words))
            current_words = [word]
            continue

        # A single pathological token/word can exceed the budget. Preserve it
        # whole so extraction remains lossless and validation can report it.
        pieces.append(word)
        current_words = []

    if current_words:
        pieces.append(" ".join(current_words))

    return pieces

@dataclass
class StructuredChunk:
    chunk_index: int
    content: str
    section_heading: str
    page_number: int | None
    page_end: int | None
    token_count: int
    char_count: int
    has_list: bool
    is_continuation: bool
    metadata: dict


def chunk_sections(
    sections: list[DocumentSection],
    max_tokens: int = MAX_CHUNK_TOKENS,
    overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
) -> list[StructuredChunk]:
    """Chunks structured document sections according to token budgets,
    keeping sections together and applying overlap only within split sections.
    """
    chunks: list[StructuredChunk] = []
    chunk_idx = 0

    for section in sections:
        section_text = section.full_text.strip()
        if not section_text:
            continue

        section_tokens = count_tokens(section_text)
        has_list = any(b.block_type == "list_item" for b in section.blocks)

        # -------------------------------------------------------------
        # CASE 1: Section fits comfortably in one chunk -> Keep intact!
        # -------------------------------------------------------------
        if section_tokens <= max_tokens:
            chunk = StructuredChunk(
                chunk_index=chunk_idx,
                content=section_text,
                section_heading=section.heading,
                page_number=section.page_start,
                page_end=section.page_end,
                token_count=section_tokens,
                char_count=len(section_text),
                has_list=has_list,
                is_continuation=False,
                metadata={
                    "section_heading": section.heading,
                    "page_number": section.page_start,
                    "page_end": section.page_end,
                    "token_count": section_tokens,
                    "char_count": len(section_text),
                    "has_list": has_list,
                    "is_continuation": False,
                },
            )
            chunks.append(chunk)
            chunk_idx += 1
            continue

        # -------------------------------------------------------------
        # CASE 2: Section exceeds max_tokens -> Split by blocks / sentences
        # -------------------------------------------------------------
        sub_chunks = _split_large_section(
            section,
            start_chunk_idx=chunk_idx,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        )
        for sc in sub_chunks:
            chunks.append(sc)
            chunk_idx += 1

    logger.info(
        "Chunking produced %d structured chunks across %d sections (target: %d tokens, max: %d)",
        len(chunks),
        len(sections),
        max_tokens,
        max([c.token_count for c in chunks]) if chunks else 0,
    )
    return chunks


def _split_large_section(
    section: DocumentSection,
    start_chunk_idx: int,
    max_tokens: int,
    overlap_tokens: int,
) -> list[StructuredChunk]:
    """Sub-chunks an oversized section cleanly along block and sentence boundaries."""
    sub_chunks: list[StructuredChunk] = []
    current_text_parts: list[str] = []
    current_tokens = 0
    current_pages: set[int] = set()
    current_has_list = False
    is_cont = False

    # Heading prefix to maintain context across sub-chunks
    heading_prefix = f"[{section.heading}]\n" if section.heading and section.heading != "Preamble" else ""
    prefix_tokens = count_tokens(heading_prefix)
    body_token_budget = max(1, max_tokens - prefix_tokens)
    effective_overlap_tokens = min(overlap_tokens, max(0, body_token_budget // 5))
    current_tokens = prefix_tokens

    def emit_chunk(overlap_seed: str = ""):
        nonlocal current_text_parts, current_tokens, current_pages, current_has_list, is_cont
        if not current_text_parts:
            return

        body = "\n\n".join(current_text_parts).strip()
        full_chunk_text = f"{heading_prefix}{body}".strip()
        t_count = count_tokens(full_chunk_text)

        min_p = min(current_pages) if current_pages else section.page_start
        max_p = max(current_pages) if current_pages else section.page_end

        chunk = StructuredChunk(
            chunk_index=start_chunk_idx + len(sub_chunks),
            content=full_chunk_text,
            section_heading=section.heading,
            page_number=min_p,
            page_end=max_p,
            token_count=t_count,
            char_count=len(full_chunk_text),
            has_list=current_has_list,
            is_continuation=is_cont,
            metadata={
                "section_heading": section.heading,
                "page_number": min_p,
                "page_end": max_p,
                "token_count": t_count,
                "char_count": len(full_chunk_text),
                "has_list": current_has_list,
                "is_continuation": is_cont,
            },
        )
        sub_chunks.append(chunk)
        is_cont = True

        # Initialize next chunk with sentence overlap
        if overlap_seed and count_tokens(overlap_seed) <= effective_overlap_tokens:
            current_text_parts = [overlap_seed]
            current_tokens = prefix_tokens + count_tokens(overlap_seed)
        else:
            current_text_parts = []
            current_tokens = prefix_tokens

        current_pages = set()
        current_has_list = False

    def get_sentence_overlap(text_parts: list[str]) -> str:
        """Extracts whole trailing sentences up to overlap_tokens."""
        if not text_parts:
            return ""
        all_sentences: list[str] = []
        for part in text_parts:
            all_sentences.extend(split_into_sentences(part))
        if not all_sentences:
            return ""

        overlap_sents: list[str] = []
        accum_tok = 0
        for sent in reversed(all_sentences):
            tok = count_tokens(sent)
            if accum_tok + tok <= effective_overlap_tokens:
                overlap_sents.insert(0, sent)
                accum_tok += tok
            else:
                break
        return " ".join(overlap_sents)

    # Process blocks in the section
    for block in section.blocks:
        b_content = block.content.strip()
        if not b_content:
            continue

        b_tokens = count_tokens(b_content)

        # If adding this block exceeds limit:
        if current_tokens + b_tokens > max_tokens and current_text_parts:
            overlap = get_sentence_overlap(current_text_parts)
            emit_chunk(overlap_seed=overlap)
            if current_tokens + b_tokens > max_tokens and current_text_parts:
                current_text_parts = []
                current_tokens = prefix_tokens

        if block.page_number:
            current_pages.add(block.page_number)
        if block.block_type == "list_item":
            current_has_list = True

        # If this single block alone exceeds max_tokens, split by complete
        # sentences first, then fall back to whole-word pieces for long runs.
        if b_tokens > body_token_budget:
            sentences = split_into_sentences(b_content)
            if not sentences:
                sentences = [b_content]

            for sentence in sentences:
                sentence_parts = (
                    split_by_word_boundaries(sentence, body_token_budget)
                    if count_tokens(sentence) > body_token_budget
                    else [sentence]
                )

                for part in sentence_parts:
                    part_tokens = count_tokens(part)
                    if current_tokens + part_tokens > max_tokens and current_text_parts:
                        overlap = get_sentence_overlap(current_text_parts)
                        emit_chunk(overlap_seed=overlap)
                        if block.page_number:
                            current_pages.add(block.page_number)
                        if block.block_type == "list_item":
                            current_has_list = True
                        if current_tokens + part_tokens > max_tokens and current_text_parts:
                            current_text_parts = []
                            current_tokens = prefix_tokens

                    current_text_parts.append(part)
                    current_tokens += part_tokens
        else:
            current_text_parts.append(b_content)
            current_tokens += b_tokens

    # Emit final remaining chunk
    if current_text_parts:
        emit_chunk()

    return sub_chunks


# Backward compatibility export
def hybrid_chunk_text(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
) -> list[str]:
    """Legacy helper: splits text into string chunks for backward compatibility."""
    from app.services.structure_parser import parse_document_structure
    sections = parse_document_structure([(1, text)])
    chunks = chunk_sections(sections, max_tokens=max(100, chunk_size // 4))
    return [c.content for c in chunks]
