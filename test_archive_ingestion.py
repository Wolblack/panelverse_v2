import tempfile
import unittest
from pathlib import Path

import database
from archive_service import detect_type, completeness_for


class UnifiedArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = database.DATABASE
        database.DATABASE = Path(self.tmp.name) / "test.db"
        database.init_db()

    def tearDown(self):
        database.DATABASE = self.old_db
        self.tmp.cleanup()

    def test_type_detection(self):
        self.assertEqual(detect_type("book.epub", "application/epub+zip")[0], "BOOK")
        self.assertEqual(detect_type("issue.cbz", "application/zip")[0], "COMIC")
        self.assertEqual(detect_type("track.flac", "audio/flac")[0], "MUSIC")
        self.assertEqual(detect_type("movie.mkv", "video/x-matroska")[0], "VIDEO")

    def test_additive_schema_and_duplicate_hash(self):
        item_id = database.archive_create_item("BOOK", "Clean Code", {"isbn13": "9780132350884"}, "test")
        database.archive_add_file(
            item_id, "clean.pdf", "/tmp/clean.pdf", "application/pdf", ".pdf",
            1234, "abc123", "BOOK", {}
        )
        duplicate = database.archive_find_duplicate("abc123", "other", "")
        self.assertIsNotNone(duplicate)
        self.assertEqual(duplicate[1], "exact_hash")

    def test_completeness(self):
        score = completeness_for(
            "BOOK",
            {"title": "Clean Code", "authors": "Robert C. Martin", "language": "en"},
            Path("/tmp/clean.pdf"),
            ""
        )
        self.assertEqual(score, 100)


if __name__ == "__main__":
    unittest.main()
