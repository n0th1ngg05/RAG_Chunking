"""
Text extraction, per source file type, with word-boundary and cross-page integrity.

Key improvements:
- Line-end dehyphenation: fixes words broken by line wraps (e.g. "distrib-\\nuted" -> "distributed").
- Cross-page boundary stitching: ensures words and sentences cut across page boundaries
  are never truncated into dangling fragments.
- Bullet and symbol normalization: maps obscure PDF bullet encodings to clean standard list markers.
- Multi-format support: PDF (with OCR fallback), DOCX, TXT, and Images (JPG/PNG).
"""

import logging
import re
from pathlib import Path

import pypdf
import pytesseract
from docx import Document as DocxDocument
from PIL import Image
from pdf2image import convert_from_path

logger = logging.getLogger("extractor")

MIN_TEXT_LAYER_CHARS = 50


def clean_and_dehyphenate(text: str) -> str:
    """Normalizes whitespace, fixes line-break hyphenation, and standardizes bullets.
    Ensures words are never cut in half by layout line wraps.
    """
    if not text:
        return ""

    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Normalize obscure bullet glyphs (including PDF unicode bullet replacements) to standard '- '
    text = re.sub(r'(?m)^[\s]*[\ufffd\u2022\u2023\u25e6\u2043\u2219▪▫·►›]+\s*', '- ', text)

    # Dehyphenate words broken across line wraps:
    # 1. Syllable splits (second part is lowercase): "develop-\n ment" -> "development"
    text = re.sub(r'(\b[A-Za-z]+)-\s*\n\s*([a-z]+[A-Za-z]*\b)', r'\1\2', text)
    # 2. Compound words (e.g. "agent-\n callable" -> "agent-callable")
    text = re.sub(r'(\b[A-Za-z0-9]+)-\s*\n\s*([A-Za-z0-9]+\b)', r'\1-\2', text)

    # Clean double spaces (preserving intentional newlines)
    text = re.sub(r'[ \t]{2,}', ' ', text)

    return text.strip()


def stitch_cross_page_boundaries(pages: list[tuple[int | None, str]]) -> list[tuple[int | None, str]]:
    """Stitches words split across consecutive page boundaries.
    For example, if Page 1 ends with 'multi-' and Page 2 begins with 'threading',
    they are joined as 'multi-threading' on Page 1 rather than leaving an orphan.
    """
    if len(pages) <= 1:
        return [(p_num, clean_and_dehyphenate(t)) for p_num, t in pages if t and t.strip()]

    cleaned = [(p_num, clean_and_dehyphenate(t)) for p_num, t in pages]
    stitched: list[tuple[int | None, str]] = []

    for i in range(len(cleaned)):
        p_num, cur_text = cleaned[i]
        if not cur_text:
            continue

        if i < len(cleaned) - 1:
            next_p_num, next_text = cleaned[i + 1]
            if next_text:
                # 1. Check for hyphenated word split at page end
                page_end_hyphen = re.search(r'(\b[A-Za-z]+)-\s*$', cur_text)
                next_start_word = re.match(r'^\s*([A-Za-z]+)\b', next_text)

                if page_end_hyphen and next_start_word:
                    prefix = page_end_hyphen.group(1)
                    suffix = next_start_word.group(1)

                    if suffix[0].islower():
                        repaired = prefix + suffix
                    else:
                        repaired = prefix + "-" + suffix

                    cur_text = cur_text[:page_end_hyphen.start()] + repaired
                    cleaned[i + 1] = (next_p_num, next_text[next_start_word.end():].lstrip())
                    logger.debug("Repaired cross-page word split '%s' across pages %s and %s", repaired, p_num, next_p_num)

        stitched.append((p_num, cur_text))

    return [(p_num, t) for p_num, t in stitched if t and t.strip()]


def extract_txt(file_path: str) -> list[tuple[int | None, str]]:
    """TXT extraction with line cleanup and de-hyphenation."""
    filename = Path(file_path).name
    text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    cleaned = clean_and_dehyphenate(text)
    logger.info("TXT extraction for '%s': read %d characters", filename, len(cleaned))
    return [(1, cleaned)]


