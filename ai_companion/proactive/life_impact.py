"""Impact evaluation for bot life and relationship experiences."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from ..memory.extractor import MemoryCandidate


@dataclass
class LifeImpact:
    """A structured description of how an experience affects the bot."""

    source: str
    summary: str
    intensity: float = 0.0
    mood_before: str = ""
    mood_after: str = ""
    activity_update: str = ""
    relationship_effect: str = "ordinary"
    life_journal_record: bool = False
    memory_candidates: list[MemoryCandidate] = field(default_factory=list)
    persona_patch_candidate: bool = False
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["memory_candidates"] = [
            {
                "type": item.type,
                "key": item.key,
                "value": item.value,
                "summary": item.summary,
                "importance": item.importance,
                "confidence": item.confidence,
                "source": item.source,
                "metadata": item.metadata,
            }
            for item in self.memory_candidates
        ]
        return payload


class LifeImpactEngine:
    """Deterministic impact engine for experiences that shape the bot."""

    POSITIVE_CUES = {
        "开心", "高兴", "喜欢你", "想你", "抱抱", "亲亲", "谢谢你", "真好",
        "在一起", "爱你", "陪你", "甜", "安心",
    }
    NEGATIVE_CUES = {
        "难过", "崩溃", "焦虑", "失眠", "委屈", "生气", "烦", "累",
        "哭", "害怕", "不理你", "讨厌你",
    }
    CONFLICT_CUES = {"吵架", "道歉", "冷淡", "别烦", "不想聊", "分手", "越界"}
    SHARED_EXPERIENCE_CUES = {
        "我们", "一起", "第一次", "约定", "承诺", "牵手", "拥抱", "海边",
        "旅行", "生日", "见面", "和好", "表白", "陪我", "陪你",
    }
    SENSITIVE_CUES = {"创伤", "疾病", "身体", "前任", "自杀", "自残", "隐私", "家暴"}

    def evaluate_turn_impact(
        self,
        *,
        user_input: str,
        bot_output: str,
        current_mood: str = "平静",
        relationship_state: dict[str, Any] | None = None,
        session_id: str = "",
        turn_signals: dict[str, Any] | None = None,
    ) -> LifeImpact:
        text = f"{user_input}\n{bot_output}"
        signals = _turn_signal_view(turn_signals, relationship_state)
        positive = signals["positive"] or _contains_any(text, self.POSITIVE_CUES)
        negative = signals["negative"] or _contains_any(text, self.NEGATIVE_CUES)
        conflict = signals["conflict"] or _contains_any(text, self.CONFLICT_CUES)
        shared = signals["shared_experience"] or (_contains_any(text, self.SHARED_EXPERIENCE_CUES) and "我们" in text)

        intensity = max(0.12, signals["intensity"])
        mood_after = ""
        effect = "ordinary"
        reason = "ordinary_turn"
        if conflict:
            intensity = max(intensity, 0.68)
            mood_after = "有点绷着，心里还挂着刚才的话"
            effect = "tension"
            reason = "structured_relationship_tension" if signals["conflict"] else "relationship_tension"
        elif negative:
            intensity = max(intensity, 0.52)
            mood_after = "被你牵动，有点心疼"
            effect = "caring"
            reason = "structured_user_emotion" if signals["negative"] else "user_emotion_touched_bot"
        elif positive:
            intensity = max(intensity, 0.44)
            mood_after = "被你哄得有点柔软"
            effect = "closer"
            reason = "structured_warm_interaction" if signals["positive"] else "warm_interaction"
        if shared:
            intensity = max(intensity, 0.74)
            mood_after = mood_after or "因为共同经历变得更靠近一点"
            effect = "shared_experience"
            reason = "structured_shared_experience" if signals["shared_experience"] else "shared_experience"

        if not mood_after and intensity < 0.35:
            mood_after = current_mood or "平静"

        summary = _compact_text(user_input, 90)
        candidates: list[MemoryCandidate] = []
        if shared:
            sensitivity = "sensitive" if signals["sensitive"] or _contains_any(text, self.SENSITIVE_CUES) else "normal"
            candidates.append(
                MemoryCandidate(
                    type="episode",
                    title="共同经历影响",
                    summary=f"这次互动让关系留下痕迹：{summary}",
                    content=f"用户：{user_input}\n助手：{bot_output}",
                    confidence=0.72,
                    importance=0.76,
                    source="life_impact",
                    evidence=[session_id] if session_id else [],
                    metadata={
                        "participants": ["user", "bot"],
                        "topics": ["shared_experience"],
                        "emotion_tags": [mood_after] if mood_after else [],
                        "relationship_effect": effect,
                        "sensitivity": sensitivity,
                        "recall_style": "以后只在自然相关时轻轻承接，不要炫耀记忆。",
                        "cue_tags": _cue_tags(user_input),
                    },
                )
            )

        return LifeImpact(
            source="conversation_turn",
            summary=summary or "一次普通互动",
            intensity=intensity,
            mood_before=current_mood or "平静",
            mood_after=mood_after,
            activity_update="在消化刚才和你的对话" if intensity >= 0.35 else "",
            relationship_effect=effect,
            life_journal_record=intensity >= 0.35,
            memory_candidates=candidates,
            persona_patch_candidate=False,
            reason=reason,
            metadata={
                "session_id": session_id,
                "relationship_label": (relationship_state or {}).get("relationship_label"),
                "structured_signals": signals["evidence"],
            },
        )

    def evaluate_life_event_impact(self, *, event: Any, major: bool = False) -> LifeImpact:
        description = str(getattr(event, "description", "") or "").strip()
        mood_before = str(getattr(event, "mood_before", "") or "").strip()
        mood_after = str(getattr(event, "mood_after", "") or "").strip()
        importance = _float(getattr(event, "importance", 0.0), default=0.0)
        intensity = min(1.0, max(0.25 if description else 0.0, importance / 10.0))
        if major:
            intensity = max(intensity, 0.9)
        return LifeImpact(
            source="major_life_event" if major else "daily_life_event",
            summary=_compact_text(description, 120) or "生活事件",
            intensity=intensity,
            mood_before=mood_before,
            mood_after=mood_after or mood_before or "平静",
            activity_update=f"在消化这件事：{_compact_text(description, 36)}" if description else "",
            relationship_effect="self_life",
            life_journal_record=True,
            memory_candidates=[],
            persona_patch_candidate=major or importance >= 8.5,
            reason="major_life_event" if major else "daily_life_event",
            metadata={
                "event_id": getattr(event, "id", ""),
                "scenario_key": getattr(event, "scenario_key", ""),
                "importance": importance,
                "mood_tags": list(getattr(event, "mood_tags", []) or []),
            },
        )

    async def apply_impact(
        self,
        *,
        impact: LifeImpact,
        life_state: Any,
        memory: Any = None,
        bot_id: str = "",
        user_id: str = "default_user",
        session_id: str = "",
    ) -> dict[str, Any]:
        if impact.mood_after and impact.intensity >= 0.25:
            life_state.bot_mood = impact.mood_after
        if impact.activity_update and impact.intensity >= 0.35:
            life_state.bot_current_activity = impact.activity_update

        if hasattr(life_state, "add_impact_record"):
            life_state.add_impact_record(impact.to_dict())

        written = 0
        skipped = 0
        if memory is not None and impact.memory_candidates and hasattr(memory, "governor"):
            result = await memory.governor.apply(
                impact.memory_candidates,
                bot_id=bot_id or getattr(memory, "bot_id", ""),
                user_id=user_id or getattr(memory, "user_id", "default_user"),
                session_id=session_id,
            )
            written = len(result.written)
            skipped = len(result.skipped)

        return {
            "applied": True,
            "source": impact.source,
            "intensity": impact.intensity,
            "memory_written": written,
            "memory_skipped": skipped,
            "persona_patch_candidate": impact.persona_patch_candidate,
            "applied_at": datetime.now().isoformat(),
        }


def _contains_any(text: str, cues: set[str]) -> bool:
    return any(cue in text for cue in cues)


def _turn_signal_view(
    turn_signals: dict[str, Any] | None,
    relationship_state: dict[str, Any] | None,
) -> dict[str, Any]:
    """Normalize non-lexical signals so cues remain a fallback, not authority."""
    signals = turn_signals if isinstance(turn_signals, dict) else {}
    relationship = relationship_state if isinstance(relationship_state, dict) else {}
    evidence: dict[str, Any] = {}

    emotion = str(
        signals.get("user_emotion")
        or signals.get("emotion")
        or signals.get("emotional_valence")
        or ""
    ).strip().lower()
    relationship_effect = str(signals.get("relationship_effect") or "").strip().lower()
    try:
        intensity = max(0.0, min(1.0, float(signals.get("intensity", 0.0) or 0.0)))
    except (TypeError, ValueError):
        intensity = 0.0

    tension_score = _float(relationship.get("tension_score"), default=0.0)
    stage_confidence = _float(relationship.get("stage_confidence"), default=0.0)
    relationship_status = str(relationship.get("relationship_status") or "").strip().lower()
    if tension_score >= 55:
        evidence["relationship_tension_score"] = tension_score
        intensity = max(intensity, min(1.0, tension_score / 100.0))
    if stage_confidence:
        evidence["stage_confidence"] = stage_confidence

    positive = emotion in {"positive", "warm", "happy", "comforted", "secure"} or relationship_effect in {"closer", "warm", "repair"}
    negative = emotion in {"negative", "sad", "distressed", "anxious", "hurt", "vulnerable"} or relationship_effect in {"caring", "support"}
    conflict = (
        emotion in {"angry", "conflict", "tense"}
        or relationship_effect in {"tension", "conflict", "rupture"}
        or tension_score >= 55
        or relationship_status in {"紧张", "冲突", "修复中", "冷淡"}
    )
    shared_experience = _as_bool(signals.get("shared_experience")) or relationship_effect in {"shared_experience", "milestone"}
    sensitive = _as_bool(signals.get("sensitive")) or emotion in {"vulnerable", "trauma"}

    if emotion:
        evidence["emotion"] = emotion
    if relationship_effect:
        evidence["relationship_effect"] = relationship_effect
    if intensity:
        evidence["intensity"] = intensity

    return {
        "positive": positive,
        "negative": negative,
        "conflict": conflict,
        "shared_experience": shared_experience,
        "sensitive": sensitive,
        "intensity": intensity,
        "evidence": evidence,
    }


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on", "enabled"}


def _compact_text(text: str, limit: int) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _cue_tags(text: str) -> list[str]:
    tags = []
    for cue in ["海边", "生日", "旅行", "牵手", "拥抱", "约定", "和好", "表白", "第一次"]:
        if cue in text:
            tags.append(cue)
    return tags[:6]


def _float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
