"""Lightweight memory rollup store."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite


class MemoryRollupStore:
    """SQLite-backed rollup summaries above raw memory fragments."""

    def __init__(self, db_path: str | Path, *, enabled: bool = True):
        self.db_path = Path(db_path)
        self.enabled = bool(enabled)

    async def init(self):
        if not self.enabled:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_rollups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    topic_key TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    evidence_json TEXT,
                    source_json TEXT,
                    confidence REAL DEFAULT 0.0,
                    freshness REAL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_rollups_scope ON memory_rollups(bot_id, user_id, scope, updated_at)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_rollups_topic ON memory_rollups(bot_id, user_id, topic_key, updated_at)"
            )
            await db.commit()

    async def append_rollup(
        self,
        *,
        bot_id: str,
        user_id: str,
        scope: str,
        topic_key: str,
        summary: str,
        evidence: list[str] | None = None,
        confidence: float = 0.0,
        freshness: float = 0.0,
        source: dict[str, Any] | None = None,
    ):
        if not self.enabled:
            return
        scope = str(scope or "").strip()
        topic_key = str(topic_key or "").strip()
        summary = str(summary or "").strip()
        if not scope or not topic_key or not summary:
            return
        now = datetime.now().isoformat(timespec="seconds")
        evidence_json = json.dumps([str(item) for item in (evidence or []) if str(item).strip()], ensure_ascii=False)
        source_json = json.dumps(source or {}, ensure_ascii=False)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO memory_rollups (
                    bot_id, user_id, scope, topic_key, summary,
                    evidence_json, source_json, confidence, freshness,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bot_id,
                    user_id,
                    scope,
                    topic_key,
                    summary,
                    evidence_json,
                    source_json,
                    float(confidence or 0.0),
                    float(freshness or 0.0),
                    now,
                    now,
                ),
            )
            await db.commit()

    async def get_recent_rollups(
        self,
        *,
        bot_id: str,
        user_id: str,
        scope: str | None = None,
        topic_key: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        query = [
            "SELECT id, bot_id, user_id, scope, topic_key, summary, evidence_json, source_json, confidence, freshness, created_at, updated_at",
            "FROM memory_rollups",
            "WHERE bot_id = ? AND user_id = ?",
        ]
        params: list[Any] = [bot_id, user_id]
        if scope:
            query.append("AND scope = ?")
            params.append(str(scope))
        if topic_key:
            query.append("AND topic_key = ?")
            params.append(str(topic_key))
        query.append("ORDER BY updated_at DESC, id DESC LIMIT ?")
        params.append(max(1, int(limit or 5)))

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(" ".join(query), params)
            rows = await cursor.fetchall()

        return [_row_to_rollup(row) for row in rows]

    async def get_latest_for_topic(
        self,
        *,
        bot_id: str,
        user_id: str,
        topic_key: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        return await self.get_recent_rollups(bot_id=bot_id, user_id=user_id, topic_key=topic_key, limit=limit)

    async def get_latest_by_scope(
        self,
        *,
        bot_id: str,
        user_id: str,
        scope: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        return await self.get_recent_rollups(bot_id=bot_id, user_id=user_id, scope=scope, limit=limit)

    async def close(self):
        return None


def _row_to_rollup(row) -> dict[str, Any]:
    if isinstance(row, tuple):
        row = {
            "id": row[0],
            "bot_id": row[1],
            "user_id": row[2],
            "scope": row[3],
            "topic_key": row[4],
            "summary": row[5],
            "evidence_json": row[6],
            "source_json": row[7],
            "confidence": row[8],
            "freshness": row[9],
            "created_at": row[10],
            "updated_at": row[11],
        }
    return {
        "id": row["id"],
        "bot_id": row["bot_id"],
        "user_id": row["user_id"],
        "scope": row["scope"],
        "topic_key": row["topic_key"],
        "summary": row["summary"],
        "evidence": _loads_list(row["evidence_json"]),
        "source": _loads_dict(row["source_json"]),
        "confidence": row["confidence"],
        "freshness": row["freshness"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _loads_list(value: object) -> list[str]:
    if not value:
        return []
    try:
        data = json.loads(str(value))
    except Exception:
        return []
    return [str(item).strip() for item in data if str(item).strip()] if isinstance(data, list) else []


def _loads_dict(value: object) -> dict[str, Any]:
    if not value:
        return {}
    try:
        data = json.loads(str(value))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}
