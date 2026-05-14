import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_companion.context.document_reader import (
    extract_document_text,
    is_document_media,
    split_text_chunks,
)


class DocumentReaderTest(unittest.TestCase):
    def test_extracts_utf8_text_document(self):
        with TemporaryDirectory(prefix="doc-reader-") as td:
            path = Path(td) / "note.txt"
            path.write_text("第一行\n第二行", encoding="utf-8")

            result = extract_document_text(str(path), media_type="text/plain")

        self.assertEqual(result.error, "")
        self.assertIn("第一行", result.text)
        self.assertEqual(result.name, "note.txt")

    def test_detects_document_media_without_treating_images_as_documents(self):
        self.assertTrue(is_document_media("/tmp/report.pdf", "application/pdf"))
        self.assertTrue(is_document_media("/tmp/report.txt", "text/plain"))
        self.assertFalse(is_document_media("/tmp/photo.jpg", "image/jpeg"))

    def test_splits_large_text_into_chunks(self):
        text = "A" * 6500 + "\n\n" + "B" * 6500
        chunks = split_text_chunks(text, max_chars=6000, overlap=0)

        self.assertGreaterEqual(len(chunks), 2)
        self.assertIn("A", chunks[0])
        self.assertIn("B", chunks[-1])


if __name__ == "__main__":
    unittest.main()
