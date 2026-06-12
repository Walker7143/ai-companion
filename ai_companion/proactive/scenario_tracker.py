from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ScenarioEntry:
    id: str
    bot_id: str
    session_id: str
    actor: str  # "bot" | "user"
    description: str
    start_time: datetime
    estimated_duration_minutes: int
    progression_hint: str
    status: str = "active"  # "active" | "progressed" | "stale"
    created_at: datetime = field(default_factory=datetime.now)

    def is_progressed(self, now: datetime) -> bool:
        if self.status != "active":
            return False
        elapsed = (now - self.start_time).total_seconds() / 60
        return elapsed >= self.estimated_duration_minutes

    def is_stale(self, now: datetime) -> bool:
        elapsed = (now - self.start_time).total_seconds() / 60
        return elapsed >= self.estimated_duration_minutes * 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "session_id": self.session_id,
            "actor": self.actor,
            "description": self.description,
            "start_time": self.start_time.isoformat(),
            "estimated_duration_minutes": self.estimated_duration_minutes,
            "progression_hint": self.progression_hint,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScenarioEntry:
        return cls(
            id=str(data["id"]),
            bot_id=str(data["bot_id"]),
            session_id=str(data.get("session_id") or ""),
            actor=str(data["actor"]),
            description=str(data["description"]),
            start_time=datetime.fromisoformat(str(data["start_time"])),
            estimated_duration_minutes=int(data["estimated_duration_minutes"]),
            progression_hint=str(data.get("progression_hint") or ""),
            status=str(data.get("status", "active")),
            created_at=datetime.fromisoformat(str(data.get("created_at", datetime.now().isoformat()))),
        )


class ScenarioStore:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / "scenarios.db"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scenarios (
                    id TEXT PRIMARY KEY,
                    bot_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    description TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    estimated_duration_minutes INTEGER NOT NULL,
                    progression_hint TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scenarios_status ON scenarios(bot_id, status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scenarios_session ON scenarios(bot_id, session_id)")
            conn.commit()

    def upsert(self, entry: ScenarioEntry) -> None:
        data = entry.to_dict()
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                INSERT INTO scenarios (
                    id, bot_id, session_id, actor, description, start_time,
                    estimated_duration_minutes, progression_hint, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    progression_hint=excluded.progression_hint
                """,
                (
                    data["id"],
                    data["bot_id"],
                    data["session_id"],
                    data["actor"],
                    data["description"],
                    data["start_time"],
                    data["estimated_duration_minutes"],
                    data["progression_hint"],
                    data["status"],
                    data["created_at"],
                ),
            )
            conn.commit()

    def upsert_many(self, entries: list[ScenarioEntry]) -> None:
        for entry in entries:
            self.upsert(entry)

    def list_active(self, bot_id: str) -> list[ScenarioEntry]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT * FROM scenarios WHERE bot_id = ? AND status = 'active' ORDER BY start_time ASC",
                (bot_id,),
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def list_progressed(self, bot_id: str, now: datetime, limit: int = 5) -> list[ScenarioEntry]:
        active = self.list_active(bot_id)
        progressed = []
        for entry in active:
            if entry.is_progressed(now):
                progressed.append(entry)
        progressed.sort(key=lambda e: e.start_time)
        return progressed[:limit]

    def mark_stale(self, bot_id: str, session_id: str) -> int:
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.execute(
                "UPDATE scenarios SET status = 'stale' WHERE bot_id = ? AND session_id = ? AND status = 'active'",
                (bot_id, session_id),
            )
            conn.commit()
            return cursor.rowcount

    def mark_progressed(self, entry_id: str) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "UPDATE scenarios SET status = 'progressed' WHERE id = ? AND status = 'active'",
                (entry_id,),
            )
            conn.commit()

    def cleanup_stale(self, bot_id: str, now: datetime) -> int:
        active = self.list_active(bot_id)
        count = 0
        for entry in active:
            if entry.is_stale(now):
                self.store.mark_stale(bot_id, entry.session_id)
                count += 1
        return count

    def delete_older_than(self, bot_id: str, before: datetime) -> int:
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.execute(
                "DELETE FROM scenarios WHERE bot_id = ? AND created_at < ?",
                (bot_id, before.isoformat()),
            )
            conn.commit()
            return cursor.rowcount

    def _row_to_entry(self, row: tuple[Any, ...]) -> ScenarioEntry:
        return ScenarioEntry(
            id=str(row[0]),
            bot_id=str(row[1]),
            session_id=str(row[2]),
            actor=str(row[3]),
            description=str(row[4]),
            start_time=datetime.fromisoformat(str(row[5])),
            estimated_duration_minutes=int(row[6]),
            progression_hint=str(row[7]),
            status=str(row[8]),
            created_at=datetime.fromisoformat(str(row[9])),
        )


class ScenarioTracker:
    def __init__(self, store: ScenarioStore, bot_id: str):
        self.store = store
        self.bot_id = bot_id

    @staticmethod
    def create_entry(
        bot_id: str,
        session_id: str,
        actor: str,
        description: str,
        start_time: datetime,
        estimated_duration_minutes: int,
        progression_hint: str = "",
    ) -> ScenarioEntry:
        return ScenarioEntry(
            id=str(uuid.uuid4()),
            bot_id=bot_id,
            session_id=session_id,
            actor=actor,
            description=description,
            start_time=start_time,
            estimated_duration_minutes=estimated_duration_minutes,
            progression_hint=progression_hint,
            status="active",
        )

    def ingest_closeout_scenarios(
        self,
        session_id: str,
        scenarios_raw: list[dict[str, Any]],
        start_time: datetime,
    ) -> None:
        entries = []
        for raw in scenarios_raw:
            actor = str(raw.get("actor") or "").strip().lower()
            if actor not in ("bot", "user"):
                continue
            description = str(raw.get("description") or "").strip()
            if not description:
                continue
            duration = raw.get("estimated_duration_minutes")
            if duration is None:
                continue
            try:
                duration = int(duration)
            except (TypeError, ValueError):
                continue
            if duration <= 0:
                continue
            progression_hint = str(raw.get("progression_hint") or "").strip()
            entries.append(
                self.create_entry(
                    bot_id=self.bot_id,
                    session_id=session_id,
                    actor=actor,
                    description=description,
                    start_time=start_time,
                    estimated_duration_minutes=duration,
                    progression_hint=progression_hint,
                )
            )
        if entries:
            self.store.upsert_many(entries)

    def on_session_user_message(self, session_id: str) -> None:
        marked = self.store.mark_stale(self.bot_id, session_id)
        if marked > 0:
            import logging
            logging.getLogger(__name__).debug(
                "[ScenarioTracker] 用户发消息，标记 %d 个场景为 stale (session=%s)", marked, session_id
            )

    def list_progressed(self, now: datetime) -> list[ScenarioEntry]:
        return self.store.list_progressed(self.bot_id, now)

    def mark_progressed(self, entry_id: str) -> None:
        self.store.mark_progressed(entry_id)

    def tick_cleanup(self, now: datetime) -> None:
        active = self.store.list_active(self.bot_id)
        count = 0
        for entry in active:
            if entry.is_stale(now):
                self.mark_stale(bot_id, entry.session_id)
                count += 1
        if count > 0:
            import logging
            logging.getLogger(__name__).debug(
                "[ScenarioTracker] 清理 %d 个过期场景", count
            )
