"""
Document structure parser: identifies headings, paragraphs, lists, and page numbers,
and groups them into cohesive DocumentSection objects.
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger("structure_parser")

# Regex patterns for structural identification
HEADING_ALL_CAPS = re.compile(r"^[A-Z0-9\s&/\-,:|]{3,65}$")
HEADING_NUMBERED = re.compile(r"^(?:(?:SECTION|CHAPTER|PART)\s+\d+|\d+(?:\.\d+)*)\s+([A-Z0-9].{2,80})$", re.IGNORECASE)
HEADING_MARKDOWN = re.compile(r"^(#{1,6})\s+(.+)$")

LIST_BULLET_PATTERN = re.compile(r"^[-*•▪▫►›]\s+(.+)$")
LIST_NUMBERED_PATTERN = re.compile(r"^(\d+|[a-zA-Z])[\.\)]\s+(.+)$")


@dataclass
class StructuralBlock:
    block_type: str  # 'heading', 'paragraph', 'list_item'
    content: str
    page_number: int | None
    heading_level: int = 0


@dataclass
class DocumentSection:
    heading: str
    heading_level: int
    page_start: int | None
    page_end: int | None
    blocks: list[StructuralBlock] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        parts: list[str] = []
        if self.heading and self.heading != "Preamble":
            parts.append(self.heading)
        for b in self.blocks:
            parts.append(b.content)
        return "\n\n".join(parts)


def is_heading_candidate(line: str) -> tuple[bool, int, str]:
    """Detects whether a line represents a section heading.
    Returns (is_heading, level, cleaned_title).
    """
    cleaned = line.strip()
    if not cleaned or len(cleaned) > 85:
        return False, 0, ""

    # 1. Markdown headings (# Heading 1, ## Heading 2)
    md_match = HEADING_MARKDOWN.match(cleaned)
    if md_match:
        level = len(md_match.group(1))
        title = md_match.group(2).strip()
        return True, level, title

    # Skip lines that end in punctuation typical of sentences
    if cleaned.endswith((".", ",", ";", ":", "?", "!")):
        return False, 0, ""

    # Skip lines with typical contact/link separators
    if "|" in cleaned or "@" in cleaned or "http://" in cleaned or "https://" in cleaned:
        return False, 0, ""

    # 2. Numbered Section (e.g. "1. Introduction" or "Section 2: Architecture")
    num_match = HEADING_NUMBERED.match(cleaned)
    if num_match:
        return True, 1, cleaned

    # 3. All-Caps Headings (e.g. "PROFESSIONAL SUMMARY", "WORK EXPERIENCE")
    letters = [ch for ch in cleaned if ch.isalpha()]
    if len(letters) >= 3 and cleaned.isupper() and HEADING_ALL_CAPS.match(cleaned):
        return True, 1, cleaned

    return False, 0, ""


def parse_document_structure(pages: list[tuple[int | None, str]]) -> list[DocumentSection]:
    """Parses raw extracted pages into structural sections, detecting headings,
    paragraphs, lists, and page numbers.
    """
    sections: list[DocumentSection] = []
    current_section = DocumentSection(
        heading="Preamble",
        heading_level=0,
        page_start=pages[0][0] if pages else 1,
        page_end=pages[0][0] if pages else 1,
        blocks=[],
    )
    sections.append(current_section)

    for page_num, page_text in pages:
        if not page_text or not page_text.strip():
            continue

        raw_paragraphs = re.split(r"\n\s*\n", page_text)

        for para in raw_paragraphs:
            para = para.strip()
            if not para:
                continue

            lines = [l.strip() for l in para.split("\n") if l.strip()]
            if not lines:
                continue

            # Check if paragraph is a single standalone heading
            if len(lines) == 1:
                is_head, level, title = is_heading_candidate(lines[0])
                if is_head:
                    # Start new section
                    current_section = DocumentSection(
                        heading=title,
                        heading_level=level,
                        page_start=page_num,
                        page_end=page_num,
                        blocks=[],
                    )
                    sections.append(current_section)
                    continue

            # Process lines within the block
            current_list_items: list[str] = []
            current_prose_lines: list[str] = []

            for line in lines:
                is_head, level, title = is_heading_candidate(line)
                if is_head:
                    # Flush accumulated prose or lists before switching heading
                    if current_list_items:
                        current_section.blocks.append(
                            StructuralBlock("list_item", "\n".join(current_list_items), page_num)
                        )
                        current_list_items = []
                    if current_prose_lines:
                        current_section.blocks.append(
                            StructuralBlock("paragraph", " ".join(current_prose_lines), page_num)
                        )
                        current_prose_lines = []

                    current_section = DocumentSection(
                        heading=title,
                        heading_level=level,
                        page_start=page_num,
                        page_end=page_num,
                        blocks=[],
                    )
                    sections.append(current_section)
                    continue

                # Check if line is a bullet/numbered list item
                if LIST_BULLET_PATTERN.match(line) or LIST_NUMBERED_PATTERN.match(line):
                    if current_prose_lines:
                        current_section.blocks.append(
                            StructuralBlock("paragraph", " ".join(current_prose_lines), page_num)
                        )
                        current_prose_lines = []
                    current_list_items.append(line)
                else:
                    if current_list_items:
                        # Continuation of the previous list item
                        current_list_items[-1] += f" {line}"
                    else:
                        current_prose_lines.append(line)

            # Flush remaining
            if current_list_items:
                current_section.blocks.append(
                    StructuralBlock("list_item", "\n".join(current_list_items), page_num)
                )
            if current_prose_lines:
                current_section.blocks.append(
                    StructuralBlock("paragraph", " ".join(current_prose_lines), page_num)
                )

            current_section.page_end = page_num

    # Filter out empty sections
    non_empty = [s for s in sections if s.blocks or (s.heading and s.heading != "Preamble")]

    logger.info("Parsed document structure into %d distinct sections", len(non_empty))
    for s in non_empty:
        logger.debug(
            "Section '%s' (pages %s-%s): %d blocks",
            s.heading,
            s.page_start,
            s.page_end,
            len(s.blocks),
        )

    return non_empty
