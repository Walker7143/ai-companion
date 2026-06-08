import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_companion.memory.retriever import RetrievedMemory
from ai_companion.proactive.config import ProactiveConfig
from ai_companion.proactive.engine import ProactiveEngine
from ai_companion.proactive.life_config import LifeConfig
from ai_companion.proactive.life_engine import LifeEngine
from ai_companion.proactive.life_state import LifeEvent, LifeState
from ai_companion.proactive.state import ProactiveState


class StaticModel:
    provider = "test"
    model = "static-model"

    def __init__(self, response: str):
        self.response = response

    async def chat(self, messages, system_prompt="", **kwargs):
        return self.response


class CaptureModel:
    provider = "test"
    model = "capture-model"

    def __init__(self, response: str):
        self.response = response
        self.calls = []

    async def chat(self, messages, system_prompt="", **kwargs):
        self.calls.append({"messages": messages, "system_prompt": system_prompt, "kwargs": kwargs})
        return self.response


class SequenceModel:
    provider = "test"
    model = "sequence-model"

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls = []

    async def chat(self, messages, system_prompt="", **kwargs):
        self.calls.append({"messages": messages, "system_prompt": system_prompt, "kwargs": kwargs})
        if not self.responses:
            return ""
        return self.responses.pop(0)


def _build_engine(root: Path, response: str) -> ProactiveEngine:
    persona_dir = root / "persona"
    persona_dir.mkdir(parents=True, exist_ok=True)

    config = ProactiveConfig(persona_dir)
    state = ProactiveState("test_bot", root / "runtime")
    state.last_message_time = datetime.now()

    engine = ProactiveEngine(
        bot_id="test_bot",
        config=config,
        state=state,
        model=StaticModel(response),
        memory=None,
        personality_type="温柔",
    )
    engine.bot_name = "测试 Bot"
    return engine


