"""Memory lifecycle orchestration.

This module owns write-side memory evolution: confirmation, supersession,
archival, and lifecycle event logging.  Stores keep durable data; the lifecycle
manager decides how a new candidate changes the existing memory graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .extractor import MemoryCandidate


@dataclass
class LifecycleDecision:
    """Decision made before a candidate is written."""

    candidate: MemoryCandidate
    action: str = "write"
    reason: str = ""
    skip_reason: str | None = None
    confirmed: bool = False
    superseded: bool = False
    archived: list[dict[str, Any]] = field(default_factory=list)


class MemoryLifecycleManager:
    """Coordinate durable memory evolution across stores."""

    STABLE_FACT_CATEGORIES = {
        "identity",
        "preferences",
        "dislikes",
        "boundaries",
        "communication_style",
        "important_people",
        "routines",
    }

    def __init__(self, *, semantic_store, relationship_store=None, user_understanding=None):
        self.semantic = semantic_store
        self.relationship = relationship_store
        self.user_understanding = user_understanding

    async def prepare_user_fact(
        self,
        candidate: MemoryCandidate,
        *,
        bot_id: str,
        user_id: str,
        session_id: str,
    ) -> LifecycleDecision:
        candidate = candidate.normalized()
        confirmed = self._is_confirmed_user_fact(candidate)
        if confirmed:
            candidate.confidence = max(candidate.confidence, 0.9)
            if candidate.source in {"auto", "rule"}:
                candidate.source = "user_confirmed"
            if candidate.category in self.STABLE_FACT_CATEGORIES:
                candidate.ttl_days = None

        existing = await self.semantic.get_fact_record(
            candidate.key,
            bot_id=bot_id,
            user_id=user_id,
            include_archived=False,
        )
        if not existing:
            return LifecycleDecision(
                candidate=candidate,
                action="promote" if confirmed else "write",
                reason="new_confirmed_fact" if confirmed else "new_observed_fact",
                confirmed=confirmed,
            )

        old_value = str(existing.get("value") or "").strip()
        new_value = str(candidate.value or "").strip()
        if _same_memory_value(old_value, new_value):
            candidate.confidence = max(candidate.confidence, _float(existing.get("confidence")))
            if not confirmed and existing.get("source"):
                candidate.source = str(existing.get("source"))
            return LifecycleDecision(
                candidate=candidate,
                action="confirm" if confirmed else "refresh",
                reason="same_fact_confirmed" if confirmed else "same_fact_observed_again",
                confirmed=confirmed,
            )

        if not self._should_supersede(existing, candidate, confirmed=confirmed):
            await self.semantic.record_lifecycle_event(
                memory_type="semantic_fact",
                memory_key=candidate.key,
                action="conflict_skip",
                reason="incoming_fact_weaker_than_existing",
                before=existing,
                after=_candidate_dict(candidate),
                evidence=candidate.evidence,
                bot_id=bot_id,
                user_id=user_id,
            )
            return LifecycleDecision(
                candidate=candidate,
                action="skip",
                reason="incoming_fact_weaker_than_existing",
                skip_reason="weaker_conflict",
            )

        reason = "user_confirmed_supersession" if confirmed else "newer_fact_supersedes_old_value"
        await self.semantic.record_fact_supersession(
            old_fact=existing,
            new_value=candidate.value,
            reason=reason,
            bot_id=bot_id,
            user_id=user_id,
        )
        await self.semantic.record_lifecycle_event(
            memory_type="semantic_fact",
            memory_key=candidate.key,
            action="supersede",
            reason=reason,
            before=existing,
            after=_candidate_dict(candidate),
            evidence=candidate.evidence,
            bot_id=bot_id,
            user_id=user_id,
        )
        return LifecycleDecision(
            candidate=candidate,
            action="supersede",
            reason=reason,
            confirmed=confirmed,
            superseded=True,
        )

    async def after_user_fact_written(
        self,
        decision: LifecycleDecision,
        *,
        bot_id: str,
        user_id: str,
    ):
        candidate = decision.candidate
        if decision.confirmed:
            await self.semantic.confirm_fact(
                candidate.key,
                bot_id=bot_id,
                user_id=user_id,
                confidence=max(candidate.confidence, 0.92),
                source="user_confirmed",
                evidence=candidate.evidence,
            )
        if decision.action not in {"supersede", "conflict_skip"}:
            await self.semantic.record_lifecycle_event(
                memory_type="semantic_fact",
                memory_key=candidate.key,
                action=decision.action,
                reason=decision.reason,
                after=_candidate_dict(candidate),
                evidence=candidate.evidence,
                bot_id=bot_id,
                user_id=user_id,
            )

    async def prepare_relationship_event(
        self,
        candidate: MemoryCandidate,
        *,
        bot_id: str,
        user_id: str,
    ) -> LifecycleDecision:
        candidate = candidate.normalized()
        meta = dict(candidate.metadata or {})
        label = _normalize_relationship_label(meta.get("label") or candidate.value)
        if label == "恋人":
            candidate.confidence = max(candidate.confidence, 0.9)
            if not str(meta.get("key_moment") or "").strip():
                meta["key_moment"] = "确认恋人/男女朋友关系"
            meta["label"] = "恋人"
            candidate.metadata = meta
            await self.semantic.record_lifecycle_event(
                memory_type="relationship",
                memory_key="relationship_state",
                action="confirm",
                reason="confirmed_committed_relationship",
                after=_candidate_dict(candidate),
                evidence=candidate.evidence,
                bot_id=bot_id,
                user_id=user_id,
            )
            return LifecycleDecision(
                candidate=candidate,
                action="confirm",
                reason="confirmed_committed_relationship",
                confirmed=True,
            )
        return LifecycleDecision(candidate=candidate, action="write", reason="relationship_event")

    async def after_relationship_written(
        self,
        state: dict,
        decision: LifecycleDecision,
        *,
        bot_id: str,
        user_id: str,
    ) -> list[dict]:
        label = str(state.get("relationship_label") or "").strip()
        archived: list[dict] = []
        if _is_committed_relationship(label):
            archived = await self.semantic.archive_facts_matching(
                bot_id=bot_id,
                user_id=user_id,
                categories={"open_threads", "general", "life_context"},
                predicate=lambda fact: _is_stale_pre_commitment_thread(
                    f"{fact.get('key', '')} {fact.get('value', '')}"
                ),
                reason="confirmed_relationship_supersedes_pre_commitment_threads",
            )
            await self.semantic.record_lifecycle_event(
                memory_type="relationship",
                memory_key="relationship_state",
                action="stabilize",
                reason="committed_relationship_is_stable_anchor",
                after=state,
                evidence=decision.candidate.evidence,
                bot_id=bot_id,
                user_id=user_id,
            )
        decision.archived = archived
        return archived

    def _should_supersede(self, existing: dict, candidate: MemoryCandidate, *, confirmed: bool) -> bool:
        if bool(existing.get("manual_override")):
            return False
        if confirmed:
            return True
        old_confidence = _float(existing.get("confidence"))
        if candidate.confidence >= max(0.72, old_confidence - 0.05):
            return True
        if candidate.source in {"rule_explicit_correction", "user_explicit", "user_confirmed"}:
            return candidate.confidence >= old_confidence - 0.18
        return False

    def _is_confirmed_user_fact(self, candidate: MemoryCandidate) -> bool:
        if candidate.source in {"rule_explicit_correction", "user_confirmed", "manual_repair"}:
            return True
        text = f"{candidate.key} {candidate.value} {candidate.reason}"
        confirmation_cues = ("明确", "纠正", "不是", "已经", "确定", "确认", "以后都", "别再")
        if candidate.confidence >= 0.88 and any(cue in text for cue in confirmation_cues):
            return True
        return candidate.category in {"boundaries", "dislikes"} and candidate.confidence >= 0.86


def _candidate_dict(candidate: MemoryCandidate) -> dict[str, Any]:
    return {
        "type": candidate.type,
        "key": candidate.key,
        "value": candidate.value,
        "category": candidate.category,
        "confidence": candidate.confidence,
        "importance": candidate.importance,
        "source": candidate.source,
        "ttl_days": candidate.ttl_days,
        "evidence": list(candidate.evidence or []),
        "reason": candidate.reason,
        "metadata": dict(candidate.metadata or {}),
        "created_at": datetime.now().isoformat(),
    }


def _same_memory_value(left: str, right: str) -> bool:
    return _normalize_text(left) == _normalize_text(right)


def _normalize_text(value: object) -> str:
    return "".join(str(value or "").split()).lower()


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_relationship_label(value: object) -> str:
    text = str(value or "").strip()
    aliases = {
        "情侣": "恋人",
        "伴侣": "恋人",
        "男朋友": "恋人",
        "女朋友": "恋人",
        "恋爱中": "恋人",
        "暧昧": "暧昧中",
        "暧昧关系": "暧昧中",
        "好友": "好朋友",
    }
    if text in aliases:
        return aliases[text]
    for token, label in [
        ("恋人", "恋人"),
        ("情侣", "恋人"),
        ("伴侣", "恋人"),
        ("男朋友", "恋人"),
        ("女朋友", "恋人"),
        ("暧昧", "暧昧中"),
        ("好朋友", "好朋友"),
        ("朋友", "朋友"),
    ]:
        if token in text:
            return label
    return text


def _is_committed_relationship(label: object) -> bool:
    text = str(label or "").strip()
    return any(token in text for token in ("恋人", "情侣", "伴侣", "男朋友", "女朋友", "恋爱中"))


def _is_stale_pre_commitment_thread(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    stale_cues = (
        "尚未明确回应",
        "尚未明确答复",
        "尚未获得明确回应",
        "等待答案",
        "等待助手",
        "等助手答复",
        "确认正式关系",
        "关系下一步正式确认",
        "还没正式答应",
        "还没有正式答应",
        "未正式答应",
        "可能想就此确认正式关系",
        "你们目前像恋人",
    )
    return any(cue in text for cue in stale_cues)
