import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_companion.bot.instance import BotInstance
from ai_companion.persona.engine import PersonaEngine
from ai_companion.persona.loader import PersonaLoader


class BrokenModel:
    provider = "broken"
    model = "broken-model"

    async def chat(self, messages, system_prompt="", **kwargs):
        raise TypeError("'NoneType' object is not subscriptable")


class SchedulerModel:
    provider = "test"
    model = "scheduler-model"

    async def chat(self, messages, system_prompt="", **kwargs):
        text = messages[-1].get("content", "") if messages else ""
        if "输出一个 JSON 对象" in text:
            return '{"is_major": false, "reason": "test"}'
        return "[]"


def _write_test_persona(root: Path, bot_id: str) -> None:
    import json

    persona_dir = root / bot_id / "persona"
    persona_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "profile.json": {
            "id": bot_id,
            "name": "测试 Bot",
            "age": 24,
            "occupation": "测试员",
            "personality_tags": ["温柔"],
            "relationship_to_user": "朋友",
        },
        "backstory.json": {"key_moments": []},
        "values.json": {"non_negotiable": []},
        "speaking_style.json": {"tone": "自然"},
        "proactive.json": {
            "enabled": True,
            "mode": "active",
            "scheduler": {"check_interval_seconds": 600, "contact_probability": 0},
            "platform": {"type": "cli"},
            "preferred_contact_times": ["00:00-23:59"],
        },
        "life.json": {
            "daily_interval_seconds": 86400,
            "major_interval_seconds": 604800,
            "time_ratio": 1,
        },
    }
    for filename, data in files.items():
        (persona_dir / filename).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class BotInstanceModelFallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_chat_with_fallback_handles_unexpected_model_exceptions(self):
        bot = BotInstance({"id": "shen_nian", "name": "沈念"}, model=BrokenModel())

        with self.assertLogs("ai_companion.bot.instance", level="ERROR") as logs:
            result = await bot._chat_with_fallback([{"role": "user", "content": "hi"}])

        self.assertIsNone(result)
        self.assertTrue(any("对话异常" in item for item in logs.output))

    async def test_handle_message_includes_model_failure_diagnostics(self):
        bot = BotInstance(
            {"id": "shen_nian", "name": "沈念"},
            model=BrokenModel(),
            refusal_enabled=False,
        )
        bot._initialized = True
        bot._schedulers_started = True

        try:
            result = await bot.handle_message("hi")
        finally:
            await bot.close()

        self.assertIn("模型请求失败", result)
        self.assertIn("broken / broken-model", result)
        self.assertIn("'NoneType' object is not subscriptable", result)

    async def test_scheduler_runtime_lock_prevents_duplicate_bot_schedulers(self):
        with TemporaryDirectory(prefix="bot-scheduler-lock-") as td:
            root = Path(td)
            bot_id = "lock_bot"
            _write_test_persona(root, bot_id)
            config = {"id": bot_id, "name": "测试 Bot", "data_dir": str(root)}
            first = BotInstance(config, model=SchedulerModel(), data_dir=root, refusal_enabled=False)
            second = BotInstance(config, model=SchedulerModel(), data_dir=root, refusal_enabled=False)

            try:
                await first.init()
                await second.init()

                self.assertTrue(first._schedulers_started)
                self.assertIsNotNone(first.proactive_scheduler)
                self.assertIsNotNone(first.life_scheduler)
                self.assertIsNone(second.proactive_scheduler)
                self.assertIsNone(second.life_scheduler)
                self.assertFalse(second._schedulers_started)
                self.assertIsNotNone(second._proactive_scheduler_lock_owner)
                self.assertIsNotNone(second._life_scheduler_lock_owner)

                await first.close()
                await second.ensure_schedulers_started()

                self.assertTrue(second._schedulers_started)
                self.assertIsNotNone(second.proactive_scheduler)
                self.assertIsNotNone(second.life_scheduler)
            finally:
                await second.close()
                await first.close()


class PersonaEngineDefaultStyleTest(unittest.TestCase):
    def test_system_prompt_includes_global_embodied_expression_guidance(self):
        with TemporaryDirectory(prefix="persona-default-style-") as td:
            root = Path(td)
            bot_id = "style_bot"
            _write_test_persona(root, bot_id)

            persona = PersonaLoader(root / bot_id / "persona").load()
            prompt = PersonaEngine(persona).build_system_prompt()

        self.assertIn("肢体/神态表达", prompt)
        self.assertIn("括号动作", prompt)
        self.assertIn("不要每句都用", prompt)

    def test_system_prompt_honors_embodied_expression_frequency(self):
        import json

        with TemporaryDirectory(prefix="persona-high-style-") as td:
            root = Path(td)
            bot_id = "style_bot"
            _write_test_persona(root, bot_id)
            style_path = root / bot_id / "persona" / "speaking_style.json"
            style_path.write_text(
                json.dumps(
                    {
                        "tone": "自然",
                        "embodied_expression": {"enabled": True, "frequency": "high"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            persona = PersonaLoader(root / bot_id / "persona").load()
            prompt = PersonaEngine(persona).build_system_prompt()

        self.assertIn("肢体/神态表达：开启", prompt)
        self.assertIn("高频", prompt)
        self.assertIn("多数合适回复", prompt)

    def test_system_prompt_can_disable_embodied_expression(self):
        import json

        with TemporaryDirectory(prefix="persona-style-off-") as td:
            root = Path(td)
            bot_id = "style_bot"
            _write_test_persona(root, bot_id)
            style_path = root / bot_id / "persona" / "speaking_style.json"
            style_path.write_text(
                json.dumps(
                    {
                        "tone": "自然",
                        "embodied_expression": {"enabled": False, "frequency": "high"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            persona = PersonaLoader(root / bot_id / "persona").load()
            prompt = PersonaEngine(persona).build_system_prompt()

        self.assertIn("肢体/神态表达：当前已关闭", prompt)
        self.assertIn("不要主动加入括号动作", prompt)
        self.assertNotIn("多数合适回复", prompt)


if __name__ == "__main__":
    unittest.main()
