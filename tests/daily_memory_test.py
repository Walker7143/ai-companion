import asyncio
import tempfile
import unittest
from pathlib import Path

from ai_companion.memory.engine import MemoryEngine
from ai_companion.proactive.config import ProactiveConfig
from ai_companion.proactive.engine import ProactiveEngine
from ai_companion.proactive.state import ProactiveState


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

    def test_turn_context_session_controls_background_memory_write(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="daily-memory-session-") as tmp:
                engine = MemoryEngine(
                    "daily_session_bot",
                    Path(tmp),
                    config={"embedding": "none"},
                )
                await engine.init()
                engine.start_session("cli-session")
                await engine.on_message(
                    "gateway user text",
                    "gateway reply",
                    turn_context={
                        "platform": "weixin",
                        "session_id": "gw-session",
                        "user_id": "gateway-user",
                        "channel_type": "dm",
                        "message_id": "msg-1",
                    },
                )
                working_gw = engine.working.get_all_messages("gw-session")
                working_cli = engine.working.get_all_messages("cli-session")
                daily_ctx = engine.daily.get_recent_context(
                    bot_id="daily_session_bot",
                    user_id="gateway-user",
                )
                await engine.close()
                return working_gw, working_cli, daily_ctx

        working_gw, working_cli, daily_ctx = asyncio.run(run())
        self.assertEqual([item["content"] for item in working_gw], ["gateway user text", "gateway reply"])
        self.assertEqual(working_cli, [])
        self.assertEqual(daily_ctx["recent_messages"][0]["session_id"], "gw-session")

    def test_assistant_originated_message_is_recorded_without_user_turn(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="daily-memory-assistant-") as tmp:
                engine = MemoryEngine(
                    "daily_assistant_bot",
                    Path(tmp),
                    config={"embedding": "none"},
                )
                await engine.init()
                engine.start_session("gw-weixin-home")
                await engine.record_assistant_message(
                    "我刚刚主动分享了家里的小事",
                    turn_context={
                        "platform": "weixin",
                        "session_id": "gw-weixin-home",
                        "user_id": "gateway-user",
                        "channel_type": "dm",
                        "chat_id": "wx-user",
                    },
                )
                working = engine.working.get_all_messages("gw-weixin-home")
                daily_ctx = engine.daily.get_recent_context(
                    bot_id="daily_assistant_bot",
                    user_id="gateway-user",
                )
                await engine.close()
                return working, daily_ctx

        working, daily_ctx = asyncio.run(run())
        self.assertEqual([item["role"] for item in working], ["assistant"])
        self.assertEqual(working[0]["content"], "我刚刚主动分享了家里的小事")
        self.assertEqual(len(daily_ctx["recent_messages"]), 1)
        self.assertEqual(daily_ctx["recent_messages"][0]["role"], "assistant")

    def test_proactive_engine_records_successful_sends(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="daily-memory-proactive-") as tmp:
                root = Path(tmp)
                persona_dir = root / "persona"
                persona_dir.mkdir(parents=True, exist_ok=True)
                (persona_dir / "proactive.json").write_text(
                    '{"enabled": true, "mode": "active"}',
                    encoding="utf-8",
                )
                memory = MemoryEngine("proactive_memory_bot", root, config={"embedding": "none"})
                await memory.init()
                memory.start_session("default-proactive-session")
                engine = ProactiveEngine(
                    bot_id="proactive_memory_bot",
                    config=ProactiveConfig(persona_dir),
                    state=ProactiveState("proactive_memory_bot", root),
                    memory=memory,
                )

                async def sender(message: str):
                    return True

                engine._platform_sender = sender
                engine.set_next_record_context(
                    {
                        "platform": "cli",
                        "session_id": "cli-proactive-session",
                        "user_id": "default_user",
                        "channel_type": "local",
                    }
                )
                sent = await engine._send_proactive_message("主动消息统一出口测试")
                working = memory.working.get_all_messages("cli-proactive-session")
                daily_ctx = memory.daily.get_recent_context(
                    bot_id="proactive_memory_bot",
                    user_id="default_user",
                )
                await memory.close()
                return sent, working, daily_ctx

        sent, working, daily_ctx = asyncio.run(run())
        self.assertTrue(sent)
        self.assertEqual([item["content"] for item in working], ["主动消息统一出口测试"])
        self.assertEqual(daily_ctx["recent_messages"][0]["content"], "主动消息统一出口测试")

    def test_proactive_engine_does_not_record_failed_sends(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="daily-memory-proactive-failed-") as tmp:
                root = Path(tmp)
                persona_dir = root / "persona"
                persona_dir.mkdir(parents=True, exist_ok=True)
                (persona_dir / "proactive.json").write_text(
                    '{"enabled": true, "mode": "active"}',
                    encoding="utf-8",
                )
                memory = MemoryEngine("proactive_failed_bot", root, config={"embedding": "none"})
                await memory.init()
                memory.start_session("proactive-failed-session")
                engine = ProactiveEngine(
                    bot_id="proactive_failed_bot",
                    config=ProactiveConfig(persona_dir),
                    state=ProactiveState("proactive_failed_bot", root),
                    memory=memory,
                )

                async def sender(message: str):
                    return False

                engine._platform_sender = sender
                sent = await engine._send_proactive_message("不该入库")
                working = memory.working.get_all_messages("proactive-failed-session")
                daily_count = memory.daily.count_messages(
                    bot_id="proactive_failed_bot",
                    user_id="default_user",
                )
                await memory.close()
                return sent, working, daily_count

        sent, working, daily_count = asyncio.run(run())
        self.assertFalse(sent)
        self.assertEqual(working, [])
        self.assertEqual(daily_count, 0)


if __name__ == "__main__":
    unittest.main()
