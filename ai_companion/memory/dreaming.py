"""Dreaming orchestration layer for memory productization.

This module adds a product-facing "dreaming" / memory organization surface on
top of the existing memory stores without replacing them as the source of truth.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .dreaming_scheduler import DreamingScheduler


def _now_iso() -> str:
    return datetime.now().isoformat()


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _truncate(value: str, limit: int = 160) -> str:
    value = _clean_text(value)
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _int(value: Any, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        result = int(value)
    except Exception:
        result = int(default)
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


DEFAULT_DREAMING_CONFIG: dict[str, Any] = {
    "enabled": False,
    "auto_run_enabled": False,
    "auto_check_interval_seconds": 900,
    "min_run_interval_minutes": 120,
    "min_new_messages": 6,
    "report_retention": 10,
    "max_candidates": 24,
    "max_promotions": 6,
    "show_sensitive_reason_only": True,
}


@dataclass
class DreamingCandidate:
    candidate_id: str
    source_layer: str
    source_ref: str
    summary: str
    detail: str = ""
    confidence: float = 0.7
    importance: float = 0.6
    sensitivity: str = "normal"
    proposed_target: str = "semantic"
    category: str = "general"
    reason_tags: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "source_layer": self.source_layer,
            "source_ref": self.source_ref,
            "summary": self.summary,
            "detail": self.detail,
            "confidence": self.confidence,
            "importance": self.importance,
            "sensitivity": self.sensitivity,
            "proposed_target": self.proposed_target,
            "category": self.category,
            "reason_tags": list(self.reason_tags),
            "payload": dict(self.payload),
        }


@dataclass
class PromotionDecision:
    candidate_id: str
    action: str
    target_store: str | None = None
    reason_tags: list[str] = field(default_factory=list)
    written_ref: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "action": self.action,
            "target_store": self.target_store,
            "reason_tags": list(self.reason_tags),
            "written_ref": dict(self.written_ref or {}),
        }


class DreamingRunStore:
    """SQLite-backed runtime status, run history, and reports."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._closed = False

    async def init(self):
        self._closed = False
        await asyncio.to_thread(self._init_sync)

    def _init_sync(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dreaming_runs (
                    run_id TEXT PRIMARY KEY,
                    bot_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    trigger_source TEXT NOT NULL,
                    trigger_reason TEXT,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    failed_stage TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    candidate_count INTEGER DEFAULT 0,
                    promoted_count INTEGER DEFAULT 0,
                    kept_short_term_count INTEGER DEFAULT 0,
                    discarded_count INTEGER DEFAULT 0,
                    held_sensitive_count INTEGER DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dreaming_reports (
                    run_id TEXT PRIMARY KEY,
                    bot_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    user_summary TEXT,
                    debug_summary TEXT,
                    promoted_json TEXT,
                    kept_short_term_json TEXT,
                    discarded_json TEXT,
                    held_sensitive_json TEXT,
                    promoted_refs_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dreaming_state (
                    bot_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    auto_run_enabled INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    last_run_id TEXT,
                    last_status TEXT,
                    last_summary TEXT,
                    last_error TEXT,
                    last_run_at TEXT,
                    last_working_turns INTEGER DEFAULT 0,
                    PRIMARY KEY (bot_id, user_id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dreaming_runs_bot_user ON dreaming_runs(bot_id, user_id, started_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dreaming_reports_bot_user ON dreaming_reports(bot_id, user_id, created_at DESC)")
            columns = {
                row[1]: row
                for row in conn.execute("PRAGMA table_info(dreaming_state)").fetchall()
            }
            if "last_working_turns" not in columns:
                conn.execute("ALTER TABLE dreaming_state ADD COLUMN last_working_turns INTEGER DEFAULT 0")
            conn.commit()

    async def write_state(
        self,
        *,
        bot_id: str,
        user_id: str,
        enabled: bool,
        auto_run_enabled: bool,
        last_run_id: str | None,
        last_status: str | None,
        last_summary: str | None,
        last_error: str | None,
        last_run_at: str | None,
        last_working_turns: int = 0,
    ):
        await asyncio.to_thread(
            self._write_state_sync,
            bot_id,
            user_id,
            enabled,
            auto_run_enabled,
            last_run_id,
            last_status,
            last_summary,
            last_error,
            last_run_at,
            last_working_turns,
        )

    def _write_state_sync(
        self,
        bot_id: str,
        user_id: str,
        enabled: bool,
        auto_run_enabled: bool,
        last_run_id: str | None,
        last_status: str | None,
        last_summary: str | None,
        last_error: str | None,
        last_run_at: str | None,
        last_working_turns: int = 0,
    ):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO dreaming_state (
                    bot_id, user_id, enabled, auto_run_enabled, updated_at,
                    last_run_id, last_status, last_summary, last_error, last_run_at, last_working_turns
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(bot_id, user_id) DO UPDATE SET
                    enabled = excluded.enabled,
                    auto_run_enabled = excluded.auto_run_enabled,
                    updated_at = excluded.updated_at,
                    last_run_id = excluded.last_run_id,
                    last_status = excluded.last_status,
                    last_summary = excluded.last_summary,
                    last_error = excluded.last_error,
                    last_run_at = excluded.last_run_at,
                    last_working_turns = excluded.last_working_turns
                """,
                (
                    bot_id,
                    user_id,
                    1 if enabled else 0,
                    1 if auto_run_enabled else 0,
                    _now_iso(),
                    last_run_id,
                    last_status,
                    last_summary,
                    last_error,
                    last_run_at,
                    int(last_working_turns or 0),
                ),
            )
            conn.commit()

    async def get_state(self, *, bot_id: str, user_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_state_sync, bot_id, user_id)

    def _get_state_sync(self, bot_id: str, user_id: str) -> dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT enabled, auto_run_enabled, updated_at, last_run_id, last_status,
                       last_summary, last_error, last_run_at, last_working_turns
                FROM dreaming_state
                WHERE bot_id = ? AND user_id = ?
                """,
                (bot_id, user_id),
            ).fetchone()
        if not row:
            return {}
        return {
            "enabled": bool(row["enabled"]),
            "auto_run_enabled": bool(row["auto_run_enabled"]),
            "updated_at": row["updated_at"],
            "last_run_id": row["last_run_id"],
            "last_status": row["last_status"],
            "last_summary": row["last_summary"],
            "last_error": row["last_error"],
            "last_run_at": row["last_run_at"],
            "last_working_turns": int(row["last_working_turns"] or 0),
        }

    async def create_run(self, record: dict[str, Any]):
        await asyncio.to_thread(self._create_run_sync, record)

    def _create_run_sync(self, record: dict[str, Any]):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO dreaming_runs (
                    run_id, bot_id, user_id, trigger_source, trigger_reason, status,
                    started_at, finished_at, failed_stage, error_code, error_message,
                    candidate_count, promoted_count, kept_short_term_count,
                    discarded_count, held_sensitive_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["run_id"],
                    record["bot_id"],
                    record["user_id"],
                    record["trigger_source"],
                    record.get("trigger_reason"),
                    record["status"],
                    record["started_at"],
                    record.get("finished_at"),
                    record.get("failed_stage"),
                    record.get("error_code"),
                    record.get("error_message"),
                    int(record.get("candidate_count", 0)),
                    int(record.get("promoted_count", 0)),
                    int(record.get("kept_short_term_count", 0)),
                    int(record.get("discarded_count", 0)),
                    int(record.get("held_sensitive_count", 0)),
                ),
            )
            conn.commit()

    async def update_run(self, record: dict[str, Any]):
        await asyncio.to_thread(self._update_run_sync, record)

    def _update_run_sync(self, record: dict[str, Any]):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE dreaming_runs
                SET status = ?, finished_at = ?, failed_stage = ?, error_code = ?, error_message = ?,
                    candidate_count = ?, promoted_count = ?, kept_short_term_count = ?,
                    discarded_count = ?, held_sensitive_count = ?
                WHERE run_id = ?
                """,
                (
                    record["status"],
                    record.get("finished_at"),
                    record.get("failed_stage"),
                    record.get("error_code"),
                    record.get("error_message"),
                    int(record.get("candidate_count", 0)),
                    int(record.get("promoted_count", 0)),
                    int(record.get("kept_short_term_count", 0)),
                    int(record.get("discarded_count", 0)),
                    int(record.get("held_sensitive_count", 0)),
                    record["run_id"],
                ),
            )
            conn.commit()

    async def save_report(self, report: dict[str, Any]):
        await asyncio.to_thread(self._save_report_sync, report)

    def _save_report_sync(self, report: dict[str, Any]):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO dreaming_reports (
                    run_id, bot_id, user_id, created_at, user_summary, debug_summary,
                    promoted_json, kept_short_term_json, discarded_json, held_sensitive_json,
                    promoted_refs_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report["run_id"],
                    report["bot_id"],
                    report["user_id"],
                    report["created_at"],
                    report.get("user_summary"),
                    report.get("debug_summary"),
                    json.dumps(report.get("promoted_items") or [], ensure_ascii=False),
                    json.dumps(report.get("kept_short_term_items") or [], ensure_ascii=False),
                    json.dumps(report.get("discarded_items") or [], ensure_ascii=False),
                    json.dumps(report.get("held_sensitive_items") or [], ensure_ascii=False),
                    json.dumps(report.get("promoted_refs") or [], ensure_ascii=False),
                ),
            )
            conn.commit()

    async def get_latest_report(self, *, bot_id: str, user_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_latest_report_sync, bot_id, user_id)

    def _get_latest_report_sync(self, bot_id: str, user_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT run_id, created_at, user_summary, debug_summary,
                       promoted_json, kept_short_term_json, discarded_json, held_sensitive_json,
                       promoted_refs_json
                FROM dreaming_reports
                WHERE bot_id = ? AND user_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (bot_id, user_id),
            ).fetchone()
        if not row:
            return None
        return {
            "run_id": row["run_id"],
            "created_at": row["created_at"],
            "user_summary": row["user_summary"],
            "debug_summary": row["debug_summary"],
            "promoted_items": json.loads(row["promoted_json"] or "[]"),
            "kept_short_term_items": json.loads(row["kept_short_term_json"] or "[]"),
            "discarded_items": json.loads(row["discarded_json"] or "[]"),
            "held_sensitive_items": json.loads(row["held_sensitive_json"] or "[]"),
            "promoted_refs": json.loads(row["promoted_refs_json"] or "[]"),
        }

    async def get_run(self, *, run_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_run_sync, run_id)

    def _get_run_sync(self, run_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM dreaming_runs WHERE run_id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    async def close(self):
        self._closed = True


class DreamingCandidateCollector:
    def __init__(self, memory_engine):
        self.memory_engine = memory_engine

    async def collect(self, *, bot_id: str, user_id: str, max_candidates: int) -> list[DreamingCandidate]:
        candidates: list[DreamingCandidate] = []

        daily_context = self.memory_engine.daily.get_recent_context(bot_id=bot_id, user_id=user_id, intent="planning")
        for thread in (daily_context.get("open_threads") or [])[: max_candidates]:
            text = _clean_text(thread)
            if not text:
                continue
            candidates.append(
                DreamingCandidate(
                    candidate_id=f"daily-thread:{uuid.uuid4().hex[:10]}",
                    source_layer="daily",
                    source_ref=text,
                    summary=_truncate(text, 90),
                    detail=text,
                    confidence=0.72,
                    importance=0.74,
                    sensitivity="normal",
                    proposed_target="semantic",
                    category="open_threads",
                    reason_tags=["daily_open_thread"],
                    payload={"key": f"open_thread::{text[:48]}", "value": text},
                )
            )

        for commitment in (daily_context.get("commitments") or [])[: max_candidates]:
            text = _clean_text(commitment)
            if not text:
                continue
            candidates.append(
                DreamingCandidate(
                    candidate_id=f"daily-commit:{uuid.uuid4().hex[:10]}",
                    source_layer="daily",
                    source_ref=text,
                    summary=_truncate(text, 90),
                    detail=text,
                    confidence=0.76,
                    importance=0.8,
                    sensitivity="normal",
                    proposed_target="semantic",
                    category="goals",
                    reason_tags=["daily_commitment"],
                    payload={"key": f"goal::{text[:48]}", "value": text},
                )
            )

        facts = await self.memory_engine.semantic.list_facts(
            bot_id=bot_id,
            user_id=user_id,
            min_confidence=0.0,
            include_archived=False,
            limit=max_candidates,
        )
        for fact in facts:
            key = _clean_text(fact.get("key"))
            value = _clean_text(fact.get("value"))
            if not key or not value:
                continue
            confidence = float(fact.get("confidence") or 0.7)
            if confidence >= 0.85 or fact.get("manual_override"):
                continue
            candidates.append(
                DreamingCandidate(
                    candidate_id=f"semantic:{key}",
                    source_layer="semantic",
                    source_ref=key,
                    summary=f"{key}: {value}",
                    detail=value,
                    confidence=confidence,
                    importance=min(0.9, 0.45 + confidence * 0.4),
                    sensitivity="normal",
                    proposed_target="semantic",
                    category=_clean_text(fact.get("category") or "general"),
                    reason_tags=["low_confidence_fact"],
                    payload={"key": key, "value": value, "fact": fact},
                )
            )

        recent_episodes = self.memory_engine.episodic.list_recent(limit=max_candidates, bot_id=bot_id, user_id=user_id)
        for episode in recent_episodes[:max_candidates]:
            summary = _clean_text(episode.get("summary"))
            if not summary:
                continue
            candidates.append(
                DreamingCandidate(
                    candidate_id=f"episodic:{episode.get('id')}",
                    source_layer="episodic",
                    source_ref=str(episode.get("id") or ""),
                    summary=summary,
                    detail=_clean_text(episode.get("content")),
                    confidence=float(episode.get("confidence") or 0.72),
                    importance=float(episode.get("importance") or 0.7),
                    sensitivity=_clean_text(episode.get("sensitivity") or "normal"),
                    proposed_target="episodic",
                    category="shared_experience",
                    reason_tags=["recent_episode"],
                    payload=dict(episode),
                )
            )

        relationship = await self.memory_engine.relationship.get_state(bot_id=bot_id, user_id=user_id)
        for field_name in ("relationship_narrative", "current_posture", "interaction_guidance"):
            text = _clean_text(relationship.get(field_name))
            if not text:
                continue
            candidates.append(
                DreamingCandidate(
                    candidate_id=f"relationship:{field_name}",
                    source_layer="relationship",
                    source_ref=field_name,
                    summary=_truncate(text, 90),
                    detail=text,
                    confidence=0.86,
                    importance=0.88,
                    sensitivity="normal",
                    proposed_target="understanding",
                    category="relationship",
                    reason_tags=["relationship_signal"],
                    payload={"field": field_name, "value": text},
                )
            )

        deduped: list[DreamingCandidate] = []
        seen = set()
        for item in sorted(candidates, key=lambda c: (c.importance, c.confidence), reverse=True):
            signature = (item.source_layer, item.summary, item.proposed_target)
            if signature in seen:
                continue
            seen.add(signature)
            deduped.append(item)
            if len(deduped) >= max_candidates:
                break
        return deduped


class DreamingPromotionGovernor:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def decide(self, candidates: list[DreamingCandidate]) -> list[PromotionDecision]:
        max_promotions = _int(self.config.get("max_promotions"), 6, 0)
        decisions: list[PromotionDecision] = []
        promoted = 0
        for candidate in candidates:
            if candidate.sensitivity not in {"", "normal"}:
                decisions.append(
                    PromotionDecision(
                        candidate_id=candidate.candidate_id,
                        action="hold_sensitive",
                        target_store=None,
                        reason_tags=["sensitive_memory"],
                    )
                )
                continue
            if candidate.confidence >= 0.82 and candidate.importance >= 0.72 and promoted < max_promotions:
                decisions.append(
                    PromotionDecision(
                        candidate_id=candidate.candidate_id,
                        action="promote",
                        target_store=candidate.proposed_target,
                        reason_tags=["high_value_candidate"],
                    )
                )
                promoted += 1
                continue
            if candidate.importance >= 0.62:
                decisions.append(
                    PromotionDecision(
                        candidate_id=candidate.candidate_id,
                        action="keep_short_term",
                        target_store=None,
                        reason_tags=["keep_recent_only"],
                    )
                )
                continue
            decisions.append(
                PromotionDecision(
                    candidate_id=candidate.candidate_id,
                    action="discard",
                    target_store=None,
                    reason_tags=["low_value_candidate"],
                )
            )
        return decisions


class DreamingPersistenceFacade:
    def __init__(self, memory_engine):
        self.memory_engine = memory_engine

    async def persist(
        self,
        *,
        bot_id: str,
        user_id: str,
        candidates: list[DreamingCandidate],
        decisions: list[PromotionDecision],
    ) -> list[PromotionDecision]:
        candidate_map = {item.candidate_id: item for item in candidates}
        written: list[PromotionDecision] = []
        facts_for_refresh: list[dict[str, Any]] = []
        relationship = await self.memory_engine.relationship.get_state(bot_id=bot_id, user_id=user_id)
        daily_context = self.memory_engine.daily.get_recent_context(bot_id=bot_id, user_id=user_id, intent="planning")

        for decision in decisions:
            if decision.action != "promote":
                written.append(decision)
                continue
            candidate = candidate_map.get(decision.candidate_id)
            if not candidate:
                written.append(decision)
                continue

            if decision.target_store == "semantic":
                key = _clean_text(candidate.payload.get("key")) or f"dreaming::{candidate.candidate_id}"
                value = _clean_text(candidate.payload.get("value")) or candidate.summary
                await self.memory_engine.semantic.set_fact(
                    key,
                    value,
                    bot_id=bot_id,
                    user_id=user_id,
                    category=candidate.category or "general",
                    confidence=max(candidate.confidence, 0.86),
                    source="dreaming_promoted",
                    evidence=[candidate.summary],
                )
                decision.written_ref = {"store": "semantic", "key": key}
                facts_for_refresh.append(
                    {
                        "key": key,
                        "value": value,
                        "category": candidate.category or "general",
                        "confidence": max(candidate.confidence, 0.86),
                        "source": "dreaming_promoted",
                    }
                )
            elif decision.target_store == "understanding":
                facts_for_refresh.append(
                    {
                        "key": candidate.payload.get("field") or candidate.candidate_id,
                        "value": candidate.detail or candidate.summary,
                        "category": "communication_style" if candidate.category == "relationship" else candidate.category,
                        "confidence": max(candidate.confidence, 0.86),
                        "source": "dreaming_projection",
                    }
                )
                decision.written_ref = {"store": "understanding_projection", "field": candidate.payload.get("field")}
            elif decision.target_store == "episodic":
                await self.memory_engine.episodic.store_episode(
                    summary=candidate.summary,
                    content=candidate.detail or candidate.summary,
                    bot_id=bot_id,
                    user_id=user_id,
                    importance=max(candidate.importance, 0.76),
                    confidence=max(candidate.confidence, 0.82),
                    sensitivity=candidate.sensitivity or "normal",
                    relationship_effect=_clean_text(candidate.payload.get("relationship_effect")),
                    recall_style=_clean_text(candidate.payload.get("recall_style")),
                    cue_tags=candidate.payload.get("cue_tags_json") if isinstance(candidate.payload.get("cue_tags_json"), list) else None,
                )
                decision.written_ref = {"store": "episodic", "source_ref": candidate.source_ref}
            written.append(decision)

        if facts_for_refresh:
            await self.memory_engine.user_understanding.refresh_auto_from_sources(
                facts=facts_for_refresh,
                relationship=relationship,
                daily_context=daily_context,
            )
        return written

    async def delete_promoted_refs(self, *, bot_id: str, user_id: str, refs: list[dict[str, Any]]) -> dict[str, int]:
        deleted = {"semantic": 0, "understanding_projection": 0, "episodic": 0}
        for ref in refs:
            store = _clean_text(ref.get("store"))
            if store == "semantic":
                key = _clean_text(ref.get("key"))
                if key:
                    await self.memory_engine.semantic.archive_fact(key, bot_id=bot_id, user_id=user_id, reason="dreaming_report_delete")
                    deleted["semantic"] += 1
            elif store == "understanding_projection":
                key = _clean_text(ref.get("field"))
                if key:
                    await self.memory_engine.user_understanding.delete_auto_fact(key)
                    deleted["understanding_projection"] += 1
            elif store == "episodic":
                # V1 does not selectively delete episodic items unless we carry stable ids.
                deleted["episodic"] += 0
        return deleted


class DreamingReportBuilder:
    def build(
        self,
        *,
        run_id: str,
        bot_id: str,
        user_id: str,
        candidates: list[DreamingCandidate],
        decisions: list[PromotionDecision],
    ) -> dict[str, Any]:
        candidate_map = {item.candidate_id: item for item in candidates}
        promoted_items: list[dict[str, Any]] = []
        kept_short_term_items: list[dict[str, Any]] = []
        discarded_items: list[dict[str, Any]] = []
        held_sensitive_items: list[dict[str, Any]] = []
        promoted_refs: list[dict[str, Any]] = []

        for decision in decisions:
            candidate = candidate_map.get(decision.candidate_id)
            item = {
                "candidate_id": decision.candidate_id,
                "summary": candidate.summary if candidate else "",
                "source_layer": candidate.source_layer if candidate else "",
                "reason_tags": list(decision.reason_tags),
                "target_store": decision.target_store,
                "written_ref": dict(decision.written_ref or {}),
            }
            if decision.action == "promote":
                promoted_items.append(item)
                if decision.written_ref:
                    promoted_refs.append(dict(decision.written_ref))
            elif decision.action == "keep_short_term":
                kept_short_term_items.append(item)
            elif decision.action == "discard":
                discarded_items.append(item)
            elif decision.action == "hold_sensitive":
                held_sensitive_items.append(item)

        lines = ["本次记忆整理完成。"]
        if promoted_items:
            lines.append("我保留了这些长期更有价值的内容：")
            for item in promoted_items[:5]:
                lines.append(f"- {item['summary']}")
        if kept_short_term_items:
            lines.append("这些内容暂时只保留为近期连续性：")
            for item in kept_short_term_items[:4]:
                lines.append(f"- {item['summary']}")
        if held_sensitive_items:
            lines.append("有些较敏感内容我只记录边界，不直接长期展开。")
        if discarded_items:
            lines.append("低价值或重复内容没有进入长期层。")

        debug_summary = (
            f"run={run_id} candidates={len(candidates)} promote={len(promoted_items)} "
            f"keep={len(kept_short_term_items)} discard={len(discarded_items)} "
            f"sensitive={len(held_sensitive_items)}"
        )
        return {
            "run_id": run_id,
            "bot_id": bot_id,
            "user_id": user_id,
            "created_at": _now_iso(),
            "user_summary": "\n".join(lines),
            "debug_summary": debug_summary,
            "promoted_items": promoted_items,
            "kept_short_term_items": kept_short_term_items,
            "discarded_items": discarded_items,
            "held_sensitive_items": held_sensitive_items,
            "promoted_refs": promoted_refs,
        }


class DreamingDoctor:
    def __init__(self, memory_engine, run_store: DreamingRunStore):
        self.memory_engine = memory_engine
        self.run_store = run_store

    async def inspect(self, *, bot_id: str, user_id: str) -> dict[str, Any]:
        latest_state = await self.run_store.get_state(bot_id=bot_id, user_id=user_id)
        latest_report = await self.run_store.get_latest_report(bot_id=bot_id, user_id=user_id)
        status = await self.memory_engine.get_memory_status()
        issues: list[str] = []
        suggestions: list[str] = []
        if not latest_state.get("enabled"):
            issues.append("dreaming_disabled")
            suggestions.append("开启记忆整理后，状态与报告才会持续更新。")
        if not status.get("user_understanding_path"):
            issues.append("understanding_missing")
            suggestions.append("检查 user_understanding.json 是否存在。")
        if latest_state.get("last_status") == "failed":
            issues.append("latest_run_failed")
            if latest_state.get("last_error"):
                suggestions.append(f"最近一次失败：{latest_state.get('last_error')}")
        if status.get("vector_count") in (None, 0):
            suggestions.append("如需更稳定召回，可重建向量索引。")
        return {
            "ok": not issues,
            "issues": issues,
            "suggestions": suggestions,
            "state": latest_state,
            "latest_report": latest_report,
        }


class DreamingOrchestrator:
    def __init__(self, memory_engine, config: dict[str, Any] | None = None):
        self.memory_engine = memory_engine
        self.config = self._normalize_config(config or {})
        self.run_store = DreamingRunStore(memory_engine.memory_dir / "dreaming_runs.db")
        self.collector = DreamingCandidateCollector(memory_engine)
        self.governor = DreamingPromotionGovernor(self.config)
        self.persistence = DreamingPersistenceFacade(memory_engine)
        self.report_builder = DreamingReportBuilder()
        self.doctor = DreamingDoctor(memory_engine, self.run_store)
        self.scheduler = DreamingScheduler(self)

    def _normalize_config(self, config: dict[str, Any]) -> dict[str, Any]:
        merged = dict(DEFAULT_DREAMING_CONFIG)
        dreaming = config.get("dreaming") if isinstance(config.get("dreaming"), dict) else config
        merged.update(dreaming if isinstance(dreaming, dict) else {})
        return {
            "enabled": _bool(merged.get("enabled"), DEFAULT_DREAMING_CONFIG["enabled"]),
            "auto_run_enabled": _bool(merged.get("auto_run_enabled"), DEFAULT_DREAMING_CONFIG["auto_run_enabled"]),
            "auto_check_interval_seconds": _int(merged.get("auto_check_interval_seconds"), DEFAULT_DREAMING_CONFIG["auto_check_interval_seconds"], 30, 86400),
            "min_run_interval_minutes": _int(merged.get("min_run_interval_minutes"), DEFAULT_DREAMING_CONFIG["min_run_interval_minutes"], 1, 10080),
            "min_new_messages": _int(merged.get("min_new_messages"), DEFAULT_DREAMING_CONFIG["min_new_messages"], 1, 500),
            "report_retention": _int(merged.get("report_retention"), DEFAULT_DREAMING_CONFIG["report_retention"], 1, 100),
            "max_candidates": _int(merged.get("max_candidates"), DEFAULT_DREAMING_CONFIG["max_candidates"], 1, 200),
            "max_promotions": _int(merged.get("max_promotions"), DEFAULT_DREAMING_CONFIG["max_promotions"], 0, 50),
            "show_sensitive_reason_only": _bool(merged.get("show_sensitive_reason_only"), True),
        }

    @property
    def auto_check_interval_seconds(self) -> int:
        return int(self.config.get("auto_check_interval_seconds") or DEFAULT_DREAMING_CONFIG["auto_check_interval_seconds"])

    async def init(self):
        await self.run_store.init()
        await self.run_store.write_state(
            bot_id=self.memory_engine.bot_id,
            user_id=self.memory_engine.user_id,
            enabled=self.config["enabled"],
            auto_run_enabled=self.config["auto_run_enabled"],
            last_run_id=None,
            last_status=None,
            last_summary=None,
            last_error=None,
            last_run_at=None,
            last_working_turns=0,
        )

    def configure(self, config: dict[str, Any] | None):
        self.config = self._normalize_config(config or {})

    async def set_enabled(self, enabled: bool):
        self.config["enabled"] = bool(enabled)
        state = await self.run_store.get_state(bot_id=self.memory_engine.bot_id, user_id=self.memory_engine.user_id)
        await self.run_store.write_state(
            bot_id=self.memory_engine.bot_id,
            user_id=self.memory_engine.user_id,
            enabled=bool(enabled),
            auto_run_enabled=self.config["auto_run_enabled"],
            last_run_id=state.get("last_run_id"),
            last_status=state.get("last_status"),
            last_summary=state.get("last_summary"),
            last_error=state.get("last_error"),
            last_run_at=state.get("last_run_at"),
            last_working_turns=state.get("last_working_turns", 0),
        )

    async def status(self) -> dict[str, Any]:
        state = await self.run_store.get_state(bot_id=self.memory_engine.bot_id, user_id=self.memory_engine.user_id)
        latest_report = await self.run_store.get_latest_report(bot_id=self.memory_engine.bot_id, user_id=self.memory_engine.user_id)
        return {
            "enabled": self.config["enabled"],
            "auto_run_enabled": self.config["auto_run_enabled"],
            "auto_check_interval_seconds": self.config["auto_check_interval_seconds"],
            "min_run_interval_minutes": self.config["min_run_interval_minutes"],
            "min_new_messages": self.config["min_new_messages"],
            "report_retention": self.config["report_retention"],
            "max_candidates": self.config["max_candidates"],
            "max_promotions": self.config["max_promotions"],
            "scheduler": self.scheduler.get_status(),
            **state,
            "latest_report": latest_report,
        }

    async def latest_report(self) -> dict[str, Any] | None:
        return await self.run_store.get_latest_report(bot_id=self.memory_engine.bot_id, user_id=self.memory_engine.user_id)

    async def should_auto_run(self) -> bool:
        state = await self.run_store.get_state(bot_id=self.memory_engine.bot_id, user_id=self.memory_engine.user_id)
        current_session = self.memory_engine._session_id or self.memory_engine.working.current_session
        current_turns = self.memory_engine.working.get_turn_count(current_session) if current_session else 0
        last_turns = int(state.get("last_working_turns") or 0)
        if current_turns <= 0:
            return False
        if (current_turns - last_turns) < int(self.config.get("min_new_messages") or 1):
            return False
        last_run_at = _clean_text(state.get("last_run_at"))
        if last_run_at:
            try:
                last_dt = datetime.fromisoformat(last_run_at)
                delta_seconds = (datetime.now() - last_dt).total_seconds()
                if delta_seconds < int(self.config.get("min_run_interval_minutes") or 0) * 60:
                    return False
            except Exception:
                pass
        return True

    async def run(self, *, trigger_source: str, trigger_reason: str = "") -> dict[str, Any]:
        run_id = uuid.uuid4().hex
        started_at = _now_iso()
        current_session = self.memory_engine._session_id or self.memory_engine.working.current_session
        current_turns = self.memory_engine.working.get_turn_count(current_session) if current_session else 0
        record = {
            "run_id": run_id,
            "bot_id": self.memory_engine.bot_id,
            "user_id": self.memory_engine.user_id,
            "trigger_source": trigger_source,
            "trigger_reason": trigger_reason,
            "status": "running",
            "started_at": started_at,
            "candidate_count": 0,
            "promoted_count": 0,
            "kept_short_term_count": 0,
            "discarded_count": 0,
            "held_sensitive_count": 0,
        }
        await self.run_store.create_run(record)

        try:
            candidates = await self.collector.collect(
                bot_id=self.memory_engine.bot_id,
                user_id=self.memory_engine.user_id,
                max_candidates=self.config["max_candidates"],
            )
            decisions = self.governor.decide(candidates)
            decisions = await self.persistence.persist(
                bot_id=self.memory_engine.bot_id,
                user_id=self.memory_engine.user_id,
                candidates=candidates,
                decisions=decisions,
            )
            report = self.report_builder.build(
                run_id=run_id,
                bot_id=self.memory_engine.bot_id,
                user_id=self.memory_engine.user_id,
                candidates=candidates,
                decisions=decisions,
            )
            await self.run_store.save_report(report)
            record.update(
                {
                    "status": "completed",
                    "finished_at": _now_iso(),
                    "candidate_count": len(candidates),
                    "promoted_count": len(report["promoted_items"]),
                    "kept_short_term_count": len(report["kept_short_term_items"]),
                    "discarded_count": len(report["discarded_items"]),
                    "held_sensitive_count": len(report["held_sensitive_items"]),
                }
            )
            await self.run_store.update_run(record)
            await self.run_store.write_state(
                bot_id=self.memory_engine.bot_id,
                user_id=self.memory_engine.user_id,
                enabled=self.config["enabled"],
                auto_run_enabled=self.config["auto_run_enabled"],
                last_run_id=run_id,
                last_status="completed",
                last_summary=report["user_summary"],
                last_error=None,
                last_run_at=record["finished_at"],
                last_working_turns=current_turns,
            )
            return {
                "run": record,
                "report": report,
            }
        except Exception as exc:
            record.update(
                {
                    "status": "failed",
                    "finished_at": _now_iso(),
                    "failed_stage": "run",
                    "error_code": type(exc).__name__,
                    "error_message": str(exc),
                }
            )
            await self.run_store.update_run(record)
            await self.run_store.write_state(
                bot_id=self.memory_engine.bot_id,
                user_id=self.memory_engine.user_id,
                enabled=self.config["enabled"],
                auto_run_enabled=self.config["auto_run_enabled"],
                last_run_id=run_id,
                last_status="failed",
                last_summary=None,
                last_error=str(exc),
                last_run_at=record["finished_at"],
                last_working_turns=current_turns,
            )
            raise

    async def doctor_status(self) -> dict[str, Any]:
        return await self.doctor.inspect(bot_id=self.memory_engine.bot_id, user_id=self.memory_engine.user_id)

    async def delete_latest_promotions(self) -> dict[str, Any]:
        latest_report = await self.latest_report()
        if not latest_report:
            return {"deleted": {}, "ok": False, "message": "暂无可删除的最近整理结果。"}
        deleted = await self.persistence.delete_promoted_refs(
            bot_id=self.memory_engine.bot_id,
            user_id=self.memory_engine.user_id,
            refs=latest_report.get("promoted_refs") or [],
        )
        return {"deleted": deleted, "ok": True, "run_id": latest_report.get("run_id")}

    async def start_scheduler(self):
        await self.scheduler.start()

    async def stop_scheduler(self):
        await self.scheduler.stop()

    async def close(self):
        try:
            await self.stop_scheduler()
        except Exception:
            pass
        await self.run_store.close()
        self.collector = None
        self.governor = None
        self.persistence = None
        self.report_builder = None
        self.doctor = None
