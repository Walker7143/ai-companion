import unittest
import json
import os
from datetime import datetime, timedelta
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


class PromiseModel:
    provider = "test"
    model = "promise-model"

    async def chat(self, messages, system_prompt="", **kwargs):
        return "我想一下，一会儿回复你。"


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
            "sync_with_local_time_when_realtime": False,
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


class BotInstanceProactiveCloseoutTest(unittest.IsolatedAsyncioTestCase):
    async def test_deferred_reply_promise_records_conversation_task(self):
        from ai_companion.proactive.motives import ConversationTaskType

        with TemporaryDirectory(prefix="bot-deferred-task-") as td:
            root = Path(td)
            bot_id = "promise_bot"
            _write_test_persona(root, bot_id)
            proactive_path = root / bot_id / "persona" / "proactive.json"
            proactive_payload = json.loads(proactive_path.read_text(encoding="utf-8"))
            proactive_payload["conversation_continuity"] = {
                "deferred_reply": {"default_delay_minutes": 8},
            }
            proactive_path.write_text(json.dumps(proactive_payload, ensure_ascii=False), encoding="utf-8")

            bot = BotInstance(
                {"id": bot_id, "name": "测试 Bot", "data_dir": str(root)},
                model=PromiseModel(),
                data_dir=root,
                memory_config={"embedding": "none"},
                refusal_enabled=False,
            )
            try:
                await bot.init(start_schedulers=False)
                await bot.handle_message(
                    "那你怎么看？",
                    memory_turn_context={
                        "platform": "weixin",
                        "session_id": "gw_abc",
                        "user_id": "default_user",
                        "chat_id": "wx-1",
                        "metadata": {"chat_name": "微信私聊"},
                    },
                )

                due = bot.conversation_task_store.list_due(
                    bot_id,
                    datetime.now() + timedelta(minutes=9),
                )
            finally:
                await bot.close()

            self.assertEqual(len(due), 1)
            self.assertEqual(due[0].type, ConversationTaskType.DEFERRED_REPLY)
            self.assertEqual(due[0].target["chat_id"], "wx-1")


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
        self.assertNotIn("避免反复使用同一动作词", prompt)

    def test_system_prompt_mentions_embodied_expression_variety(self):
        with TemporaryDirectory(prefix="persona-style-variety-") as td:
            root = Path(td)
            bot_id = "style_bot"
            _write_test_persona(root, bot_id)

            persona = PersonaLoader(root / bot_id / "persona").load()
            prompt = PersonaEngine(persona).build_system_prompt()

        self.assertIn("避免反复使用同一动作词", prompt)

    def test_turn_prompt_derives_action_guidance_from_persona(self):
        with TemporaryDirectory(prefix="persona-action-guidance-") as td:
            root = Path(td)
            bot_id = "style_bot"
            _write_test_persona(root, bot_id)
            profile_path = root / bot_id / "persona" / "profile.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "id": bot_id,
                        "name": "测试 Bot",
                        "age": 24,
                        "occupation": "急诊科医生",
                        "personality_tags": ["冷静可靠", "低表达", "保护欲强"],
                        "relationship_to_user": "很熟悉的人",
                        "appearance": "常穿深色外套，手指骨节明显",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            style_path = root / bot_id / "persona" / "speaking_style.json"
            style_path.write_text(
                json.dumps(
                    {
                        "tone": "简洁、沉稳、直接",
                        "emotion_indicators": {"tender": "关心会藏在行动里"},
                        "embodied_expression": {
                            "enabled": True,
                            "frequency": "medium",
                            "action_examples": ["把杯子往你手边推近一点"],
                            "avoid_actions": ["夸张拥抱"],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            persona = PersonaLoader(root / bot_id / "persona").load()
            prompt = PersonaEngine(persona).build_embodied_expression_turn_prompt(
                user_input="我有点不舒服",
                intent="emotional_support",
                recent_actions=["低头看了你一眼"],
            )

        self.assertIn("性格化动作方向", prompt)
        self.assertIn("动作幅度偏小", prompt)
        self.assertIn("关心要落在实际动作上", prompt)
        self.assertIn("动作参考样例", prompt)
        self.assertIn("避免动作：夸张拥抱", prompt)


class ResponseStyleEmbodiedActionPolishTest(unittest.TestCase):
    def test_extracts_recent_actions_for_turn_prompt(self):
        from ai_companion.bot.response_style import ResponseStylePolisher

        polisher = ResponseStylePolisher()
        recent = [
            "（低头看了你一眼）嗯，我在听。",
            "（指尖轻轻敲了敲桌面）你继续说。",
            "（低头看了你一眼）别急。",
        ]
        actions = polisher.list_recent_actions(recent)

        self.assertEqual(actions, ["低头看了你一眼", "指尖轻轻敲了敲桌面"])

    def test_does_not_rewrite_actions_in_post_polish(self):
        from ai_companion.bot.response_style import ResponseStylePolisher

        polisher = ResponseStylePolisher()
        raw = "（消息）我在。 （停顿）你慢慢讲。 （又发一条）（小声）"
        polished = polisher.polish(raw)

        self.assertIn("（消息）", polished)
        self.assertIn("（停顿）", polished)
        self.assertIn("（又发一条）", polished)
        self.assertIn("（小声）", polished)
        self.assertIn("我在。", polished)
        self.assertIn("你慢慢讲。", polished)


class BotInstanceEmbodiedPromptTest(unittest.IsolatedAsyncioTestCase):
    async def test_main_generation_prompt_includes_dynamic_embodied_context(self):
        class PromptCaptureModel:
            provider = "test"
            model = "prompt-capture"

            def __init__(self):
                self.system_prompts = []

            async def chat(self, messages, system_prompt="", **kwargs):
                self.system_prompts.append(system_prompt)
                return "ok"

        with TemporaryDirectory(prefix="bot-embodied-prompt-") as td:
            root = Path(td)
            bot_id = "style_bot"
            _write_test_persona(root, bot_id)
            style_path = root / bot_id / "persona" / "speaking_style.json"
            style_path.write_text(
                json.dumps(
                    {
                        "tone": "安静、克制",
                        "emotion_indicators": {"sad": "回复会短一点，语气放慢"},
                        "embodied_expression": {"enabled": True, "frequency": "high"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            model = PromptCaptureModel()
            bot = BotInstance({"id": bot_id, "name": "测试 Bot", "data_dir": str(root)}, model=model, data_dir=root, refusal_enabled=False)
            bot._initialized = True
            bot._schedulers_started = True
            bot.conversation_history.append({"role": "assistant", "content": "（低头看了你一眼）嗯。"})
            try:
                response = await bot.handle_message("有点累，陪我说会儿话")
            finally:
                await bot.close()

            self.assertEqual(response, "ok")
            self.assertEqual(len(model.system_prompts), 1)
            prompt = model.system_prompts[0]
            self.assertIn("【本轮肢体/神态表达】", prompt)
            self.assertIn("当前配置：high", prompt)
            self.assertIn("最近已用过的动作：低头看了你一眼", prompt)
            self.assertIn("性格化动作方向", prompt)
            self.assertIn("动作幅度偏小", prompt)
            self.assertIn("情绪动作线索", prompt)
            self.assertIn("禁止使用“（消息）”“（打字）”“（停顿）”“（小声）”“（又发一条）”", prompt)
            self.assertNotIn("对话润色器", prompt)


class BotInstanceDirectTimeQueryTest(unittest.IsolatedAsyncioTestCase):
    async def test_direct_time_question_injects_local_clock_into_generation_prompt(self):
        class TimeCaptureModel:
            provider = "test"
            model = "time-capture"

            def __init__(self):
                self.calls = 0
                self.system_prompts = []
                self.messages = []

            async def chat(self, messages, system_prompt="", **kwargs):
                self.calls += 1
                self.messages.append(messages)
                self.system_prompts.append(system_prompt)
                return "现在是 16:58（下午）。"

        with TemporaryDirectory(prefix="bot-time-query-") as td:
            root = Path(td)
            bot_id = "style_bot"
            _write_test_persona(root, bot_id)
            model = TimeCaptureModel()
            bot = BotInstance({"id": bot_id, "name": "测试 Bot", "data_dir": str(root)}, model=model, data_dir=root, refusal_enabled=False)
            bot._initialized = True
            bot._schedulers_started = True
            bot.life_engine.get_status = lambda: {
                "current_date": "2026-05-09",
                "day_of_week": "周六",
                "local_time": "16:58",
                "time_of_day": "下午",
                "current_datetime_text": "2026-05-09 16:58（周六，下午）",
            }

            try:
                response = await bot.handle_message("现在几点")
            finally:
                await bot.close()

            self.assertEqual(model.calls, 1)
            self.assertIn("当前本地时间：16:58（下午）", model.system_prompts[0])
            self.assertIn("当前时刻：2026-05-09 16:58（周六，下午）", model.system_prompts[0])
            self.assertIn("直接用本段的当前本地时间/当前日期回答", model.system_prompts[0])
            self.assertEqual(response, "现在是 16:58（下午）。")


class BotInstanceRealtimeContextTest(unittest.IsolatedAsyncioTestCase):
    async def test_direct_time_question_does_not_include_old_time_history(self):
        class TimeCaptureModel:
            provider = "test"
            model = "time-capture"

            def __init__(self):
                self.system_prompts = []
                self.messages = []

            async def chat(self, messages, system_prompt="", **kwargs):
                self.messages.append(messages)
                self.system_prompts.append(system_prompt)
                return "\u73b0\u5728\u662f 16:58\uff08\u4e0b\u5348\uff09\u3002"

        with TemporaryDirectory(prefix="bot-time-query-clean-") as td:
            root = Path(td)
            bot_id = "style_bot"
            _write_test_persona(root, bot_id)
            model = TimeCaptureModel()
            bot = BotInstance(
                {"id": bot_id, "name": "\u6d4b\u8bd5 Bot", "data_dir": str(root)},
                model=model,
                memory_config={"embedding": "none"},
                data_dir=root,
                refusal_enabled=False,
            )
            bot._initialized = True
            bot._schedulers_started = True
            bot.life_engine.get_status = lambda: {
                "current_date": "2026-05-09",
                "day_of_week": "\u5468\u516d",
                "local_time": "16:58",
                "time_of_day": "\u4e0b\u5348",
                "current_datetime_text": "2026-05-09 16:58\uff08\u5468\u516d\uff0c\u4e0b\u5348\uff09",
            }
            await bot.memory.init()
            await bot.memory.working.append(
                user_input="\u73b0\u5728\u51e0\u70b9",
                bot_output="\uff08\u6d88\u606f\uff09\u4e0b\u5348\u4e09\u70b9\u591a\u3002\uff08\u6253\u5b57\uff09",
                session_id=bot.memory.working.current_session,
            )

            try:
                response = await bot.handle_message("\u73b0\u5728\u51e0\u70b9")
            finally:
                await bot.close()

            sent_history = "\n".join(str(msg.get("content", "")) for msg in model.messages[0])
            self.assertNotIn("\u4e0b\u5348\u4e09\u70b9\u591a", sent_history)
            self.assertNotIn("\uff08\u6d88\u606f\uff09", sent_history)
            self.assertNotIn("\u4e0b\u5348\u4e09\u70b9\u591a", model.system_prompts[0])
            self.assertIn("16:58", model.system_prompts[0])
            self.assertEqual(response, "\u73b0\u5728\u662f 16:58\uff08\u4e0b\u5348\uff09\u3002")


class BotInstanceGenerationContextTest(unittest.IsolatedAsyncioTestCase):
    async def test_old_generic_action_labels_are_removed_from_llm_history_only(self):
        class HistoryCaptureModel:
            provider = "test"
            model = "history-capture"

            def __init__(self):
                self.messages = []

            async def chat(self, messages, system_prompt="", **kwargs):
                self.messages.append(messages)
                return "（低头看了你一眼）我在。"

        with TemporaryDirectory(prefix="bot-context-clean-") as td:
            root = Path(td)
            bot_id = "style_bot"
            _write_test_persona(root, bot_id)
            model = HistoryCaptureModel()
            bot = BotInstance(
                {"id": bot_id, "name": "测试 Bot", "data_dir": str(root)},
                model=model,
                memory_config={"embedding": "none"},
                data_dir=root,
                refusal_enabled=False,
            )
            bot._initialized = True
            bot._schedulers_started = True
            await bot.memory.init()
            await bot.memory.working.append(
                user_input="你吃饭了吗",
                bot_output="（消息）还没。（打字）准备煮点东西。（停顿）你呢？（又发一条）（小声）别又不吃。",
                session_id=bot.memory.working.current_session,
            )

            try:
                response = await bot.handle_message("陪我聊会儿")
            finally:
                await bot.close()

            sent_history = "\n".join(str(msg.get("content", "")) for msg in model.messages[0])
            self.assertNotIn("（消息）", sent_history)
            self.assertNotIn("（打字）", sent_history)
            self.assertNotIn("（停顿）", sent_history)
            self.assertNotIn("（又发一条）", sent_history)
            self.assertNotIn("（小声）", sent_history)
            self.assertIn("准备煮点东西", sent_history)
            self.assertEqual(response, "（低头看了你一眼）我在。")


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

    async def test_image_skills_accept_simple_three_field_config(self):
        bot = BotInstance(
            {
                "id": "shen_nian",
                "name": "沈念",
                "skills": {
                    "image_generation": {
                        "enabled": True,
                        "auto": True,
                        "base_url": "https://example.com/v1",
                        "model": "gpt-image-1",
                        "api_key": "image-key",
                    },
                    "image_understanding": {
                        "enabled": True,
                        "auto": True,
                        "base_url": "https://example.com/v1",
                        "model": "gpt-4o",
                        "api_key": "vision-key",
                    },
                },
            },
            model=None,
            memory_config=None,
        )
        try:
            caps = bot.get_skill_capabilities()["skills"]
            self.assertTrue(caps["image_generation"]["available"])
            self.assertEqual(caps["image_generation"]["provider"], "openai_compatible")
            self.assertEqual(caps["image_generation"]["model"], "gpt-image-1")
            self.assertTrue(caps["image_understanding"]["available"])
            self.assertEqual(caps["image_understanding"]["provider"], "openai_compatible")
            self.assertEqual(caps["image_understanding"]["model"], "gpt-4o")
        finally:
            await bot.close()

    async def test_admin_skill_api_masks_and_preserves_image_api_keys(self):
        from ai_companion.gateway.admin_services import ConfigAdminService, MASKED_SECRET

        class _Config:
            def __init__(self, root: Path):
                self.config_dir = root / "config"
                self._models = None
                self._config = None

            @property
            def models(self):
                return {}

            @property
            def config(self):
                return {}

            def get_model_config(self):
                return {"provider": "openai", "api_key": "", "base_url": "https://api.openai.com/v1", "model": "gpt-4o"}

        with TemporaryDirectory(prefix="skill-admin-mask-") as td:
            root = Path(td)
            cfg = _Config(root)
            cfg.config_dir.mkdir(parents=True, exist_ok=True)
            (cfg.config_dir / "models.yaml").write_text(
                json.dumps(
                    {
                        "skills": {
                            "image_generation": {
                                "enabled": True,
                                "base_url": "https://example.com/v1",
                                "model": "gpt-image-1",
                                "api_key": "real-image-key",
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (cfg.config_dir / "bots.yaml").write_text("bots: []\n", encoding="utf-8")
            service = ConfigAdminService(cfg)

            public = service._public_skills("shen_nian", {"skills": {"image_generation": {"api_key": "real-image-key"}}})
            self.assertEqual(public["global"]["image_generation"]["api_key"], "real...-key")

            service._save_skills(
                "shen_nian",
                {
                    "global": {
                        "image_generation": {
                            "enabled": True,
                            "base_url": "https://example.com/v1",
                            "model": "gpt-image-1",
                            "api_key": MASKED_SECRET,
                        }
                    },
                    "bot": {},
                },
            )
            saved = (cfg.config_dir / "models.yaml").read_text(encoding="utf-8")
            self.assertIn("real-image-key", saved)

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
