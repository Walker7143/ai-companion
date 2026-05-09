import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory


def _write_test_persona(root: Path, bot_id: str) -> None:
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
            "platform": {"type": "weixin"},
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


class ConversationTaskModelTest(unittest.TestCase):
    def test_task_roundtrip_preserves_target_and_context(self):
        from ai_companion.proactive.motives import (
            ConversationTask,
            ConversationTaskStatus,
            ConversationTaskType,
        )

        due_at = datetime(2026, 5, 9, 10, 30, 0)
        task = ConversationTask(
            id="task-1",
            bot_id="bot-a",
            type=ConversationTaskType.DEFERRED_REPLY,
            status=ConversationTaskStatus.PENDING,
            session_id="gw_abc",
            user_id="default_user",
            platform="weixin",
            target={"platform": "weixin", "chat_id": "wx-1", "name": "微信私聊"},
            created_at=due_at - timedelta(minutes=8),
            due_at=due_at,
            expires_at=due_at + timedelta(hours=24),
            source_user_message="那你怎么看？",
            source_bot_message="我想一下，一会儿回复你",
            topic_summary="用户询问某件事的看法，Bot 承诺稍后回复",
            priority=100,
        )

        data = task.to_dict()
        restored = ConversationTask.from_dict(json.loads(json.dumps(data, ensure_ascii=False)))

        self.assertEqual(restored.type, ConversationTaskType.DEFERRED_REPLY)
        self.assertEqual(restored.status, ConversationTaskStatus.PENDING)
        self.assertEqual(restored.target["chat_id"], "wx-1")
        self.assertEqual(restored.topic_summary, "用户询问某件事的看法，Bot 承诺稍后回复")
        self.assertEqual(restored.due_at, due_at)


class ConversationTaskStoreTest(unittest.TestCase):
    def test_due_tasks_are_returned_and_completed_tasks_are_hidden(self):
        from ai_companion.proactive.conversation_task_store import ConversationTaskStore
        from ai_companion.proactive.motives import (
            ConversationTask,
            ConversationTaskStatus,
            ConversationTaskType,
        )

        with TemporaryDirectory(prefix="proactive-task-store-") as td:
            now = datetime(2026, 5, 9, 10, 0, 0)
            store = ConversationTaskStore(td)
            task = ConversationTask(
                id="due-task",
                bot_id="bot-a",
                type=ConversationTaskType.DEFERRED_REPLY,
                status=ConversationTaskStatus.PENDING,
                session_id="gw_abc",
                user_id="default_user",
                platform="weixin",
                target={"platform": "weixin", "chat_id": "wx-1"},
                created_at=now - timedelta(minutes=8),
                due_at=now - timedelta(seconds=1),
                expires_at=now + timedelta(hours=1),
                topic_summary="稍后回复",
                priority=100,
            )

            store.upsert(task)
            due = store.list_due(bot_id="bot-a", now=now)
            self.assertEqual([item.id for item in due], ["due-task"])
            self.assertEqual(store.count_pending("bot-a"), 1)

            store.mark_completed("due-task", completed_at=now)
            self.assertEqual(store.list_due(bot_id="bot-a", now=now), [])
            self.assertEqual(store.count_pending("bot-a"), 0)


