"""Relationship state store."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite


class RelationshipStore:
    """Dynamic relationship state between one bot and one user."""

    DEFAULT_LABEL = "朋友"

    def __init__(self, db_path: str | Path, persona_backstory_path: str | None = None):
        self.db_path = str(db_path)
        self._persona_backstory_path = persona_backstory_path

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS relationship_state (
                    bot_id TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT 'default_user',
                    relationship_label TEXT DEFAULT '朋友',
                    intimacy_score REAL DEFAULT 0,
                    trust_score REAL DEFAULT 0,
                    tension_score REAL DEFAULT 0,
                    affection_score REAL DEFAULT 0,
                    attitude_score REAL DEFAULT 0,
                    last_conflict_at TEXT,
                    last_repair_at TEXT,
                    last_meaningful_contact_at TEXT,
                    open_emotional_threads_json TEXT,
                    key_moments_json TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(bot_id, user_id)
                )
                """
            )
            await db.commit()

    async def get_state(self, *, bot_id: str, user_id: str = "default_user") -> dict:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT relationship_label, intimacy_score, trust_score, tension_score,
                       affection_score, attitude_score, last_conflict_at, last_repair_at,
                       last_meaningful_contact_at, open_emotional_threads_json,
                       key_moments_json, updated_at
                FROM relationship_state
                WHERE bot_id = ? AND user_id = ?
                """,
                (bot_id, user_id),
            )
            row = await cursor.fetchone()
        if not row:
            return self._default_state(bot_id, user_id)
        open_threads = _load_json_list(row[9])
        key_moments = _load_json_list(row[10])
        return {
            "bot_id": bot_id,
            "user_id": user_id,
            "relationship_label": row[0] or self.DEFAULT_LABEL,
            "relationship_level": row[0] or self.DEFAULT_LABEL,
            "intimacy_score": float(row[1] or 0),
            "trust_score": float(row[2] or 0),
            "tension_score": float(row[3] or 0),
            "affection_score": float(row[4] or 0),
            "attitude_score": float(row[5] or 0),
            "last_conflict_at": row[6],
            "last_repair_at": row[7],
            "last_meaningful_contact_at": row[8],
            "open_emotional_threads": open_threads,
            "key_moments": key_moments,
            "updated_at": row[11],
        }

    async def apply_event(
        self,
        *,
        bot_id: str,
        user_id: str = "default_user",
        label: Optional[str] = None,
        intimacy_delta: float = 0,
        trust_delta: float = 0,
        tension_delta: float = 0,
        affection_delta: float = 0,
        attitude_delta: float = 0,
        key_moment: Optional[str] = None,
        open_thread: Optional[str] = None,
    ) -> dict:
        state = await self.get_state(bot_id=bot_id, user_id=user_id)
        now = datetime.now().isoformat()

        state["relationship_label"] = label or state.get("relationship_label") or self.DEFAULT_LABEL
        state["intimacy_score"] = _clamp(float(state.get("intimacy_score", 0)) + intimacy_delta, -10, 10)
        state["trust_score"] = _clamp(float(state.get("trust_score", 0)) + trust_delta, -10, 10)
        state["tension_score"] = _clamp(float(state.get("tension_score", 0)) + tension_delta, 0, 10)
        state["affection_score"] = _clamp(float(state.get("affection_score", 0)) + affection_delta, -10, 10)
        state["attitude_score"] = _clamp(float(state.get("attitude_score", 0)) + attitude_delta, -10, 10)
        state["updated_at"] = now
        if tension_delta > 0:
            state["last_conflict_at"] = now
        if tension_delta < 0 or trust_delta > 0:
            state["last_repair_at"] = now
        if any([label, intimacy_delta, trust_delta, affection_delta, key_moment, open_thread]):
            state["last_meaningful_contact_at"] = now
        if open_thread:
            threads = list(state.get("open_emotional_threads") or [])
            if open_thread not in threads:
                threads.append(open_thread)
            state["open_emotional_threads"] = threads[-10:]
        if key_moment:
            moments = list(state.get("key_moments") or [])
            if key_moment not in moments:
                moments.append(key_moment)
            state["key_moments"] = moments[-20:]

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO relationship_state (
                    bot_id, user_id, relationship_label, intimacy_score, trust_score,
                    tension_score, affection_score, attitude_score, last_conflict_at,
                    last_repair_at, last_meaningful_contact_at, open_emotional_threads_json,
                    key_moments_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bot_id,
                    user_id,
                    state["relationship_label"],
                    state["intimacy_score"],
                    state["trust_score"],
                    state["tension_score"],
                    state["affection_score"],
                    state["attitude_score"],
                    state.get("last_conflict_at"),
                    state.get("last_repair_at"),
                    state.get("last_meaningful_contact_at"),
                    json.dumps(state.get("open_emotional_threads", []), ensure_ascii=False),
                    json.dumps(state.get("key_moments", []), ensure_ascii=False),
                    now,
                ),
            )
            await db.commit()
        self._sync_runtime_profile(state)
        return state

    async def clear(self, *, bot_id: str | None = None, user_id: str | None = None) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            if bot_id and user_id:
                cursor = await db.execute(
                    "DELETE FROM relationship_state WHERE bot_id = ? AND user_id = ?",
                    (bot_id, user_id),
                )
            elif bot_id:
                cursor = await db.execute("DELETE FROM relationship_state WHERE bot_id = ?", (bot_id,))
            else:
                cursor = await db.execute("DELETE FROM relationship_state")
            await db.commit()
            return max(cursor.rowcount or 0, 0)

    def _default_state(self, bot_id: str, user_id: str) -> dict:
        return {
            "bot_id": bot_id,
            "user_id": user_id,
            "relationship_label": self.DEFAULT_LABEL,
            "relationship_level": self.DEFAULT_LABEL,
            "intimacy_score": 0.0,
            "trust_score": 0.0,
            "tension_score": 0.0,
            "affection_score": 0.0,
            "attitude_score": 0.0,
            "last_conflict_at": None,
            "last_repair_at": None,
            "last_meaningful_contact_at": None,
            "open_emotional_threads": [],
            "key_moments": [],
            "updated_at": datetime.now().isoformat(),
        }

    def _runtime_profile_path(self) -> Optional[Path]:
        if not self._persona_backstory_path:
            return None
        return Path(self._persona_backstory_path).parent / "runtime_profile.json"

    def _sync_runtime_profile(self, state: dict):
        path = self._runtime_profile_path()
        if not path:
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            data = {}
        data["relationship_to_user"] = state.get("relationship_label", self.DEFAULT_LABEL)
        data["attitude_score"] = state.get("attitude_score", 0)
        if state.get("key_moments"):
            data["key_moments"] = state["key_moments"]
        data["updated_at"] = datetime.now().isoformat()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)

    async def close(self):
        return None


def _load_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        data = json.loads(value)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data if str(item).strip()]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
