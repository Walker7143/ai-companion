from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import aiosqlite


def _utcnow() -> str:
    return datetime.now().isoformat()


def _clean_text(value: object, limit: int = 240) -> str:
    text = " ".join(str(value or "").strip().split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _loads_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


@dataclass
class SessionStateItem:
    state_id: str
    session_id: str
    scope: str
    subject: str
    predicate: str
    value: str
    confidence: float
    status: str
    effective_at: str
    expires_at: str | None = None
    source_kind: str = "user_explicit"
    evidence_turn_ids: list[str] = field(default_factory=list)
    supersedes_state_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_id": self.state_id,
            "session_id": self.session_id,
            "scope": self.scope,
            "subject": self.subject,
            "predicate": self.predicate,
            "value": self.value,
            "confidence": self.confidence,
            "status": self.status,
            "effective_at": self.effective_at,
            "expires_at": self.expires_at,
            "source_kind": self.source_kind,
            "evidence_turn_ids": list(self.evidence_turn_ids),
            "supersedes_state_ids": list(self.supersedes_state_ids),
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class SessionStateDiff:
    upserts: list[dict[str, Any]] = field(default_factory=list)
    confirmations: list[dict[str, Any]] = field(default_factory=list)
    invalidations: list[dict[str, Any]] = field(default_factory=list)
    no_change: bool = False
    confidence_explanations: list[str] = field(default_factory=list)


class SessionStateStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS session_states (
                    state_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    value TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.7,
                    status TEXT NOT NULL DEFAULT 'active',
                    effective_at TEXT NOT NULL,
                    expires_at TEXT,
                    source_kind TEXT NOT NULL DEFAULT 'user_explicit',
                    evidence_turn_ids_json TEXT,
                    supersedes_state_ids_json TEXT,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS session_state_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    state_id TEXT,
                    payload_json TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_session_states_session ON session_states(session_id, status, updated_at)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_session_states_slot ON session_states(session_id, scope, predicate, status)")
            await db.commit()

    async def upsert_state(self, item: SessionStateItem):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO session_states (
                    state_id, session_id, scope, subject, predicate, value, confidence,
                    status, effective_at, expires_at, source_kind, evidence_turn_ids_json,
                    supersedes_state_ids_json, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(state_id) DO UPDATE SET
                    value = excluded.value,
                    confidence = excluded.confidence,
                    status = excluded.status,
                    effective_at = excluded.effective_at,
                    expires_at = excluded.expires_at,
                    source_kind = excluded.source_kind,
                    evidence_turn_ids_json = excluded.evidence_turn_ids_json,
                    supersedes_state_ids_json = excluded.supersedes_state_ids_json,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    item.state_id,
                    item.session_id,
                    item.scope,
                    item.subject,
                    item.predicate,
                    item.value,
                    float(item.confidence),
                    item.status,
                    item.effective_at,
                    item.expires_at,
                    item.source_kind,
                    json.dumps(item.evidence_turn_ids, ensure_ascii=False),
                    json.dumps(item.supersedes_state_ids, ensure_ascii=False),
                    json.dumps(item.metadata, ensure_ascii=False),
                    item.created_at,
                    item.updated_at,
                ),
            )
            await db.commit()

    async def append_event(self, session_id: str, event_type: str, payload: dict[str, Any], state_id: str | None = None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO session_state_events (session_id, event_type, state_id, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, event_type, state_id, json.dumps(payload, ensure_ascii=False), _utcnow()),
            )
            await db.commit()

    async def mark_superseded(self, state_ids: list[str]):
        if not state_ids:
            return
        async with aiosqlite.connect(self.db_path) as db:
            placeholders = ", ".join("?" for _ in state_ids)
            params = [_utcnow(), *state_ids]
            await db.execute(
                f"UPDATE session_states SET status = 'superseded', updated_at = ? WHERE state_id IN ({placeholders})",
                params,
            )
            await db.commit()

    async def mark_invalidated(self, state_ids: list[str]):
        if not state_ids:
            return
        async with aiosqlite.connect(self.db_path) as db:
            placeholders = ", ".join("?" for _ in state_ids)
            params = [_utcnow(), *state_ids]
            await db.execute(
                f"UPDATE session_states SET status = 'expired', updated_at = ? WHERE state_id IN ({placeholders})",
                params,
            )
            await db.commit()

    async def list_active_states(self, session_id: str) -> list[SessionStateItem]:
        items = await self._list_states(session_id=session_id, statuses={"active", "tentative"})
        latest_by_slot: dict[tuple[str, str], SessionStateItem] = {}
        for item in items:
            slot = (item.scope, item.predicate)
            existing = latest_by_slot.get(slot)
            if existing is None or str(item.updated_at or "") > str(existing.updated_at or ""):
                latest_by_slot[slot] = item
        return sorted(latest_by_slot.values(), key=lambda item: str(item.updated_at or ""), reverse=True)

    async def list_recent_states(self, session_id: str, limit: int = 12) -> list[SessionStateItem]:
        return await self._list_states(session_id=session_id, statuses=None, limit=limit)

    async def _list_states(
        self,
        *,
        session_id: str,
        statuses: set[str] | None,
        limit: int | None = None,
    ) -> list[SessionStateItem]:
        clauses = ["session_id = ?"]
        params: list[Any] = [session_id]
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            params.extend(sorted(statuses))
        clauses.append("(expires_at IS NULL OR expires_at > ?)")
        params.append(_utcnow())
        sql = f"""
            SELECT state_id, session_id, scope, subject, predicate, value, confidence, status,
                   effective_at, expires_at, source_kind, evidence_turn_ids_json,
                   supersedes_state_ids_json, metadata_json, created_at, updated_at
            FROM session_states
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC
        """
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()
        return [self._row_to_item(row) for row in rows]

    def _row_to_item(self, row) -> SessionStateItem:
        return SessionStateItem(
            state_id=row[0],
            session_id=row[1],
            scope=row[2],
            subject=row[3],
            predicate=row[4],
            value=row[5],
            confidence=float(row[6] or 0.0),
            status=row[7],
            effective_at=row[8],
            expires_at=row[9],
            source_kind=row[10],
            evidence_turn_ids=_as_list(json.loads(row[11]) if row[11] else []),
            supersedes_state_ids=_as_list(json.loads(row[12]) if row[12] else []),
            metadata=_loads_dict(row[13]),
            created_at=row[14],
            updated_at=row[15],
        )


class SessionStateExtractor:
    EXTRACT_PROMPT = """你是短时世界状态跟踪器。

任务：基于当前这一轮对话、最近上下文、以及当前已知活跃状态，输出“相对旧状态的变化 diff”。

当前活跃状态:
{active_states}

最近上下文:
{conversation_context}

当前这一轮:
用户: {user_input}
助手: {bot_output}

输出 JSON:
{{
  "upserts": [
    {{
      "scope": "trip/lodging|trip/route|current_scene|task/status|meeting/time|...",
      "subject": "user|assistant|shared|external",
      "predicate": "booking_status|route_status|current_destination|task_completion|...",
      "value": "语义化状态值，不要照抄原句",
      "confidence": 0.0,
      "source_kind": "user_explicit|joint_inference|bot_commitment_confirmed",
      "expires_hours": 72,
      "reason": "为什么这轮应写入该状态"
    }}
  ],
  "confirmations": [
    {{
      "scope": "...",
      "predicate": "...",
      "reason": "为什么是确认而不是新状态"
    }}
  ],
  "invalidations": [
    {{
      "scope": "...",
      "predicate": "...",
      "reason": "为什么旧状态应失效"
    }}
  ],
  "no_change": false,
  "confidence_explanations": ["简短解释"]
}}

要求:
- 只输出状态语义，不要摘抄原句。
- 这是 diff，不是重写整份状态。
- 如果没有足够证据，请输出 no_change=true。
- 不要编造用户未明确建立的状态。
"""

    def __init__(self, summarizer: object | None = None):
        self._summarizer = summarizer

    def set_summarizer(self, summarizer):
        self._summarizer = summarizer

    async def extract(
        self,
        *,
        user_input: str,
        bot_output: str,
        conversation_context: str,
        active_states: list[SessionStateItem],
    ) -> SessionStateDiff:
        if self._summarizer is None:
            return SessionStateDiff(no_change=True)
        active_text = "\n".join(
            f"- {item.scope} / {item.predicate} = {item.value} [{item.status}]"
            for item in active_states[:8]
        ) or "无"
        prompt = self.EXTRACT_PROMPT.format(
            active_states=active_text,
            conversation_context=conversation_context or "无",
            user_input=user_input,
            bot_output=bot_output,
        )
        try:
            response = await self._summarizer.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=None,
            )
            text = str(response.get("content") if isinstance(response, dict) else response or "").strip()
            text = re.sub(r"```json\s*", "", text)
            text = re.sub(r"```\s*", "", text).strip()
            payload = json.loads(text)
        except Exception:
            return SessionStateDiff(no_change=True)
        if not isinstance(payload, dict):
            return SessionStateDiff(no_change=True)
        return SessionStateDiff(
            upserts=payload.get("upserts") if isinstance(payload.get("upserts"), list) else [],
            confirmations=payload.get("confirmations") if isinstance(payload.get("confirmations"), list) else [],
            invalidations=payload.get("invalidations") if isinstance(payload.get("invalidations"), list) else [],
            no_change=bool(payload.get("no_change")),
            confidence_explanations=_as_list(payload.get("confidence_explanations")),
        )


