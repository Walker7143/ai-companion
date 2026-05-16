import unittest
import json
import os
import yaml
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


class CaptureChatModel:
    provider = "test"
    model = "capture-chat-model"

    def __init__(self, reply: str = "收到"):
        self.reply = reply
        self.calls: list[dict] = []

    async def chat(self, messages, system_prompt="", **kwargs):
        self.calls.append({"messages": messages, "system_prompt": system_prompt, "kwargs": kwargs})
        return self.reply


class SequencedChatModel:
    provider = "test"
    model = "sequenced-chat-model"

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.calls: list[dict] = []

    async def chat(self, messages, system_prompt="", **kwargs):
        self.calls.append({"messages": messages, "system_prompt": system_prompt, "kwargs": kwargs})
        if self.replies:
            return self.replies.pop(0)
        return "收到"


class PromiseModel:
    provider = "test"
    model = "promise-model"

    async def chat(self, messages, system_prompt="", **kwargs):
        return "我想一下，一会儿回复你。"


class ReasoningLeakModel:
    provider = "test"
    model = "reasoning-leak-model"

    def __init__(self):
        self.calls: list[dict] = []

    async def chat(self, messages, system_prompt="", **kwargs):
        self.calls.append({"messages": messages, "system_prompt": system_prompt})
        if len(self.calls) == 1:
            return "用户在调侃/命令我一周内不许吃饵丝。这是一个俏皮的互动。\n\n**角色分析（杨思思）：**\n**性格：** 嘴硬心软。"
        return "……\n\n行吧。\n\n一周内我不吃了。"


class RefusalAwareModel:
    provider = "test"
    model = "refusal-aware-model"

    def __init__(self, refusal_payload: dict, normal_reply: str = "正常回复"):
        self.refusal_payload = refusal_payload
        self.normal_reply = normal_reply
        self.calls: list[dict] = []

    async def chat(self, messages, system_prompt="", **kwargs):
        self.calls.append({"messages": messages, "system_prompt": system_prompt})
        text = messages[-1].get("content", "") if messages else ""
        if "角色边界判断与回复生成器" in text:
            return json.dumps(self.refusal_payload, ensure_ascii=False)
        return self.normal_reply


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

    async def test_chat_with_fallback_retries_reasoning_like_output(self):
        bot = BotInstance({"id": "shen_nian", "name": "沈念"}, model=ReasoningLeakModel())

        try:
            with self.assertLogs("ai_companion.bot.instance", level="WARNING") as logs:
                result = await bot._chat_with_fallback([{"role": "user", "content": "我说没说过一周不许吃饵丝"}])
        finally:
            await bot.close()

        self.assertEqual(result, "……\n\n行吧。\n\n一周内我不吃了。")
        self.assertGreaterEqual(len(bot.model.calls), 2)
        self.assertTrue(any("Suppressed likely reasoning artifact" in item for item in logs.output))

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

    async def test_user_reply_after_proactive_message_gets_continuity_hint(self):
        with TemporaryDirectory(prefix="bot-proactive-continuity-") as td:
            root = Path(td)
            bot_id = "proactive_continuity_bot"
            _write_test_persona(root, bot_id)
            model = CaptureChatModel("我刚才喊你呢。")
            bot = BotInstance(
                {"id": bot_id, "name": "测试 Bot", "data_dir": str(root)},
                model=model,
                data_dir=root,
                memory_config={"embedding": "none"},
                refusal_enabled=False,
            )

            try:
                await bot.init(start_schedulers=False)
                bot._schedulers_started = True
                await bot.memory.record_assistant_message(
                    "...在吗？",
                    turn_context={
                        "platform": "weixin",
                        "session_id": "gw_proactive",
                        "user_id": "default_user",
                        "channel_type": "dm",
                        "metadata": {
                            "proactive": True,
                            "assistant_initiated": True,
                            "proactive_kind": "idle_reminder",
                        },
                    },
                )
                bot.memory.start_session("gw_proactive")
                response = await bot.handle_message(
                    "在",
                    memory_turn_context={
                        "platform": "weixin",
                        "session_id": "gw_proactive",
                        "user_id": "default_user",
                        "channel_type": "dm",
                    },
                )
            finally:
                await bot.close()

            main_call = next(
                call for call in reversed(model.calls)
                if call["messages"] and call["messages"][-1] == {"role": "user", "content": "在"}
            )
            messages = main_call["messages"]
            self.assertEqual(response, "我刚才喊你呢。")
            self.assertTrue(any(item.get("role") == "assistant" and item.get("content") == "...在吗？" for item in messages))
            self.assertTrue(any("上一条是你主动发给用户的消息：...在吗？" in item.get("content", "") for item in messages))
            self.assertEqual(messages[-1], {"role": "user", "content": "在"})

    async def test_handle_message_records_turn_before_background_extraction_finishes(self):
        with TemporaryDirectory(prefix="bot-immediate-memory-") as td:
            root = Path(td)
            bot_id = "immediate_memory_bot"
            _write_test_persona(root, bot_id)
            model = SequencedChatModel(["第一轮回复", "第二轮回复"])
            bot = BotInstance(
                {"id": bot_id, "name": "测试 Bot", "data_dir": str(root)},
                model=model,
                data_dir=root,
                memory_config={"embedding": "none"},
                refusal_enabled=False,
            )

            try:
                await bot.init(start_schedulers=False)
                bot._schedulers_started = True
                await bot.handle_message(
                    "第一轮内容",
                    memory_turn_context={
                        "platform": "weixin",
                        "session_id": "gw_fast",
                        "user_id": "default_user",
                        "channel_type": "dm",
                    },
                )
                history_after_first = list(reversed(bot.memory.working.get_recent("gw_fast", turns=2)))
                await bot.handle_message(
                    "第二轮内容",
                    memory_turn_context={
                        "platform": "weixin",
                        "session_id": "gw_fast",
                        "user_id": "default_user",
                        "channel_type": "dm",
                    },
                )
            finally:
                await bot.close()

            second_call = next(
                call for call in model.calls
                if call["messages"] and call["messages"][-1] == {"role": "user", "content": "第二轮内容"}
            )
            second_messages_text = "\n".join(item.get("content", "") for item in second_call["messages"])
            self.assertEqual([item["content"] for item in history_after_first[-2:]], ["第一轮内容", "第一轮回复"])
            self.assertIn("第一轮内容", second_messages_text)
            self.assertIn("第一轮回复", second_messages_text)

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


