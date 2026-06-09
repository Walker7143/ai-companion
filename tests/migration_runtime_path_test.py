import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_companion.config.loader import Config
from ai_companion.gateway.cmd import load_platform_config
from ai_companion.gateway.path_resolver import discover_bots, get_data_dir as gateway_get_data_dir
from ai_companion.main import get_data_dir as main_get_data_dir


class MigrationRuntimePathTest(unittest.TestCase):
    def test_runtime_respects_ai_companion_home_for_config_and_bots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_home = root / "custom-home"
            config_dir = app_home / "config"
            bot_dir = app_home / "data" / "bots" / "migrated_bot"
            persona_dir = bot_dir / "persona"

            config_dir.mkdir(parents=True)
            persona_dir.mkdir(parents=True)

            (config_dir / "bots.yaml").write_text(
                "bots:\n  - id: migrated_bot\n    name: Migrated Bot\n    enabled: true\n",
                encoding="utf-8",
            )
            (config_dir / "models.yaml").write_text("model:\n  provider: minimax\n", encoding="utf-8")
            (persona_dir / "profile.json").write_text(
                json.dumps({"name": "Migrated Bot", "description": "restored"}, ensure_ascii=False),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"AI_COMPANION_HOME": str(app_home)}, clear=False):
                cfg = Config()
                self.assertEqual(cfg.config_dir.resolve(), config_dir.resolve())
                self.assertEqual(main_get_data_dir().resolve(), (app_home / "data" / "bots").resolve())
                self.assertEqual(gateway_get_data_dir().resolve(), (app_home / "data" / "bots").resolve())
                self.assertEqual(load_platform_config("weixin"), None)

                bots = discover_bots()
                migrated = next((bot for bot in bots if bot["id"] == "migrated_bot"), None)
                self.assertIsNotNone(migrated)
                self.assertEqual(migrated["name"], "Migrated Bot")

    def test_platform_config_loader_reads_from_ai_companion_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_home = root / "custom-home"
            config_dir = app_home / "config"
            config_dir.mkdir(parents=True)
            (config_dir / "config.yaml").write_text(
                "platforms:\n  weixin:\n    enabled: true\n    token: migrated-token\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"AI_COMPANION_HOME": str(app_home)}, clear=False):
                weixin_cfg = load_platform_config("weixin")
                self.assertIsNotNone(weixin_cfg)
                self.assertTrue(weixin_cfg.get("enabled"))
                self.assertEqual(weixin_cfg.get("token"), "migrated-token")


if __name__ == "__main__":
    unittest.main()
