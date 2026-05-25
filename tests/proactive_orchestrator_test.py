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

    def test_detects_user_requested_deferred_reply_when_bot_accepts(self):
        from ai_companion.proactive.deferred_detector import DeferredReplyDetector

        detector = DeferredReplyDetector(default_delay_minutes=8, min_delay_minutes=2, max_delay_minutes=60)
        result = detector.detect(
            user_message="你要记得想好了告诉我啊",
            bot_message="知道了，去吧去吧，开会别走神。我想好了给你发消息。",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.delay_minutes, 8)
        self.assertIn("想好了告诉我", result.topic_summary)

    def test_ignores_user_requested_deferred_reply_without_bot_acceptance(self):
        from ai_companion.proactive.deferred_detector import DeferredReplyDetector

        detector = DeferredReplyDetector(default_delay_minutes=8, min_delay_minutes=2, max_delay_minutes=60)
        result = detector.detect(
            user_message="是啊，你帮我好好想想，一会告诉我奥，我先忙个会",
            bot_message="行。去忙你的。",
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

    async def test_idle_ping_selected_when_no_higher_priority_motive(self):
        from ai_companion.proactive.conversation_task_store import ConversationTaskStore
        from ai_companion.proactive.orchestrator import ProactiveOrchestrator

        class Config:
            continuity_enabled = True
            is_active = True
            deferred_reply_enabled = False
            topic_continuation_enabled = False
            emotion_followup_enabled = False
            life_event_motive_enabled = False
            idle_ping_enabled = True
            idle_ping_requires_scene_anchor = True
            idle_threshold_hours = 3
            preferred_contact_times = ["00:00-23:59"]
            max_daily = 10
            min_interval_hours = 0

        class State:
            today_proactive_count = 0
            annoyance_level = 0

            def get_cooldown(self, trigger_name):
                return None

        class Engine:
            bot_id = "bot-a"
            config = Config()
            state = State()

            def __init__(self):
                self.sent = []

            async def send_contextual_proactive_message(self, motive):
                self.sent.append(motive)
                return True

            def has_scene_anchor_for_idle_ping(self):
                return True

            def can_send_idle_ping_now(self, now):
                return True

            def has_grounded_idle_reminder_scene(self):
                return False

            def _calc_idle_hours(self):
                return 4

        with TemporaryDirectory(prefix="proactive-idle-ping-") as td:
            engine = Engine()
            orchestrator = ProactiveOrchestrator(engine=engine, task_store=ConversationTaskStore(td))

            sent = await orchestrator.tick(now=datetime(2026, 5, 9, 10, 0, 0))

            self.assertTrue(sent)
            self.assertEqual(engine.sent[0].type.value, "idle_ping")

    async def test_life_event_motive_marks_event_shared_after_send(self):
        from ai_companion.proactive.conversation_task_store import ConversationTaskStore
        from ai_companion.proactive.life_state import LifeEvent, LifeState
        from ai_companion.proactive.orchestrator import ProactiveOrchestrator

        class Config:
            continuity_enabled = True
            deferred_reply_enabled = False
            topic_continuation_enabled = False
            emotion_followup_enabled = False
            life_event_motive_enabled = True
            deferred_reply_bypass_idle_threshold = False

        class LifeEngine:
            def __init__(self, root):
                self.state = LifeState("bot-life", root)

        class Engine:
            bot_id = "bot-life"
            config = Config()

            def __init__(self, root):
                self.life_engine = LifeEngine(root)
                self.sent = []

            async def send_contextual_proactive_message(self, motive):
                self.sent.append(motive)
                return True

        with TemporaryDirectory(prefix="proactive-life-shared-") as td:
            now = datetime(2026, 5, 11, 10, 0, 0)
            engine = Engine(Path(td))
            event = LifeEvent(
                description="今天整理文件时发现一张旧照片",
                timestamp=now.isoformat(),
                shareable=True,
                topic_prompt="想跟你说个小事",
            )
            engine.life_engine.state.add_event(event)
            orchestrator = ProactiveOrchestrator(
                engine=engine,
                task_store=ConversationTaskStore(Path(td) / "tasks"),
            )

            first_sent = await orchestrator.tick(now=now)
            second_sent = await orchestrator.tick(now=now + timedelta(minutes=10))
            events = engine.life_engine.state.to_dict().get("life_events", [])
            shared_at = events[0].get("shared_at")

            self.assertTrue(first_sent)
            self.assertFalse(second_sent)
            self.assertEqual(len(engine.sent), 1)
            self.assertTrue(shared_at)


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


class TopicContinuationMotiveTest(unittest.IsolatedAsyncioTestCase):
    async def test_topic_continuation_task_dispatched_by_orchestrator(self):
        from ai_companion.proactive.conversation_task_store import ConversationTaskStore
        from ai_companion.proactive.motives import (
            ConversationTask,
            ConversationTaskStatus,
            ConversationTaskType,
        )
        from ai_companion.proactive.orchestrator import ProactiveOrchestrator

        class Config:
            continuity_enabled = True
            deferred_reply_enabled = True
            deferred_reply_bypass_idle_threshold = True
            topic_continuation_enabled = True
            emotion_followup_enabled = True
            life_event_motive_enabled = False
            idle_ping_enabled = False

        class Engine:
            bot_id = "bot-a"
            config = Config()

            def __init__(self):
                self.sent = []

            async def send_contextual_proactive_message(self, motive):
                self.sent.append(motive)
                return True

        with TemporaryDirectory(prefix="proactive-topic-") as td:
            now = datetime(2026, 5, 9, 10, 0, 0)
            store = ConversationTaskStore(td)
            store.upsert(
                ConversationTask(
                    id="topic-1",
                    bot_id="bot-a",
                    type=ConversationTaskType.TOPIC_CONTINUATION,
                    status=ConversationTaskStatus.PENDING,
                    session_id="gw_abc",
                    user_id="default_user",
                    platform="weixin",
                    target={"platform": "weixin", "chat_id": "wx-1"},
                    created_at=now - timedelta(minutes=45),
                    due_at=now,
                    expires_at=now + timedelta(hours=12),
                    source_user_message="那你觉得我应该继续做这个项目吗？",
                    source_bot_message="这个问题我也挺想聊的。",
                    topic_summary="用户询问是否继续做项目",
                    priority=70,
                )
            )
            engine = Engine()
            orchestrator = ProactiveOrchestrator(engine=engine, task_store=store)

            sent = await orchestrator.tick(now=now)

            self.assertTrue(sent)
            self.assertEqual(engine.sent[0].type.value, "topic_continuation")
            self.assertEqual(store.list_due("bot-a", now), [])


class ProactiveOrchestratorGateTest(unittest.IsolatedAsyncioTestCase):
    async def test_topic_continuation_waits_when_daily_limit_reached(self):
        from ai_companion.proactive.conversation_task_store import ConversationTaskStore
        from ai_companion.proactive.motives import (
            ConversationTask,
            ConversationTaskStatus,
            ConversationTaskType,
        )
        from ai_companion.proactive.orchestrator import ProactiveOrchestrator

        class Config:
            is_active = True
            continuity_enabled = True
            deferred_reply_enabled = True
            deferred_reply_bypass_idle_threshold = True
            topic_continuation_enabled = True
            emotion_followup_enabled = True
            life_event_motive_enabled = False
            max_daily = 1
            min_interval_hours = 0
            preferred_contact_times = ["00:00-23:59"]

        class State:
            today_proactive_count = 1
            annoyance_level = 0

            def get_cooldown(self, trigger_name):
                return None

        class Engine:
            bot_id = "bot-a"
            config = Config()
            state = State()

            def __init__(self):
                self.sent = []

            async def send_contextual_proactive_message(self, motive):
                self.sent.append(motive)
                return True

        with TemporaryDirectory(prefix="proactive-gate-daily-") as td:
            now = datetime(2026, 5, 9, 10, 0, 0)
            store = ConversationTaskStore(td)
            store.upsert(
                ConversationTask(
                    id="topic-limit",
                    bot_id="bot-a",
                    type=ConversationTaskType.TOPIC_CONTINUATION,
                    status=ConversationTaskStatus.PENDING,
                    session_id="gw_abc",
                    user_id="default_user",
                    platform="weixin",
                    target={"platform": "weixin", "chat_id": "wx-1"},
                    created_at=now - timedelta(minutes=45),
                    due_at=now,
                    expires_at=now + timedelta(hours=12),
                    topic_summary="用户询问是否继续做项目",
                    priority=70,
                )
            )
            engine = Engine()
            orchestrator = ProactiveOrchestrator(engine=engine, task_store=store)

            sent = await orchestrator.tick(now=now)

            self.assertFalse(sent)
            self.assertEqual(engine.sent, [])
            self.assertEqual([task.id for task in store.list_due("bot-a", now)], ["topic-limit"])

    async def test_topic_continuation_waits_during_min_interval_cooldown(self):
        from ai_companion.proactive.conversation_task_store import ConversationTaskStore
        from ai_companion.proactive.motives import (
            ConversationTask,
            ConversationTaskStatus,
            ConversationTaskType,
        )
        from ai_companion.proactive.orchestrator import ProactiveOrchestrator

        class Config:
            is_active = True
            continuity_enabled = True
            deferred_reply_enabled = True
            deferred_reply_bypass_idle_threshold = True
            topic_continuation_enabled = True
            emotion_followup_enabled = True
            life_event_motive_enabled = False
            max_daily = 5
            min_interval_hours = 1
            preferred_contact_times = ["00:00-23:59"]

        class State:
            today_proactive_count = 0
            annoyance_level = 0

            def __init__(self, cooldown_end):
                self.cooldown_end = cooldown_end

            def get_cooldown(self, trigger_name):
                return self.cooldown_end

        class Engine:
            bot_id = "bot-a"
            config = Config()

            def __init__(self, cooldown_end):
                self.state = State(cooldown_end)
                self.sent = []

            async def send_contextual_proactive_message(self, motive):
                self.sent.append(motive)
                return True

        with TemporaryDirectory(prefix="proactive-gate-cooldown-") as td:
            now = datetime(2026, 5, 9, 10, 0, 0)
            store = ConversationTaskStore(td)
            store.upsert(
                ConversationTask(
                    id="topic-cooldown",
                    bot_id="bot-a",
                    type=ConversationTaskType.TOPIC_CONTINUATION,
                    status=ConversationTaskStatus.PENDING,
                    session_id="gw_abc",
                    user_id="default_user",
                    platform="weixin",
                    target={"platform": "weixin", "chat_id": "wx-1"},
                    created_at=now - timedelta(minutes=45),
                    due_at=now,
                    expires_at=now + timedelta(hours=12),
                    topic_summary="用户询问是否继续做项目",
                    priority=70,
                )
            )
            engine = Engine(now + timedelta(minutes=30))
            orchestrator = ProactiveOrchestrator(engine=engine, task_store=store)

            sent = await orchestrator.tick(now=now)

            self.assertFalse(sent)
            self.assertEqual(engine.sent, [])
            self.assertEqual([task.id for task in store.list_due("bot-a", now)], ["topic-cooldown"])

    async def test_deferred_reply_still_respects_preferred_contact_time(self):
        from ai_companion.proactive.conversation_task_store import ConversationTaskStore
        from ai_companion.proactive.motives import (
            ConversationTask,
            ConversationTaskStatus,
            ConversationTaskType,
        )
        from ai_companion.proactive.orchestrator import ProactiveOrchestrator

        class Config:
            is_active = True
            continuity_enabled = True
            deferred_reply_enabled = True
            deferred_reply_bypass_idle_threshold = True
            topic_continuation_enabled = False
            emotion_followup_enabled = False
            life_event_motive_enabled = False
            max_daily = 5
            min_interval_hours = 0
            preferred_contact_times = ["09:00-22:00"]

        class State:
            today_proactive_count = 0
            annoyance_level = 0

            def get_cooldown(self, trigger_name):
                return None

        class Engine:
            bot_id = "bot-a"
            config = Config()
            state = State()

            def __init__(self):
                self.sent = []

            async def send_contextual_proactive_message(self, motive):
                self.sent.append(motive)
                return True

        with TemporaryDirectory(prefix="proactive-gate-hours-") as td:
            now = datetime(2026, 5, 9, 23, 0, 0)
            store = ConversationTaskStore(td)
            store.upsert(
                ConversationTask(
                    id="deferred-late",
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
                    source_user_message="想好了告诉我",
                    source_bot_message="好，我想好了给你发消息",
                    topic_summary="稍后回复",
                    priority=100,
                )
            )
            engine = Engine()
            orchestrator = ProactiveOrchestrator(engine=engine, task_store=store)

            sent = await orchestrator.tick(now=now)

            self.assertFalse(sent)
            self.assertEqual(engine.sent, [])
            self.assertEqual([task.id for task in store.list_due("bot-a", now)], ["deferred-late"])

    async def test_life_event_is_not_marked_shared_when_gate_blocks_send(self):
        from ai_companion.proactive.conversation_task_store import ConversationTaskStore
        from ai_companion.proactive.life_state import LifeEvent, LifeState
        from ai_companion.proactive.orchestrator import ProactiveOrchestrator

        class Config:
            is_active = True
            continuity_enabled = True
            deferred_reply_enabled = False
            topic_continuation_enabled = False
            emotion_followup_enabled = False
            life_event_motive_enabled = True
            deferred_reply_bypass_idle_threshold = False
            max_daily = 1
            min_interval_hours = 0
            preferred_contact_times = ["00:00-23:59"]

        class State:
            today_proactive_count = 1
            annoyance_level = 0

            def get_cooldown(self, trigger_name):
                return None

        class LifeEngine:
            def __init__(self, root):
                self.state = LifeState("bot-life", root)

        class Engine:
            bot_id = "bot-life"
            config = Config()
            state = State()

            def __init__(self, root):
                self.life_engine = LifeEngine(root)
                self.sent = []

            async def send_contextual_proactive_message(self, motive):
                self.sent.append(motive)
                return True

        with TemporaryDirectory(prefix="proactive-life-gate-") as td:
            now = datetime(2026, 5, 11, 10, 0, 0)
            engine = Engine(Path(td))
            event = LifeEvent(
                description="今天整理文件时发现一张旧照片",
                shareable=True,
                topic_prompt="想跟你说个小事",
            )
            engine.life_engine.state.add_event(event)
            orchestrator = ProactiveOrchestrator(
                engine=engine,
                task_store=ConversationTaskStore(Path(td) / "tasks"),
            )

            sent = await orchestrator.tick(now=now)
            events = engine.life_engine.state.to_dict().get("life_events", [])

            self.assertFalse(sent)
            self.assertEqual(engine.sent, [])
            self.assertFalse(events[0].get("shared_at"))


class TaskCancelOnUserReturnTest(unittest.TestCase):
    def test_cancel_pending_for_session(self):
        from ai_companion.proactive.conversation_task_store import ConversationTaskStore
        from ai_companion.proactive.motives import (
            ConversationTask,
            ConversationTaskStatus,
            ConversationTaskType,
        )

        with TemporaryDirectory(prefix="proactive-cancel-") as td:
            now = datetime(2026, 5, 9, 10, 0, 0)
            store = ConversationTaskStore(td)
            store.upsert(
                ConversationTask(
                    id="cancel-1",
                    bot_id="bot-a",
                    type=ConversationTaskType.DEFERRED_REPLY,
                    status=ConversationTaskStatus.PENDING,
                    session_id="session-x",
                    user_id="user-1",
                    platform="weixin",
                    target={},
                    created_at=now - timedelta(minutes=5),
                    due_at=now + timedelta(minutes=3),
                    expires_at=now + timedelta(hours=24),
                    topic_summary="test",
                    priority=100,
                )
            )
            store.upsert(
                ConversationTask(
                    id="cancel-2",
                    bot_id="bot-a",
                    type=ConversationTaskType.TOPIC_CONTINUATION,
                    status=ConversationTaskStatus.PENDING,
                    session_id="session-x",
                    user_id="user-1",
                    platform="weixin",
                    target={},
                    created_at=now - timedelta(minutes=5),
                    due_at=now + timedelta(minutes=40),
                    expires_at=now + timedelta(hours=12),
                    topic_summary="test topic",
                    priority=70,
                )
            )

            cancelled = store.cancel_pending_for_session("bot-a", "session-x", now)
            self.assertEqual(cancelled, 2)
            self.assertEqual(store.count_pending("bot-a"), 0)


class TaskExpireOverdueTest(unittest.TestCase):
    def test_expire_overdue_marks_expired_tasks(self):
        from ai_companion.proactive.conversation_task_store import ConversationTaskStore
        from ai_companion.proactive.motives import (
            ConversationTask,
            ConversationTaskStatus,
            ConversationTaskType,
        )

        with TemporaryDirectory(prefix="proactive-expire-") as td:
            now = datetime(2026, 5, 9, 10, 0, 0)
            store = ConversationTaskStore(td)
            store.upsert(
                ConversationTask(
                    id="expired-1",
                    bot_id="bot-a",
                    type=ConversationTaskType.DEFERRED_REPLY,
                    status=ConversationTaskStatus.PENDING,
                    session_id="gw_abc",
                    user_id="user-1",
                    platform="weixin",
                    target={},
                    created_at=now - timedelta(hours=25),
                    due_at=now - timedelta(hours=24),
                    expires_at=now - timedelta(hours=1),
                    topic_summary="old task",
                    priority=100,
                )
            )

            expired = store.expire_overdue(now)
            self.assertEqual(expired, 1)
            self.assertEqual(store.count_pending("bot-a"), 0)


class CloseoutAnalyzerTest(unittest.IsolatedAsyncioTestCase):
    async def test_llm_parse_detects_deferred_reply(self):
        from ai_companion.proactive.closeout_analyzer import CloseoutAnalyzer

        class Config:
            closeout_analyzer_enabled = True
            closeout_analyzer_max_tokens = 200
            closeout_analyzer_fallback_to_regex = True
            deferred_reply_default_delay_minutes = 8
            deferred_reply_min_delay_minutes = 2
            deferred_reply_max_delay_minutes = 60
            topic_continuation_min_score = 0.55

        class Model:
            async def chat(self, messages, system_prompt=None, max_tokens=200):
                return '{"deferred_reply": {"detected": true, "summary": "承诺查资料后回复", "delay_minutes": 10}, "unresolved_topic": {"detected": false, "summary": "", "confidence": 0.0}, "emotion_followup": {"detected": false, "emotion": "", "summary": ""}}'

        analyzer = CloseoutAnalyzer(Model(), Config())
        result = await analyzer.analyze("帮我查一下那个数据", "好的，我查一下，稍后告诉你", [])

        self.assertIsNotNone(result.deferred_reply)
        self.assertEqual(result.deferred_reply.delay_minutes, 10)
        self.assertIn("查资料", result.deferred_reply.summary)
        self.assertIsNone(result.unresolved_topic)
        self.assertIsNone(result.emotion_followup)

    async def test_llm_parse_detects_emotion(self):
        from ai_companion.proactive.closeout_analyzer import CloseoutAnalyzer

        class Config:
            closeout_analyzer_enabled = True
            closeout_analyzer_max_tokens = 200
            closeout_analyzer_fallback_to_regex = True
            deferred_reply_default_delay_minutes = 8
            deferred_reply_min_delay_minutes = 2
            deferred_reply_max_delay_minutes = 60
            topic_continuation_min_score = 0.55

        class Model:
            async def chat(self, messages, system_prompt=None, max_tokens=200):
                return '{"deferred_reply": {"detected": false, "summary": "", "delay_minutes": 0}, "unresolved_topic": {"detected": false, "summary": "", "confidence": 0.0}, "emotion_followup": {"detected": true, "emotion": "焦虑", "summary": "用户对工作压力感到焦虑"}}'

        analyzer = CloseoutAnalyzer(Model(), Config())
        result = await analyzer.analyze("最近工作压力好大，感觉快撑不住了", "我理解你的感受...", [])

        self.assertIsNone(result.deferred_reply)
        self.assertIsNotNone(result.emotion_followup)
        self.assertEqual(result.emotion_followup.emotion, "焦虑")

    async def test_fallback_to_regex_on_llm_failure(self):
        from ai_companion.proactive.closeout_analyzer import CloseoutAnalyzer

        class Config:
            closeout_analyzer_enabled = True
            closeout_analyzer_max_tokens = 200
            closeout_analyzer_fallback_to_regex = True
            deferred_reply_default_delay_minutes = 8
            deferred_reply_min_delay_minutes = 2
            deferred_reply_max_delay_minutes = 60
            topic_continuation_min_score = 0.55

        class Model:
            async def chat(self, messages, system_prompt=None, max_tokens=200):
                raise RuntimeError("API error")

        analyzer = CloseoutAnalyzer(Model(), Config())
        result = await analyzer.analyze("你怎么看？", "我想一下，一会儿回复你", [])

        self.assertIsNotNone(result.deferred_reply)
        self.assertEqual(result.deferred_reply.delay_minutes, 8)

    async def test_fallback_to_regex_when_llm_misses_user_requested_deferred_reply(self):
        from ai_companion.proactive.closeout_analyzer import CloseoutAnalyzer

        class Config:
            closeout_analyzer_enabled = True
            closeout_analyzer_max_tokens = 200
            closeout_analyzer_fallback_to_regex = True
            deferred_reply_default_delay_minutes = 8
            deferred_reply_min_delay_minutes = 2
            deferred_reply_max_delay_minutes = 60
            topic_continuation_min_score = 0.55

        class Model:
            async def chat(self, messages, system_prompt=None, max_tokens=200):
                return '{"deferred_reply": {"detected": false, "summary": "", "delay_minutes": 0}, "unresolved_topic": {"detected": false, "summary": "", "confidence": 0.0}, "emotion_followup": {"detected": false, "emotion": "", "summary": ""}}'

        analyzer = CloseoutAnalyzer(Model(), Config())
        result = await analyzer.analyze(
            "你要记得想好了告诉我啊",
            "知道了，去吧去吧，开会别走神。我想好了给你发消息。",
            [],
        )

        self.assertIsNotNone(result.deferred_reply)
        self.assertEqual(result.deferred_reply.delay_minutes, 8)

    async def test_no_false_positive_on_musing(self):
        from ai_companion.proactive.closeout_analyzer import CloseoutAnalyzer

        class Config:
            closeout_analyzer_enabled = False
            closeout_analyzer_max_tokens = 200
            closeout_analyzer_fallback_to_regex = True
            deferred_reply_default_delay_minutes = 8
            deferred_reply_min_delay_minutes = 2
            deferred_reply_max_delay_minutes = 60
            topic_continuation_min_score = 0.55

        analyzer = CloseoutAnalyzer(None, Config())
        result = await analyzer.analyze("你觉得呢？", "我想想也是，确实有道理", [])

        self.assertIsNone(result.deferred_reply)

    async def test_dedup_has_pending(self):
        from ai_companion.proactive.conversation_task_store import ConversationTaskStore
        from ai_companion.proactive.motives import (
            ConversationTask,
            ConversationTaskStatus,
            ConversationTaskType,
        )

        with TemporaryDirectory(prefix="proactive-dedup-") as td:
            now = datetime(2026, 5, 9, 10, 0, 0)
            store = ConversationTaskStore(td)
            store.upsert(
                ConversationTask(
                    id="existing-1",
                    bot_id="bot-a",
                    type=ConversationTaskType.DEFERRED_REPLY,
                    status=ConversationTaskStatus.PENDING,
                    session_id="session-x",
                    user_id="user-1",
                    platform="weixin",
                    target={},
                    created_at=now,
                    due_at=now + timedelta(minutes=5),
                    expires_at=now + timedelta(hours=24),
                    topic_summary="existing",
                    priority=100,
                )
            )

            self.assertTrue(store.has_pending("bot-a", "session-x", "deferred_reply"))
            self.assertFalse(store.has_pending("bot-a", "session-x", "topic_continuation"))


class DeferredDetectorNegationTest(unittest.TestCase):
    def test_negation_not_detected(self):
        from ai_companion.proactive.deferred_detector import DeferredReplyDetector

        detector = DeferredReplyDetector(default_delay_minutes=8, min_delay_minutes=2, max_delay_minutes=60)
        result = detector.detect("你能稍后回复我吗？", "不稍后回复你了，现在就说吧")
        self.assertIsNone(result)

    def test_positive_still_works(self):
        from ai_companion.proactive.deferred_detector import DeferredReplyDetector

        detector = DeferredReplyDetector(default_delay_minutes=8, min_delay_minutes=2, max_delay_minutes=60)
        result = detector.detect("你怎么看？", "等会跟你说，我先忙一下")
        self.assertIsNotNone(result)


class ProactiveSchedulerFallbackGuardTest(unittest.IsolatedAsyncioTestCase):
    async def test_scheduler_does_not_fallback_to_legacy_idle_path_when_orchestrator_exists(self):
        from ai_companion.proactive.scheduler import ProactiveScheduler

        class Config:
            is_active = True
            idle_reminder_enabled = True
            check_interval = 60
            preferred_contact_times = ["00:00-23:59"]
            timezone = "Asia/Shanghai"

        class State:
            def __init__(self):
                self._state = {}

            def save(self):
                return None

        class Orchestrator:
            def __init__(self):
                self.calls = 0

            async def tick(self):
                self.calls += 1
                return False

        class Engine:
            bot_id = "bot-a"
            config = Config()

            def __init__(self):
                self.state = State()
                self.orchestrator = Orchestrator()
                self.legacy_calls = 0

            async def check_and_maybe_remind(self):
                self.legacy_calls += 1
                return "legacy message"

        engine = Engine()
        scheduler = ProactiveScheduler(engine)
        scheduler._is_golden_hour = lambda: True

        await scheduler._tick()

        self.assertEqual(engine.orchestrator.calls, 1)
        self.assertEqual(engine.legacy_calls, 0)


if __name__ == "__main__":
    unittest.main()
