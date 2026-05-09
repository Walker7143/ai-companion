# Proactive Continuity Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace timer-like proactive wakeups with context-aware proactive behavior that can fulfill delayed-reply promises, continue unfinished topics, and explain the new controls in the Web UI.

**Architecture:** Keep the existing `ProactiveScheduler` process ownership and platform delivery path, but route each tick through a new motive/orchestration layer. The orchestrator collects candidate motives from persisted conversation tasks, recent working memory, life events, emotion triggers, and idle companionship, then sends one context-aware message through `ProactiveEngine` using the existing rate limits.

**Tech Stack:** Python 3.11, SQLite, JSON persona config under `persona/proactive.json`, React 19 + TypeScript Settings UI, existing unittest-style tests in `tests/*_test.py`, and `python -m compileall -q ai_companion`.

---

## Product Behavior

The user-facing behavior should be explained in Web UI as:

- `延迟回复履约`: If the Bot says "我想一下，一会儿回复你", it records a pending obligation and proactively returns to the same chat when due.
- `接上文续聊`: If the last conversation ended with an unresolved question, plan, worry, or interesting topic, proactive messages prefer continuing that context instead of opening with an unrelated greeting.
- `生活事件分享`: The Bot can still share concrete life events from `LifeEngine`, but those messages include the event context.
- `普通陪伴问候`: Plain idle greetings are the fallback and should only fire when no higher-quality motive exists.

Default priority order:

1. `deferred_reply`, hard obligation, highest priority.
2. `topic_continuation`, medium priority.
3. `emotion_followup`, medium priority.
4. `life_event`, medium-low priority.
5. `idle_ping`, lowest priority.

Important constraints:

- Deferred replies must target the same platform session/chat that created the promise.
- Motives must respect `enabled`, `mode`, golden hours, `max_daily`, and `min_interval_hours`, except that a deferred reply may use its own shorter delay and can be allowed to bypass the idle threshold.
- A proactive message must include its motive context in the generation prompt. If no motive is available, do not generate a random topic unless idle ping is enabled.
- Runtime state is under `~/.ai-companion/data/bots/{bot_id}/`, but tests should use temporary directories.

## Trigger Timing

The system has two separate timing moments:

1. **Immediately after each Bot reply:** run a lightweight "conversation closeout analysis". This analysis only records motives/tasks; it does not send another message in the same turn.
2. **When a motive becomes due:** `ProactiveScheduler` continues to tick in the background. On each tick, `ProactiveOrchestrator` loads due motives, scores them, and sends at most one context-aware message.

Default due times:

- `deferred_reply`: due after `deferred_reply_delay_minutes` when the Bot explicitly promised a later reply. Default 8 minutes.
- `topic_continuation`: due after `topic_continuation_idle_after_minutes` of user silence when the latest topic is unresolved. Default 45 minutes.
- `emotion_followup`: due after `emotion_followup_delay_minutes` when the user expressed a negative state. Default 20 minutes.
- `life_event`: due when a shareable life event is produced and passes rate/relationship checks.
- `idle_ping`: due only after the existing idle threshold. Default 24 hours.

Because dispatch still happens on scheduler ticks, real send time is `due_at` plus up to `check_interval_seconds`. For a human-like feel, production configs should prefer `check_interval_seconds` around 60-120 seconds while relying on motive due times and rate limits to prevent spam.

## File Structure

Create:

- `ai_companion/proactive/motives.py`: Dataclasses/enums for proactive motives and conversation tasks.
- `ai_companion/proactive/conversation_task_store.py`: SQLite persistence for pending/finished proactive conversation tasks.
- `ai_companion/proactive/deferred_detector.py`: Detect delayed-reply promises from user/bot turns.
- `ai_companion/proactive/orchestrator.py`: Candidate collection, scoring, dispatch, and task completion.
- `tests/proactive_orchestrator_test.py`: Focused unit tests for task storage, deferred detection, motive scoring, and same-chat delivery.

Modify:

- `ai_companion/proactive/config.py`: Add nested `conversation_continuity` defaults and typed accessors.
- `ai_companion/proactive/engine.py`: Add context-aware generation and public `send_contextual_proactive_message`.
- `ai_companion/proactive/scheduler.py`: Delegate `_tick()` to orchestrator when present, keep old path as fallback.
- `ai_companion/bot/instance.py`: Wire task store/orchestrator, record tasks after normal replies, pass gateway context to proactive state.
- `ai_companion/gateway/cmd.py`: Preserve enough platform/session metadata for same-chat proactive delivery.
- `ai_companion/gateway/admin_services.py`: Expose/save new config and schema descriptions.
- `ai-companion-ui/src/types/index.ts`: Add TypeScript shape for continuity config.
- `ai-companion-ui/src/pages/Settings/Settings.tsx`: Add Web UI controls and explanatory hints.
- `tests/system_test_suite.py`: Extend config roundtrip and add a system-level deferred-reply case.

Do not restructure gateway adapters in this phase. Use the existing `BotInstance._wrap_gateway_send()` platform sender.

## Config Shape

Add this to `ProactiveConfig.DEFAULT_CONFIG`:

```python
"conversation_continuity": {
    "enabled": True,
    "deferred_reply": {
        "enabled": True,
        "default_delay_minutes": 8,
        "min_delay_minutes": 2,
        "max_delay_minutes": 60,
        "expires_hours": 24,
        "bypass_idle_threshold": True,
    },
    "topic_continuation": {
        "enabled": True,
        "idle_after_minutes": 45,
        "expires_hours": 12,
        "min_score": 0.55,
    },
    "emotion_followup": {
        "enabled": True,
        "delay_minutes": 20,
        "expires_hours": 24,
    },
    "life_event": {
        "enabled": True,
    },
    "idle_ping": {
        "enabled": True,
    },
}
```

Public Web API fields should be flattened under `proactive.continuity_*` to match the existing Settings style:

- `continuity_enabled`
- `deferred_reply_enabled`
- `deferred_reply_delay_minutes`
- `deferred_reply_min_delay_minutes`
- `deferred_reply_max_delay_minutes`
- `deferred_reply_expires_hours`
- `deferred_reply_bypass_idle_threshold`
- `topic_continuation_enabled`
- `topic_continuation_idle_after_minutes`
- `topic_continuation_expires_hours`
- `topic_continuation_min_score`
- `emotion_followup_enabled`
- `emotion_followup_delay_minutes`
- `emotion_followup_expires_hours`
- `life_event_motive_enabled`
- `idle_ping_enabled`

Web UI copy should make the timing model explicit: "每次 Bot 回复后会立即记录可能的后续动机；真正发送会等动机到期，并在下一次后台检查时执行。"

## Task 1: Add Motive And Task Models

**Files:**
- Create: `ai_companion/proactive/motives.py`
- Test: `tests/proactive_orchestrator_test.py`

- [ ] **Step 1: Write failing tests for task serialization**

Add this to `tests/proactive_orchestrator_test.py`:

```python
import json
import unittest
from datetime import datetime, timedelta


class ConversationTaskModelTest(unittest.TestCase):
    def test_task_roundtrip_preserves_target_and_context(self):
        from ai_companion.proactive.motives import ConversationTask, ConversationTaskStatus, ConversationTaskType

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
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
PYTHONPATH=. python tests/proactive_orchestrator_test.py
```

Expected: `ModuleNotFoundError: No module named 'ai_companion.proactive.motives'`.

- [ ] **Step 3: Implement the model file**

