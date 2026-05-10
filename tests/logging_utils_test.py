import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_companion.logging_utils import (
    DEFAULT_LOG_MAX_BYTES,
    TailPreservingFileHandler,
    get_log_max_bytes,
    parse_size_to_bytes,
    trim_log_file,
)


class LoggingUtilsTest(unittest.TestCase):
    def test_parse_size_to_bytes(self):
        self.assertEqual(parse_size_to_bytes("50MB"), 50 * 1024 * 1024)
        self.assertEqual(parse_size_to_bytes("1.5m"), int(1.5 * 1024 * 1024))
        self.assertEqual(parse_size_to_bytes(1234), 1234)
        self.assertIsNone(parse_size_to_bytes("not-a-size"))

    def test_get_log_max_bytes_prefers_env(self):
        with patch.dict("os.environ", {"AI_COMPANION_LOG_MAX_SIZE": "2KB"}):
            self.assertEqual(get_log_max_bytes({"logging": {"max_file_size": "1MB"}}), 2048)

    def test_get_log_max_bytes_uses_config_default(self):
        self.assertEqual(get_log_max_bytes({"logging": {"max_file_size": "3KB"}}), 3 * 1024)
        self.assertEqual(get_log_max_bytes({}), DEFAULT_LOG_MAX_BYTES)

    def test_trim_log_file_keeps_recent_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "app.log"
            log_path.write_text(
                "old line 1\nold line 2\nnew line 1\nnew line 2\n",
                encoding="utf-8",
            )

            self.assertTrue(trim_log_file(log_path, max_bytes=24))

            content = log_path.read_text(encoding="utf-8")
            self.assertNotIn("old line", content)
            self.assertIn("new line 1", content)
            self.assertIn("new line 2", content)
            self.assertLessEqual(log_path.stat().st_size, 24)

    def test_tail_preserving_file_handler_caps_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "app.log"
            logger = logging.getLogger(f"logging-utils-test-{id(log_path)}")
            logger.setLevel(logging.INFO)
            logger.propagate = False
            handler = TailPreservingFileHandler(log_path, max_bytes=80, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
            try:
                for index in range(20):
                    logger.info("line %02d xxxxxxxxxx", index)
            finally:
                logger.removeHandler(handler)
                handler.close()

            content = log_path.read_text(encoding="utf-8")
            self.assertNotIn("line 00", content)
            self.assertIn("line 19", content)
            self.assertLessEqual(log_path.stat().st_size, 100)


if __name__ == "__main__":
    unittest.main()
