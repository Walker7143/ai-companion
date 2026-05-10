from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

from .motives import ConversationTask, ConversationTaskStatus


class ConversationTaskStore:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / "conversation_tasks.db"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
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
            conn.commit()

    def upsert(self, task: ConversationTask) -> None:
        data = task.to_dict()
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    id, bot_id, type, status, session_id, user_id, platform,
                    target_json, created_at, due_at, expires_at,
                    source_user_message, source_bot_message, topic_summary,
                    priority, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    bot_id=excluded.bot_id,
                    type=excluded.type,
                    status=excluded.status,
                    session_id=excluded.session_id,
                    user_id=excluded.user_id,
                    platform=excluded.platform,
                    target_json=excluded.target_json,
                    created_at=excluded.created_at,
                    due_at=excluded.due_at,
                    expires_at=excluded.expires_at,
                    source_user_message=excluded.source_user_message,
                    source_bot_message=excluded.source_bot_message,
                    topic_summary=excluded.topic_summary,
                    priority=excluded.priority,
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
            conn.commit()

    def list_due(self, bot_id: str, now: datetime, limit: int = 10) -> list[ConversationTask]:
        with closing(sqlite3.connect(self.db_path)) as conn:
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

    def count_pending(self, bot_id: str) -> int:
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE bot_id = ? AND status = ?",
                (bot_id, ConversationTaskStatus.PENDING.value),
            ).fetchone()
        return int((row or [0])[0] or 0)

    def mark_completed(self, task_id: str, completed_at: datetime) -> None:
        self._mark(task_id, ConversationTaskStatus.COMPLETED, completed_at)

    def mark_expired(self, task_id: str, expired_at: datetime) -> None:
        self._mark(task_id, ConversationTaskStatus.EXPIRED, expired_at)

    def cancel_pending_for_session(self, bot_id: str, session_id: str, now: datetime) -> int:
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.execute(
                "UPDATE tasks SET status = ?, metadata_json = json_set(COALESCE(metadata_json, '{}'), '$.cancelled_at', ?) "
                "WHERE bot_id = ? AND session_id = ? AND status = ?",
                (
                    ConversationTaskStatus.CANCELLED.value,
                    now.isoformat(),
                    bot_id,
                    session_id,
                    ConversationTaskStatus.PENDING.value,
                ),
            )
            conn.commit()
            return cursor.rowcount

    def expire_overdue(self, now: datetime) -> int:
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.execute(
                "UPDATE tasks SET status = ? WHERE status = ? AND expires_at < ?",
                (ConversationTaskStatus.EXPIRED.value, ConversationTaskStatus.PENDING.value, now.isoformat()),
            )
            conn.commit()
            return cursor.rowcount

    def has_pending(self, bot_id: str, session_id: str, task_type: str) -> bool:
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT 1 FROM tasks WHERE bot_id = ? AND session_id = ? AND type = ? AND status = ? LIMIT 1",
                (bot_id, session_id, task_type, ConversationTaskStatus.PENDING.value),
            ).fetchone()
        return row is not None

    def _mark(self, task_id: str, status: ConversationTaskStatus, when: datetime) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute("SELECT metadata_json FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                return
            metadata = json.loads(row[0] or "{}")
            metadata[f"{status.value}_at"] = when.isoformat()
            conn.execute(
                "UPDATE tasks SET status = ?, metadata_json = ? WHERE id = ?",
                (status.value, json.dumps(metadata, ensure_ascii=False), task_id),
            )
            conn.commit()

    def _row_to_task(self, row: tuple[Any, ...]) -> ConversationTask:
        keys = [
            "id",
            "bot_id",
            "type",
            "status",
            "session_id",
            "user_id",
            "platform",
            "target",
            "created_at",
            "due_at",
            "expires_at",
            "source_user_message",
            "source_bot_message",
            "topic_summary",
            "priority",
            "metadata",
        ]
        data = dict(zip(keys, row))
        data["target"] = json.loads(data["target"] or "{}")
        data["metadata"] = json.loads(data["metadata"] or "{}")
        return ConversationTask.from_dict(data)