class SessionStateResolver:
    async def apply_diff(
        self,
        *,
        store: SessionStateStore,
        session_id: str,
        diff: SessionStateDiff,
        evidence_turn_id: str,
    ) -> dict[str, Any]:
        active = await store.list_active_states(session_id)
        active_by_slot = {(item.scope, item.predicate): item for item in active}
        written: list[dict[str, Any]] = []
        superseded_ids: list[str] = []
        invalidated_ids: list[str] = []
        now = _utcnow()

        for item in diff.invalidations:
            if not isinstance(item, dict):
                continue
            slot = (str(item.get("scope") or "").strip(), str(item.get("predicate") or "").strip())
            current = active_by_slot.get(slot)
            if current:
                invalidated_ids.append(current.state_id)

        for item in diff.upserts:
            if not isinstance(item, dict):
                continue
            scope = str(item.get("scope") or "").strip()
            predicate = str(item.get("predicate") or "").strip()
            subject = str(item.get("subject") or "shared").strip() or "shared"
            value = _clean_text(item.get("value"), 200)
            if not scope or not predicate or not value:
                continue
            slot = (scope, predicate)
            current = active_by_slot.get(slot)
            state_id = str(uuid.uuid4())
            supersedes_state_ids: list[str] = []
            if current:
                superseded_ids.append(current.state_id)
                supersedes_state_ids.append(current.state_id)
            expires_hours = item.get("expires_hours")
            expires_at = None
            try:
                if expires_hours is not None:
                    expires_at = (datetime.now() + timedelta(hours=max(1, int(expires_hours)))).isoformat()
            except (TypeError, ValueError):
                expires_at = None
            state = SessionStateItem(
                state_id=state_id,
                session_id=session_id,
                scope=scope,
                subject=subject,
                predicate=predicate,
                value=value,
                confidence=max(0.0, min(1.0, float(item.get("confidence") or 0.7))),
                status="active",
                effective_at=now,
                expires_at=expires_at,
                source_kind=str(item.get("source_kind") or "user_explicit"),
                evidence_turn_ids=[evidence_turn_id],
                supersedes_state_ids=supersedes_state_ids,
                metadata={"reason": str(item.get("reason") or "").strip()},
                created_at=now,
                updated_at=now,
            )
            await store.upsert_state(state)
            await store.append_event(session_id, "upsert", state.to_dict(), state_id=state.state_id)
            written.append(state.to_dict())

        if superseded_ids:
            await store.mark_superseded(sorted(set(superseded_ids)))
        if invalidated_ids:
            await store.mark_invalidated(sorted(set(invalidated_ids)))

        for item in diff.confirmations:
            if not isinstance(item, dict):
                continue
            slot = (str(item.get("scope") or "").strip(), str(item.get("predicate") or "").strip())
            current = active_by_slot.get(slot)
            if current:
                current.confidence = max(current.confidence, 0.9)
                current.updated_at = now
                current.evidence_turn_ids = list(dict.fromkeys([*current.evidence_turn_ids, evidence_turn_id]))
                current.metadata["confirmation_reason"] = str(item.get("reason") or "").strip()
                await store.upsert_state(current)
                await store.append_event(session_id, "confirmation", current.to_dict(), state_id=current.state_id)

        return {
            "written": written,
            "superseded_state_ids": sorted(set(superseded_ids)),
            "invalidated_state_ids": sorted(set(invalidated_ids)),
            "no_change": diff.no_change,
            "confidence_explanations": list(diff.confidence_explanations),
        }