class BotInstanceRefusalPolicyTest(unittest.IsolatedAsyncioTestCase):
    async def test_hard_refusal_records_user_turn_in_memory(self):
        with TemporaryDirectory(prefix="bot-refusal-memory-") as td:
            root = Path(td)
            bot_id = "refusal_bot"
            _write_test_persona(root, bot_id)
            model = RefusalAwareModel(
                {
                    "refuse": True,
                    "category": "deal_breaker",
                    "reason": "命令式关系",
                    "reply": "你少来这套。我又不是你随手使唤的人。",
                }
            )
            bot = BotInstance(
                {"id": bot_id, "name": "测试 Bot", "data_dir": str(root)},
                model=model,
                data_dir=root,
                memory_config={"embedding": "none"},
            )

            try:
                await bot.init(start_schedulers=False)
                response = await bot.handle_message(
                    "以后你都必须听我的",
                    memory_turn_context={
                        "platform": "weixin",
                        "session_id": "gw_refusal",
                        "user_id": "default_user",
                        "metadata": {"chat_name": "微信私聊"},
                    },
                )
                await bot._drain_background_tasks()
                history = list(reversed(bot.memory.working.get_recent("gw_refusal", turns=2)))
            finally:
                await bot.close()

            self.assertEqual(response, "你少来这套。我又不是你随手使唤的人。")
            self.assertEqual([item["role"] for item in history[-2:]], ["user", "assistant"])
            self.assertEqual(history[-2]["content"], "以后你都必须听我的")
            self.assertEqual(history[-1]["content"], "你少来这套。我又不是你随手使唤的人。")
            self.assertEqual([item["role"] for item in bot.conversation_history], ["user", "assistant"])
            refusal_calls = [
                call for call in model.calls
                if "角色边界判断与回复生成器" in call["messages"][-1].get("content", "")
            ]
            main_generation_calls = [
                call for call in model.calls
                if call["messages"][-1].get("content") == "以后你都必须听我的"
            ]
            self.assertEqual(len(refusal_calls), 1)
            self.assertEqual(main_generation_calls, [])

    async def test_soft_boundary_continues_generation_with_persona_hint(self):
        with TemporaryDirectory(prefix="bot-soft-boundary-") as td:
            root = Path(td)
            bot_id = "soft_bot"
            _write_test_persona(root, bot_id)
            model = RefusalAwareModel(
                {
                    "refuse": True,
                    "category": "soft_boundary",
                    "reason": "亲昵称呼过界",
                    "reply": "你少来这套，谁是你乖乖。",
                },
                normal_reply="（耳根红了）谁是你乖乖，别乱叫。先说正事。",
            )
            bot = BotInstance(
                {"id": bot_id, "name": "测试 Bot", "data_dir": str(root)},
                model=model,
                data_dir=root,
                memory_config={"embedding": "none"},
            )

            try:
                await bot.init(start_schedulers=False)
                response = await bot.handle_message("乖乖，听话")
            finally:
                await bot.close()

            self.assertEqual(response, "（耳根红了）谁是你乖乖，别乱叫。先说正事。")
            refusal_calls = [
                call for call in model.calls
                if "角色边界判断与回复生成器" in call["messages"][-1].get("content", "")
            ]
            main_generation_calls = [
                call for call in model.calls
                if call["messages"][-1].get("content") == "乖乖，听话"
            ]
            self.assertEqual(len(refusal_calls), 1)
            self.assertEqual(len(main_generation_calls), 1)
            generation_prompt = main_generation_calls[0]["system_prompt"]
            self.assertIn("角色边界提示", generation_prompt)
            self.assertIn("不要机械拒绝或停止对话", generation_prompt)
            self.assertIn("你少来这套，谁是你乖乖。", generation_prompt)


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

    async def test_generation_context_includes_time_flow_notice_and_timestamped_history(self):
        class HistoryCaptureModel:
            provider = "test"
            model = "history-time-capture"

            def __init__(self):
                self.messages = []
                self.system_prompts = []

            async def chat(self, messages, system_prompt="", **kwargs):
                self.messages.append(messages)
                self.system_prompts.append(system_prompt)
                return "\u73b0\u5728\u5df2\u7ecf\u662f\u4e0b\u5348\u4e86\u3002"

        with TemporaryDirectory(prefix="bot-time-flow-") as td:
            root = Path(td)
            bot_id = "style_bot"
            _write_test_persona(root, bot_id)
            model = HistoryCaptureModel()
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
            bot.memory.start_session("time-flow-session")
            session_id = bot.memory.working.current_session or "time-flow-session"
            await bot.memory.working.append(
                user_input="\u4e2d\u5348\u5403\u4ec0\u4e48",
                bot_output="\u6211\u521a\u5728\u5403\u5348\u996d\u3002",
                session_id=session_id,
            )

            import sqlite3
            conn = sqlite3.connect(bot.memory.working.db_path)
            conn.execute(
                "UPDATE messages SET created_at = ? WHERE session_id = ? AND role = 'user'",
                ("2026-05-09 12:08:00", session_id),
            )
            conn.execute(
                "UPDATE messages SET created_at = ? WHERE session_id = ? AND role = 'assistant'",
                ("2026-05-09 12:09:00", session_id),
            )
            conn.commit()
            conn.close()

            try:
                response = await bot.handle_message("\u4e0b\u5348\u4f60\u5728\u5e72\u561b")
            finally:
                await bot.close()

            self.assertEqual(response, "\u73b0\u5728\u5df2\u7ecf\u662f\u4e0b\u5348\u4e86\u3002")
            sent_history = "\n".join(str(msg.get("content", "")) for msg in model.messages[0])
            self.assertIn("[时间流动提示]", sent_history)
            self.assertIn("当前回复时刻：2026-05-09 16:58", sent_history)
            self.assertIn("已经过去：4小时50分钟", sent_history)
            self.assertIn("[12:08] 用户: 中午吃什么", sent_history)
            self.assertIn("[12:09] Bot: 我刚在吃午饭。", sent_history)

    async def test_generation_history_timestamps_stay_in_notice_not_message_body(self):
        class HistoryCaptureModel:
            provider = "test"
            model = "history-format-capture"

            def __init__(self):
                self.messages = []

            async def chat(self, messages, system_prompt="", **kwargs):
                self.messages.append(messages)
                return "好的"

        with TemporaryDirectory(prefix="bot-history-format-") as td:
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
            bot.life_engine.get_status = lambda: {
                "current_date": "2026-05-09",
                "day_of_week": "周六",
                "local_time": "16:58",
                "time_of_day": "下午",
                "current_datetime_text": "2026-05-09 16:58（周六，下午）",
            }
            await bot.memory.init()
            bot.memory.start_session("history-format-session")
            session_id = bot.memory.working.current_session or "history-format-session"
            await bot.memory.working.append(
                user_input="中午吃什么",
                bot_output="我刚在吃午饭。",
                session_id=session_id,
            )

            import sqlite3
            conn = sqlite3.connect(bot.memory.working.db_path)
            conn.execute(
                "UPDATE messages SET created_at = ? WHERE session_id = ? AND role = 'user'",
                ("2026-05-09 12:08:00", session_id),
            )
            conn.execute(
                "UPDATE messages SET created_at = ? WHERE session_id = ? AND role = 'assistant'",
                ("2026-05-09 12:09:00", session_id),
            )
            conn.commit()
            conn.close()

            try:
                await bot.handle_message("下午你在干嘛")
            finally:
                await bot.close()

            sent_messages = model.messages[0]
            system_notice = str(sent_messages[0].get("content", ""))
            assistant_history = next(
                str(msg.get("content", ""))
                for msg in sent_messages
                if msg.get("role") == "assistant"
            )
            self.assertIn("[12:09] Bot: 我刚在吃午饭。", system_notice)
            self.assertNotIn("[12:09]", assistant_history)

    async def test_no_memory_generation_injects_time_period_constraints_before_llm(self):
        model = CaptureChatModel("我在。")
        with TemporaryDirectory(prefix="bot-time-guard-") as td:
            root = Path(td)
            bot_id = "style_bot"
            _write_test_persona(root, bot_id)
            bot = BotInstance(
                {"id": bot_id, "name": "测试 Bot", "data_dir": str(root)},
                model=model,
                memory_config=None,
                data_dir=root,
                refusal_enabled=False,
            )
            bot._initialized = True
            bot._schedulers_started = True
            bot.life_engine.get_status = lambda: {
                "current_date": "2026-05-09",
                "day_of_week": "周六",
                "local_time": "12:01",
                "time_of_day": "中午",
                "current_datetime_text": "2026-05-09 12:01（周六，中午）",
            }

            try:
                await bot.handle_message("你在干嘛")
            finally:
                await bot.close()

        prompt = model.calls[-1]["system_prompt"]
        self.assertIn("[当前时间一致性约束]", prompt)
        self.assertIn("当前真实时刻：2026-05-09 12:01（周六，中午）", prompt)
        self.assertIn("不要说今天晚饭、晚饭后、夜宵、睡前或晚上活动已经发生", prompt)

    async def test_memory_generation_hides_future_evening_life_events_at_noon(self):
        model = CaptureChatModel("还没到晚上。")
        with TemporaryDirectory(prefix="bot-future-life-event-") as td:
            root = Path(td)
            bot_id = "style_bot"
            _write_test_persona(root, bot_id)
            bot = BotInstance(
                {"id": bot_id, "name": "测试 Bot", "data_dir": str(root)},
                model=model,
                memory_config={"embedding": "none"},
                data_dir=root,
                refusal_enabled=False,
            )
            bot._initialized = True
            bot._schedulers_started = True
            bot.life_engine.get_status = lambda: {
                "current_date": "2026-05-09",
                "day_of_week": "周六",
                "local_time": "12:01",
                "time_of_day": "中午",
                "current_datetime_text": "2026-05-09 12:01（周六，中午）",
                "recent_life_events": [
                    {
                        "description": "2026-05-09 晚饭后去小区快走了3公里，刚开始不想动，走完反而清醒不少。",
                        "scenario_key": "night_walk",
                    }
                ],
            }
            await bot.memory.init()

            try:
                await bot.handle_message("你刚吃完晚饭了吗")
            finally:
                await bot.close()

        prompt = model.calls[-1]["system_prompt"]
        self.assertIn("[当前时间一致性约束]", prompt)
        self.assertIn("不要说今天晚饭、晚饭后、夜宵、睡前或晚上活动已经发生", prompt)
        self.assertNotIn("晚饭后去小区快走", prompt)


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