def _paragraph_style_name(paragraph) -> str:
    """Return a normalized paragraph style name, tolerating malformed DOCX styles."""
    style = getattr(paragraph, "style", None)
    style_name = getattr(style, "name", None)
    return (style_name or "").lower()


def extract_docx(file_path: str) -> list[tuple[int | None, str]]:
    """DOCX extraction preserving paragraph styles (headings vs text vs list items)."""
    filename = Path(file_path).name
    doc = DocxDocument(file_path)
    lines: list[str] = []

    for p in doc.paragraphs:
        txt = p.text.strip()
        if not txt:
            continue
        style_name = _paragraph_style_name(p)
        if "heading" in style_name or "title" in style_name:
            lines.append(f"\n{txt}\n")
        elif "list" in style_name or "bullet" in style_name:
            lines.append(f"- {txt}")
        else:
            lines.append(txt)

    combined = clean_and_dehyphenate("\n\n".join(lines))
    logger.info(
        "DOCX extraction for '%s': parsed %d paragraphs (%d characters total)",
        filename,
        len(lines),
        len(combined),
    )
    return [(1, combined)]


def extract_image(file_path: str) -> list[tuple[int | None, str]]:
    """JPG/JPEG/PNG — OCR via Tesseract."""
    filename = Path(file_path).name
    image = Image.open(file_path)
    logger.info(
        "Image OCR for '%s': format=%s, size=%sx%s - invoking Tesseract...",
        filename,
        image.format,
        image.width,
        image.height,
    )
    raw_text = pytesseract.image_to_string(image)
    cleaned = clean_and_dehyphenate(raw_text)
    logger.info("Image OCR completed for '%s': extracted %d characters", filename, len(cleaned))
    return [(1, cleaned)]


def extract_pdf(file_path: str) -> list[tuple[int | None, str]]:
    """PDF extraction with OCR fallback and boundary protection."""
    filename = Path(file_path).name
    reader = pypdf.PdfReader(file_path)
    total_pages = len(reader.pages)
    logger.info("PDF extraction for '%s': %d total pages detected", filename, total_pages)

    pages: list[tuple[int | None, str]] = []

    for i, page in enumerate(reader.pages):
        page_num = i + 1
        text = page.extract_text() or ""
        char_count = len(text.strip())

        if char_count >= MIN_TEXT_LAYER_CHARS:
            cleaned = clean_and_dehyphenate(text)
            logger.info(
                "PDF Page %d/%d: extracted %d characters from embedded text layer",
                page_num,
                total_pages,
                len(cleaned),
            )
            pages.append((page_num, cleaned))
            continue

        logger.warning(
            "PDF Page %d/%d: sparse text layer (%d chars < %d limit) — falling back to Tesseract OCR...",
            page_num,
            total_pages,
            char_count,
            MIN_TEXT_LAYER_CHARS,
        )
        try:
            images = convert_from_path(
                file_path, dpi=200, first_page=page_num, last_page=page_num
            )
            if images:
                ocr_text = pytesseract.image_to_string(images[0])
                cleaned_ocr = clean_and_dehyphenate(ocr_text)
                logger.info(
                    "PDF Page %d/%d: OCR successful, extracted %d characters",
                    page_num,
                    total_pages,
                    len(cleaned_ocr),
                )
                pages.append((page_num, cleaned_ocr))
            else:
                pages.append((page_num, clean_and_dehyphenate(text)))
        except Exception as err:
            logger.error("PDF Page %d/%d: OCR conversion failed: %s", page_num, total_pages, err)
            pages.append((page_num, clean_and_dehyphenate(text)))

    return stitch_cross_page_boundaries(pages)


EXTRACTORS = {
    "PDF": extract_pdf,
    "DOCX": extract_docx,
    "TXT": extract_txt,
    "PNG": extract_image,
    "JPG": extract_image,
    "JPEG": extract_image,
}


def extract_text(file_path: str, file_type: str) -> list[tuple[int | None, str]]:
    extractor = EXTRACTORS.get(file_type.upper())
    if extractor is None:
        raise ValueError(f"No extractor for file_type={file_type!r}")
    return extractor(file_path)
