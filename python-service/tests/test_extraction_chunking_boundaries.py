import unittest

from app.services.chunker import chunk_sections, count_tokens, split_by_word_boundaries
from app.services.extractor import stitch_cross_page_boundaries
from app.services.structure_parser import parse_document_structure
from app.services.validator import validate_chunks


class ExtractionChunkingBoundaryTests(unittest.TestCase):
    def test_cross_page_hyphenated_word_is_stitched_without_loss(self):
        pages = stitch_cross_page_boundaries(
            [
                (1, "The worker repairs distrib-"),
                (2, "uted retrieval text."),
            ]
        )

        self.assertEqual(pages[0][1], "The worker repairs distributed")
        self.assertEqual(pages[1][1], "retrieval text.")

    def test_word_boundary_split_never_truncates_words(self):
        text = " ".join(f"boundaryword{i}" for i in range(80))
        pieces = split_by_word_boundaries(text, max_tokens=20)
        original_words = text.split()
        split_words = " ".join(pieces).split()

        self.assertEqual(split_words, original_words)
        self.assertTrue(all(count_tokens(piece) <= 20 for piece in pieces))

    def test_section_chunks_respect_token_limit_and_metadata(self):
        pages = [
            (
                3,
                "PROJECT SUMMARY\n\n"
                + " ".join(f"retrievaltoken{i}" for i in range(120)),
            )
        ]
        sections = parse_document_structure(pages)
        chunks = chunk_sections(sections, max_tokens=40, overlap_tokens=8)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.token_count <= 40 for chunk in chunks))
        self.assertTrue(all(chunk.page_number == 3 for chunk in chunks))
        self.assertTrue(all(chunk.section_heading == "PROJECT SUMMARY" for chunk in chunks))
        self.assertEqual([chunk.chunk_index for chunk in chunks], list(range(len(chunks))))

    def test_validator_drops_empty_duplicate_and_broken_boundary_chunks(self):
        sections = parse_document_structure(
            [
                (1, "EXPERIENCE\n\nA complete valid chunk with enough words to embed safely."),
                (2, "EXPERIENCE\n\nA complete valid chunk with enough words to embed safely."),
                (3, "EXPERIENCE\n\nThis chunk ends with a broken-"),
            ]
        )
        chunks = chunk_sections(sections, max_tokens=80, overlap_tokens=8)
        valid_chunks, summary = validate_chunks(chunks, document_id=42)

        self.assertEqual(summary.dropped_duplicates, 1)
        self.assertEqual(summary.dropped_malformed, 1)
        self.assertEqual(len(valid_chunks), 1)
        self.assertEqual(valid_chunks[0].metadata["document_id"], 42)
        self.assertEqual(valid_chunks[0].metadata["chunk_index"], 0)


if __name__ == "__main__":
    unittest.main()