class BotInstanceDocumentContextTest(unittest.IsolatedAsyncioTestCase):
    async def test_document_without_instruction_asks_how_to_handle_it(self):
        class DocumentCaptureModel:
            provider = "test"
            model = "document-capture"

            def __init__(self):
                self.system_prompts = []

            async def chat(self, messages, system_prompt="", **kwargs):
                if isinstance(system_prompt, str):
                    self.system_prompts.append(system_prompt)
                return "不应该调用模型"

        with TemporaryDirectory(prefix="bot-doc-context-") as td:
            root = Path(td)
            doc_path = root / "report.txt"
            first = "FIRST_CHUNK_MARKER " + ("一" * 6500)
            second = "SECOND_CHUNK_MARKER " + ("二" * 6500)
            doc_path.write_text(first + "\n\n" + second, encoding="utf-8")

            model = DocumentCaptureModel()
            bot = BotInstance(
                {"id": "shen_nian", "name": "测试 Bot"},
                model=model,
                memory_config=None,
                refusal_enabled=False,
            )
            bot._initialized = True
            bot._schedulers_started = True

            try:
                first_response = await bot.handle_message(
                    "",
                    memory_turn_context={
                        "platform": "weixin",
                        "session_id": "gw_doc",
                        "user_id": "default_user",
                        "media_urls": [str(doc_path)],
                        "media_types": ["text/plain"],
                    },
                )
            finally:
                await bot.close()

        self.assertIn("我收到 report.txt 了", first_response)
        self.assertIn("等你说要怎么处理", first_response)
        self.assertEqual(model.system_prompts, [])
        self.assertEqual(bot.conversation_history[0]["content"], "[用户发送了一份文档]")

    async def test_document_waiting_state_is_persisted_to_memory(self):
        class DocumentCaptureModel:
            provider = "test"
            model = "document-memory-capture"

            async def chat(self, messages, system_prompt="", **kwargs):
                text = messages[-1].get("content", "") if messages else ""
                if "输出一个 JSON 对象" in text:
                    return '{"facts": [], "episodes": [], "relationship": {}, "open_threads": []}'
                return "我看到了许知行和林若棠。"

        with TemporaryDirectory(prefix="bot-doc-memory-") as td:
            root = Path(td)
            bot_id = "doc_memory_bot"
            _write_test_persona(root, bot_id)
            doc_path = root / "review.txt"
            doc_path.write_text(
                "《把海吹向从前》读后感\n许知行在文中遇见了林若棠，这段关系很重要。",
                encoding="utf-8",
            )

            bot = BotInstance(
                {"id": bot_id, "name": "测试 Bot", "data_dir": str(root)},
                model=DocumentCaptureModel(),
                memory_config={"embedding": "none"},
                data_dir=root,
                refusal_enabled=False,
            )
            bot._initialized = True
            bot._schedulers_started = True
            await bot.memory.init()

            try:
                await bot.handle_message(
                    "",
                    memory_turn_context={
                        "platform": "weixin",
                        "session_id": "gw_doc_memory",
                        "user_id": "default_user",
                        "media_urls": [str(doc_path)],
                        "media_types": ["text/plain"],
                    },
                )
                history = bot.memory.working.get_recent("gw_doc_memory", turns=1)
            finally:
                await bot.close()

        user_messages = [item["content"] for item in history if item["role"] == "user"]
        self.assertEqual(len(user_messages), 1)
        self.assertIn("[用户发送了一份文档，等待处理指令]", user_messages[0])

    async def test_document_followup_persists_user_question_with_excerpt(self):
        class DocumentCaptureModel:
            provider = "test"
            model = "document-followup-memory-capture"

            async def chat(self, messages, system_prompt="", **kwargs):
                return "我看到了。"

        with TemporaryDirectory(prefix="bot-doc-followup-memory-") as td:
            root = Path(td)
            bot_id = "doc_followup_memory_bot"
            _write_test_persona(root, bot_id)
            doc_path = root / "review.txt"
            doc_path.write_text(
                "FIRST_CHUNK_MARKER 许知行\n\n" + "A" * 6500,
                encoding="utf-8",
            )

            bot = BotInstance(
                {"id": bot_id, "name": "测试 Bot", "data_dir": str(root)},
                model=DocumentCaptureModel(),
                memory_config={"embedding": "none"},
                data_dir=root,
                refusal_enabled=False,
            )
            bot._initialized = True
            bot._schedulers_started = True
            await bot.memory.init()

            try:
                await bot.handle_message(
                    "",
                    memory_turn_context={
                        "platform": "weixin",
                        "session_id": "gw_doc_followup_memory",
                        "user_id": "default_user",
                        "media_urls": [str(doc_path)],
                        "media_types": ["text/plain"],
                    },
                )
                await bot.handle_message(
                    "你说说文档里的人名",
                    memory_turn_context={
                        "platform": "weixin",
                        "session_id": "gw_doc_followup_memory",
                        "user_id": "default_user",
                    },
                )
                history = bot.memory.working.get_recent("gw_doc_followup_memory", turns=2)
            finally:
                await bot.close()

        user_messages = [item["content"] for item in history if item["role"] == "user"]
        self.assertTrue(any("你说说文档里的人名" in item and "[关联文档摘录]" in item for item in user_messages))
        self.assertTrue(any("FIRST_CHUNK_MARKER" in item and "许知行" in item for item in user_messages))

    async def test_document_followup_injects_pending_document_for_instruction(self):
        class DocumentCaptureModel:
            provider = "test"
            model = "document-followup-capture"

            def __init__(self):
                self.system_prompts = []

            async def chat(self, messages, system_prompt="", **kwargs):
                if isinstance(system_prompt, str):
                    self.system_prompts.append(system_prompt)
                return "我再看一眼。"

        with TemporaryDirectory(prefix="bot-doc-followup-") as td:
            root = Path(td)
            doc_path = root / "review.txt"
            doc_path.write_text(
                "FIRST_CHUNK_MARKER 许知行\n\n" + "A" * 6500,
                encoding="utf-8",
            )

            model = DocumentCaptureModel()
            bot = BotInstance(
                {"id": "shen_nian", "name": "测试 Bot"},
                model=model,
                memory_config=None,
                refusal_enabled=False,
            )
            bot._initialized = True
            bot._schedulers_started = True

            try:
                await bot.handle_message(
                    "",
                    memory_turn_context={
                        "platform": "weixin",
                        "session_id": "gw_doc_followup",
                        "user_id": "default_user",
                        "media_urls": [str(doc_path)],
                        "media_types": ["text/plain"],
                    },
                )
                await bot.handle_message(
                    "你说说文档里的人名",
                    memory_turn_context={
                        "platform": "weixin",
                        "session_id": "gw_doc_followup",
                        "user_id": "default_user",
                    },
                )
            finally:
                await bot.close()

        document_prompts = [
            prompt for prompt in model.system_prompts if "[用户已发送文档，以下内容供本轮任务使用]" in prompt
        ]
        self.assertEqual(len(document_prompts), 1)
        self.assertIn("FIRST_CHUNK_MARKER", document_prompts[0])
        self.assertIn("许知行", document_prompts[0])

    async def test_document_followup_can_jump_to_requested_chapter(self):
        class DocumentCaptureModel:
            provider = "test"
            model = "document-chapter-capture"

            def __init__(self):
                self.system_prompts = []

            async def chat(self, messages, system_prompt="", **kwargs):
                if isinstance(system_prompt, str):
                    self.system_prompts.append(system_prompt)
                return "我看第十五章。"

        with TemporaryDirectory(prefix="bot-doc-chapter-") as td:
            root = Path(td)
            doc_path = root / "book.txt"
            chapters = []
            for idx in range(1, 18):
                marker = "TARGET_CHAPTER_15" if idx == 15 else f"CHAPTER_{idx}"
                chapters.append(f"第{idx}章\n{marker}\n" + (f"正文{idx}" * 80))
            doc_path.write_text("\n\n".join(chapters), encoding="utf-8")

            model = DocumentCaptureModel()
            bot = BotInstance(
                {"id": "shen_nian", "name": "测试 Bot"},
                model=model,
                memory_config=None,
                refusal_enabled=False,
            )
            bot._initialized = True
            bot._schedulers_started = True

            try:
                await bot.handle_message(
                    "",
                    memory_turn_context={
                        "platform": "weixin",
                        "session_id": "gw_doc_chapter",
                        "user_id": "default_user",
                        "media_urls": [str(doc_path)],
                        "media_types": ["text/plain"],
                    },
                )
                await bot.handle_message(
                    "从15章开始看",
                    memory_turn_context={
                        "platform": "weixin",
                        "session_id": "gw_doc_chapter",
                        "user_id": "default_user",
                    },
                )
            finally:
                await bot.close()

        document_prompts = [
            prompt for prompt in model.system_prompts if "[用户已发送文档，以下内容供本轮任务使用]" in prompt
        ]
        self.assertEqual(len(document_prompts), 1)
        self.assertIn("已定位到 第15章", document_prompts[0])
        self.assertIn("TARGET_CHAPTER_15", document_prompts[0])
        self.assertNotIn("CHAPTER_1\n", document_prompts[0])


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
                                "auto": True,
                                "provider": "openai",
                                "base_url": "https://example.com/v1",
                                "model": "gpt-image-1",
                                "api_key": "real-image-key",
                                "output_dir": "data/bots/_images",
                            },
                            "image_understanding": {
                                "enabled": True,
                                "auto": True,
                                "model": "openai",
                                "openai": {
                                    "base_url": "https://vision.example.com/v1",
                                    "model": "gpt-4o",
                                    "api_key": "nested-vision-key",
                                },
                                "max_image_size_mb": 8,
                                "max_images_per_message": 3,
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (cfg.config_dir / "bots.yaml").write_text("bots: []\n", encoding="utf-8")
            service = ConfigAdminService(cfg)

            public = service._public_skills(
                "shen_nian",
                {
                    "skills": {
                        "image_generation": {
                            "enabled": True,
                            "auto": True,
                            "provider": "openai",
                            "api_key": "real-image-key",
                            "output_dir": "data/bots/_images",
                        },
                        "image_understanding": {
                            "model": "openai",
                            "openai": {
                                "base_url": "https://vision.example.com/v1",
                                "model": "gpt-4o",
                                "api_key": "nested-vision-key",
                            },
                            "max_image_size_mb": 8,
                            "max_images_per_message": 3,
                        },
                    }
                },
            )
            self.assertEqual(public["global"]["image_generation"]["api_key"], "real...-key")
            self.assertEqual(public["global"]["image_generation"]["base_url"], "https://api.openai.com/v1")
            self.assertNotIn("enabled", public["global"]["image_generation"])
            self.assertNotIn("auto", public["global"]["image_generation"])
            self.assertNotIn("output_dir", public["global"]["image_generation"])
            self.assertEqual(public["global"]["image_understanding"]["base_url"], "https://vision.example.com/v1")
            self.assertEqual(public["global"]["image_understanding"]["api_key"], "nest...-key")
            self.assertNotIn("openai", public["global"]["image_understanding"])
            self.assertNotIn("max_image_size_mb", public["global"]["image_understanding"])

            service._save_skills(
                "shen_nian",
                {
                    "global": {
                        "image_generation": {
                            "enabled": True,
                            "base_url": "https://example.com/v1",
                            "model": "gpt-image-1",
                            "api_key": MASKED_SECRET,
                            "output_dir": "data/bots/_images",
                        },
                        "image_understanding": {
                            "base_url": "https://vision.example.com/v1",
                            "model": "gpt-4o",
                            "api_key": MASKED_SECRET,
                            "max_image_size_mb": 8,
                        }
                    },
                    "bot": {},
                },
            )
            saved = yaml.safe_load((cfg.config_dir / "models.yaml").read_text(encoding="utf-8"))
            self.assertEqual(
                saved["skills"]["image_generation"],
                {
                    "base_url": "https://example.com/v1",
                    "model": "gpt-image-1",
                    "api_key": "real-image-key",
                },
            )
            self.assertEqual(
                saved["skills"]["image_understanding"],
                {
                    "base_url": "https://vision.example.com/v1",
                    "model": "gpt-4o",
                    "api_key": "nested-vision-key",
                },
            )

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
