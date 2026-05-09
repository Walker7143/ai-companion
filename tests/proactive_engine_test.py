import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_companion.proactive.config import ProactiveConfig
from ai_companion.proactive.engine import ProactiveEngine
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

    def test_parse_structured_message_keeps_valid_parts(self):
        with TemporaryDirectory(prefix="proactive-placeholder-") as td:
            engine = _build_engine(Path(td), "")
            parsed = engine._parse_structured_message(
                '{"opening":"开场白/称呼","topic":"今天路上看到很美的晚霞","ending":"结尾语"}'
            )
            self.assertEqual(parsed, "今天路上看到很美的晚霞")

    async def test_generate_message_falls_back_when_model_returns_placeholder_text(self):
        with TemporaryDirectory(prefix="proactive-placeholder-") as td:
            engine = _build_engine(Path(td), "《开场白/称呼，话题内容或空字符串，结尾语》")
            message = await engine.generate_message("测试占位文本回退")
            self.assertEqual(message, "最近怎么样？")
            self.assertNotIn("开场白/称呼", message)
            self.assertNotIn("话题内容或空字符串", message)
            self.assertNotIn("结尾语", message)


class ProactiveEngineContextualMessageTest(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()
