import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import yaml

from ai_companion.config.loader import Config
from ai_companion.gateway.commands import GatewayCommandHandler, parse_gateway_command


class DummyModel:
    def __init__(self, provider="openai", model="gpt-old"):
        self._provider = provider
        self.model = model

    @property
    def provider(self):
        return self._provider


class DummyBot:
    def __init__(self):
        self.id = "bot1"
        self.name = "Bot One"
        self.model = DummyModel()
        self.reset_called = False
        self.memory = None

    def reset_history(self):
        self.reset_called = True

    def set_model(self, model):
        self.model = model

    def get_proactive_status(self):
        return {"config": {"enabled": False}}


class GatewayCommandTest(unittest.IsolatedAsyncioTestCase):
    def _config(self):
        tmp = tempfile.TemporaryDirectory()
        config_dir = Path(tmp.name)
        (config_dir / "models.yaml").write_text(
            yaml.safe_dump(
                {
                    "model": {"provider": "openai"},
                    "openai": {
                        "api_key": "sk-test",
                        "base_url": "https://api.openai.com/v1",
                        "model": "gpt-4o",
                    },
                    "ollama": {
                        "base_url": "http://localhost:11434",
                        "model": "qwen2.5:7b",
                    },
                    "memory": {"embedding": "none"},
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        (config_dir / "bots.yaml").write_text("bots: []\n", encoding="utf-8")
        (config_dir / "config.yaml").write_text("{}\n", encoding="utf-8")
        self.addCleanup(tmp.cleanup)
        return Config(config_dir)

    def test_parse_gateway_command_strips_mentions(self):
        parsed = parse_gateway_command("/model@bot openai gpt-4o")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.name, "model")
        self.assertEqual(parsed.args, "openai gpt-4o")

    async def test_new_models_model_and_status_commands(self):
        handler = GatewayCommandHandler(self._config())
        bot = DummyBot()

        new_reply = await handler.handle("/new", bot)
        models_reply = await handler.handle("/models", bot)
        current_reply = await handler.handle("/model", bot)
        switch_reply = await handler.handle("/model ollama llama3.1:8b", bot)
        status_reply = await handler.handle(
            "/status",
            bot,
            SimpleNamespace(source=SimpleNamespace(chat_type="group", chat_name="Test Chat")),
        )

        self.assertTrue(bot.reset_called)
        self.assertIn("已开启新会话", new_reply)
        self.assertIn("openai", models_reply)
        self.assertIn("当前模型", current_reply)
        self.assertIn("已切换模型: ollama / llama3.1:8b", switch_reply)
        self.assertEqual(bot.model.provider, "ollama")
        self.assertEqual(bot.model.model, "llama3.1:8b")
        self.assertIn("状态:", status_reply)
        self.assertIn("Bot One", status_reply)

    async def test_dream_commands(self):
        class DummyDreaming:
            def __init__(self):
                self.enabled = False

            async def set_enabled(self, enabled: bool):
                self.enabled = enabled

            async def run(self, *, trigger_source: str, trigger_reason: str = ""):
                return {
                    "run": {
                        "candidate_count": 3,
                        "promoted_count": 1,
                        "kept_short_term_count": 1,
                    },
                    "report": {
                        "user_summary": "本次记忆整理完成。\n- 用户最近在忙一个项目",
                    },
                }

            async def doctor_status(self):
                return {"ok": False, "issues": ["latest_run_failed"], "suggestions": ["重试一次整理"]}

            async def latest_report(self):
                return {"user_summary": "最近整理摘要"}

            async def status(self):
                return {
                    "enabled": self.enabled,
                    "auto_run_enabled": False,
                    "last_status": "completed",
                    "last_run_at": "2026-05-22T10:00:00",
                    "latest_report": {"user_summary": "最近整理摘要"},
                }

            async def delete_latest_promotions(self):
                return {"ok": True, "deleted": {"semantic": 1, "understanding_projection": 1}}

        handler = GatewayCommandHandler(self._config())
        bot = DummyBot()
        bot.memory = SimpleNamespace(dreaming=DummyDreaming())

        on_reply = await handler.handle("/dream on", bot)
        status_reply = await handler.handle("/dream status", bot)
        run_reply = await handler.handle("/dream run", bot)
        doctor_reply = await handler.handle("/dream doctor", bot)
        report_reply = await handler.handle("/dream report", bot)
        delete_reply = await handler.handle("/dream delete", bot)

        self.assertIn("已开启记忆整理", on_reply)
        self.assertIn("记忆整理状态", status_reply)
        self.assertIn("记忆整理已完成", run_reply)
        self.assertIn("记忆整理诊断", doctor_reply)
        self.assertIn("最近整理摘要", report_reply)
        self.assertIn("已删除最近一次整理新增的自动记忆", delete_reply)


if __name__ == "__main__":
    unittest.main()
