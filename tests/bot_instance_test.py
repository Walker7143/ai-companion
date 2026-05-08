import unittest
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_companion.bot.instance import BotInstance
from ai_companion.persona.engine import PersonaEngine
from ai_companion.persona.loader import PersonaLoader
from ai_companion.skill.base import SkillContext
from ai_companion.skill.command import execute_skill_command


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


class EchoModel:
    provider = "test"
    model = "echo-model"

    async def chat(self, messages, system_prompt="", **kwargs):
        return "ok"


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


class BotSkillCapabilityStatusTest(unittest.IsolatedAsyncioTestCase):
    async def test_unconfigured_builtin_skills_are_disabled_with_reason(self):
        bot = BotInstance({"id": "shen_nian", "name": "沈念", "skills": {}}, model=None, memory_config=None)
        try:
            caps = bot.get_skill_capabilities()["skills"]
            self.assertEqual(caps["image_generation"]["reason"], "not_configured")
            self.assertEqual(caps["tts"]["reason"], "not_configured")
            self.assertFalse(caps["image_generation"]["registered"])
            self.assertFalse(caps["tts"]["registered"])
        finally:
            await bot.close()

    async def test_runtime_skills_view_includes_builtin_and_installed(self):
        with TemporaryDirectory(prefix="cap-skill-home-") as td:
            previous_home = os.environ.get("AI_COMPANION_HOME")
            os.environ["AI_COMPANION_HOME"] = td
            try:
                skill_dir = Path(td) / "data" / "bots" / "_skills" / "skill-hello"
                skill_dir.mkdir(parents=True, exist_ok=True)
                (skill_dir / "skill.json").write_text(
                    json.dumps(
                        {
                            "name": "hello",
                            "version": "1.0.0",
                            "description": "测试技能",
                            "entry": "hello_skill.py",
                            "enabled": True,
                            "requirements": [],
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                (skill_dir / "hello_skill.py").write_text(
                    "\n".join(
                        [
                            "from ai_companion.skill.base import Skill, SkillContext, SkillResult",
                            "class HelloSkill(Skill):",
                            "    name = 'hello'",
                            "    description = '测试技能'",
                            "    capabilities = ['hello']",
                            "    async def execute(self, params: dict, context: SkillContext) -> SkillResult:",
                            "        return SkillResult(success=True, content='hi')",
                        ]
                    ),
                    encoding="utf-8",
                )

                bot = BotInstance({"id": "shen_nian", "name": "沈念", "skills": {}}, model=None, memory_config=None)
                try:
                    output = await execute_skill_command(
                        bot.skill_dispatcher,
                        "/skills",
                        SkillContext(bot_id="shen_nian", user_id="u", conversation_history=[], personality_tags=[]),
                        bot.skill_registry,
                        capabilities=bot.get_skill_capabilities(),
                    )
                    self.assertIn("运行时能力", output)
                    self.assertIn("image_generation", output)
                    self.assertIn("hello", output)
                finally:
                    await bot.close()
            finally:
                if previous_home is None:
                    os.environ.pop("AI_COMPANION_HOME", None)
                else:
                    os.environ["AI_COMPANION_HOME"] = previous_home

    async def test_installed_skill_auto_route_via_natural_text(self):
        with TemporaryDirectory(prefix="cap-skill-home-") as td:
            previous_home = os.environ.get("AI_COMPANION_HOME")
            os.environ["AI_COMPANION_HOME"] = td
            try:
                skill_dir = Path(td) / "data" / "bots" / "_skills" / "skill-knowledge_lookup"
                skill_dir.mkdir(parents=True, exist_ok=True)
                (skill_dir / "skill.json").write_text(
                    json.dumps(
                        {
                            "name": "knowledge_lookup",
                            "version": "1.0.0",
                            "description": "知识检索",
                            "entry": "lookup_skill.py",
                            "enabled": True,
                            "auto": True,
                            "routing_keywords": ["查一下", "汇率"],
                            "confidence_threshold": 0.72,
                            "requirements": [],
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                (skill_dir / "lookup_skill.py").write_text(
                    "\n".join(
                        [
                            "from ai_companion.skill.base import Skill, SkillContext, SkillResult",
                            "class LookupSkill(Skill):",
                            "    name = 'knowledge_lookup'",
                            "    description = '知识检索'",
                            "    capabilities = ['lookup']",
                            "    async def execute(self, params: dict, context: SkillContext) -> SkillResult:",
                            "        return SkillResult(success=True, content='lookup-result')",
                        ]
                    ),
                    encoding="utf-8",
                )

                bot = BotInstance({"id": "shen_nian", "name": "沈念", "skills": {}}, model=EchoModel(), memory_config=None)
                try:
                    bot._initialized = True
                    bot._schedulers_started = True
                    response = await bot.handle_message("帮我查一下今天美元汇率")
                finally:
                    await bot.close()

                self.assertEqual(response, "lookup-result")
            finally:
                if previous_home is None:
                    os.environ.pop("AI_COMPANION_HOME", None)
                else:
                    os.environ["AI_COMPANION_HOME"] = previous_home


if __name__ == "__main__":
    unittest.main()