Create `ai_companion/proactive/motives.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ConversationTaskType(str, Enum):
    DEFERRED_REPLY = "deferred_reply"
    TOPIC_CONTINUATION = "topic_continuation"
    EMOTION_FOLLOWUP = "emotion_followup"


class ConversationTaskStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ProactiveMotiveType(str, Enum):
    DEFERRED_REPLY = "deferred_reply"
    TOPIC_CONTINUATION = "topic_continuation"
    EMOTION_FOLLOWUP = "emotion_followup"
    LIFE_EVENT = "life_event"
    IDLE_PING = "idle_ping"


def _parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


@dataclass
class ConversationTask:
    id: str
    bot_id: str
    type: ConversationTaskType
    status: ConversationTaskStatus
    session_id: str
    user_id: str
    platform: str
    target: dict[str, Any]
    created_at: datetime
    due_at: datetime
    expires_at: datetime
    source_user_message: str = ""
    source_bot_message: str = ""
    topic_summary: str = ""
    priority: int = 50
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "type": self.type.value,
            "status": self.status.value,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "platform": self.platform,
            "target": self.target,
            "created_at": self.created_at.isoformat(),
            "due_at": self.due_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "source_user_message": self.source_user_message,
            "source_bot_message": self.source_bot_message,
            "topic_summary": self.topic_summary,
            "priority": self.priority,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationTask":
        return cls(
            id=str(data["id"]),
            bot_id=str(data["bot_id"]),
            type=ConversationTaskType(str(data["type"])),
            status=ConversationTaskStatus(str(data["status"])),
            session_id=str(data.get("session_id") or ""),
            user_id=str(data.get("user_id") or "default_user"),
            platform=str(data.get("platform") or ""),
            target=dict(data.get("target") or {}),
            created_at=_parse_dt(data.get("created_at")) or datetime.now(),
            due_at=_parse_dt(data.get("due_at")) or datetime.now(),
            expires_at=_parse_dt(data.get("expires_at")) or datetime.now(),
            source_user_message=str(data.get("source_user_message") or ""),
            source_bot_message=str(data.get("source_bot_message") or ""),
            topic_summary=str(data.get("topic_summary") or ""),
            priority=int(data.get("priority") or 50),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ProactiveMotive:
    type: ProactiveMotiveType
    priority: int
    reason: str
    prompt_context: str
    task: ConversationTask | None = None
    target: dict[str, Any] | None = None
    bypass_idle_threshold: bool = False
```

- [ ] **Step 4: Run the test**

Run:

```bash
PYTHONPATH=. python tests/proactive_orchestrator_test.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai_companion/proactive/motives.py tests/proactive_orchestrator_test.py
git commit -m "feat: add proactive motive models"
```

## Task 2: Persist Conversation Tasks

**Files:**
- Create: `ai_companion/proactive/conversation_task_store.py`
- Modify: `tests/proactive_orchestrator_test.py`

- [ ] **Step 1: Write failing tests for SQLite task store**

Append:

```python
from tempfile import TemporaryDirectory


class ConversationTaskStoreTest(unittest.TestCase):
    def test_due_tasks_are_returned_and_completed_tasks_are_hidden(self):
        from ai_companion.proactive.conversation_task_store import ConversationTaskStore
        from ai_companion.proactive.motives import ConversationTask, ConversationTaskStatus, ConversationTaskType

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

            store.mark_completed("due-task", completed_at=now)
            self.assertEqual(store.list_due(bot_id="bot-a", now=now), [])
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
PYTHONPATH=. python tests/proactive_orchestrator_test.py
```

Expected: `ModuleNotFoundError: No module named 'ai_companion.proactive.conversation_task_store'`.

- [ ] **Step 3: Implement SQLite store**

Create `ai_companion/proactive/conversation_task_store.py`:

```python
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .motives import ConversationTask, ConversationTaskStatus


class ConversationTaskStore:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / "conversation_tasks.db"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    bot_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    target_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    source_user_message TEXT NOT NULL,
                    source_bot_message TEXT NOT NULL,
                    topic_summary TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(bot_id, status, due_at)")

    def upsert(self, task: ConversationTask) -> None:
        data = task.to_dict()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    id, bot_id, type, status, session_id, user_id, platform,
                    target_json, created_at, due_at, expires_at,
                    source_user_message, source_bot_message, topic_summary,
                    priority, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    due_at=excluded.due_at,
                    expires_at=excluded.expires_at,
                    topic_summary=excluded.topic_summary,
                    metadata_json=excluded.metadata_json
                """,
                (
                    data["id"],
                    data["bot_id"],
                    data["type"],
                    data["status"],
                    data["session_id"],
                    data["user_id"],
                    data["platform"],
                    json.dumps(data["target"], ensure_ascii=False),
                    data["created_at"],
                    data["due_at"],
                    data["expires_at"],
                    data["source_user_message"],
                    data["source_bot_message"],
                    data["topic_summary"],
                    data["priority"],
                    json.dumps(data["metadata"], ensure_ascii=False),
                ),
            )

    def list_due(self, bot_id: str, now: datetime, limit: int = 10) -> list[ConversationTask]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, bot_id, type, status, session_id, user_id, platform,
                       target_json, created_at, due_at, expires_at,
                       source_user_message, source_bot_message, topic_summary,
                       priority, metadata_json
                FROM tasks
                WHERE bot_id = ? AND status = ? AND due_at <= ? AND expires_at >= ?
                ORDER BY priority DESC, due_at ASC
                LIMIT ?
                """,
                (bot_id, ConversationTaskStatus.PENDING.value, now.isoformat(), now.isoformat(), limit),
            ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def mark_completed(self, task_id: str, completed_at: datetime) -> None:
        self._mark(task_id, ConversationTaskStatus.COMPLETED, completed_at)

    def mark_expired(self, task_id: str, expired_at: datetime) -> None:
        self._mark(task_id, ConversationTaskStatus.EXPIRED, expired_at)

    def _mark(self, task_id: str, status: ConversationTaskStatus, when: datetime) -> None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT metadata_json FROM tasks WHERE id = ?", (task_id,)).fetchone()
            metadata = json.loads(row[0]) if row else {}
            metadata[f"{status.value}_at"] = when.isoformat()
            conn.execute(
                "UPDATE tasks SET status = ?, metadata_json = ? WHERE id = ?",
                (status.value, json.dumps(metadata, ensure_ascii=False), task_id),
            )

    def _row_to_task(self, row) -> ConversationTask:
        keys = [
            "id", "bot_id", "type", "status", "session_id", "user_id", "platform",
            "target", "created_at", "due_at", "expires_at",
            "source_user_message", "source_bot_message", "topic_summary",
            "priority", "metadata",
        ]
        data = dict(zip(keys, row))
        data["target"] = json.loads(data["target"] or "{}")
        data["metadata"] = json.loads(data["metadata"] or "{}")
        return ConversationTask.from_dict(data)
```

- [ ] **Step 4: Run tests**

Run:

```bash
PYTHONPATH=. python tests/proactive_orchestrator_test.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai_companion/proactive/conversation_task_store.py tests/proactive_orchestrator_test.py
git commit -m "feat: persist proactive conversation tasks"
```

## Task 3: Add Continuity Config

**Files:**
- Modify: `ai_companion/proactive/config.py`
- Modify: `tests/proactive_orchestrator_test.py`

- [ ] **Step 1: Write config tests**

Append:

```python
class ProactiveContinuityConfigTest(unittest.TestCase):
    def test_continuity_defaults_and_overrides(self):
        from pathlib import Path
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
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
PYTHONPATH=. python tests/proactive_orchestrator_test.py
```

Expected: `AttributeError` for missing config properties.

- [ ] **Step 3: Add config defaults and properties**

In `ai_companion/proactive/config.py`, add the config shape shown in the "Config Shape" section to `DEFAULT_CONFIG`.

Add helper and properties:

