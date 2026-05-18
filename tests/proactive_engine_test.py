import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

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
            self.assertEqual(
                engine._classify_generated_message_issue('{"opening":"喂","topic":"test","ending":"来"}'),
                "raw_json",
            )
            self.assertIsNone(engine._classify_generated_message_issue("今天风有点大，突然想起你了。"))

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
            self.assertIn(sent_messages[0], ["对了，昨天...", "有件事想跟你分享～", "你知道吗，今天..."])
            self.assertNotIn("开头", sent_messages[0])
            self.assertNotIn("主体", sent_messages[0])
            self.assertNotIn("结尾", sent_messages[0])

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
            self.assertEqual(second, "在忙什么呀？")
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


if __name__ == "__main__":
    unittest.main()