class ResponseStateConsistencyChecker:
    CHECK_PROMPT = """你是对话状态一致性裁判。

当前活跃状态:
{active_states}

候选回复:
{response}

判断回复是否和当前状态冲突。只输出 JSON:
{{
  "consistent": true,
  "severity": "none|low|medium|high",
  "conflicts": ["..."],
  "rewrite_guidance": ""
}}

要求:
- 如果回复否认已确认状态，判为冲突。
- 如果回复重新引入已被覆盖的旧设定，判为冲突。
- 不要因为语气变化误判。
"""

    REWRITE_PROMPT = """你要重写一条回复，使其与当前状态保持一致，同时尽量保留原有语气。

当前活跃状态:
{active_states}

原回复:
{response}

冲突说明:
{conflicts}

只输出可直接发给用户的最终回复，不要解释。"""

    def __init__(self, summarizer: object | None = None):
        self._summarizer = summarizer

    def set_summarizer(self, summarizer):
        self._summarizer = summarizer

    async def check(self, response: str, active_states: list[SessionStateItem]) -> dict[str, Any]:
        if self._summarizer is None or not active_states:
            return {"consistent": True, "severity": "none", "conflicts": [], "rewrite_guidance": ""}
        active_text = "\n".join(
            f"- {item.scope} / {item.predicate} = {item.value}"
            for item in active_states[:8]
        )
        prompt = self.CHECK_PROMPT.format(active_states=active_text, response=response)
        try:
            raw = await self._summarizer.chat(messages=[{"role": "user", "content": prompt}], system_prompt=None)
            text = str(raw.get("content") if isinstance(raw, dict) else raw or "").strip()
            text = re.sub(r"```json\s*", "", text)
            text = re.sub(r"```\s*", "", text).strip()
            payload = json.loads(text)
            if isinstance(payload, dict):
                return {
                    "consistent": bool(payload.get("consistent", True)),
                    "severity": str(payload.get("severity") or "none"),
                    "conflicts": _as_list(payload.get("conflicts")),
                    "rewrite_guidance": str(payload.get("rewrite_guidance") or ""),
                }
        except Exception:
            pass
        return {"consistent": True, "severity": "none", "conflicts": [], "rewrite_guidance": ""}

    async def rewrite(self, response: str, active_states: list[SessionStateItem], conflicts: list[str]) -> str:
        if self._summarizer is None or not conflicts:
            return response
        active_text = "\n".join(
            f"- {item.scope} / {item.predicate} = {item.value}"
            for item in active_states[:8]
        )
        prompt = self.REWRITE_PROMPT.format(
            active_states=active_text,
            response=response,
            conflicts="\n".join(f"- {item}" for item in conflicts),
        )
        try:
            raw = await self._summarizer.chat(messages=[{"role": "user", "content": prompt}], system_prompt=None)
            text = str(raw.get("content") if isinstance(raw, dict) else raw or "").strip()
            if text:
                return text
        except Exception:
            pass
        return response