```python
    def _continuity_section(self, *keys: str) -> dict:
        current = self._config.get("conversation_continuity", {})
        for key in keys:
            current = current.get(key, {}) if isinstance(current, dict) else {}
        return current if isinstance(current, dict) else {}

    @property
    def continuity_enabled(self) -> bool:
        return bool(self._continuity_section().get("enabled", True))

    @property
    def deferred_reply_enabled(self) -> bool:
        return bool(self._continuity_section("deferred_reply").get("enabled", True))

    @property
    def deferred_reply_default_delay_minutes(self) -> int:
        return int(self._continuity_section("deferred_reply").get("default_delay_minutes", 8))

    @property
    def deferred_reply_min_delay_minutes(self) -> int:
        return int(self._continuity_section("deferred_reply").get("min_delay_minutes", 2))

    @property
    def deferred_reply_max_delay_minutes(self) -> int:
        return int(self._continuity_section("deferred_reply").get("max_delay_minutes", 60))

    @property
    def deferred_reply_expires_hours(self) -> int:
        return int(self._continuity_section("deferred_reply").get("expires_hours", 24))

    @property
    def deferred_reply_bypass_idle_threshold(self) -> bool:
        return bool(self._continuity_section("deferred_reply").get("bypass_idle_threshold", True))

    @property
    def topic_continuation_enabled(self) -> bool:
        return bool(self._continuity_section("topic_continuation").get("enabled", True))

    @property
    def topic_continuation_idle_after_minutes(self) -> int:
        return int(self._continuity_section("topic_continuation").get("idle_after_minutes", 45))

    @property
    def topic_continuation_expires_hours(self) -> int:
        return int(self._continuity_section("topic_continuation").get("expires_hours", 12))

    @property
    def topic_continuation_min_score(self) -> float:
        return float(self._continuity_section("topic_continuation").get("min_score", 0.55))

    @property
    def emotion_followup_enabled(self) -> bool:
        return bool(self._continuity_section("emotion_followup").get("enabled", True))

    @property
    def emotion_followup_delay_minutes(self) -> int:
        return int(self._continuity_section("emotion_followup").get("delay_minutes", 20))

    @property
    def emotion_followup_expires_hours(self) -> int:
        return int(self._continuity_section("emotion_followup").get("expires_hours", 24))

    @property
    def life_event_motive_enabled(self) -> bool:
        return bool(self._continuity_section("life_event").get("enabled", True))

    @property
    def idle_ping_enabled(self) -> bool:
        return bool(self._continuity_section("idle_ping").get("enabled", True))
```

- [ ] **Step 4: Run tests**

Run:

```bash
PYTHONPATH=. python tests/proactive_orchestrator_test.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai_companion/proactive/config.py tests/proactive_orchestrator_test.py
git commit -m "feat: add proactive continuity config"
```

## Task 4: Detect Delayed Reply Promises

**Files:**
- Create: `ai_companion/proactive/deferred_detector.py`
- Modify: `tests/proactive_orchestrator_test.py`

- [ ] **Step 1: Write detector tests**

Append:

```python
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
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
PYTHONPATH=. python tests/proactive_orchestrator_test.py
```

Expected: `ModuleNotFoundError` for `deferred_detector`.

- [ ] **Step 3: Implement rule-based detector**

Create `ai_companion/proactive/deferred_detector.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class DeferredReplyDetection:
    delay_minutes: int
    topic_summary: str


class DeferredReplyDetector:
    PROMISE_PATTERNS = (
        re.compile(r"(一会儿|等会|待会|晚点|稍后|过会儿).{0,12}(回复|告诉|跟你说|和你说|回你)"),
        re.compile(r"(我想想|我想一下|我考虑一下|我查一下|我看一下).{0,16}(回复你|告诉你|再说|再跟你说)?"),
    )
    DONE_HINTS = ("我想了一下", "我查到了", "结论是", "所以我觉得", "可以先", "我建议")

    def __init__(self, default_delay_minutes: int, min_delay_minutes: int, max_delay_minutes: int):
        self.default_delay_minutes = default_delay_minutes
        self.min_delay_minutes = min_delay_minutes
        self.max_delay_minutes = max_delay_minutes

    def detect(self, user_message: str, bot_message: str) -> DeferredReplyDetection | None:
        text = str(bot_message or "").strip()
        if not text:
            return None
        if any(hint in text for hint in self.DONE_HINTS) and "一会" not in text and "晚点" not in text and "稍后" not in text:
            return None
        if not any(pattern.search(text) for pattern in self.PROMISE_PATTERNS):
            return None
        delay = self._extract_delay_minutes(text)
        summary = f"稍后回复：用户说「{str(user_message or '')[:80]}」，Bot 承诺「{text[:80]}」"
        return DeferredReplyDetection(delay_minutes=delay, topic_summary=summary)

    def _extract_delay_minutes(self, text: str) -> int:
        match = re.search(r"(\d{1,3})\s*分钟", text)
        if match:
            value = int(match.group(1))
        elif re.search(r"半小时|三十分钟", text):
            value = 30
        else:
            value = self.default_delay_minutes
        return max(self.min_delay_minutes, min(self.max_delay_minutes, value))
```

- [ ] **Step 4: Run tests**

Run:

```bash
PYTHONPATH=. python tests/proactive_orchestrator_test.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai_companion/proactive/deferred_detector.py tests/proactive_orchestrator_test.py
git commit -m "feat: detect deferred reply promises"
```

## Task 5: Run Conversation Closeout Analysis After Bot Replies

**Files:**
- Modify: `ai_companion/bot/instance.py`
- Modify: `tests/bot_instance_test.py`

- [ ] **Step 1: Write BotInstance task-recording test**

Add to `tests/bot_instance_test.py`:

```python
    async def test_deferred_reply_promise_records_conversation_task(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from ai_companion.proactive.motives import ConversationTaskType

        class PromiseModel:
            async def chat(self, messages, system_prompt=None, **kwargs):
                return "我想一下，一会儿回复你。"

        with TemporaryDirectory(prefix="bot-deferred-task-") as td:
            root = Path(td)
            persona_dir = root / "data" / "bots" / "promise_bot" / "persona"
            persona_dir.mkdir(parents=True)
            for name, payload in {
                "profile.json": {"name": "测试", "age": 20, "occupation": "学生", "personality_tags": ["温柔"]},
                "backstory.json": {},
                "values.json": {},
                "speaking_style.json": {},
                "proactive.json": {
                    "enabled": True,
                    "mode": "active",
                    "conversation_continuity": {"deferred_reply": {"default_delay_minutes": 8}},
                },
                "life.json": {},
            }.items():
                (persona_dir / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            bot = BotInstance(
                {"id": "promise_bot", "name": "测试", "data_dir": str(root / "data" / "bots")},
                model=PromiseModel(),
                data_dir=root / "data" / "bots",
                memory_config={"embedding": "none"},
                refusal_enabled=False,
            )
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

            due = bot.conversation_task_store.list_due("promise_bot", datetime.now() + timedelta(minutes=9))
            self.assertEqual(len(due), 1)
            self.assertEqual(due[0].type, ConversationTaskType.DEFERRED_REPLY)
            self.assertEqual(due[0].target["chat_id"], "wx-1")
            await bot.close()
```

Ensure `json`, `datetime`, and `timedelta` are imported in the test file if missing.

- [ ] **Step 2: Run the failing test**

Run:

```bash
PYTHONPATH=. python tests/bot_instance_test.py -k deferred
```

If `unittest` does not support `-k` in this environment, run:

```bash
PYTHONPATH=. python tests/bot_instance_test.py
```

Expected: missing `conversation_task_store` or no task recorded.

- [ ] **Step 3: Wire store and closeout analysis in BotInstance**

In `ai_companion/bot/instance.py`:

Add imports:

```python
import uuid
from datetime import datetime, timedelta
from ..proactive.conversation_task_store import ConversationTaskStore
from ..proactive.deferred_detector import DeferredReplyDetector
from ..proactive.motives import ConversationTask, ConversationTaskStatus, ConversationTaskType
```

In `__init__`, after proactive state creation:

```python
        self.conversation_task_store = ConversationTaskStore(self._data_dir / self.id)
```

Add method. This method is the post-reply closeout analysis: it runs immediately after the Bot has produced a normal reply, records due-later tasks, and never sends a proactive message inside the same user turn.

```python
    def _run_proactive_closeout_analysis(self, user_input: str, response: str, memory_turn_context: dict | None) -> None:
        if not self.proactive_config.continuity_enabled or not self.proactive_config.deferred_reply_enabled:
            return
        context = memory_turn_context if isinstance(memory_turn_context, dict) else {}
        detector = DeferredReplyDetector(
            default_delay_minutes=self.proactive_config.deferred_reply_default_delay_minutes,
            min_delay_minutes=self.proactive_config.deferred_reply_min_delay_minutes,
            max_delay_minutes=self.proactive_config.deferred_reply_max_delay_minutes,
        )
        detected = detector.detect(user_input, response)
        if detected is None:
            return
        now = datetime.now()
        platform = str(context.get("platform") or self.proactive_config.platform_type or "cli")
        chat_id = str(context.get("chat_id") or "")
        session_id = str(context.get("session_id") or getattr(getattr(self.memory, "working", None), "current_session", "") or "")
        target = {
            "platform": platform,
            "chat_id": chat_id,
            "name": str((context.get("metadata") or {}).get("chat_name") or ""),
        }
        task = ConversationTask(
            id=uuid.uuid4().hex,
            bot_id=self.id,
            type=ConversationTaskType.DEFERRED_REPLY,
            status=ConversationTaskStatus.PENDING,
            session_id=session_id,
            user_id=str(context.get("user_id") or "default_user"),
            platform=platform,
            target=target,
            created_at=now,
            due_at=now + timedelta(minutes=detected.delay_minutes),
            expires_at=now + timedelta(hours=self.proactive_config.deferred_reply_expires_hours),
            source_user_message=user_input,
            source_bot_message=response,
            topic_summary=detected.topic_summary,
            priority=100,
        )
        self.conversation_task_store.upsert(task)
```