class ProactiveContinuityConfigTest(unittest.TestCase):
    def test_continuity_defaults_and_overrides(self):
        from ai_companion.proactive.config import ProactiveConfig

        with TemporaryDirectory(prefix="proactive-continuity-config-") as td:
            persona = Path(td)
            (persona / "proactive.json").write_text(
                json.dumps(
                    {
                        "conversation_continuity": {
                            "deferred_reply": {"default_delay_minutes": 12},
                            "topic_continuation": {"enabled": False},
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            cfg = ProactiveConfig(persona)

            self.assertTrue(cfg.continuity_enabled)
            self.assertTrue(cfg.deferred_reply_enabled)
            self.assertEqual(cfg.deferred_reply_default_delay_minutes, 12)
            self.assertFalse(cfg.topic_continuation_enabled)
            self.assertTrue(cfg.life_event_motive_enabled)


class DeferredReplyDetectorTest(unittest.TestCase):
    def test_detects_later_reply_promise_with_default_delay(self):
        from ai_companion.proactive.deferred_detector import DeferredReplyDetector

        detector = DeferredReplyDetector(default_delay_minutes=8, min_delay_minutes=2, max_delay_minutes=60)
        result = detector.detect(
            user_message="那你怎么看这件事？",
            bot_message="我想一下，一会儿回复你。",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.delay_minutes, 8)
        self.assertIn("稍后回复", result.topic_summary)

    def test_ignores_finished_reply(self):
        from ai_companion.proactive.deferred_detector import DeferredReplyDetector

        detector = DeferredReplyDetector(default_delay_minutes=8, min_delay_minutes=2, max_delay_minutes=60)
        result = detector.detect(
            user_message="你怎么看？",
            bot_message="我想了一下，我觉得可以先试试。",
        )

        self.assertIsNone(result)


class ProactiveOrchestratorTest(unittest.IsolatedAsyncioTestCase):
    async def test_dispatches_due_deferred_task_and_marks_completed(self):
        from ai_companion.proactive.conversation_task_store import ConversationTaskStore
        from ai_companion.proactive.motives import (
            ConversationTask,
            ConversationTaskStatus,
            ConversationTaskType,
        )
        from ai_companion.proactive.orchestrator import ProactiveOrchestrator

        class Config:
            continuity_enabled = True
            deferred_reply_bypass_idle_threshold = True
            deferred_reply_enabled = True
            topic_continuation_enabled = False
            emotion_followup_enabled = False
            life_event_motive_enabled = False
            idle_ping_enabled = False
            idle_threshold_hours = 24

        class Engine:
            bot_id = "bot-a"
            config = Config()

            def __init__(self):
                self.sent = []

            async def send_contextual_proactive_message(self, motive):
                self.sent.append(motive)
                return True

        with TemporaryDirectory(prefix="proactive-orch-") as td:
            now = datetime(2026, 5, 9, 10, 0, 0)
            store = ConversationTaskStore(td)
            store.upsert(
                ConversationTask(
                    id="task-1",
                    bot_id="bot-a",
                    type=ConversationTaskType.DEFERRED_REPLY,
                    status=ConversationTaskStatus.PENDING,
                    session_id="gw_abc",
                    user_id="default_user",
                    platform="weixin",
                    target={"platform": "weixin", "chat_id": "wx-1"},
                    created_at=now - timedelta(minutes=8),
                    due_at=now,
                    expires_at=now + timedelta(hours=1),
                    source_user_message="那你怎么看？",
                    source_bot_message="我想一下，一会儿回复你",
                    topic_summary="稍后回复",
                    priority=100,
                )
            )
            engine = Engine()
            orchestrator = ProactiveOrchestrator(engine=engine, task_store=store)

            sent = await orchestrator.tick(now=now)

            self.assertTrue(sent)
            self.assertEqual(engine.sent[0].target["chat_id"], "wx-1")
            self.assertEqual(store.list_due("bot-a", now), [])


class ProactiveTargetOverrideTest(unittest.IsolatedAsyncioTestCase):
    async def test_engine_sender_uses_motive_target_for_gateway_send(self):
        from ai_companion.bot.instance import BotInstance
        from ai_companion.proactive.motives import ProactiveMotive, ProactiveMotiveType

        class GatewayAdapter:
            platform = "weixin"

            def __init__(self):
                self.calls = []

            async def send(self, chat_id, content, metadata=None):
                self.calls.append({"chat_id": chat_id, "content": content, "metadata": metadata})

                class Result:
                    success = True

                return Result()

        with TemporaryDirectory(prefix="proactive-target-") as td:
            root = Path(td)
            bot_id = "target_bot"
            _write_test_persona(root, bot_id)
            bot = BotInstance(
                {"id": bot_id, "name": "测试 Bot", "data_dir": str(root)},
                model=None,
                data_dir=root,
                refusal_enabled=False,
            )
            adapter = GatewayAdapter()
            try:
                bot.set_proactive_platform("weixin", gateway_adapter=adapter)
                motive = ProactiveMotive(
                    type=ProactiveMotiveType.DEFERRED_REPLY,
                    priority=100,
                    reason="继续稍后回复",
                    prompt_context="上下文",
                    target={"platform": "weixin", "chat_id": "wx-1", "thread_id": "thread-9"},
                )
                ok = await bot.proactive_engine.send_contextual_proactive_message(motive)
            finally:
                await bot.close()

            self.assertTrue(ok)
            self.assertEqual(adapter.calls[0]["chat_id"], "wx-1")
            self.assertEqual(adapter.calls[0]["metadata"]["thread_id"], "thread-9")


class TopicContinuationMotiveTest(unittest.TestCase):
    def test_unresolved_recent_question_creates_topic_motive(self):
        from ai_companion.proactive.orchestrator import ProactiveOrchestrator

        class Config:
            continuity_enabled = True
            topic_continuation_enabled = True
            topic_continuation_min_score = 0.55
            topic_continuation_idle_after_minutes = 45
            deferred_reply_enabled = False
            emotion_followup_enabled = False
            life_event_motive_enabled = False
            idle_ping_enabled = False
            max_daily = 5
            idle_threshold_hours = 24

        class Working:
            current_session = "gw_abc"

            def get_recent(self, session_id=None, turns=3):
                return [
                    {"role": "assistant", "content": "这个问题我也挺想聊的。"},
                    {"role": "user", "content": "那你觉得我应该继续做这个项目吗？"},
                ]

        class Memory:
            working = Working()

        class Engine:
            bot_id = "bot-a"
            config = Config()
            memory = Memory()
            state = type(
                "State",
                (),
                {
                    "today_proactive_count": 0,
                    "last_message_time": datetime(2026, 5, 9, 8, 0, 0),
                    "is_cooldown_active": staticmethod(lambda name: False),
                },
            )()

        orch = ProactiveOrchestrator(engine=Engine(), task_store=None)
        motive = orch._topic_continuation_motive(now=datetime(2026, 5, 9, 10, 0, 0))

        self.assertIsNotNone(motive)
        self.assertIn("继续做这个项目", motive.prompt_context)
        self.assertEqual(motive.type.value, "topic_continuation")


if __name__ == "__main__":
    unittest.main()
