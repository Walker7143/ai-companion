from pathlib import Path
import tempfile
import unittest
import zipfile

from ai_companion.migration import export_runtime_data, import_runtime_data


class MigrationTest(unittest.TestCase):
    def test_export_import_runtime_data_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_home = tmp_path / "source-home"
            target_home = tmp_path / "target-home"
            archive = tmp_path / "migration.zip"

            (source_home / "config").mkdir(parents=True)
            (source_home / "data" / "bots" / "bot_a" / "persona").mkdir(parents=True)
            (source_home / "data" / "bots" / "bot_a" / "memory").mkdir(parents=True)
            (source_home / "logs").mkdir(parents=True)

            (source_home / "config" / "bots.yaml").write_text("bots: []\n", encoding="utf-8")
            (source_home / ".env").write_text("SECRET=value\n", encoding="utf-8")
            (source_home / "data" / "bots" / "bot_a" / "persona" / "profile.json").write_text('{"name":"A"}', encoding="utf-8")
            (source_home / "data" / "bots" / "bot_a" / "memory" / "working.db").write_bytes(b"db")
            (source_home / "logs" / "gateway.log").write_text("ignored\n", encoding="utf-8")

            exported = export_runtime_data(archive, home=source_home)
            self.assertEqual(exported.archive, archive.resolve())
            self.assertEqual(exported.file_count, 4)

            imported = import_runtime_data(archive, home=target_home)
            self.assertEqual(imported.file_count, 4)
            self.assertEqual((target_home / "config" / "bots.yaml").read_text(encoding="utf-8"), "bots: []\n")
            self.assertEqual((target_home / ".env").read_text(encoding="utf-8"), "SECRET=value\n")
            self.assertEqual((target_home / "data" / "bots" / "bot_a" / "memory" / "working.db").read_bytes(), b"db")
            self.assertFalse((target_home / "logs" / "gateway.log").exists())

    def test_import_backs_up_overwritten_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_home = tmp_path / "source-home"
            target_home = tmp_path / "target-home"
            archive = tmp_path / "migration.zip"

            (source_home / "config").mkdir(parents=True)
            (target_home / "config").mkdir(parents=True)
            (source_home / "config" / "config.yaml").write_text("new: true\n", encoding="utf-8")
            (target_home / "config" / "config.yaml").write_text("old: true\n", encoding="utf-8")

            export_runtime_data(archive, home=source_home)
            result = import_runtime_data(archive, home=target_home)

            self.assertEqual((target_home / "config" / "config.yaml").read_text(encoding="utf-8"), "new: true\n")
            self.assertIsNotNone(result.backup_dir)
            self.assertEqual((result.backup_dir / "config" / "config.yaml").read_text(encoding="utf-8"), "old: true\n")

    def test_import_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            archive = tmp_path / "bad.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr(
                    "ai-companion-migration.json",
                    '{"format":"ai-companion-runtime-migration","version":1}',
                )
                zf.writestr("../escape.txt", "nope")

            with self.assertRaisesRegex(ValueError, "Unsafe archive path"):
                import_runtime_data(archive, home=tmp_path / "target")


if __name__ == "__main__":
    unittest.main()