class RelationshipConsistencyChecker:
    DENIAL_PATTERNS = (
        "没答应",
        "不记得承认",
        "谁给你封的官",
        "谁封的官",
        "还不是",
        "别乱认",
        "我怎么不记得批准",
        "没批准过这任命",
    )

    CHECK_PROMPT = """你是关系一致性裁判。

当前关系状态:
{relationship_state}

候选回复:
{response}

判断回复是否否认了已经确认的关系事实。只输出 JSON:
{{
  "consistent": true,
  "severity": "none|low|medium|high",
  "conflicts": ["..."],
  "rewrite_guidance": ""
}}

要求:
- 如果关系标签已经是恋人/男女朋友，回复不能再说“没答应”“不记得承认”“谁封的官”等否认关系事实的话。
- 可以嘴硬、害羞、别扭，但不能推翻已确认关系。
"""

    REWRITE_PROMPT = """你要重写一条回复，使其承接已经确认的关系事实，同时尽量保留原有语气。

当前关系状态:
{relationship_state}

原回复:
{response}

冲突说明:
{conflicts}

只输出可直接发给用户的最终回复，不要解释。"""

    def __init__(self, summarizer: object | None = None):
        self._summarizer = summarizer

    def set_summarizer(self, summarizer):
        self._summarizer = summarizer

    def rule_check(self, response: str, relationship_state: dict[str, Any] | None) -> dict[str, Any]:
        state = relationship_state if isinstance(relationship_state, dict) else {}
        label = str(state.get("relationship_label") or state.get("relationship_level") or "").strip()
        if label not in {"恋人", "男女朋友", "男朋友", "女朋友", "伴侣", "爱人", "老婆", "老公"}:
            return {"consistent": True, "severity": "none", "conflicts": [], "rewrite_guidance": "", "matched_rules": []}
        text = str(response or "").strip()
        matched = [pattern for pattern in self.DENIAL_PATTERNS if pattern and pattern in text]
        if not matched:
            return {"consistent": True, "severity": "none", "conflicts": [], "rewrite_guidance": "", "matched_rules": []}
        return {
            "consistent": False,
            "severity": "high",
            "conflicts": [f"回复包含对已确认关系的否认模板: {pattern}" for pattern in matched],
            "rewrite_guidance": "承接已确认关系；可以嘴硬或傲娇，但不能否认关系本身。",
            "matched_rules": matched,
        }

    async def llm_check(self, response: str, relationship_state: dict[str, Any] | None) -> dict[str, Any]:
        state = relationship_state if isinstance(relationship_state, dict) else {}
        label = str(state.get("relationship_label") or state.get("relationship_level") or "").strip()
        if self._summarizer is None or not label:
            return {"consistent": True, "severity": "none", "conflicts": [], "rewrite_guidance": ""}
        prompt = self.CHECK_PROMPT.format(
            relationship_state=json.dumps(state, ensure_ascii=False),
            response=response,
        )
        try:
            raw = await self._summarizer.chat(messages=[{"role": "user", "content": prompt}], system_prompt=None)
            text = str(raw.get("content") if isinstance(raw, dict) else raw or "").strip()
            text = re.sub(r"```json\s*", "", text)
            text = re.sub(r"```\s*", "", text).strip()
            payload = json.loads(text)
            if isinstance(payload, dict):
                return {
                    "consistent": bool(payload.get("consistent", True)),
                    "severity": str(payload.get("severity") or "none"),
                    "conflicts": _as_list(payload.get("conflicts")),
                    "rewrite_guidance": str(payload.get("rewrite_guidance") or ""),
                }
        except Exception:
            pass
        return {"consistent": True, "severity": "none", "conflicts": [], "rewrite_guidance": ""}

    async def check(self, response: str, relationship_state: dict[str, Any] | None) -> dict[str, Any]:
        rule_result = self.rule_check(response, relationship_state)
        llm_result = await self.llm_check(response, relationship_state)
        consistent = bool(rule_result.get("consistent", True) and llm_result.get("consistent", True))
        severity = "none"
        if not consistent:
            severity = "high" if rule_result.get("matched_rules") else str(llm_result.get("severity") or "high")
        return {
            "consistent": consistent,
            "severity": severity,
            "conflicts": [*(rule_result.get("conflicts") or []), *(llm_result.get("conflicts") or [])],
            "rewrite_guidance": rule_result.get("rewrite_guidance") or llm_result.get("rewrite_guidance") or "",
            "matched_rules": rule_result.get("matched_rules") or [],
        }

    async def rewrite(self, response: str, relationship_state: dict[str, Any] | None, conflicts: list[str]) -> str:
        state = relationship_state if isinstance(relationship_state, dict) else {}
        if self._summarizer is None or not conflicts or not state:
            return response
        prompt = self.REWRITE_PROMPT.format(
            relationship_state=json.dumps(state, ensure_ascii=False),
            response=response,
            conflicts="\n".join(f"- {item}" for item in conflicts),
        )
        try:
            raw = await self._summarizer.chat(messages=[{"role": "user", "content": prompt}], system_prompt=None)
            text = str(raw.get("content") if isinstance(raw, dict) else raw or "").strip()
            if text:
                return text
        except Exception:
            pass
        return response
