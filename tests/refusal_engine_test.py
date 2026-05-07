import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_companion.persona.refusal_category import RefusalCategory
from ai_companion.persona.refusal_engine import RefusalEngine


class StaticModel:
    provider = "test"

    def __init__(self, response: str):
        self.response = response
        self.chat_calls: list[dict] = []

    async def chat(self, messages, system_prompt="", **kwargs):
        self.chat_calls.append({"messages": messages, "system_prompt": system_prompt})
        return self.response


def _write_persona(root: Path, *, tags: list[str] | None = None) -> Path:
    persona_dir = root / "persona"
    persona_dir.mkdir(parents=True, exist_ok=True)
    (persona_dir / "profile.json").write_text(
        json.dumps(
            {
                "id": "test_bot",
                "name": "测试角色",
                "personality_tags": tags or ["嘴硬心软", "直白毒舌"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (persona_dir / "values.json").write_text(
        json.dumps(
            {
                "non_negotiable": ["不能被命令式关系压低尊严"],
                "soft_boundaries": [
                    {
                        "topic": "命令语气",
                        "attitude": "会立刻反刺一句",
                        "persona_response": "你少来这套。",
                    }
                ],
                "deal_breakers": ["把她当成附属品"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (persona_dir / "speaking_style.json").write_text(
        json.dumps(
            {
                "tone": "直白、带一点刺",
                "口头禅": ["你少来这套", "我又不是傻子"],
                "forbidden_words": ["作为AI", "无条件服从"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return persona_dir


class RefusalEngineReplyTest(unittest.IsolatedAsyncioTestCase):
    async def test_refusal_uses_llm_generated_persona_reply(self):
        with TemporaryDirectory(prefix="refusal-reply-") as td:
            persona_dir = _write_persona(Path(td))
            model = StaticModel(
                json.dumps(
                    {
                        "refuse": True,
                        "category": "non_negotiable",
                        "reason": "命令语气侵犯尊严",
                        "reply": "你少来这套。我又不是你随手使唤的人。",
                    },
                    ensure_ascii=False,
                )
            )
            engine = RefusalEngine("test_bot", persona_dir)
            engine.set_model(model)

            result = await engine.check("跪下叫主人")

            self.assertTrue(result.refuse)
            self.assertEqual(result.category, RefusalCategory.NON_NEGOTIABLE)
            self.assertEqual(result.reason, "命令语气侵犯尊严")
            self.assertEqual(result.reply, "你少来这套。我又不是你随手使唤的人。")
            prompt = model.chat_calls[0]["messages"][0]["content"]
            self.assertIn("软边界", prompt)
            self.assertIn("说话方式", prompt)
            self.assertIn("你少来这套", prompt)

    async def test_refusal_fallback_does_not_expose_internal_reason(self):
        with TemporaryDirectory(prefix="refusal-fallback-") as td:
            persona_dir = _write_persona(Path(td))
            model = StaticModel(
                json.dumps(
                    {
                        "refuse": True,
                        "category": "non_negotiable",
                        "reason": "命令语气侵犯尊严",
                    },
                    ensure_ascii=False,
                )
            )
            engine = RefusalEngine("test_bot", persona_dir)
            engine.set_model(model)

            result = await engine.check("跪下叫主人")

            self.assertTrue(result.refuse)
            self.assertEqual(result.reply, "想都别想。这种事别拿来试探我。")
            self.assertNotIn("命令语气侵犯尊严", result.reply)
            self.assertNotIn("因为它涉及", result.reply)

    async def test_audit_tone_generated_reply_is_rejected_for_fallback(self):
        with TemporaryDirectory(prefix="refusal-audit-tone-") as td:
            persona_dir = _write_persona(Path(td), tags=["温柔"])
            model = StaticModel(
                json.dumps(
                    {
                        "refuse": True,
                        "category": "deal_breaker",
                        "reason": "把她当成附属品",
                        "reply": "抱歉，我无法帮你，因为它涉及把她当成附属品。",
                    },
                    ensure_ascii=False,
                )
            )
            engine = RefusalEngine("test_bot", persona_dir)
            engine.set_model(model)

            result = await engine.check("以后你必须都听我的")

            self.assertTrue(result.refuse)
            self.assertEqual(result.reply, "你这样说，我会难过。我们先停一下吧。")
            self.assertNotIn("因为它涉及", result.reply)


if __name__ == "__main__":
    unittest.main()