For later motive types, keep the same closeout method and add separate helpers:

```python
        self._record_topic_continuation_task(user_input, response, memory_turn_context)
        self._record_emotion_followup_task(user_input, response, memory_turn_context)
```

`_record_topic_continuation_task` should set `due_at = now + timedelta(minutes=self.proactive_config.topic_continuation_idle_after_minutes)`. `_record_emotion_followup_task` should set `due_at = now + timedelta(minutes=self.proactive_config.emotion_followup_delay_minutes)`. Both are due-later records only.

Call this after `response = self._polish_response(...)` and before scheduling `self.memory.on_message(...)` in both memory and no-memory branches:

```python
            self._run_proactive_closeout_analysis(user_input, response, memory_turn_context)
```

- [ ] **Step 4: Run tests**

Run:

```bash
PYTHONPATH=. python tests/bot_instance_test.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai_companion/bot/instance.py tests/bot_instance_test.py
git commit -m "feat: record deferred proactive tasks"
```

## Task 6: Add Context-Aware Message Generation

**Files:**
- Modify: `ai_companion/proactive/engine.py`
- Modify: `tests/proactive_engine_test.py`

- [ ] **Step 1: Write engine prompt test**

Add to `tests/proactive_engine_test.py`:

```python
class ProactiveEngineContextualMessageTest(unittest.IsolatedAsyncioTestCase):
    async def test_contextual_message_prompt_includes_motive_and_prior_topic(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from ai_companion.proactive.config import ProactiveConfig
        from ai_companion.proactive.engine import ProactiveEngine
        from ai_companion.proactive.motives import ProactiveMotive, ProactiveMotiveType
        from ai_companion.proactive.state import ProactiveState

        class CaptureModel:
            def __init__(self):
                self.calls = []

            async def chat(self, messages, system_prompt=None, **kwargs):
                self.calls.append({"messages": messages, "system_prompt": system_prompt})
                return '{"opening":"刚才你问的那个问题","topic":"我想了一下，可以先从小范围试试","ending":"你觉得呢？"}'

        with TemporaryDirectory(prefix="proactive-contextual-") as td:
            root = Path(td)
            persona = root / "persona"
            persona.mkdir()
            model = CaptureModel()
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
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
PYTHONPATH=. python tests/proactive_engine_test.py
```

Expected: `AttributeError: 'ProactiveEngine' object has no attribute 'generate_contextual_message'`.

- [ ] **Step 3: Implement contextual generation**

Add imports:

```python
from .motives import ProactiveMotive
```

Add prompt:

```python
GENERATE_CONTEXTUAL_MESSAGE_PROMPT = """【角色】
你是{bot_name}，性格：{personality_tags}

【Bot 时间线】
{bot_time_context}

【主动联系原因】
{motive_reason}

【必须接上的上下文】
{motive_context}

【当前关系】
{relationship_desc}

【要求】
- 自然接上之前的话题，不要像重新开一个话题。
- 如果这是稍后回复，要表现为你回来履行承诺。
- 不要使用“在吗”“最近怎么样”这类无上下文开场。
- 只写一条适合直接发送的短消息。

【输出格式】
输出 JSON：{{"opening":"开头","topic":"主体","ending":"结尾"}}
只输出 JSON，不要其他内容。"""
```

Add methods to `ProactiveEngine`:

```python
    async def generate_contextual_message(self, motive: ProactiveMotive) -> str:
        if self.model is None:
            return self._fallback_contextual_message(motive)
        personality_type = self._get_personality_type()
        rel_desc = await self._get_relationship_desc()
        prompt = GENERATE_CONTEXTUAL_MESSAGE_PROMPT.format(
            bot_name=getattr(self, "bot_name", self.bot_id),
            personality_tags=personality_type,
            bot_time_context=self._build_bot_time_context(),
            motive_reason=motive.reason,
            motive_context=motive.prompt_context,
            relationship_desc=rel_desc,
        )
        try:
            response = await self.model.chat(messages=[{"role": "user", "content": prompt}], system_prompt=None)
            parsed = self._parse_structured_message(response)
            if parsed:
                return parsed
            cleaned = self._clean_message(response)
            if cleaned and not self._is_placeholder_message(cleaned):
                return cleaned
        except Exception as e:
            logger.error(f"[ProactiveEngine] 上下文主动消息生成失败: {e}")
        return self._fallback_contextual_message(motive)

    async def send_contextual_proactive_message(self, motive: ProactiveMotive) -> bool:
        message = await self.generate_contextual_message(motive)
        return await self._send_proactive_message(message)

    def _fallback_contextual_message(self, motive: ProactiveMotive) -> str:
        if motive.type.value == "deferred_reply":
            return "刚才你问的那个问题，我想了一下，还是想接着跟你说。"
        if motive.type.value == "topic_continuation":
            return "刚才那个话题我还在想，想接着跟你聊聊。"
        if motive.type.value == "emotion_followup":
            return "我刚才还是有点放心不下你，想问问你现在好些了吗？"
        return self._get_fallback_message("with_topic")
```

- [ ] **Step 4: Run tests**

Run:

```bash
PYTHONPATH=. python tests/proactive_engine_test.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai_companion/proactive/engine.py tests/proactive_engine_test.py
git commit -m "feat: generate context-aware proactive messages"
```

## Task 7: Implement Orchestrator And Scheduler Delegation

**Files:**
- Create: `ai_companion/proactive/orchestrator.py`
- Modify: `ai_companion/proactive/scheduler.py`
- Modify: `ai_companion/bot/instance.py`
- Modify: `tests/proactive_orchestrator_test.py`

- [ ] **Step 1: Write orchestrator dispatch test**

Append:

```python
class ProactiveOrchestratorTest(unittest.IsolatedAsyncioTestCase):
    async def test_dispatches_due_deferred_task_and_marks_completed(self):
        from tempfile import TemporaryDirectory
        from ai_companion.proactive.conversation_task_store import ConversationTaskStore
        from ai_companion.proactive.motives import ConversationTask, ConversationTaskStatus, ConversationTaskType
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
```

- [ ] **Step 2: Run failing test**

Run:

```bash
PYTHONPATH=. python tests/proactive_orchestrator_test.py
```

Expected: missing `orchestrator`.

- [ ] **Step 3: Implement orchestrator**

Create `ai_companion/proactive/orchestrator.py`:

```python
from __future__ import annotations

import logging
from datetime import datetime

from .conversation_task_store import ConversationTaskStore
from .motives import ConversationTaskType, ProactiveMotive, ProactiveMotiveType

logger = logging.getLogger(__name__)


class ProactiveOrchestrator:
    def __init__(self, engine, task_store: ConversationTaskStore):
        self.engine = engine
        self.config = engine.config
        self.task_store = task_store

    async def tick(self, now: datetime | None = None) -> bool:
        now = now or datetime.now()
        if not self.config.continuity_enabled:
            return False
        motive = self._select_motive(now)
        if motive is None:
            return False
        sent = await self.engine.send_contextual_proactive_message(motive)
        if sent and motive.task:
            self.task_store.mark_completed(motive.task.id, completed_at=now)
        return bool(sent)

    def _select_motive(self, now: datetime) -> ProactiveMotive | None:
        candidates = self._due_task_motives(now)
        if not candidates:
            return None
        return sorted(candidates, key=lambda m: (-m.priority, m.task.due_at if m.task else now))[0]

    def _due_task_motives(self, now: datetime) -> list[ProactiveMotive]:
        motives: list[ProactiveMotive] = []
        for task in self.task_store.list_due(self.engine.bot_id, now=now, limit=10):
            if task.type == ConversationTaskType.DEFERRED_REPLY and not self.config.deferred_reply_enabled:
                continue
            motive_type = ProactiveMotiveType(task.type.value)
            motives.append(
                ProactiveMotive(
                    type=motive_type,
                    priority=task.priority,
                    reason=self._reason_for_task(task),
                    prompt_context=self._context_for_task(task),
                    task=task,
                    target=task.target,
                    bypass_idle_threshold=(
                        task.type == ConversationTaskType.DEFERRED_REPLY
                        and self.config.deferred_reply_bypass_idle_threshold
                    ),
                )
            )
        return motives

    def _reason_for_task(self, task) -> str:
        if task.type == ConversationTaskType.DEFERRED_REPLY:
            return "继续刚才承诺的稍后回复"
        if task.type == ConversationTaskType.TOPIC_CONTINUATION:
            return "接上之前未完成的话题"
        if task.type == ConversationTaskType.EMOTION_FOLLOWUP:
            return "关心用户之前提到的情绪状态"
        return "继续之前的对话"

    def _context_for_task(self, task) -> str:
        return (
            f"上一段话题摘要：{task.topic_summary}\n"
            f"用户当时说：{task.source_user_message}\n"
            f"Bot 当时说：{task.source_bot_message}\n"
            f"平台：{task.platform}\n"
            f"会话：{task.session_id}"
        )
```

- [ ] **Step 4: Delegate scheduler tick**

In `ai_companion/proactive/scheduler.py`, inside `_tick()` before old idle reminder logic:

```python
        orchestrator = getattr(self.engine, "orchestrator", None)
        if orchestrator is not None:
            sent = await orchestrator.tick()
            if sent:
                logger.info("[ProactiveScheduler] 已通过 motive orchestrator 发送主动消息")
                return
```

In `BotInstance.__init__`, after creating `conversation_task_store`:

```python
        from ..proactive.orchestrator import ProactiveOrchestrator
        self.proactive_orchestrator = ProactiveOrchestrator(
            engine=self.proactive_engine,
            task_store=self.conversation_task_store,
        )
        self.proactive_engine.orchestrator = self.proactive_orchestrator
```

- [ ] **Step 5: Run tests**

Run:

```bash
PYTHONPATH=. python tests/proactive_orchestrator_test.py
PYTHONPATH=. python tests/proactive_engine_test.py
PYTHONPATH=. python tests/bot_instance_test.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ai_companion/proactive/orchestrator.py ai_companion/proactive/scheduler.py ai_companion/bot/instance.py tests/proactive_orchestrator_test.py
git commit -m "feat: dispatch proactive motives through orchestrator"
```

## Task 8: Ensure Same-Chat Delivery For Deferred Motives

**Files:**
- Modify: `ai_companion/bot/instance.py`
- Modify: `tests/proactive_orchestrator_test.py`

- [ ] **Step 1: Write target override test**

Append:

```python
class ProactiveTargetOverrideTest(unittest.IsolatedAsyncioTestCase):
    async def test_engine_sender_uses_motive_target_for_gateway_send(self):
        from ai_companion.proactive.motives import ProactiveMotive, ProactiveMotiveType

        sent = []

        class Engine:
            async def generate_contextual_message(self, motive):
                return "刚才那个问题，我想了一下。"

            async def _platform_sender(self, message, target=None):
                sent.append({"message": message, "target": target})
                return True

        engine = Engine()
        motive = ProactiveMotive(
            type=ProactiveMotiveType.DEFERRED_REPLY,
            priority=100,
            reason="继续稍后回复",
            prompt_context="上下文",
            target={"platform": "weixin", "chat_id": "wx-1"},
        )

        # This calls the method added to ProactiveEngine as an unbound method.
        from ai_companion.proactive.engine import ProactiveEngine
        ok = await ProactiveEngine.send_contextual_proactive_message(engine, motive)

        self.assertTrue(ok)
        self.assertEqual(sent[0]["target"]["chat_id"], "wx-1")
```

- [ ] **Step 2: Run failing test**

Run:

```bash
PYTHONPATH=. python tests/proactive_orchestrator_test.py
```

Expected: sender receives no target.

- [ ] **Step 3: Update contextual send path**

In `ProactiveEngine.send_contextual_proactive_message`, replace the body with:

```python
        message = await self.generate_contextual_message(motive)
        if motive.target and self._platform_sender:
            try:
                sent = await self._platform_sender(message, target=motive.target)
                if sent is False:
                    return False
            except TypeError:
                sent = await self._platform_sender(message)
                if sent is False:
                    return False
            except Exception as e:
                logger.error(f"[ProactiveEngine] 上下文主动消息发送失败: {e}")
                return False
            self.state.increment_proactive()
            self.state.unreplied_count = self.state.unreplied_count + 1
            cooldown_end = datetime.now() + timedelta(hours=self.config.min_interval_hours)
            self.state.set_cooldown("idle_reminder", cooldown_end)
            return True
        return await self._send_proactive_message(message)
```

Update `BotInstance.set_proactive_platform()` lambdas to accept optional target:

```python
self.proactive_engine._platform_sender = lambda msg, target=None: self._wrap_gateway_send(msg, gateway_adapter, str(ptype).lower(), target=target)
```

Update `_wrap_gateway_send` signature:

```python
    async def _wrap_gateway_send(self, msg: str, gateway_adapter, platform_type: str, target: dict | None = None):
```

Inside `_wrap_gateway_send`, before reading `home_channel`, use:

```python
            if isinstance(target, dict) and target.get("chat_id"):
                return await gateway_adapter.send_message(str(target["chat_id"]), msg)
```

Use the adapter's actual send method signature. If the adapter exposes `send(bot_id, msg)` instead, adapt this line to the existing method used in `_wrap_gateway_send`; do not add a new adapter API in this task.

- [ ] **Step 4: Run tests**

Run:

```bash
PYTHONPATH=. python tests/proactive_orchestrator_test.py
PYTHONPATH=. python tests/weixin_gateway_test.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai_companion/proactive/engine.py ai_companion/bot/instance.py tests/proactive_orchestrator_test.py
git commit -m "feat: deliver deferred proactive replies to source chat"
```

## Task 9: Add Topic Continuation Candidate

**Files:**
- Modify: `ai_companion/proactive/orchestrator.py`
- Modify: `tests/proactive_orchestrator_test.py`

- [ ] **Step 1: Write topic continuation test**

Append:

```python
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

        orch = ProactiveOrchestrator(engine=Engine(), task_store=None)
        motive = orch._topic_continuation_motive(now=datetime(2026, 5, 9, 10, 0, 0))

        self.assertIsNotNone(motive)
        self.assertIn("继续做这个项目", motive.prompt_context)
```

- [ ] **Step 2: Run failing test**

Run:

```bash
PYTHONPATH=. python tests/proactive_orchestrator_test.py
```

Expected: `_topic_continuation_motive` missing.

- [ ] **Step 3: Implement heuristic topic continuation**

In `ProactiveOrchestrator._select_motive`, after due task motives:

```python
        topic = self._topic_continuation_motive(now)
        if topic:
            candidates.append(topic)
```

Add:

```python
    def _topic_continuation_motive(self, now: datetime) -> ProactiveMotive | None:
        if not getattr(self.config, "topic_continuation_enabled", False):
            return None
        memory = getattr(self.engine, "memory", None)
        working = getattr(memory, "working", None)
        if working is None:
            return None
        recent = working.get_recent(getattr(working, "current_session", None), turns=3)
        if not recent:
            return None
        text = "\n".join(f"{m.get('role')}：{m.get('content')}" for m in reversed(recent))
        unresolved_markers = ("吗", "？", "?", "怎么看", "怎么办", "要不要", "该不该", "继续", "选择")
        if not any(marker in text for marker in unresolved_markers):
            return None
        score = 0.7
        if score < self.config.topic_continuation_min_score:
            return None
        return ProactiveMotive(
            type=ProactiveMotiveType.TOPIC_CONTINUATION,
            priority=70,
            reason="接上之前未完成的话题",
            prompt_context=f"最近对话里还有未完成的话题：\n{text}",
        )
```

- [ ] **Step 4: Run tests**

Run:

```bash
PYTHONPATH=. python tests/proactive_orchestrator_test.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai_companion/proactive/orchestrator.py tests/proactive_orchestrator_test.py
git commit -m "feat: add topic-continuation proactive motive"
```

## Task 10: Expose Config Through Admin API

**Files:**
- Modify: `ai_companion/gateway/admin_services.py`
- Modify: `tests/system_test_suite.py`

- [ ] **Step 1: Extend system config roundtrip assertions**

In `case_web_config_center_roundtrip`, add these fields to the `"proactive"` update payload:

```python
                        "continuity_enabled": True,
                        "deferred_reply_enabled": True,
                        "deferred_reply_delay_minutes": 9,
                        "deferred_reply_min_delay_minutes": 2,
                        "deferred_reply_max_delay_minutes": 45,
                        "deferred_reply_expires_hours": 18,
                        "deferred_reply_bypass_idle_threshold": True,
                        "topic_continuation_enabled": True,
                        "topic_continuation_idle_after_minutes": 50,
                        "topic_continuation_expires_hours": 10,
                        "topic_continuation_min_score": 0.6,
                        "emotion_followup_enabled": True,
                        "emotion_followup_delay_minutes": 25,
                        "emotion_followup_expires_hours": 20,
                        "life_event_motive_enabled": True,
                        "idle_ping_enabled": False,
```

Add assertions near existing proactive assertions:

```python
            and proactive["conversation_continuity"]["deferred_reply"]["default_delay_minutes"] == 9
            and proactive["conversation_continuity"]["topic_continuation"]["idle_after_minutes"] == 50
            and proactive["conversation_continuity"]["idle_ping"]["enabled"] is False
            and web_after["proactive"]["deferred_reply_delay_minutes"] == 9
```

- [ ] **Step 2: Run failing system case**

Run:

```bash
PYTHONPATH=. python tests/system_test_suite.py
```

Expected: T36 fails because the API does not expose or persist new fields.

- [ ] **Step 3: Update schema copy**

In `WEB_CONFIG_SCHEMA` proactive section, update description:

```python
"description": "控制 Bot 主动联系用户的频率、时段、对话连续性、情绪触发和投递平台。",
```

Add fields:

```python
                "continuity_enabled": "启用后，主动消息会优先履行稍后回复、接上未完成话题，再考虑普通问候。",
                "deferred_reply_enabled": "Bot 承诺稍后回复时，到期自动回到同一会话继续。",
                "deferred_reply_delay_minutes": "没有明确时间时，默认多久后履行稍后回复。",
                "topic_continuation_enabled": "允许 Bot 基于最近未完成话题继续对话。",
                "topic_continuation_idle_after_minutes": "用户沉默多久后才考虑接上文。",
                "idle_ping_enabled": "没有具体动机时，是否允许普通陪伴问候。",
```

- [ ] **Step 4: Update public/save methods**

In `_public_proactive`, add:

```python
        continuity = cfg.get("conversation_continuity", {})
        deferred = continuity.get("deferred_reply", {})
        topic = continuity.get("topic_continuation", {})
        emotion_followup = continuity.get("emotion_followup", {})
        life_event = continuity.get("life_event", {})
        idle_ping = continuity.get("idle_ping", {})
```

Return fields:

```python
            "continuity_enabled": bool(continuity.get("enabled", True)),
            "deferred_reply_enabled": bool(deferred.get("enabled", True)),
            "deferred_reply_delay_minutes": _as_int(deferred.get("default_delay_minutes"), 8, 1),
            "deferred_reply_min_delay_minutes": _as_int(deferred.get("min_delay_minutes"), 2, 1),
            "deferred_reply_max_delay_minutes": _as_int(deferred.get("max_delay_minutes"), 60, 1),
            "deferred_reply_expires_hours": _as_int(deferred.get("expires_hours"), 24, 1),
            "deferred_reply_bypass_idle_threshold": bool(deferred.get("bypass_idle_threshold", True)),
            "topic_continuation_enabled": bool(topic.get("enabled", True)),
            "topic_continuation_idle_after_minutes": _as_int(topic.get("idle_after_minutes"), 45, 1),
            "topic_continuation_expires_hours": _as_int(topic.get("expires_hours"), 12, 1),
            "topic_continuation_min_score": _as_float(topic.get("min_score"), 0.55, 0, 1),
            "emotion_followup_enabled": bool(emotion_followup.get("enabled", True)),
            "emotion_followup_delay_minutes": _as_int(emotion_followup.get("delay_minutes"), 20, 1),
            "emotion_followup_expires_hours": _as_int(emotion_followup.get("expires_hours"), 24, 1),
            "life_event_motive_enabled": bool(life_event.get("enabled", True)),
            "idle_ping_enabled": bool(idle_ping.get("enabled", True)),
```

In `_save_proactive`, add:

```python
        continuity = existing.setdefault("conversation_continuity", {})
        deferred = continuity.setdefault("deferred_reply", {})
        topic = continuity.setdefault("topic_continuation", {})
        emotion_followup = continuity.setdefault("emotion_followup", {})
        life_event = continuity.setdefault("life_event", {})
        idle_ping = continuity.setdefault("idle_ping", {})
        continuity["enabled"] = bool(proactive_data.get("continuity_enabled", continuity.get("enabled", True)))
        deferred["enabled"] = bool(proactive_data.get("deferred_reply_enabled", deferred.get("enabled", True)))
        deferred["default_delay_minutes"] = _as_int(proactive_data.get("deferred_reply_delay_minutes"), deferred.get("default_delay_minutes", 8), 1)
        deferred["min_delay_minutes"] = _as_int(proactive_data.get("deferred_reply_min_delay_minutes"), deferred.get("min_delay_minutes", 2), 1)
        deferred["max_delay_minutes"] = _as_int(proactive_data.get("deferred_reply_max_delay_minutes"), deferred.get("max_delay_minutes", 60), 1)
        deferred["expires_hours"] = _as_int(proactive_data.get("deferred_reply_expires_hours"), deferred.get("expires_hours", 24), 1)
        deferred["bypass_idle_threshold"] = bool(proactive_data.get("deferred_reply_bypass_idle_threshold", deferred.get("bypass_idle_threshold", True)))
        topic["enabled"] = bool(proactive_data.get("topic_continuation_enabled", topic.get("enabled", True)))
        topic["idle_after_minutes"] = _as_int(proactive_data.get("topic_continuation_idle_after_minutes"), topic.get("idle_after_minutes", 45), 1)
        topic["expires_hours"] = _as_int(proactive_data.get("topic_continuation_expires_hours"), topic.get("expires_hours", 12), 1)
        topic["min_score"] = _as_float(proactive_data.get("topic_continuation_min_score"), topic.get("min_score", 0.55), 0, 1)
        emotion_followup["enabled"] = bool(proactive_data.get("emotion_followup_enabled", emotion_followup.get("enabled", True)))
        emotion_followup["delay_minutes"] = _as_int(proactive_data.get("emotion_followup_delay_minutes"), emotion_followup.get("delay_minutes", 20), 1)
        emotion_followup["expires_hours"] = _as_int(proactive_data.get("emotion_followup_expires_hours"), emotion_followup.get("expires_hours", 24), 1)
        life_event["enabled"] = bool(proactive_data.get("life_event_motive_enabled", life_event.get("enabled", True)))
        idle_ping["enabled"] = bool(proactive_data.get("idle_ping_enabled", idle_ping.get("enabled", True)))
```

- [ ] **Step 5: Run system test**

Run:

```bash
PYTHONPATH=. python tests/system_test_suite.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ai_companion/gateway/admin_services.py tests/system_test_suite.py
git commit -m "feat: expose proactive continuity config"
```

## Task 11: Add Web UI Controls And Explanations

**Files:**
- Modify: `ai-companion-ui/src/types/index.ts`
- Modify: `ai-companion-ui/src/pages/Settings/Settings.tsx`

- [ ] **Step 1: Extend TypeScript config type**

In `ProactiveConfig`, add:

```ts
  continuity_enabled: boolean;
  deferred_reply_enabled: boolean;
  deferred_reply_delay_minutes: number;
  deferred_reply_min_delay_minutes: number;
  deferred_reply_max_delay_minutes: number;
  deferred_reply_expires_hours: number;
  deferred_reply_bypass_idle_threshold: boolean;
  topic_continuation_enabled: boolean;
  topic_continuation_idle_after_minutes: number;
  topic_continuation_expires_hours: number;
  topic_continuation_min_score: number;
  emotion_followup_enabled: boolean;
  emotion_followup_delay_minutes: number;
  emotion_followup_expires_hours: number;
  life_event_motive_enabled: boolean;
  idle_ping_enabled: boolean;
```

- [ ] **Step 2: Add defaults**

In `defaultProactive`, add:

```ts
  continuity_enabled: true,
  deferred_reply_enabled: true,
  deferred_reply_delay_minutes: 8,
  deferred_reply_min_delay_minutes: 2,
  deferred_reply_max_delay_minutes: 60,
  deferred_reply_expires_hours: 24,
  deferred_reply_bypass_idle_threshold: true,
  topic_continuation_enabled: true,
  topic_continuation_idle_after_minutes: 45,
  topic_continuation_expires_hours: 12,
  topic_continuation_min_score: 0.55,
  emotion_followup_enabled: true,
  emotion_followup_delay_minutes: 20,
  emotion_followup_expires_hours: 24,
  life_event_motive_enabled: true,
  idle_ping_enabled: true,
```

- [ ] **Step 3: Add warnings**

In `warnings`, add:

```ts
    if (draft.proactive.enabled && draft.proactive.continuity_enabled && !draft.proactive.deferred_reply_enabled) {
      items.push('已关闭延迟回复履约：Bot 说“稍后回复你”后不会自动回来继续。');
    }
    if (draft.proactive.enabled && draft.proactive.idle_ping_enabled && !draft.proactive.topic_continuation_enabled) {
      items.push('已关闭接上文续聊但保留普通问候，主动消息可能更像定时问候。');
    }
```

- [ ] **Step 4: Add controls in proactive section**

In the proactive `SectionCard`, after the enabled toggle and before timing inputs, add:

```tsx
        <div style={{ border: '1px solid var(--border-subtle)', borderRadius: 8, padding: 16, marginBottom: 16, background: 'var(--bg-secondary)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>对话连续性</div>
              <FieldHint text="每次 Bot 回复后会立即记录可能的后续动机；真正发送会等动机到期，并在下一次后台检查时执行。" />
              <FieldHint text="主动消息会优先履行“稍后回复”、接上未完成话题，再考虑生活事件或普通问候。" />
            </div>
            <Toggle checked={draft.proactive.continuity_enabled} onChange={(event) => patchProactive({ continuity_enabled: event.target.checked })} />
          </div>
          <div style={{ ...gridStyle, marginTop: 16 }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>延迟回复履约</div>
              <Toggle checked={draft.proactive.deferred_reply_enabled} onChange={(event) => patchProactive({ deferred_reply_enabled: event.target.checked })} />
              <FieldHint text="Bot 说“一会儿回复你/我想想晚点告诉你”后，到期会回到同一会话继续。" />
            </div>
            <Input label="默认延迟（分钟）" type="number" value={draft.proactive.deferred_reply_delay_minutes} onChange={(event) => patchProactive({ deferred_reply_delay_minutes: Number(event.target.value) })} />
            <Input label="最短延迟（分钟）" type="number" value={draft.proactive.deferred_reply_min_delay_minutes} onChange={(event) => patchProactive({ deferred_reply_min_delay_minutes: Number(event.target.value) })} />
            <Input label="最长延迟（分钟）" type="number" value={draft.proactive.deferred_reply_max_delay_minutes} onChange={(event) => patchProactive({ deferred_reply_max_delay_minutes: Number(event.target.value) })} />
            <Input label="任务过期（小时）" type="number" value={draft.proactive.deferred_reply_expires_hours} onChange={(event) => patchProactive({ deferred_reply_expires_hours: Number(event.target.value) })} />
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>延迟回复绕过空闲阈值</div>
              <Toggle checked={draft.proactive.deferred_reply_bypass_idle_threshold} onChange={(event) => patchProactive({ deferred_reply_bypass_idle_threshold: event.target.checked })} />
              <FieldHint text="建议开启。否则 Bot 承诺稍后回复也要等空闲阈值，体验会变差。" />
            </div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>接上文续聊</div>
              <Toggle checked={draft.proactive.topic_continuation_enabled} onChange={(event) => patchProactive({ topic_continuation_enabled: event.target.checked })} />
              <FieldHint text="用户沉默后，Bot 可继续最近未收尾的话题，而不是突兀问候。" />
            </div>
            <Input label="续聊等待（分钟）" type="number" value={draft.proactive.topic_continuation_idle_after_minutes} onChange={(event) => patchProactive({ topic_continuation_idle_after_minutes: Number(event.target.value) })} />
            <Input label="续聊过期（小时）" type="number" value={draft.proactive.topic_continuation_expires_hours} onChange={(event) => patchProactive({ topic_continuation_expires_hours: Number(event.target.value) })} />
            <Input label="续聊最低分" type="number" min="0" max="1" step="0.01" value={draft.proactive.topic_continuation_min_score} onChange={(event) => patchProactive({ topic_continuation_min_score: Number(event.target.value) })} />
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>情绪跟进</div>
              <Toggle checked={draft.proactive.emotion_followup_enabled} onChange={(event) => patchProactive({ emotion_followup_enabled: event.target.checked })} />
              <FieldHint text="用户提到累、难过、烦等状态后，Bot 可隔一段时间自然关心。" />
            </div>
            <Input label="情绪跟进延迟（分钟）" type="number" value={draft.proactive.emotion_followup_delay_minutes} onChange={(event) => patchProactive({ emotion_followup_delay_minutes: Number(event.target.value) })} />
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>生活事件分享</div>
              <Toggle checked={draft.proactive.life_event_motive_enabled} onChange={(event) => patchProactive({ life_event_motive_enabled: event.target.checked })} />
              <FieldHint text="允许 Bot 分享自己生活里具体发生的事。" />
            </div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>普通陪伴问候</div>
              <Toggle checked={draft.proactive.idle_ping_enabled} onChange={(event) => patchProactive({ idle_ping_enabled: event.target.checked })} />
              <FieldHint text="最低优先级。关闭后，没有具体动机时 Bot 不会只发“在吗”。" />
            </div>
          </div>
        </div>
```

- [ ] **Step 5: Typecheck/build UI**

Run:

```bash
cd ai-companion-ui
npm run build
```

Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add ai-companion-ui/src/types/index.ts ai-companion-ui/src/pages/Settings/Settings.tsx
git commit -m "feat: add proactive continuity settings UI"
```

## Task 12: Add Runtime Status And Debug Visibility

**Files:**
- Modify: `ai_companion/bot/instance.py`
- Modify: `ai_companion/proactive/conversation_task_store.py`
- Modify: `ai_companion/gateway/admin_services.py`
- Modify: `tests/system_test_suite.py`

- [ ] **Step 1: Add pending count API in store**

Add to `ConversationTaskStore`:

```python
    def count_pending(self, bot_id: str) -> int:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE bot_id = ? AND status = ?",
                (bot_id, ConversationTaskStatus.PENDING.value),
            ).fetchone()
        return int(row[0] or 0)
```

- [ ] **Step 2: Include status in BotInstance**

In `get_proactive_status`, add under returned dict:

```python
            "conversation_tasks": {
                "pending": self.conversation_task_store.count_pending(self.id) if self.conversation_task_store else 0,
            },
```

- [ ] **Step 3: Surface in admin diagnostics**

In `ConfigAdminService.get_bot_config`, when `bot` exists, include:

```python
        proactive_status = {}
        if bot is not None and hasattr(bot, "get_proactive_status"):
            try:
                proactive_status = bot.get_proactive_status()
            except Exception:
                proactive_status = {}
```

Then put it in `diagnostics`:

```python
                "proactive_status": proactive_status,
```

- [ ] **Step 4: Extend system test**

In `case_web_config_center_roundtrip`, make fake `bot` include:

```python
                get_proactive_status=lambda: {"conversation_tasks": {"pending": 0}},
```

Assert:

```python
            and web_after["diagnostics"]["proactive_status"]["conversation_tasks"]["pending"] == 0
