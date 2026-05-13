"""Cross-channel daily memory store.

Daily memory keeps a short-lived, bot/user-scoped record of recent daily
conversation continuity.  It deliberately sits between working memory and
long-term episodic/semantic memory:

- working memory remains session-scoped and platform/session isolated;
- daily memory is shared by bot_id + user_id across channels for recent days;
- episodic/semantic stores remain the long-term promotion targets.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import aiosqlite


@dataclass
class MemoryTurnContext:
    """Metadata describing where a memory turn came from."""

    platform: str = "cli"
    session_id: str | None = None
    user_id: str = "default_user"
    channel_type: str | None = None
    chat_id: str | None = None
    message_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class DailyMemoryStore:
    """SQLite-backed short-term cross-channel daily memory."""

    DEFAULT_RETENTION_DAYS = 10
    DEFAULT_RECENT_MESSAGE_LIMIT = 16
    DEFAULT_SUMMARY_DAYS = 10
    DEFAULT_MAX_PROMPT_CHARS = 1800
    DEFAULT_SUMMARIZE_AFTER_MESSAGES = 12
    DEFAULT_SUMMARIZE_AFTER_CHARS = 3000

    SUMMARY_PROMPT = """请把下面这些同一天的跨通道对话，更新成一份简洁的“今日连续性记忆”。

要求：
- 只记录今天/最近发生的上下文，不要把临时情绪写成永久性格。
- 保留用户正在关心的主题、未完成话题、承诺/待办、明显情绪变化。
- 不要逐字复述，不要夸大亲密关系，不要加入原文没有的信息。
- 输出 JSON，字段为 summary、topics、open_threads、mood、commitments。

已有摘要：
{existing_summary}