class ProactiveEnginePlaceholderTest(unittest.IsolatedAsyncioTestCase):
    def test_parse_structured_message_rejects_placeholder_parts(self):
        with TemporaryDirectory(prefix="proactive-placeholder-") as td:
            engine = _build_engine(Path(td), "")
            parsed = engine._parse_structured_message(
                '{"opening":"开场白/称呼","topic":"话题内容或空字符串","ending":"结尾语"}'
            )
            self.assertIsNone(parsed)

    def test_parse_structured_message_rejects_contextual_placeholder_parts(self):
        with TemporaryDirectory(prefix="proactive-placeholder-") as td:
            engine = _build_engine(Path(td), "")
            parsed = engine._parse_structured_message(
                '{"opening":"开头","topic":"主体","ending":"结尾"}'
            )
            self.assertIsNone(parsed)

    def test_classify_generated_message_issue(self):
        with TemporaryDirectory(prefix="proactive-placeholder-") as td:
            engine = _build_engine(Path(td), "")
            self.assertEqual(engine._classify_generated_message_issue(""), "empty")
            self.assertEqual(engine._classify_generated_message_issue("开头，主体，结尾"), "placeholder")
            self.assertEqual(engine._classify_generated_message_issue("对了，我突然想起..."), "incomplete_fragment")
            self.assertEqual(engine._classify_generated_message_issue("对了，昨天..."), "incomplete_fragment")
            self.assertEqual(
                engine._classify_generated_message_issue('{"opening":"喂","topic":"test","ending":"来"}'),
                "raw_json",
            )
            self.assertIsNone(engine._classify_generated_message_issue("今天风有点大，突然想起你了。"))

    def test_quality_gate_flags_thin_content(self):
        with TemporaryDirectory(prefix="proactive-thin-quality-") as td:
            engine = _build_engine(Path(td), "")
            self.assertEqual(engine._classify_quality_gate_issue("想起个事。", anchor=None), "thin_content")
            self.assertEqual(engine._classify_quality_gate_issue("有件事。", anchor=None), "thin_content")
            self.assertIsNone(
                engine._classify_quality_gate_issue("刚才想到你了，就顺手来一句。", anchor=None)
            )

    def test_classify_partial_structured_parse_failure(self):
        with TemporaryDirectory(prefix="proactive-placeholder-") as td:
            engine = _build_engine(Path(td), "")
            self.assertEqual(
                engine._classify_partial_structured_parse_failure(
                    '{"opening":"喂","topic":"这天气真够呛""ending":"你倒是快点来"}'
                ),
                "broken_partial_json",
            )
            self.assertEqual(
                engine._classify_partial_structured_parse_failure(
                    '{"opening": "喂", "topic": "这天气真够呛", "ending": "你倒是快点来'
                ),
                "partial_json",
            )

    def test_parse_structured_message_keeps_valid_parts(self):
        with TemporaryDirectory(prefix="proactive-placeholder-") as td:
            engine = _build_engine(Path(td), "")
            parsed = engine._parse_structured_message(
                '{"opening":"开场白/称呼","topic":"今天路上看到很美的晚霞","ending":"结尾语"}'
            )
            self.assertEqual(parsed, "今天路上看到很美的晚霞")

    def test_parse_structured_message_recovers_truncated_json(self):
        with TemporaryDirectory(prefix="proactive-truncated-") as td:
            engine = _build_engine(Path(td), "")
            parsed = engine._parse_structured_message(
                '{"opening": "喂", "topic": "这天气真够呛，害我连客栈门都懒得出。", "ending": "你倒是快点来'
            )
            self.assertEqual(parsed, "喂，这天气真够呛，害我连客栈门都懒得出。你倒是快点来")

    async def test_send_proactive_message_normalizes_structured_payload(self):
        with TemporaryDirectory(prefix="proactive-send-normalize-") as td:
            engine = _build_engine(Path(td), "")
            sent_messages = []

            async def sender(message: str):
                sent_messages.append(message)
                return True

            engine._platform_sender = sender
            sent = await engine._send_proactive_message(
                '{"opening": "喂", "topic": "这天气真够呛，害我连客栈门都懒得出。", "ending": "你倒是快点来'
            )

            self.assertTrue(sent)
            self.assertEqual(sent_messages, ["喂，这天气真够呛，害我连客栈门都懒得出。你倒是快点来"])
            self.assertNotIn('"opening"', sent_messages[0])
            self.assertNotIn('"topic"', sent_messages[0])

    async def test_send_proactive_message_falls_back_on_plain_placeholder_message(self):
        with TemporaryDirectory(prefix="proactive-send-placeholder-") as td:
            engine = _build_engine(Path(td), "")
            sent_messages = []

            async def sender(message: str):
                sent_messages.append(message)
                return True

            engine._platform_sender = sender
            sent = await engine._send_proactive_message("开头，主体，结尾")

            self.assertTrue(sent)
            self.assertEqual(len(sent_messages), 1)
            self.assertIn(sent_messages[0], ["对了，刚才有件小事想跟你分享。", "有件事想跟你分享～", "今天有个小瞬间，突然很想讲给你听。"])
            self.assertNotIn("开头", sent_messages[0])
            self.assertNotIn("主体", sent_messages[0])
            self.assertNotIn("结尾", sent_messages[0])

    def test_fallback_message_skips_incomplete_fragments(self):
        with TemporaryDirectory(prefix="proactive-fallback-fragments-") as td:
            engine = _build_engine(Path(td), "")
            engine.personality_type = "傲娇"

            message = engine._get_fallback_message("with_topic")

            self.assertEqual(message, "对了，我刚才突然想起一件小事，想顺手跟你说一下。")
            self.assertNotEqual(message, "对了，我突然想起...")

    def test_fallback_message_avoids_reply_tone_for_proactive_opening(self):
        with TemporaryDirectory(prefix="proactive-fallback-reply-tone-") as td:
            engine = _build_engine(Path(td), "")
            engine.personality_type = "傲娇"

            default_message = engine._get_fallback_message("default")
            long_gap_message = engine._get_fallback_message("long_no_reply")
            short_gap_message = engine._get_fallback_message("short_no_reply")

            for message in (default_message, long_gap_message, short_gap_message):
                self.assertNotIn("忘了我", message)
                self.assertNotIn("不理我", message)
                self.assertNotIn("总算想起我了", message)
                self.assertNotIn("终于想起我了", message)

    def test_high_cold_fallback_message_avoids_thin_content(self):
        with TemporaryDirectory(prefix="proactive-fallback-thin-content-") as td:
            engine = _build_engine(Path(td), "")
            engine.personality_type = "高冷"

            default_message = engine._get_fallback_message("default")
            topic_message = engine._get_fallback_message("with_topic")

            for message in (default_message, topic_message):
                self.assertNotEqual(message, "想起个事。")
                self.assertNotEqual(message, "有件事。")
                self.assertNotEqual(message, "跟你说下。")
                self.assertNotEqual(message, "听好了。")

    def test_fallback_prefers_recent_scene_when_available(self):
        class WorkingStub:
            current_session = None

            def list_sessions(self, limit=1):
                return [{"session_id": "gw-scene"}]

            def get_recent(self, session_id=None, turns=6, include_proactive=True):
                rows = [
                    {"role": "assistant", "content": "你先去吃饭，别又拖到太晚。"},
                    {"role": "user", "content": "我刚点了盖饭，等会就吃。"},
                ]
                if include_proactive:
                    return rows
                return rows

        class UnderstandingStub:
            def format_for_prompt(self):
                return ""

            def known_fact_keys(self):
                return set()

        class SemanticStub:
            async def get_all_facts(self, **kwargs):
                return {}

        class MemoryStub:
            _session_id = None
            bot_id = "test_bot"
            user_id = "default_user"
            working = WorkingStub()
            user_understanding = UnderstandingStub()
            semantic = SemanticStub()

        with TemporaryDirectory(prefix="proactive-fallback-scene-") as td:
            root = Path(td)
            persona_dir = root / "persona"
            persona_dir.mkdir(parents=True, exist_ok=True)
            engine = ProactiveEngine(
                bot_id="test_bot",
                config=ProactiveConfig(persona_dir),
                state=ProactiveState("test_bot", root / "runtime"),
                model=None,
                memory=MemoryStub(),
                personality_type="温柔",
            )

            message = engine._get_fallback_message("default")

            self.assertIn("冒个泡", message)
            self.assertTrue("等那份盖饭" in message or "忙这个" in message or "刚才看你还在" in message)
            self.assertNotEqual(message, "刚刚想起你，来问一声。")

    async def test_send_proactive_message_regenerates_invalid_message_before_send(self):
        with TemporaryDirectory(prefix="proactive-send-regenerate-") as td:
            root = Path(td)
            persona = root / "persona"
            persona.mkdir()
            model = SequenceModel(['{"message":"刚才突然想到你，就过来碰一下你的窗口。"}'])
            engine = ProactiveEngine(
                bot_id="test_bot",
                config=ProactiveConfig(persona),
                state=ProactiveState("test_bot", root / "runtime"),
                model=model,
                memory=None,
                personality_type="温柔",
            )
            sent_messages = []

            async def sender(message: str):
                sent_messages.append(message)
                return True

            engine._platform_sender = sender
            sent = await engine._send_proactive_message("开头，主体，结尾")

            self.assertTrue(sent)
            self.assertEqual(sent_messages, ["刚才突然想到你，就过来碰一下你的窗口。"])
            self.assertEqual(len(model.calls), 1)

    async def test_generate_message_falls_back_when_model_returns_placeholder_text(self):
        with TemporaryDirectory(prefix="proactive-placeholder-") as td:
            engine = _build_engine(Path(td), "《开场白/称呼，话题内容或空字符串，结尾语》")
            message = await engine.generate_message("测试占位文本回退")
            self.assertEqual(message, "刚刚想起你，来问一声。")
            self.assertNotIn("开场白/称呼", message)
            self.assertNotIn("话题内容或空字符串", message)
            self.assertNotIn("结尾语", message)
            self.assertNotIn("在吗", message)
            self.assertNotIn("最近怎么样", message)

    async def test_generate_message_regenerates_before_template_fallback(self):
        with TemporaryDirectory(prefix="proactive-regenerate-") as td:
            root = Path(td)
            persona = root / "persona"
            persona.mkdir()
            model = SequenceModel(
                [
                    "《开场白/称呼，话题内容或空字符串，结尾语》",
                    '{"message":"刚才路过窗边忽然想起你，顺手戳一下。"}',
                ]
            )
            engine = ProactiveEngine(
                bot_id="test_bot",
                config=ProactiveConfig(persona),
                state=ProactiveState("test_bot", root / "runtime"),
                model=model,
                personality_type="温柔",
            )

            message = await engine.generate_message("想主动联系一下")

            self.assertEqual(message, "刚才路过窗边忽然想起你，顺手戳一下。")
            self.assertEqual(len(model.calls), 2)
            retry_prompt = model.calls[-1]["messages"][-1]["content"]
            self.assertIn("重新写一条全新的主动消息", retry_prompt)
            self.assertIn("不要使用固定模板", retry_prompt)
            self.assertIn("这是你主动发起的一条消息", retry_prompt)
            self.assertIn("不要重写成“总算想起我了”", retry_prompt)

    async def test_generate_message_falls_back_when_model_returns_unparsed_structured_payload(self):
        with TemporaryDirectory(prefix="proactive-structured-fallback-") as td:
            engine = _build_engine(
                Path(td),
                '{"opening":"喂","topic":"这天气真够呛""ending":"你倒是快点来"}',
            )
            message = await engine.generate_message("测试未解析结构回退")
            self.assertEqual(message, "刚刚想起你，来问一声。")
            self.assertNotIn('"opening"', message)
            self.assertNotIn('"topic"', message)
            self.assertNotIn('"ending"', message)

    async def test_generate_message_prompt_marks_proactive_opening_not_reply(self):
        with TemporaryDirectory(prefix="proactive-origin-guard-") as td:
            root = Path(td)
            persona = root / "persona"
            persona.mkdir()
            model = CaptureModel('{"message":"刚才想到你了，就顺手来找你。"}')
            engine = ProactiveEngine(
                bot_id="test_bot",
                config=ProactiveConfig(persona),
                state=ProactiveState("test_bot", root / "runtime"),
                model=model,
                personality_type="温柔",
            )

            await engine.generate_message("想主动联系一下")

            prompt = model.calls[-1]["messages"][-1]["content"]
            self.assertIn("这是你主动发起的一条消息", prompt)
            self.assertIn("不要写成“总算想起我了”", prompt)

    async def test_idle_ping_prompt_formats_question_rule(self):
        with TemporaryDirectory(prefix="proactive-idle-ping-prompt-") as td:
            root = Path(td)
            persona = root / "persona"
            persona.mkdir()
            model = CaptureModel('{"message":"刚才想到你了，就来冒个泡。"}')
            engine = ProactiveEngine(
                bot_id="test_bot",
                config=ProactiveConfig(persona),
                state=ProactiveState("test_bot", root / "runtime"),
                model=model,
                personality_type="温柔",
            )

            await engine.generate_message("想轻轻冒个泡", motive_type="idle_ping")

            prompt = model.calls[-1]["messages"][-1]["content"]
            self.assertIn("可以用自然问句收尾，但不能是盘问式。", prompt)
            self.assertNotIn("if allow_question else", prompt)

    def test_fallback_rotation_persists_across_state_reload(self):
        with TemporaryDirectory(prefix="proactive-fallback-rotation-") as td:
            root = Path(td)
            persona_dir = root / "persona"
            persona_dir.mkdir(parents=True, exist_ok=True)

            state = ProactiveState("test_bot", root / "runtime")
            engine = ProactiveEngine(
                bot_id="test_bot",
                config=ProactiveConfig(persona_dir),
                state=state,
                model=None,
                memory=None,
                personality_type="温柔",
            )

            first = engine._get_fallback_message("default")
            reloaded_state = ProactiveState("test_bot", root / "runtime")
            reloaded_engine = ProactiveEngine(
                bot_id="test_bot",
                config=ProactiveConfig(persona_dir),
                state=reloaded_state,
                model=None,
                memory=None,
                personality_type="温柔",
            )
            second = reloaded_engine._get_fallback_message("default")

            self.assertEqual(first, "刚刚想起你，来问一声。")
            self.assertNotEqual(second, first)
            self.assertNotIn("在吗", second)
            self.assertNotIn("最近怎么样", second)
            self.assertNotIn("总算想起我了", second)
            self.assertEqual(reloaded_state.last_opening_style, second)

    async def test_generate_contextual_message_falls_back_when_model_returns_schema_text(self):
        from ai_companion.proactive.motives import ProactiveMotive, ProactiveMotiveType

        with TemporaryDirectory(prefix="proactive-placeholder-") as td:
            engine = _build_engine(Path(td), '{"opening":"开头","topic":"主体","ending":"结尾"}')
            motive = ProactiveMotive(
                type=ProactiveMotiveType.LIFE_EVENT,
                priority=60,
                reason="想分享最近发生的事",
                prompt_context="Bot 最近发生了一件事想分享：测试",
            )
            message = await engine.generate_contextual_message(motive)
            self.assertIsInstance(message, str)
            self.assertNotIn('"opening"', message)
            self.assertNotIn("开头", message)
            self.assertNotIn("主体", message)
            self.assertNotIn("结尾", message)


