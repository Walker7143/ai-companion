import asyncio
import tempfile
import unittest
from pathlib import Path

from ai_companion.memory.engine import MemoryEngine


class DailyMemoryTest(unittest.TestCase):
    def test_daily_memory_cross_session_context_without_working_merge(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="daily-memory-") as tmp:
                engine = MemoryEngine(
                    "daily_bot",
                    Path(tmp),
                    config={
                        "embedding": "none",
                        "daily": {
                            "summarize_after_messages": 100,
                            "summarize_after_chars": 999999,
                        },
                    },
                )
                await engine.init()
                engine.start_session("gw_feishu")
                await engine.on_message(
                    "我今天在飞书说项目发布压力很大",
                    "我会记着，晚上可以再一起拆一下。",
                    turn_context={
                        "platform": "feishu",
                        "session_id": "gw_feishu",
                        "user_id": "default_user",
                        "channel_type": "dm",
                    },
                )

                engine.start_session("gw_weixin")
                ctx = await engine.load_context("刚才我们聊了什么？")
                working_text = "\n".join(item.get("content", "") for item in ctx["working_history"])
                suffix = ctx["system_suffix"]

                await engine.close()
                return working_text, suffix, ctx

        working_text, suffix, ctx = asyncio.run(run())
        self.assertNotIn("项目发布压力很大", working_text)
        self.assertIn("项目发布压力很大", suffix)
        self.assertIn("feishu", suffix)
        self.assertEqual(ctx["daily_context"]["recent_messages"][0]["platform"], "feishu")

    def test_daily_memory_can_be_disabled(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="daily-memory-off-") as tmp:
                engine = MemoryEngine(
                    "daily_off_bot",
                    Path(tmp),
                    config={"embedding": "none", "daily": {"enabled": False}},
                )
                await engine.init()
                engine.start_session("s1")
                await engine.on_message("短期信息", "收到", turn_context={"platform": "cli"})
                engine.start_session("s2")
                ctx = await engine.load_context("你记得吗")
                status = await engine.get_memory_status()
                await engine.close()
                return ctx, status

        ctx, status = asyncio.run(run())
        self.assertEqual(ctx.get("daily_context"), {})
        self.assertEqual(status.get("daily_messages"), 0)


if __name__ == "__main__":
    unittest.main()