```

- [ ] **Step 5: Run tests**

Run:

```bash
PYTHONPATH=. python tests/system_test_suite.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ai_companion/proactive/conversation_task_store.py ai_companion/bot/instance.py ai_companion/gateway/admin_services.py tests/system_test_suite.py
git commit -m "feat: expose proactive continuity runtime status"
```

## Task 13: Add End-To-End System Scenario

**Files:**
- Modify: `tests/system_test_suite.py`

- [ ] **Step 1: Add a system case**

Add a case method:

```python
    async def case_deferred_reply_proactive_continuity(self) -> tuple[bool, str, str]:
        from pathlib import Path
        import tempfile
        from ai_companion.bot.instance import BotInstance

        class PromiseThenFollowupModel:
            def __init__(self):
                self.calls = []

            async def chat(self, messages, system_prompt=None, **kwargs):
                text = messages[-1]["content"]
                self.calls.append(text)
                if "主动联系原因" in text:
                    return '{"opening":"刚才你问的那个问题","topic":"我想了一下，可以先小范围试试","ending":"你觉得呢？"}'
                return "我想一下，一会儿回复你。"

        with tempfile.TemporaryDirectory(prefix="sys-deferred-proactive-") as td:
            root = Path(td)
            bot_id = "deferred_bot"
            persona = root / "data" / "bots" / bot_id / "persona"
            persona.mkdir(parents=True)
            for name, payload in {
                "profile.json": {"name": "延迟测试", "age": 22, "occupation": "学生", "personality_tags": ["温柔"]},
                "backstory.json": {},
                "values.json": {},
                "speaking_style.json": {},
                "proactive.json": {
                    "enabled": True,
                    "mode": "active",
                    "scheduler": {"min_interval_hours": 0.1, "max_daily": 5},
                    "conversation_continuity": {"deferred_reply": {"default_delay_minutes": 1}},
                },
                "life.json": {},
            }.items():
                (persona / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            sent = []
            bot = BotInstance(
                {"id": bot_id, "name": "延迟测试", "data_dir": str(root / "data" / "bots")},
                model=PromiseThenFollowupModel(),
                data_dir=root / "data" / "bots",
                memory_config={"embedding": "none"},
                refusal_enabled=False,
            )
            await bot.init(start_schedulers=False)
            bot.proactive_engine._platform_sender = lambda msg, target=None: sent.append({"msg": msg, "target": target}) or True
            response = await bot.handle_message(
                "那你怎么看这个项目？",
                memory_turn_context={"platform": "weixin", "session_id": "gw_a", "user_id": "default_user", "chat_id": "wx-1"},
            )
            due = bot.conversation_task_store.list_due(bot_id, datetime.now() + timedelta(minutes=2))
            ok_tick = await bot.proactive_orchestrator.tick(now=datetime.now() + timedelta(minutes=2))
            await bot.close()

        passed = (
            "一会儿回复你" in response
            and len(due) == 1
            and ok_tick is True
            and sent
            and sent[0]["target"]["chat_id"] == "wx-1"
            and "刚才你问的那个问题" in sent[0]["msg"]
        )
        detail = f"response={response} due={len(due)} sent={sent}"
        return passed, detail, detail
```

Register it in the suite list:

```python
self._run_case("T52", "Deferred proactive continuity", self.case_deferred_reply_proactive_continuity)
```

Use the next available T number.

- [ ] **Step 2: Run system suite**

Run:

```bash
PYTHONPATH=. python tests/system_test_suite.py
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/system_test_suite.py
git commit -m "test: cover deferred proactive continuity"
```

## Task 14: Documentation And User-Facing Explanation

**Files:**
- Modify: `docs/DESIGN_phase5_proactive.md`
- Modify: `docs/GUIDE.md`

- [ ] **Step 1: Update design doc**

Add a section to `docs/DESIGN_phase5_proactive.md`:

```markdown
## Phase 5.x：对话连续性主动动机

主动唤醒不再只由空闲时间触发。系统会先收集主动动机，再选择最自然的一条发送：

1. 延迟回复履约：Bot 自己承诺稍后回复时，写入 conversation_tasks.db，到期回到同一会话继续。
2. 接上文续聊：最近话题未自然收尾时，Bot 可以延迟接上文。
3. 情绪跟进：用户提到负面情绪后，Bot 可稍后关心。
4. 生活事件分享：Bot 有具体生活事件时分享。
5. 普通陪伴问候：没有具体动机时才使用。

WebUI 入口：配置中心 -> 主动唤醒 -> 对话连续性。
```

- [ ] **Step 2: Update guide**

Add to `docs/GUIDE.md` under proactive configuration:

```markdown
### 对话连续性主动唤醒

在 WebUI 的「配置中心 -> 主动唤醒 -> 对话连续性」可以设置：

- 延迟回复履约：Bot 说“一会儿回复你”后，会在默认延迟时间后回到同一会话继续。
- 接上文续聊：用户沉默后优先延续最近未完成话题。
- 情绪跟进：用户提到难过、累、烦等状态后，稍后自然关心。
- 普通陪伴问候：最低优先级；关闭后可减少“在吗”式突兀消息。

触发时机分两段：Bot 每次回复后会立即分析并记录可能的后续动机；真正主动发送要等动机到期，并在下一次后台检查时执行。比如延迟回复默认 8 分钟，接上文续聊默认用户沉默 45 分钟，实际发送时间还会受到检查间隔影响。

如果希望 Bot 更像真人，建议开启延迟回复履约和接上文续聊，普通陪伴问候可以保持较低频率或关闭。
```

- [ ] **Step 3: Run doc-safe checks**

Run:

```bash
python -m compileall -q ai_companion
```

Expected: no output and exit 0.

- [ ] **Step 4: Commit**

```bash
git add docs/DESIGN_phase5_proactive.md docs/GUIDE.md
git commit -m "docs: explain proactive continuity settings"
```

## Task 15: Final Verification

**Files:**
- All modified files.

- [ ] **Step 1: Run focused tests**

Run:

```bash
PYTHONPATH=. python tests/proactive_orchestrator_test.py
PYTHONPATH=. python tests/proactive_engine_test.py
PYTHONPATH=. python tests/bot_instance_test.py
PYTHONPATH=. python tests/weixin_gateway_test.py
```

Expected: all PASS.

- [ ] **Step 2: Run compile check**

Run:

```bash
python -m compileall -q ai_companion
```

Expected: no output and exit 0.

- [ ] **Step 3: Build Web UI**

Run:

```bash
cd ai-companion-ui
npm run build
```

Expected: build succeeds.

- [ ] **Step 4: Run system suite**

Run:

```bash
PYTHONPATH=. python tests/system_test_suite.py
```

Expected: all cases PASS, including Web config center and deferred proactive continuity.

- [ ] **Step 5: Manual runtime smoke test**

Use a test Bot with proactive enabled and Weixin or Feishu target configured:

```bash
ai-companion gateway restart
ai-companion gateway logs
```

Send:

```text
那你怎么看这个问题？
```

Use a model or persona response that says:

```text
我想一下，一会儿回复你。
```

Pass criteria:

- `conversation_tasks.db` contains one pending `deferred_reply` task.
- After the configured delay, Bot sends a message to the same chat.
- The message starts by continuing the prior topic, for example "刚才你问的那个问题...".
- `/status` or WebUI diagnostics shows pending task count returning to 0 after send.

- [ ] **Step 6: Final commit if any verification fixes were needed**

```bash
git status --short
git add <fixed-files>
git commit -m "fix: stabilize proactive continuity flow"
```

## Self-Review

Spec coverage:

- Deferred reply obligation: Tasks 1, 2, 4, 5, 7, 8, 13.
- Context-aware proactive messages: Tasks 6, 7, 9, 13.
- WebUI configuration and user explanation: Tasks 10, 11, 12, 14.
- Same-chat delivery: Tasks 5, 8, 13.
- Testing and compile verification: Tasks 10, 13, 15.

Placeholder scan:

- No `TBD`, `TODO`, or open test-number placeholders remain.

Type consistency:

- `ConversationTaskType.DEFERRED_REPLY` maps to motive type `deferred_reply`.
- Public Web API uses flattened `ProactiveConfig` fields while disk config remains nested under `conversation_continuity`.
- `ConversationTaskStore` persists under the bot runtime directory, matching existing runtime state patterns.