class ProactiveEngineContextualMessageTest(unittest.IsolatedAsyncioTestCase):
    async def test_structured_message_accepts_direct_message_field(self):
        with TemporaryDirectory(prefix="proactive-direct-message-") as td:
            engine = _build_engine(
                Path(td),
                '{"message":"你这人真没劲，我今天排队买咖啡差点被风吹成傻子。"}',
            )

            message = engine._parse_structured_message(
                '{"message":"你这人真没劲，我今天排队买咖啡差点被风吹成傻子。"}'
            )

            self.assertEqual(message, "你这人真没劲，我今天排队买咖啡差点被风吹成傻子。")

    async def test_contextual_life_event_prompt_includes_persona_style(self):
        from ai_companion.proactive.motives import ProactiveMotive, ProactiveMotiveType

        with TemporaryDirectory(prefix="proactive-persona-style-") as td:
            root = Path(td)
            persona = root / "persona"
            persona.mkdir()
            (persona / "profile.json").write_text(
                '{"name":"杨思思","personality_tags":["嘴硬","带刺"]}',
                encoding="utf-8",
            )
            (persona / "speaking_style.json").write_text(
                '{"tone":"直白、鲜活、嘴上带刺，喜欢反问和吐槽","口头禅":["你这人真没劲"],"special_expressions":["会把关心伪装成抱怨"]}',
                encoding="utf-8",
            )
            (persona / "conversation_style_rules.json").write_text(
                '{"natural_patterns":["可以用反问、停顿、轻微吐槽"],"reply_principles":["日常聊天可以短一点，有停顿和个人反应"],"avoid_phrases":["作为AI","我理解你的感受"]}',
                encoding="utf-8",
            )
            model = CaptureModel('{"message":"你这人真没劲，我今天真是被咖啡外卖气笑了。"}')
            engine = ProactiveEngine(
                bot_id="yangsisi",
                config=ProactiveConfig(persona),
                state=ProactiveState("yangsisi", root / "runtime"),
                model=model,
            )
            motive = ProactiveMotive(
                type=ProactiveMotiveType.LIFE_EVENT,
                priority=60,
                reason="想把今天发生的一件小事随手讲给对方听",
                prompt_context="你准备主动发一条日常小事。\n这件事是你自己刚经历的，不要说成 Bot 状态：咖啡外卖洒了。",
            )

            message = await engine.generate_contextual_message(motive)

            prompt = model.calls[-1]["messages"][-1]["content"]
            self.assertIn("直白、鲜活、嘴上带刺", prompt)
            self.assertIn("你这人真没劲", prompt)
            self.assertIn("可以用反问、停顿、轻微吐槽", prompt)
            self.assertIn("重要：你是一个真实的人，不是 AI。请像真实的人一样说话。", prompt)
            self.assertIn("不要写成状态播报", prompt)
            self.assertIn("你这人真没劲", message)

    def test_personality_type_detects_yang_sisi_tags_as_tsun(self):
        with TemporaryDirectory(prefix="proactive-personality-tags-") as td:
            root = Path(td)
            persona = root / "persona"
            persona.mkdir()
            (persona / "profile.json").write_text(
                '{"personality_tags":["嘴硬心软","直白毒舌","敢爱敢恨"]}',
                encoding="utf-8",
            )
            engine = ProactiveEngine(
                bot_id="yangsisi",
                config=ProactiveConfig(persona),
                state=ProactiveState("yangsisi", root / "runtime"),
                model=None,
            )

            self.assertEqual(engine._get_personality_type(), "傲娇")

    async def test_build_context_uses_latest_session_and_preserves_recent_message_tail(self):
        class Working:
            current_session = None

            def __init__(self):
                self.requested_session_id = None

            def list_sessions(self, limit=1):
                return [{"session_id": "gw_latest"}]

            def get_recent(self, session_id=None, turns=3):
                self.requested_session_id = session_id
                return [
                    {
                        "role": "assistant",
                        "content": (
                            "（看了眼时间）" + "她把前面的闲聊铺垫说得很长。" * 12
                            + "行了，你的黄焖鸡该到了吧？快去吃饭，别凉了。"
                        ),
                    },
                    {"role": "user", "content": "好，嘿嘿，真乖"},
                    {"role": "assistant", "content": "……这下满意了吧？"},
                    {"role": "user", "content": "又吃牛肉粉，你除了饵丝就是牛肉粉，吃点别的"},
                ]

        class UserUnderstanding:
            def format_for_prompt(self):
                return ""

            def known_fact_keys(self):
                return set()

        class Semantic:
            async def get_all_facts(self, **kwargs):
                return {}

        class Memory:
            _session_id = None

            def __init__(self):
                self.working = Working()
                self.user_understanding = UserUnderstanding()
                self.semantic = Semantic()
                self.bot_id = "yangsisi"
                self.user_id = "default_user"

        with TemporaryDirectory(prefix="proactive-recent-context-") as td:
            root = Path(td)
            persona = root / "persona"
            persona.mkdir()
            memory = Memory()
            engine = ProactiveEngine(
                bot_id="yangsisi",
                config=ProactiveConfig(persona),
                state=ProactiveState("yangsisi", root / "runtime"),
                model=None,
                memory=memory,
            )

            context = await engine._build_context()

            self.assertEqual(memory.working.requested_session_id, "gw_latest")
            self.assertIn("黄焖鸡该到了吧", context)
            self.assertIn("又吃牛肉粉", context)

    async def test_contextual_message_prompt_includes_motive_and_prior_topic(self):
        from ai_companion.proactive.motives import ProactiveMotive, ProactiveMotiveType

        with TemporaryDirectory(prefix="proactive-contextual-") as td:
            root = Path(td)
            persona = root / "persona"
            persona.mkdir()
            model = CaptureModel(
                '{"opening":"刚才你问的那个问题","topic":"我想了一下，可以先从小范围试试","ending":"你觉得呢？"}'
            )
            engine = ProactiveEngine(
                bot_id="context_bot",
                config=ProactiveConfig(persona),
                state=ProactiveState("context_bot", root / "runtime"),
                model=model,
            )
            motive = ProactiveMotive(
                type=ProactiveMotiveType.DEFERRED_REPLY,
                priority=100,
                reason="继续刚才承诺的回复",
                prompt_context="用户问：那你怎么看？\nBot 之前说：我想一下，一会儿回复你",
                bypass_idle_threshold=True,
            )
            message = await engine.generate_contextual_message(motive)

            prompt = model.calls[-1]["messages"][-1]["content"]
            self.assertIn("继续刚才承诺的回复", prompt)
            self.assertIn("那你怎么看", prompt)
            self.assertIn("不要像重新开一个话题", prompt)
            self.assertIn("刚才你问的那个问题", message)
    async def test_contextual_message_prompt_includes_proactive_memory_layers(self):
        from ai_companion.proactive.motives import ProactiveMotive, ProactiveMotiveType

        with TemporaryDirectory(prefix="proactive-memory-layers-") as td:
            root = Path(td)
            persona = root / "persona"
            persona.mkdir()
            model = CaptureModel('{"message":"我刚才看到你提过的事，想接着说两句。"}')
            engine = ProactiveEngine(
                bot_id="context_bot",
                config=ProactiveConfig(persona),
                state=ProactiveState("context_bot", root / "runtime"),
                model=model,
            )

            class WorkingStub:
                def get_recent(self, *args, **kwargs):
                    return []

            class DailyStub:
                def get_recent_context(self, **kwargs):
                    return {
                        "today": "今天用户在处理面试和复盘",
                        "open_threads": ["面试后复盘"],
                        "commitments": ["晚上回来复盘"],
                        "mood": ["有点紧张"],
                    }

            class RelationshipStub:
                async def get_state(self, **kwargs):
                    return {
                        "relationship_label": "好朋友",
                        "current_posture": "先接住情绪，再继续聊",
                        "interaction_guidance": "关系紧张时先放慢、承认感受、少解释。",
                        "relationship_narrative": "先放慢，先接住情绪。",
                        "open_emotional_threads": ["上次那个话题还没说完"],
                    }

            class UnderstandingStub:
                def load(self):
                    return {
                        "layered": {
                            "current": {
                                "current_context": ["最近在准备面试"],
                                "open_threads": ["面试后复盘"],
                                "goals_and_projects": ["整理作品集"],
                                "recent_changes": ["最近很忙"],
                            },
                            "deep": {
                                "relationship_memory": {
                                    "what_user_seems_to_need_from_bot": ["先慢一点"],
                                    "things_that_created_tension": ["不想被追问太快"],
                                },
                            },
                        }
                    }

                def format_for_prompt(self):
                    return "最近在准备面试"

                def known_fact_keys(self):
                    return set()

            class RetrieverStub:
                async def retrieve(self, *args, **kwargs):
                    return RetrievedMemory(
                        intent="proactive_generation",
                        daily_context={"open_threads": ["面试后复盘"]},
                        relationship_state={"relationship_label": "好朋友"},
                        user_understanding={
                            "manual": {"interaction_style": {"preferred_reply_length": "短一点"}},
                        },
                    )

            class PromptBuilderStub:
                def build(self, retrieved):
                    return "【你对用户的理解】\n- 用户最近在准备面试\n使用方式：把这些当作相处背景，而不是答案清单。"

            engine.memory = type(
                "MemoryStub",
                (),
                {
                    "bot_id": "context_bot",
                    "user_id": "default_user",
                    "_session_id": "session-1",
                    "working": WorkingStub(),
                    "daily": DailyStub(),
                    "relationship": RelationshipStub(),
                    "user_understanding": UnderstandingStub(),
                    "retriever": RetrieverStub(),
                    "prompt_builder": PromptBuilderStub(),
                },
            )()
            motive = ProactiveMotive(
                type=ProactiveMotiveType.TOPIC_CONTINUATION,
                priority=100,
                reason="接上今天未完的话题",
                prompt_context="用户刚才提到面试后还想复盘一下。",
                target={
                    "message": "我们晚点再接着聊",
                    "metadata": {"source_platform": "wechat", "proactive_kind": "topic_continuation"},
                },
            )

            await engine.generate_contextual_message(motive)

            prompt = model.calls[-1]["messages"][-1]["content"]
            self.assertIn("主动动机类型：topic_continuation", prompt)
            self.assertIn("主动动机原因：接上今天未完的话题", prompt)
            self.assertIn("【今日连续性记忆】", prompt)
            self.assertIn("面试后复盘", prompt)
            self.assertIn("晚上回来复盘", prompt)
            self.assertIn("有点紧张", prompt)
            self.assertIn("【关系姿态】", prompt)
            self.assertIn("好朋友", prompt)
            self.assertIn("先接住情绪", prompt)
            self.assertIn("【长期用户理解】", prompt)
            self.assertIn("整理作品集", prompt)
            self.assertIn("不想被追问太快", prompt)
            self.assertIn("【共享记忆承接】", prompt)
            self.assertIn("【你对用户的理解】", prompt)
            self.assertIn("使用方式：把这些当作相处背景", prompt)
            self.assertIn("主动目标线索", prompt)
            self.assertIn("source_platform：wechat", prompt)

    async def test_contextual_message_polishes_ai_boilerplate(self):
        from ai_companion.proactive.motives import ProactiveMotive, ProactiveMotiveType

        with TemporaryDirectory(prefix="proactive-polish-") as td:
            root = Path(td)
            persona = root / "persona"
            persona.mkdir()
            model = CaptureModel('{"message":"作为AI，希望这能帮到你。如果你需要，我可以继续陪你聊。"}')
            engine = ProactiveEngine(
                bot_id="context_bot",
                config=ProactiveConfig(persona),
                state=ProactiveState("context_bot", root / "runtime"),
                model=model,
            )
            motive = ProactiveMotive(
                type=ProactiveMotiveType.TOPIC_CONTINUATION,
                priority=60,
                reason="接上刚才的话",
                prompt_context="用户刚才说还想继续聊。",
            )

            message = await engine.generate_contextual_message(motive)

            self.assertNotIn("作为AI", message)
            self.assertNotIn("希望这能帮到你", message)

    async def test_generate_message_prompt_includes_current_life_anchor(self):
        with TemporaryDirectory(prefix="proactive-life-anchor-") as td:
            root = Path(td)
            persona = root / "persona"
            persona.mkdir()
            model = CaptureModel('{"opening":"喂","topic":"刚在客栈门口看洱海风把招牌吹得直晃。","ending":"你忙完没"}')
            engine = ProactiveEngine(
                bot_id="yangsisi",
                config=ProactiveConfig(persona),
                state=ProactiveState("yangsisi", root / "runtime"),
                model=model,
            )
            life_state = LifeState("yangsisi", root / "life")
            life_engine = LifeEngine(
                "yangsisi",
                LifeConfig(
                    daily_life_profile={
                        "location": "在大理经营一间叫'我在风花雪月里等你'的客栈。",
                        "daily_routine": "打理客栈日常，接待住客，在洱海边散步。",
                        "living_situation": "住在大理客栈里。",
                    },
                    sync_with_local_time_when_realtime=False,
                ),
                life_state,
                model=None,
            )
            engine.set_life_engine(life_engine)

            message = await engine.generate_message("想随手发一句")

            prompt = model.calls[-1]["messages"][-1]["content"]
            self.assertIn("【统一生成合同】", prompt)
            self.assertIn("【当前生活锚点】", prompt)
            self.assertIn("大理", prompt)
            self.assertIn("客栈", prompt)
            self.assertIn("洱海", prompt)
            self.assertIn("不要把背景经历或通用职场场景写成正在发生", prompt)
            self.assertIn("客栈门口", message)

    async def test_generate_message_does_not_use_future_evening_shareable_event_at_noon(self):
        with TemporaryDirectory(prefix="proactive-future-event-") as td:
            root = Path(td)
            persona = root / "persona"
            persona.mkdir()
            model = CaptureModel('{"opening":"喂","topic":"中午这会儿还挺安静。","ending":""}')
            engine = ProactiveEngine(
                bot_id="time_bot",
                config=ProactiveConfig(persona),
                state=ProactiveState("time_bot", root / "runtime"),
                model=model,
            )
            life_state = LifeState("time_bot", root / "life")
            life_state.current_date = "2026-05-09"
            life_engine = LifeEngine(
                "time_bot",
                LifeConfig(sync_with_local_time_when_realtime=False),
                life_state,
                model=None,
            )
            life_engine._get_local_now = lambda: datetime(2026, 5, 9, 12, 1).astimezone()
            life_state.add_event(
                LifeEvent(
                    description="2026-05-09 晚饭后去小区快走了3公里，刚开始不想动，走完反而清醒不少。",
                    topic_prompt="今天强迫自己动了动，感觉状态回来一点。",
                    scenario_key="night_walk",
                    shareable=True,
                )
            )
            engine.set_life_engine(life_engine)

            await engine.generate_message("想随手发一句")

            prompt = model.calls[-1]["messages"][-1]["content"]
            self.assertIn("[当前时间一致性约束]", prompt)
            self.assertIn("不要说今天晚饭、晚饭后、夜宵或睡前活动已经发生", prompt)
            self.assertNotIn("晚饭后去小区快走", prompt)

    async def test_generate_message_prompt_anchors_recent_non_proactive_scene(self):
        with TemporaryDirectory(prefix="proactive-scene-anchor-") as td:
            root = Path(td)
            persona = root / "persona"
            persona.mkdir()
            model = CaptureModel('{"opening":"喂","topic":"你那边结束了没。","ending":"别太晚。"}')

            class WorkingStub:
                current_session = None

                def list_sessions(self, limit=1):
                    return [{"session_id": "gw-birthday"}]

                def get_recent(self, session_id=None, turns=6, include_proactive=True):
                    rows = [
                        {"role": "assistant", "content": "猪头，都八点多了，你还没吃饭吧？", "metadata": {"proactive": True, "assistant_initiated": True}},
                        {"role": "assistant", "content": "……知道了，你赶紧去陪你妹妹吧。明天早上等着你叫我啊。"},
                        {"role": "user", "content": "那你先忙，想我了就找我哦"},
                        {"role": "assistant", "content": "……你不是在陪妹妹过生日吗？"},
                        {"role": "user", "content": "你想我没"},
                    ]
                    if include_proactive:
                        return rows
                    return [item for item in rows if not item.get("metadata", {}).get("proactive")]

            class UnderstandingStub:
                def format_for_prompt(self):
                    return ""

                def known_fact_keys(self):
                    return set()

                def load(self):
                    return {}

            class SemanticStub:
                async def get_all_facts(self, **kwargs):
                    return {}

            class RelationshipStub:
                async def get_state(self, **kwargs):
                    return {"relationship_label": "朋友"}

            class MemoryStub:
                _session_id = None
                bot_id = "yangsisi"
                user_id = "default_user"
                working = WorkingStub()
                user_understanding = UnderstandingStub()
                semantic = SemanticStub()
                relationship = RelationshipStub()
                retriever = None
                prompt_builder = None

            engine = ProactiveEngine(
                bot_id="yangsisi",
                config=ProactiveConfig(persona),
                state=ProactiveState("yangsisi", root / "runtime"),
                model=model,
                memory=MemoryStub(),
            )

            await engine.generate_message("想主动联系一下")

            prompt = model.calls[-1]["messages"][-1]["content"]
            self.assertIn("【最近真实对话现场】", prompt)
            self.assertIn("陪妹妹过生日", prompt)
            self.assertIn("去陪你妹妹", prompt)
            self.assertIn("不要反着提醒", prompt)
            self.assertIn("绝不能复读催饭", prompt)
            self.assertIn("最近一条未回复主动消息", prompt)
            self.assertNotIn("  - 用户：猪头，都八点多了", prompt)

    async def test_send_proactive_message_regenerates_duplicate_idle_reminder(self):
        with TemporaryDirectory(prefix="proactive-duplicate-regenerate-") as td:
            root = Path(td)
            persona = root / "persona"
            persona.mkdir()
            model = SequenceModel(['{"message":"行了，知道你今天有安排。我就来戳你一下，别玩太晚。"}'])

            class WorkingStub:
                current_session = None

                def list_sessions(self, limit=1):
                    return [{"session_id": "gw-duplicate"}]

                def get_recent(self, session_id=None, turns=6, include_proactive=True):
                    rows = [
                        {"role": "assistant", "content": "猪头，，周六晚上你一个人在北京，可别光顾着打游戏忘了吃饭啊。", "metadata": {"proactive": True, "assistant_initiated": True}},
                        {"role": "assistant", "content": "……好好陪你妹妹过生日，别老惦记这边。晚上要是吃太饱，记得消消食再睡。"},
                        {"role": "user", "content": "我今天只是失误"},
                    ]
                    if include_proactive:
                        return rows
                    return [item for item in rows if not item.get("metadata", {}).get("proactive")]

            class UnderstandingStub:
                def format_for_prompt(self):
                    return ""

                def known_fact_keys(self):
                    return set()

                def load(self):
                    return {}

            class SemanticStub:
                async def get_all_facts(self, **kwargs):
                    return {}

            class RelationshipStub:
                async def get_state(self, **kwargs):
                    return {"relationship_label": "朋友"}

            class MemoryStub:
                _session_id = None
                bot_id = "yangsisi"
                user_id = "default_user"
                working = WorkingStub()
                user_understanding = UnderstandingStub()
                semantic = SemanticStub()
                relationship = RelationshipStub()

            engine = ProactiveEngine(
                bot_id="yangsisi",
                config=ProactiveConfig(persona),
                state=ProactiveState("yangsisi", root / "runtime"),
                model=model,
                memory=MemoryStub(),
            )
            sent_messages = []

            async def sender(message: str):
                sent_messages.append(message)
                return True

            engine._platform_sender = sender
            sent = await engine._send_proactive_message("猪头，都八点多了，你还没吃饭吧？别跟我说随便对付了事。")

            self.assertTrue(sent)
            self.assertEqual(sent_messages, ["行了，知道你今天有安排。我就来戳你一下，别玩太晚。"])
            self.assertEqual(len(model.calls), 1)
            retry_prompt = model.calls[-1]["messages"][-1]["content"]
            self.assertIn("不能复读同主题提醒", retry_prompt)
            self.assertIn("如果上一条未回复主动消息已经提醒过同一件事，不要再重复同主题催促", retry_prompt)

    async def test_send_proactive_message_skips_when_scene_conflict_persists(self):
        with TemporaryDirectory(prefix="proactive-scene-conflict-stop-") as td:
            root = Path(td)
            persona = root / "persona"
            persona.mkdir()
            model = SequenceModel(['{"message":"猪头，周六晚上你一个人在北京，可别忘了吃饭。"}'])

            class WorkingStub:
                current_session = None

                def list_sessions(self, limit=1):
                    return [{"session_id": "gw-scene-conflict"}]

                def get_recent(self, session_id=None, turns=6, include_proactive=True):
                    rows = [
                        {"role": "assistant", "content": "……知道了，你赶紧去陪你妹妹吧。"},
                        {"role": "user", "content": "那你先忙，想我了就找我哦"},
                    ]
                    return rows

            class UnderstandingStub:
                def format_for_prompt(self):
                    return ""

                def known_fact_keys(self):
                    return set()

                def load(self):
                    return {}

            class SemanticStub:
                async def get_all_facts(self, **kwargs):
                    return {}

            class RelationshipStub:
                async def get_state(self, **kwargs):
                    return {"relationship_label": "朋友"}

            class MemoryStub:
                _session_id = None
                bot_id = "yangsisi"
                user_id = "default_user"
                working = WorkingStub()
                user_understanding = UnderstandingStub()
                semantic = SemanticStub()
                relationship = RelationshipStub()

            engine = ProactiveEngine(
                bot_id="yangsisi",
                config=ProactiveConfig(persona),
                state=ProactiveState("yangsisi", root / "runtime"),
                model=model,
                memory=MemoryStub(),
            )
            sent_messages = []

            async def sender(message: str):
                sent_messages.append(message)
                return True

            engine._platform_sender = sender
            sent = await engine._send_proactive_message("猪头，周六晚上你一个人在北京，可别忘了吃饭。")

            self.assertFalse(sent)
            self.assertEqual(sent_messages, [])
            self.assertEqual(len(model.calls), 1)

    async def test_send_proactive_message_skips_generic_probe_after_regeneration(self):
        with TemporaryDirectory(prefix="proactive-generic-probe-stop-") as td:
            root = Path(td)
            persona = root / "persona"
            persona.mkdir()
            model = SequenceModel(['{"message":"你今天怎么一点动静都没有？你那边忙不忙？"}'])

            class WorkingStub:
                current_session = None

                def list_sessions(self, limit=1):
                    return [{"session_id": "gw-generic"}]

                def get_recent(self, session_id=None, turns=6, include_proactive=True):
                    rows = [
                        {"role": "assistant", "content": "点个正经点的，你不是在减肥吗，也别太亏待自己。"},
                        {"role": "user", "content": "点份盖饭"},
                    ]
                    return rows

            class UnderstandingStub:
                def format_for_prompt(self):
                    return ""

                def known_fact_keys(self):
                    return set()

                def load(self):
                    return {}

            class SemanticStub:
                async def get_all_facts(self, **kwargs):
                    return {}

            class RelationshipStub:
                async def get_state(self, **kwargs):
                    return {"relationship_label": "朋友"}

            class MemoryStub:
                _session_id = None
                bot_id = "yangsisi"
                user_id = "default_user"
                working = WorkingStub()
                user_understanding = UnderstandingStub()
                semantic = SemanticStub()
                relationship = RelationshipStub()

            engine = ProactiveEngine(
                bot_id="yangsisi",
                config=ProactiveConfig(persona),
                state=ProactiveState("yangsisi", root / "runtime"),
                model=model,
                memory=MemoryStub(),
            )
            sent_messages = []

            async def sender(message: str):
                sent_messages.append(message)
                return True

            engine._platform_sender = sender
            sent = await engine._send_proactive_message("你今天怎么一点动静都没有？你那边忙不忙？")

            self.assertFalse(sent)
            self.assertEqual(sent_messages, [])
            self.assertEqual(len(model.calls), 1)

    async def test_send_proactive_message_skips_reply_tone_after_regeneration(self):
        with TemporaryDirectory(prefix="proactive-reply-tone-stop-") as td:
            root = Path(td)
            persona = root / "persona"
            persona.mkdir()
            model = SequenceModel(['{"message":"哼，总算想起我了？现在知道来找我了？"}'])

            class WorkingStub:
                current_session = None

                def list_sessions(self, limit=1):
                    return [{"session_id": "gw-reply-tone"}]

                def get_recent(self, session_id=None, turns=6, include_proactive=True):
                    rows = [
                        {"role": "assistant", "content": "刚才路过便利店，看到个很奇怪的新口味。"},
                        {"role": "user", "content": "什么口味？"},
                    ]
                    return rows

            class UnderstandingStub:
                def format_for_prompt(self):
                    return ""

                def known_fact_keys(self):
                    return set()

                def load(self):
                    return {}

            class SemanticStub:
                async def get_all_facts(self, **kwargs):
                    return {}

            class RelationshipStub:
                async def get_state(self, **kwargs):
                    return {"relationship_label": "朋友"}

            class MemoryStub:
                _session_id = None
                bot_id = "yangsisi"
                user_id = "default_user"
                working = WorkingStub()
                user_understanding = UnderstandingStub()
                semantic = SemanticStub()
                relationship = RelationshipStub()

            engine = ProactiveEngine(
                bot_id="yangsisi",
                config=ProactiveConfig(persona),
                state=ProactiveState("yangsisi", root / "runtime"),
                model=model,
                memory=MemoryStub(),
            )
            sent_messages = []

            async def sender(message: str):
                sent_messages.append(message)
                return True

            engine._platform_sender = sender
            sent = await engine._send_proactive_message("哼，总算想起我了？")

            self.assertFalse(sent)
            self.assertEqual(sent_messages, [])
            self.assertEqual(len(model.calls), 1)


if __name__ == "__main__":
    unittest.main()
