import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ai_companion.embedding_setup import ensure_local_embedding_model


class EmbeddingSetupTest(unittest.TestCase):
    def test_uses_cached_model_when_available(self):
        calls = []

        class FakeModel:
            def __init__(self, model_name, local_files_only=False):
                calls.append((model_name, local_files_only))

            def get_sentence_embedding_dimension(self):
                return 384

        fake_module = SimpleNamespace(SentenceTransformer=FakeModel)
        with patch.dict("sys.modules", {"sentence_transformers": fake_module}):
            ok, message = ensure_local_embedding_model("demo-model")

        self.assertTrue(ok)
        self.assertIn("already cached", message)
        self.assertEqual(calls, [("demo-model", True)])

    def test_downloads_when_cache_missing(self):
        calls = []

        class FakeModel:
            def __init__(self, model_name, local_files_only=False):
                calls.append((model_name, local_files_only))
                if local_files_only:
                    raise OSError("missing local cache")

            def get_sentence_embedding_dimension(self):
                return 384

        fake_module = SimpleNamespace(SentenceTransformer=FakeModel)
        with patch.dict("sys.modules", {"sentence_transformers": fake_module}):
            ok, message = ensure_local_embedding_model("demo-model")

        self.assertTrue(ok)
        self.assertIn("downloaded", message)
        self.assertEqual(calls, [("demo-model", True), ("demo-model", False)])

    def test_can_skip_download_when_local_only(self):
        class FakeModel:
            def __init__(self, model_name, local_files_only=False):
                raise OSError("missing local cache")

        fake_module = SimpleNamespace(SentenceTransformer=FakeModel)
        with patch.dict("sys.modules", {"sentence_transformers": fake_module}):
            ok, message = ensure_local_embedding_model("demo-model", download_if_missing=False)

        self.assertFalse(ok)
        self.assertIn("not cached locally", message)


if __name__ == "__main__":
    unittest.main()
