"""Memory write governance.

The governor is the gate between extraction and durable memory.  It prevents
low-confidence guesses and ordinary chit-chat from polluting long-term recall.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable

from .extractor import MemoryCandidate


@dataclass
class GovernorResult:
    written: list[MemoryCandidate] = field(default_factory=list)
    skipped: list[tuple[MemoryCandidate, str]] = field(default_factory=list)
    projection_refresh: bool = False


class MemoryGovernor:
    """Apply memory candidates to the right stores."""

    MIN_FACT_CONFIDENCE = 0.6
    MIN_PROJECTION_CONFIDENCE = 0.75
    MIN_EPISODE_IMPORTANCE = 0.68
    MIN_EPISODE_CONFIDENCE = 0.6
    MIN_RELATIONSHIP_CONFIDENCE = 0.65

    def __init__(
        self,
        *,
        semantic_store,
        episodic_store,
        relationship_store,
        user_understanding,
    ):
        self.semantic = semantic_store
        self.episodic = episodic_store
        self.relationship = relationship_store
        self.user_understanding = user_understanding

    async def apply(
        self,
        candidates: Iterable[MemoryCandidate],
        *,
        bot_id: str,
        user_id: str,
        session_id: str,
    ) -> GovernorResult:
        result = GovernorResult()
        for candidate in candidates:
            candidate = candidate.normalized()
            if candidate.type == "user_fact":
                await self._apply_user_fact(candidate, bot_id, user_id, session_id, result)
            elif candidate.type == "episode":
                await self._apply_episode(candidate, bot_id, user_id, session_id, result)
            elif candidate.type == "relationship_event":
                await self._apply_relationship(candidate, bot_id, user_id, result)
            elif candidate.type == "temporary_context":
                await self._apply_temporary_context(candidate, bot_id, user_id, session_id, result)
            else:
                result.skipped.append((candidate, "unknown_type"))

        if result.projection_refresh:
            await self.refresh_projection(bot_id=bot_id, user_id=user_id)
        return result

    async def refresh_projection(self, *, bot_id: str, user_id: str):
        facts = await self.semantic.list_facts(
            bot_id=bot_id,
            user_id=user_id,
            min_confidence=self.MIN_PROJECTION_CONFIDENCE,
            include_archived=False,
        )
        relationship = await self.relationship.get_state(bot_id=bot_id, user_id=user_id)
        await self.user_understanding.refresh_auto_from_sources(facts=facts, relationship=relationship)

    async def _apply_user_fact(
        self,
        candidate: MemoryCandidate,
        bot_id: str,
        user_id: str,
        session_id: str,
        result: GovernorResult,
    ):
        if candidate.confidence < self.MIN_FACT_CONFIDENCE:
            result.skipped.append((candidate, "low_confidence"))
            return

        if self.user_understanding.has_manual_key(candidate.key, candidate.category):
            # User-authored understanding wins. Keep the raw fact out of prompt
            # by archiving it as conflict evidence instead of overwriting.
            result.skipped.append((candidate, "manual_conflict"))
            return

        expires_at = None
        if candidate.ttl_days:
            expires_at = (datetime.now() + timedelta(days=candidate.ttl_days)).isoformat()

        await self.semantic.set_fact(
            candidate.key,
            candidate.value,
            session_id=session_id,
            bot_id=bot_id,
            user_id=user_id,
            category=candidate.category,
            confidence=candidate.confidence,
            source=candidate.source,
            evidence=candidate.evidence,
            expires_at=expires_at,
        )
        result.written.append(candidate)
        if candidate.confidence >= self.MIN_PROJECTION_CONFIDENCE:
            result.projection_refresh = True

    async def _apply_episode(
        self,
        candidate: MemoryCandidate,
        bot_id: str,
        user_id: str,
        session_id: str,
        result: GovernorResult,
    ):
        if candidate.importance < self.MIN_EPISODE_IMPORTANCE:
            result.skipped.append((candidate, "low_importance"))
            return
        if candidate.confidence < self.MIN_EPISODE_CONFIDENCE:
            result.skipped.append((candidate, "low_confidence"))
            return
        await self.episodic.store_episode(
            summary=candidate.summary,
            content=candidate.content,
            session_id=session_id,
            bot_id=bot_id,
            user_id=user_id,
            title=candidate.title,
            importance=candidate.importance,
            confidence=candidate.confidence,
            topics=candidate.metadata.get("topics") or [],
            emotion_tags=candidate.metadata.get("emotion_tags") or [],
            source_message_ids=candidate.evidence,
        )
        result.written.append(candidate)

    async def _apply_relationship(
        self,
        candidate: MemoryCandidate,
        bot_id: str,
        user_id: str,
        result: GovernorResult,
    ):
        if candidate.confidence < self.MIN_RELATIONSHIP_CONFIDENCE:
            result.skipped.append((candidate, "low_confidence"))
            return
        meta = candidate.metadata or {}
        label = self._stable_label_hint(meta.get("label") or candidate.value or "", meta)
        await self.relationship.apply_event(
            bot_id=bot_id,
            user_id=user_id,
            label=label,
            intimacy_delta=_float(meta.get("intimacy_delta")),
            trust_delta=_float(meta.get("trust_delta")),
            tension_delta=_float(meta.get("tension_delta")),
            affection_delta=_float(meta.get("affection_delta")),
            attitude_delta=_float(meta.get("attitude_delta")),
            key_moment=meta.get("key_moment") or None,
            open_thread=meta.get("open_thread") or None,
        )
        result.written.append(candidate)
        result.projection_refresh = True

    def _stable_label_hint(self, value: object, meta: dict) -> str | None:
        label = str(value or "").strip()
        if not label:
            return None
        normalized = _normalize_relationship_label(label)
        # "朋友" is too often used by models as a safe default. Let the score
        # layer keep the existing stage unless the metadata carries explicit
        # demotion evidence.
        if normalized == "朋友" and not _has_friend_demotion_evidence(meta):
            return None
        return normalized

    async def _apply_temporary_context(
        self,
        candidate: MemoryCandidate,
        bot_id: str,
        user_id: str,
        session_id: str,
        result: GovernorResult,
    ):
        if candidate.confidence < self.MIN_FACT_CONFIDENCE:
            result.skipped.append((candidate, "low_confidence"))
            return
        expires_at = None
        if candidate.ttl_days:
            expires_at = (datetime.now() + timedelta(days=candidate.ttl_days)).isoformat()
        await self.semantic.set_fact(
            candidate.value[:40] or candidate.key,
            candidate.value,
            session_id=session_id,
            bot_id=bot_id,
            user_id=user_id,
            category="open_threads",
            confidence=candidate.confidence,
            source=candidate.source,
            evidence=candidate.evidence,
            expires_at=expires_at,
        )
        result.written.append(candidate)
        if candidate.confidence >= self.MIN_PROJECTION_CONFIDENCE:
            result.projection_refresh = True


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_relationship_label(value: str) -> str:
    aliases = {
        "陌生": "刚认识",
        "陌生网友": "刚认识",
        "普通朋友": "朋友",
        "好友": "好朋友",
        "亲密朋友": "好朋友",
        "暧昧": "暧昧中",
        "暧昧关系": "暧昧中",
        "情侣": "恋人",
        "伴侣": "恋人",
        "男朋友": "恋人",
        "女朋友": "恋人",
        "疏离": "疏远",
        "关系紧张": "紧张",
    }
    value = value.strip()
    if value in aliases:
        return aliases[value]
    for keyword, label in [
        ("恋人", "恋人"),
        ("情侣", "恋人"),
        ("伴侣", "恋人"),
        ("暧昧", "暧昧中"),
        ("好朋友", "好朋友"),
        ("好友", "好朋友"),
        ("紧张", "紧张"),
        ("疏远", "疏远"),
        ("疏离", "疏远"),
        ("陌生", "刚认识"),
        ("朋友", "朋友"),
    ]:
        if keyword in value:
            return label
    return value


def _has_friend_demotion_evidence(meta: dict) -> bool:
    text = " ".join(str(meta.get(key) or "") for key in ("key_moment", "open_thread", "reason", "evidence"))
    if any(word in text for word in ["只做朋友", "退回朋友", "分手", "结束暧昧", "不要暧昧", "拒绝表白"]):
        return True
    negative = (
        max(-_float(meta.get("intimacy_delta")), 0)
        + max(-_float(meta.get("trust_delta")), 0)
        + max(-_float(meta.get("affection_delta")), 0)
        + max(_float(meta.get("tension_delta")), 0)
    )
    return negative >= 2