新增消息：
{messages_text}
"""

    def __init__(
        self,
        db_path: str | Path,
        *,
        enabled: bool = True,
        retention_days: int = DEFAULT_RETENTION_DAYS,
        recent_message_limit: int = DEFAULT_RECENT_MESSAGE_LIMIT,
        summary_days: int = DEFAULT_SUMMARY_DAYS,
        max_prompt_chars: int = DEFAULT_MAX_PROMPT_CHARS,
        summarize_after_messages: int = DEFAULT_SUMMARIZE_AFTER_MESSAGES,
        summarize_after_chars: int = DEFAULT_SUMMARIZE_AFTER_CHARS,
    ):
        self.db_path = Path(db_path)
        self.enabled = bool(enabled)
        self.retention_days = max(1, int(retention_days or self.DEFAULT_RETENTION_DAYS))
        self.recent_message_limit = max(0, int(recent_message_limit or self.DEFAULT_RECENT_MESSAGE_LIMIT))
        self.summary_days = max(1, int(summary_days or self.DEFAULT_SUMMARY_DAYS))
        self.max_prompt_chars = max(200, int(max_prompt_chars or self.DEFAULT_MAX_PROMPT_CHARS))
        self.summarize_after_messages = max(1, int(summarize_after_messages or self.DEFAULT_SUMMARIZE_AFTER_MESSAGES))
        self.summarize_after_chars = max(200, int(summarize_after_chars or self.DEFAULT_SUMMARIZE_AFTER_CHARS))

    async def init(self):
        if not self.enabled:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    local_date TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    platform TEXT,
                    session_id TEXT,
                    channel_type TEXT,
                    chat_id_hash TEXT,
                    message_id TEXT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_chars INTEGER DEFAULT 0,
                    importance REAL DEFAULT 0,
                    metadata_json TEXT,
                    summarized INTEGER DEFAULT 0,
                    archived INTEGER DEFAULT 0
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    local_date TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    topics_json TEXT,
                    open_threads_json TEXT,
                    mood_json TEXT,
                    commitments_json TEXT,
                    last_message_id INTEGER,
                    message_count INTEGER DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    UNIQUE(bot_id, user_id, local_date)
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_daily_user_date ON daily_messages(bot_id, user_id, local_date, id)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_daily_recent ON daily_messages(bot_id, user_id, created_at)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_daily_summary_user_date ON daily_summaries(bot_id, user_id, local_date)"
            )
            await db.commit()

    async def append_turn(
        self,
        *,
        bot_id: str,
        user_id: str,
        user_input: str,
        bot_output: str,
        session_id: str | None = None,
        context: MemoryTurnContext | None = None,
    ):
        if not self.enabled:
            return
        ctx = context or MemoryTurnContext()
        now = datetime.now()
        local_date = now.strftime("%Y-%m-%d")
        created_at = now.isoformat(timespec="seconds")
        platform = ctx.platform or "unknown"
        sid = ctx.session_id or session_id
        metadata_json = json.dumps(ctx.metadata or {}, ensure_ascii=False) if ctx.metadata else None
        chat_hash = _hash_text(ctx.chat_id) if ctx.chat_id else None

        async with aiosqlite.connect(self.db_path) as db:
            for role, content in (("user", user_input), ("assistant", bot_output)):
                content = str(content or "").strip()
                if not content:
                    continue
                await db.execute(
                    """
                    INSERT INTO daily_messages (
                        bot_id, user_id, local_date, created_at, platform,
                        session_id, channel_type, chat_id_hash, message_id,
                        role, content, content_chars, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        bot_id,
                        user_id,
                        local_date,
                        created_at,
                        platform,
                        sid,
                        ctx.channel_type,
                        chat_hash,
                        ctx.message_id,
                        role,
                        content,
                        len(content),
                        metadata_json,
                    ),
                )
            await db.commit()

    async def append_message(
        self,
        *,
        bot_id: str,
        user_id: str,
        role: str,
        content: str,
        session_id: str | None = None,
        context: MemoryTurnContext | None = None,
    ):
        if not self.enabled:
            return
        content = str(content or "").strip()
        if not content:
            return
        role = str(role or "").strip()
        if role not in {"user", "assistant", "system"}:
            raise ValueError(f"unsupported daily memory role: {role}")

        ctx = context or MemoryTurnContext()
        now = datetime.now()
        local_date = now.strftime("%Y-%m-%d")
        created_at = now.isoformat(timespec="seconds")
        platform = ctx.platform or "unknown"
        sid = ctx.session_id or session_id
        metadata_json = json.dumps(ctx.metadata or {}, ensure_ascii=False) if ctx.metadata else None
        chat_hash = _hash_text(ctx.chat_id) if ctx.chat_id else None

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO daily_messages (
                    bot_id, user_id, local_date, created_at, platform,
                    session_id, channel_type, chat_id_hash, message_id,
                    role, content, content_chars, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bot_id,
                    user_id,
                    local_date,
                    created_at,
                    platform,
                    sid,
                    ctx.channel_type,
                    chat_hash,
                    ctx.message_id,
                    role,
                    content,
                    len(content),
                    metadata_json,
                ),
            )
            await db.commit()

    def get_recent_context(
        self,
        *,
        bot_id: str,
        user_id: str,
        current_session_id: str | None = None,
        intent: str = "casual_chat",
    ) -> dict[str, Any]:
        if not self.enabled:
            return {}

        today = datetime.now().strftime("%Y-%m-%d")
        summary_limit = self._summary_limit_for_intent(intent)
        message_limit = self._message_limit_for_intent(intent)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        summaries = [
            _row_to_summary(row)
            for row in conn.execute(
                """
                SELECT local_date, summary, topics_json, open_threads_json, mood_json,
                       commitments_json, updated_at, message_count
                FROM daily_summaries
                WHERE bot_id = ? AND user_id = ?
                ORDER BY local_date DESC
                LIMIT ?
                """,
                (bot_id, user_id, summary_limit),
            ).fetchall()
        ]

        message_params: list[Any] = [bot_id, user_id, message_limit]
        session_filter = ""
        if current_session_id:
            session_filter = "AND (session_id IS NULL OR session_id != ?)"
            message_params.insert(2, current_session_id)

        messages = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT local_date, created_at, platform, session_id, role, content, metadata_json
                FROM daily_messages
                WHERE bot_id = ? AND user_id = ? AND archived = 0
                  {session_filter}
                ORDER BY id DESC
                LIMIT ?
                """,
                tuple(message_params),
            ).fetchall()
        ]
        self_memory = [
            _row_to_self_memory(row)
            for row in conn.execute(
                """
                SELECT local_date, created_at, platform, session_id, role, content, metadata_json
                FROM daily_messages
                WHERE bot_id = ? AND user_id = ? AND archived = 0
                  AND role = 'assistant'
                  AND metadata_json IS NOT NULL
                ORDER BY id DESC
                LIMIT 8
                """,
                (bot_id, user_id),
            ).fetchall()
        ]
        conn.close()

        messages = list(reversed(messages))
        self_memory = [item for item in self_memory if item]
        context = {
            "today": today,
            "summaries": summaries,
            "recent_messages": messages,
            "self_memory": self_memory,
        }
        return self._trim_context(context, max_chars=self._prompt_limit_for_intent(intent))

    async def summarize_due(
        self,
        *,
        bot_id: str,
        user_id: str,
        summarizer=None,
    ) -> bool:
        if not self.enabled:
            return False
        today = datetime.now().strftime("%Y-%m-%d")
        pending = self._get_pending_messages(bot_id=bot_id, user_id=user_id, local_date=today)
        if not pending:
            return False
        total_chars = sum(len(item["content"]) for item in pending)
        if len(pending) < self.summarize_after_messages and total_chars < self.summarize_after_chars:
            return False

        existing = self._get_summary(bot_id=bot_id, user_id=user_id, local_date=today)
        summary_payload = await self._summarize_messages(existing=existing, messages=pending, summarizer=summarizer)
        await self.upsert_summary(
            bot_id=bot_id,
            user_id=user_id,
            local_date=today,
            payload=summary_payload,
            last_message_id=max(item["id"] for item in pending),
            message_count=len(pending) + int((existing or {}).get("message_count") or 0),
        )
        return True

    async def upsert_summary(
        self,
        *,
        bot_id: str,
        user_id: str,
        local_date: str,
        payload: dict[str, Any],
        last_message_id: int | None,
        message_count: int,
    ):
        if not self.enabled:
            return
        summary = str(payload.get("summary") or "").strip()
        if not summary:
            return
        now = datetime.now().isoformat(timespec="seconds")
        topics = _json_list(payload.get("topics"))
        open_threads = _json_list(payload.get("open_threads"))
        mood = _json_list(payload.get("mood"))
        commitments = _json_list(payload.get("commitments"))
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO daily_summaries (
                    bot_id, user_id, local_date, summary, topics_json,
                    open_threads_json, mood_json, commitments_json,
                    last_message_id, message_count, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(bot_id, user_id, local_date) DO UPDATE SET
                    summary = excluded.summary,
                    topics_json = excluded.topics_json,
                    open_threads_json = excluded.open_threads_json,
                    mood_json = excluded.mood_json,
                    commitments_json = excluded.commitments_json,
                    last_message_id = excluded.last_message_id,
                    message_count = excluded.message_count,
                    updated_at = excluded.updated_at
                """,
                (
                    bot_id,
                    user_id,
                    local_date,
                    summary,
                    json.dumps(topics, ensure_ascii=False),
                    json.dumps(open_threads, ensure_ascii=False),
                    json.dumps(mood, ensure_ascii=False),
                    json.dumps(commitments, ensure_ascii=False),
                    last_message_id,
                    message_count,
                    now,
                ),
            )
            if last_message_id is not None:
                await db.execute(
                    """
                    UPDATE daily_messages
                    SET summarized = 1
                    WHERE bot_id = ? AND user_id = ? AND local_date = ? AND id <= ?
                    """,
                    (bot_id, user_id, local_date, last_message_id),
                )
            await db.commit()

    async def prune_old(self, *, bot_id: str, user_id: str) -> int:
        if not self.enabled:
            return 0
        cutoff = (datetime.now() - timedelta(days=self.retention_days - 1)).strftime("%Y-%m-%d")
        async with aiosqlite.connect(self.db_path) as db:
            msg_cursor = await db.execute(
                "DELETE FROM daily_messages WHERE bot_id = ? AND user_id = ? AND local_date < ?",
                (bot_id, user_id, cutoff),
            )
            sum_cursor = await db.execute(
                "DELETE FROM daily_summaries WHERE bot_id = ? AND user_id = ? AND local_date < ?",
                (bot_id, user_id, cutoff),
            )
            await db.commit()
            return (msg_cursor.rowcount or 0) + (sum_cursor.rowcount or 0)

    def count_recent_days(self, *, bot_id: str, user_id: str) -> int:
        if not self.enabled:
            return 0
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT COUNT(DISTINCT local_date) FROM daily_messages WHERE bot_id = ? AND user_id = ?",
            (bot_id, user_id),
        ).fetchone()
        conn.close()
        return int(row[0] or 0)

    def count_messages(self, *, bot_id: str, user_id: str) -> int:
        if not self.enabled:
            return 0
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT COUNT(*) FROM daily_messages WHERE bot_id = ? AND user_id = ?",
            (bot_id, user_id),
        ).fetchone()
        conn.close()
        return int(row[0] or 0)

    async def close(self):
        pass

    def _get_pending_messages(self, *, bot_id: str, user_id: str, local_date: str) -> list[dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, created_at, platform, role, content
            FROM daily_messages
            WHERE bot_id = ? AND user_id = ? AND local_date = ?
              AND summarized = 0 AND archived = 0
            ORDER BY id ASC
            """,
            (bot_id, user_id, local_date),
        ).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def _get_summary(self, *, bot_id: str, user_id: str, local_date: str) -> dict[str, Any] | None:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT local_date, summary, topics_json, open_threads_json, mood_json,
                   commitments_json, updated_at, message_count
            FROM daily_summaries
            WHERE bot_id = ? AND user_id = ? AND local_date = ?
            """,
            (bot_id, user_id, local_date),
        ).fetchone()
        conn.close()
        return _row_to_summary(row) if row else None

    async def _summarize_messages(
        self,
        *,
        existing: dict[str, Any] | None,
        messages: list[dict[str, Any]],
        summarizer=None,
    ) -> dict[str, Any]:
        messages_text = "\n".join(
            f"[{item.get('platform') or 'unknown'}][{item['role']}] {item['content']}"
            for item in messages
        )
        existing_summary = json.dumps(existing or {}, ensure_ascii=False)
        if summarizer is not None:
            prompt = self.SUMMARY_PROMPT.format(
                existing_summary=existing_summary,
                messages_text=messages_text,
            )
            try:
                response = await summarizer.chat(
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt=None,
                )
                raw = response.get("content") or response.get("reasoning_content") if isinstance(response, dict) else str(response)
                parsed = _parse_json_object(raw)
                if parsed.get("summary"):
                    return parsed
            except Exception:
                pass
        return self._simple_summary(existing=existing, messages=messages)

    def _simple_summary(self, *, existing: dict[str, Any] | None, messages: list[dict[str, Any]]) -> dict[str, Any]:
        snippets = []
        for item in messages:
            content = str(item.get("content") or "").strip()
            if content:
                snippets.append(f"{item.get('role')}: {content[:80]}")
        base = str((existing or {}).get("summary") or "").strip()
        new_summary = "；".join(snippets[-8:])
        summary = f"{base}；{new_summary}" if base and new_summary else (base or new_summary)
        return {
            "summary": summary[:700],
            "topics": [],
            "open_threads": [],
            "mood": [],
            "commitments": [],
        }

    def _summary_limit_for_intent(self, intent: str) -> int:
        if intent in {"recall_past", "emotional_support"}:
            return self.summary_days
        if intent == "task_request":
            return min(2, self.summary_days)
        return min(4, self.summary_days)

    def _message_limit_for_intent(self, intent: str) -> int:
        if intent == "task_request":
            return min(4, self.recent_message_limit)
        if intent in {"emotional_support", "planning"}:
            return min(10, self.recent_message_limit)
        return self.recent_message_limit

    def _prompt_limit_for_intent(self, intent: str) -> int:
        if intent == "task_request":
            return min(600, self.max_prompt_chars)
        if intent in {"recall_past", "emotional_support"}:
            return self.max_prompt_chars
        return min(1200, self.max_prompt_chars)

    def _trim_context(self, context: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
        def size(data: dict[str, Any]) -> int:
            return len(json.dumps(data, ensure_ascii=False))

        while size(context) > max_chars and context.get("recent_messages"):
            context["recent_messages"].pop(0)
        while size(context) > max_chars and context.get("summaries"):
            context["summaries"].pop()
        while size(context) > max_chars and context.get("self_memory"):
            context["self_memory"].pop()
        return context


def _hash_text(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _json_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _loads_list(value: object) -> list[str]:
    if not value:
        return []
    try:
        data = json.loads(str(value))
    except Exception:
        return []
    return _json_list(data)


def _row_to_summary(row) -> dict[str, Any]:
    return {
        "local_date": row["local_date"],
        "summary": row["summary"],
        "topics": _loads_list(row["topics_json"]),
        "open_threads": _loads_list(row["open_threads_json"]),
        "mood": _loads_list(row["mood_json"]),
        "commitments": _loads_list(row["commitments_json"]),
        "updated_at": row["updated_at"],
        "message_count": row["message_count"],
    }


def _row_to_self_memory(row) -> dict[str, Any] | None:
    metadata = _loads_dict(row["metadata_json"])
    if not metadata:
        return None
    if not (metadata.get("assistant_initiated") or metadata.get("proactive")):
        return None
    content = str(row["content"] or "").strip()
    if not content:
        return None
    return {
        "local_date": row["local_date"],
        "created_at": row["created_at"],
        "platform": row["platform"] or "unknown",
        "session_id": row["session_id"],
        "content": content,
        "kind": metadata.get("proactive_kind") or metadata.get("kind") or "assistant_initiated",
        "metadata": metadata,
    }


def _loads_dict(value: object) -> dict[str, Any]:
    if not value:
        return {}
    try:
        data = json.loads(str(value))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    if "```" in text:
        parts = text.split("```")
        text = max(parts, key=len).strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}
