"""Unified memory activation planning.

The stores decide what is durable.  This planner decides what should feel
mentally present on this turn.  It gives recent lived context a natural
baseline so the bot can continue a conversation without waiting for explicit
"do you remember" style prompts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ActivatedMemory:
    """A memory candidate selected for this turn's attention window."""

    text: str
    source: str
    score: float
    expression_mode: str
    reason: str = ""
    layer: str = "context"
    recency: float = 0.0
    relevance: float = 0.0
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryActivationPlan:
    """The compact attention plan consumed by prompt and conscious builders."""

    intent: str
    strategy: str = ""
    active_memories: list[ActivatedMemory] = field(default_factory=list)
    continuity_items: list[dict[str, Any]] = field(default_factory=list)
    background_items: list[ActivatedMemory] = field(default_factory=list)
    source_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["active_memories"] = [item.to_dict() for item in self.active_memories]
        data["background_items"] = [item.to_dict() for item in self.background_items]
        return data


class MemoryActivationPlanner:
    """Build a turn-level attention window from all retrieved memory layers."""

    CONTINUITY_SOURCES = {
        "working_recent",
        "daily_recent",
        "daily_summary",
        "daily_commitment",
        "self_memory",
        "turn_constraint",
    }
    SENSITIVE_ALLOWED_INTENTS = {"recall_past", "relationship_repair", "emotional_support"}
    ACTIVE_LIMITS = {
        "task_request": 5,
        "casual_chat": 6,
        "planning": 7,
        "proactive_generation": 7,
        "emotional_support": 7,
        "relationship_repair": 7,
        "recall_past": 8,
    }

    def __init__(self, config: dict[str, Any] | None = None):
        config = config if isinstance(config, dict) else {}
        self.active_limits = dict(self.ACTIVE_LIMITS)
        for key, value in (config.get("active_limits") or {}).items():
            try:
                self.active_limits[str(key)] = max(1, min(16, int(value)))
            except (TypeError, ValueError):
                continue
        self.source_bias = {
            str(key): _float(value)
            for key, value in (config.get("source_bias") or {}).items()
        }
        self.source_floors = {
            str(key): _float(value)
            for key, value in (config.get("source_floors") or {}).items()
        }

    def build(self, retrieved: Any, current_input: str) -> MemoryActivationPlan:
        intent = str(getattr(retrieved, "intent", "") or "casual_chat")
        candidates: list[ActivatedMemory] = []
        candidates.extend(self._turn_constraint_candidates(retrieved, current_input, intent=intent))
        candidates.extend(self._working_recent_candidates(retrieved, current_input, intent=intent))
        candidates.extend(self._daily_recent_candidates(retrieved, current_input, intent=intent))
        candidates.extend(self._daily_summary_candidates(retrieved, current_input, intent=intent))
        candidates.extend(self._relationship_candidates(retrieved, current_input, intent=intent))
        candidates.extend(self._understanding_candidates(retrieved, current_input, intent=intent))
        candidates.extend(self._semantic_candidates(retrieved, current_input, intent=intent))
        candidates.extend(self._episodic_candidates(retrieved, current_input, intent=intent))
        candidates.extend(self._rollup_candidates(retrieved, current_input, intent=intent))
        candidates.extend(self._vector_candidates(retrieved, current_input, intent=intent))
        candidates.extend(self._self_memory_candidates(retrieved, current_input, intent=intent))

        self._apply_configured_bias(candidates)
        candidates = _dedupe_active_memories(candidates)
        selected = self._select_active(candidates, intent=intent)
        selected_keys = {_memory_key(item) for item in selected}
        background = [
            item
            for item in sorted(candidates, key=lambda item: item.score, reverse=True)
            if _memory_key(item) not in selected_keys
        ][:8]
        return MemoryActivationPlan(
            intent=intent,
            strategy=self._strategy(intent, bool(selected)),
            active_memories=selected,
            continuity_items=self._continuity_items(selected),
            background_items=background,
            source_counts=_source_counts(selected),
        )

    def _select_active(self, candidates: list[ActivatedMemory], *, intent: str) -> list[ActivatedMemory]:
        if not candidates:
            return []
        limit = self.active_limits.get(intent, self.active_limits["casual_chat"])
        continuity_limit = 3 if intent != "task_request" else 2

        selected: list[ActivatedMemory] = []
        for item in sorted(candidates, key=lambda candidate: candidate.score, reverse=True):
            if item.source not in self.CONTINUITY_SOURCES:
                continue
            if item.score < 0.48 and not selected:
                continue
            selected.append(item)
            if len(selected) >= continuity_limit:
                break

        selected_keys = {_memory_key(item) for item in selected}
        for item in sorted(candidates, key=lambda candidate: candidate.score, reverse=True):
            if len(selected) >= limit:
                break
            if _memory_key(item) in selected_keys:
                continue
            if item.score < self._activation_floor(intent, item.source):
                continue
            selected.append(item)
            selected_keys.add(_memory_key(item))
        return sorted(selected, key=lambda item: item.score, reverse=True)

    def _turn_constraint_candidates(self, retrieved: Any, current_input: str, *, intent: str) -> list[ActivatedMemory]:
        candidates: list[ActivatedMemory] = []
        for age, item in enumerate(getattr(retrieved, "turn_constraints", []) or []):
            if not isinstance(item, dict):
                continue
            value = _compact(item.get("value"), 180)
            if not value:
                continue
            relevance = _cue_overlap(current_input, value)
            recency = max(0.0, 1.0 - age * 0.10)
            score = 0.72 + recency * 0.12 + relevance * 0.10
            candidates.append(
                ActivatedMemory(
                    text=f"当前临时约束：{value}",
                    source="turn_constraint",
                    score=_clamp_score(score),
                    expression_mode="hard_constraint",
                    reason="用户最近给出的当前/当日约束，优先级高于旧记忆",
                    layer="short_term.constraint",
                    recency=round(recency, 3),
                    relevance=round(relevance, 3),
                    evidence=_list(item.get("evidence")),
                )
            )
        return candidates

    def _working_recent_candidates(self, retrieved: Any, current_input: str, *, intent: str) -> list[ActivatedMemory]:
        messages = [
            item
            for item in getattr(retrieved, "working_history", []) or []
            if isinstance(item, dict) and item.get("role") in {"user", "assistant"}
        ]
        turns = _message_turns(messages)[-4:]
        candidates: list[ActivatedMemory] = []
        for age, turn in enumerate(reversed(turns)):
            text = _format_turn("当前会话最近发生", turn, max_chars=260)
            if not text:
                continue
            recency = max(0.0, 1.0 - age * 0.18)
            relevance = _cue_overlap(current_input, text)
            score = 0.58 + recency * 0.22 + relevance * 0.10
            if intent in {"recall_past", "relationship_repair", "emotional_support", "planning"}:
                score += 0.06
            candidates.append(
                ActivatedMemory(
                    text=text,
                    source="working_recent",
                    score=_clamp_score(score),
                    expression_mode="context_continuity",
                    reason="当前会话的最近原文，默认作为本轮自然延续",
                    layer="working",
                    recency=round(recency, 3),
                    relevance=round(relevance, 3),
                    evidence=_message_evidence(turn),
                )
            )
        return candidates

    def _daily_recent_candidates(self, retrieved: Any, current_input: str, *, intent: str) -> list[ActivatedMemory]:
        daily = getattr(retrieved, "daily_context", {}) or {}
        messages = daily.get("recent_messages") if isinstance(daily.get("recent_messages"), list) else []
        if not messages:
            return []
        candidates: list[ActivatedMemory] = []
        recent = messages[-6:]
        for age, item in enumerate(reversed(recent)):
            if not isinstance(item, dict):
                continue
            content = _compact(item.get("content"), 180)
            if not content:
                continue
            platform = str(item.get("platform") or "unknown")
            role = "用户" if item.get("role") == "user" else "助手"
            text = f"跨会话最近发生（{platform}）：{role}: {content}"
            recency = max(0.0, 1.0 - age * 0.14)
            relevance = _cue_overlap(current_input, text)
            score = 0.50 + recency * 0.20 + relevance * 0.11
            if intent in {"planning", "emotional_support", "recall_past"}:
                score += 0.06
            candidates.append(
                ActivatedMemory(
                    text=text,
                    source="daily_recent",
                    score=_clamp_score(score),
                    expression_mode="context_continuity",
                    reason="跨通道近期原文，帮助自然接上最近事件",
                    layer="daily",
                    recency=round(recency, 3),
                    relevance=round(relevance, 3),
                    evidence=[str(item.get("session_id") or ""), platform],
                )
            )
        return candidates

    def _daily_summary_candidates(self, retrieved: Any, current_input: str, *, intent: str) -> list[ActivatedMemory]:
        daily = getattr(retrieved, "daily_context", {}) or {}
        candidates: list[ActivatedMemory] = []
        summaries = daily.get("summaries") if isinstance(daily.get("summaries"), list) else []
        for age, item in enumerate(summaries[:3]):
            if not isinstance(item, dict):
                continue
            summary = _compact(item.get("summary"), 180)
            if not summary:
                continue
            date = str(item.get("local_date") or "最近")
            text = f"{date} 的日常连续性：{summary}"
            recency = max(0.0, 0.85 - age * 0.15)
            relevance = _cue_overlap(current_input, text, _list(item.get("topics")))
            score = 0.42 + recency * 0.16 + relevance * 0.10
            if intent in {"planning", "emotional_support", "recall_past", "proactive_generation"}:
                score += 0.06
            candidates.append(
                ActivatedMemory(
                    text=text,
                    source="daily_summary",
                    score=_clamp_score(score),
                    expression_mode="light_reference",
                    reason="近日连续性概括",
                    layer="daily",
                    recency=round(recency, 3),
                    relevance=round(relevance, 3),
                    evidence=[date],
                )
            )

        for key, label in [
            ("open_threads", "跨会话未完话题"),
            ("commitments", "跨会话承诺/待办"),
            ("mood", "近期情绪线索"),
        ]:
            for item in _list(daily.get(key))[:3]:
                text = f"{label}：{item[:120]}"
                relevance = _cue_overlap(current_input, text)
                score = 0.46 + relevance * 0.12
                if key in {"open_threads", "commitments"}:
                    score += 0.08
                candidates.append(
                    ActivatedMemory(
                        text=text,
                        source="daily_commitment",
                        score=_clamp_score(score),
                        expression_mode="light_reference",
                        reason=label,
                        layer="daily",
                        recency=0.7,
                        relevance=round(relevance, 3),
                    )
                )
        return candidates

    def _relationship_candidates(self, retrieved: Any, current_input: str, *, intent: str) -> list[ActivatedMemory]:
        state = getattr(retrieved, "relationship_state", {}) or {}
        if not isinstance(state, dict) or not state:
            return []
        candidates: list[ActivatedMemory] = []
        label = str(state.get("relationship_label") or state.get("relationship_level") or "").strip()
        narrative = _compact(state.get("relationship_narrative"), 180)
        posture = _compact(state.get("current_posture"), 120)
        guidance = _compact(state.get("interaction_guidance"), 120)
        text_parts = []
        if label:
            text_parts.append(f"关系阶段：{label}")
        if narrative:
            text_parts.append(f"关系叙事：{narrative}")
        if posture:
            text_parts.append(f"当前姿态：{posture}")
        if guidance:
            text_parts.append(f"互动建议：{guidance}")
        text = "；".join(text_parts)
        if text:
            relevance = _cue_overlap(current_input, text)
            score = 0.44 + relevance * 0.10
            if _is_committed_relationship(label):
                score += 0.20
            if intent in {"relationship_repair", "emotional_support", "recall_past"}:
                score += 0.10
            candidates.append(
                ActivatedMemory(
                    text=text,
                    source="relationship",
                    score=_clamp_score(score),
                    expression_mode="relationship_posture",
                    reason="稳定关系状态影响本轮分寸",
                    layer="relationship",
                    recency=0.55,
                    relevance=round(relevance, 3),
                )
            )
        for thread in _list(state.get("open_emotional_threads"))[:3]:
            text = f"关系中未完成情绪话题：{thread[:120]}"
            relevance = _cue_overlap(current_input, text)
            candidates.append(
                ActivatedMemory(
                    text=text,
                    source="relationship",
                    score=_clamp_score(0.44 + relevance * 0.12),
                    expression_mode="silent_influence",
                    reason="关系中未完成情绪话题",
                    layer="relationship",
                    recency=0.45,
                    relevance=round(relevance, 3),
                )
            )
        return candidates

    def _understanding_candidates(self, retrieved: Any, current_input: str, *, intent: str) -> list[ActivatedMemory]:
        data = getattr(retrieved, "user_understanding", {}) or {}
        layered = data.get("layered") if isinstance(data, dict) and isinstance(data.get("layered"), dict) else {}
        candidates: list[ActivatedMemory] = []
        for layer, section_keys in [
            ("current", ("current_context", "recent_changes", "open_threads", "goals_and_projects", "routines")),
            ("core", ("identity", "facts", "preferences", "dislikes", "communication_style", "boundaries")),
            ("deep", ("emotional_patterns", "stressors", "comfort_strategies", "life_context")),
            ("relationship", ("what_user_seems_to_need_from_bot", "repair_preferences", "things_that_brought_them_closer")),
        ]:
            section = layered.get(layer) if isinstance(layered.get(layer), dict) else {}
            if not section:
                continue
            for key in section_keys:
                values = _section_values(section.get(key))
                for value in values[:4]:
                    text = f"用户理解.{layer}.{key}：{value[:140]}"
                    relevance = _cue_overlap(current_input, text)
                    baseline = 0.40 if layer == "current" else 0.32
                    if layer in {"deep", "relationship"} and intent not in {"emotional_support", "relationship_repair", "recall_past", "planning"}:
                        baseline -= 0.10
                    score = baseline + relevance * 0.14
                    if key in {"open_threads", "recent_changes"}:
                        score += 0.08
                    candidates.append(
                        ActivatedMemory(
                            text=text,
                            source=f"understanding.{layer}",
                            score=_clamp_score(score),
                            expression_mode="silent_influence" if layer in {"deep", "relationship"} else "light_reference",
                            reason="用户理解中被当前语境激活的部分",
                            layer=f"understanding.{layer}",
                            recency=0.45 if layer == "current" else 0.20,
                            relevance=round(relevance, 3),
                        )
                    )
        return candidates

    def _semantic_candidates(self, retrieved: Any, current_input: str, *, intent: str) -> list[ActivatedMemory]:
        candidates: list[ActivatedMemory] = []
        for item in getattr(retrieved, "semantic_items", []) or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            value = _compact(item.get("value"), 160)
            if not key or not value:
                continue
            category = str(item.get("category") or "general")
            text = f"语义事实.{category}：{key}={value}"
            reasons = item.get("retrieval_reasons") if isinstance(item.get("retrieval_reasons"), dict) else {}
            overlap_hint = _float(reasons.get("query_cue_overlap")) + _float(reasons.get("salient_overlap"))
            relevance = max(_cue_overlap(current_input, text), min(1.0, overlap_hint))
            confidence = _float(item.get("confidence"))
            score = 0.30 + min(0.22, confidence * 0.18) + relevance * 0.14
            candidates.append(
                ActivatedMemory(
                    text=text,
                    source="semantic",
                    score=_clamp_score(score),
                    expression_mode="light_reference",
                    reason="相关语义事实",
                    layer="semantic",
                    recency=0.15,
                    relevance=round(relevance, 3),
                    evidence=_list(item.get("evidence")),
                )
            )
        return candidates

    def _episodic_candidates(self, retrieved: Any, current_input: str, *, intent: str) -> list[ActivatedMemory]:
        candidates: list[ActivatedMemory] = []
        for item in getattr(retrieved, "episodic_recall", []) or []:
            if not isinstance(item, dict):
                continue
            summary = _compact(item.get("summary"), 180)
            if not summary:
                continue
            sensitivity = str(item.get("sensitivity") or "normal").lower()
            if sensitivity == "sensitive" and intent not in self.SENSITIVE_ALLOWED_INTENTS:
                continue
            cue_tags = _list(item.get("cue_tags"))
            relationship_effect = str(item.get("relationship_effect") or "").strip()
            text = f"共同经历：{summary}"
            if relationship_effect and relationship_effect != "普通":
                text = f"共同经历（{relationship_effect}）：{summary}"
            relevance = _cue_overlap(current_input, text, cue_tags)
            score = 0.36 + relevance * 0.16
            if intent in {"recall_past", "relationship_repair", "emotional_support"}:
                score += 0.18
            if relationship_effect in {"拉近", "修复", "紧张"}:
                score += 0.08
            candidates.append(
                ActivatedMemory(
                    text=text,
                    source="episodic",
                    score=_clamp_score(score),
                    expression_mode="explicit_recall" if intent == "recall_past" else "light_reference",
                    reason="共同经历被当前语境联想到",
                    layer="episodic",
                    recency=0.25,
                    relevance=round(relevance, 3),
                    evidence=cue_tags,
                )
            )
        return candidates

    def _rollup_candidates(self, retrieved: Any, current_input: str, *, intent: str) -> list[ActivatedMemory]:
        candidates: list[ActivatedMemory] = []
        for item in getattr(retrieved, "rollup_recall", []) or []:
            if not isinstance(item, dict):
                continue
            summary = _compact(item.get("summary"), 180)
            if not summary:
                continue
            scope = str(item.get("scope") or "rollup")
            topic_key = str(item.get("topic_key") or "").strip()
            prefix = f"高层概括.{scope}/{topic_key}" if topic_key else f"高层概括.{scope}"
            text = f"{prefix}：{summary}"
            relevance = _cue_overlap(current_input, text)
            score = 0.34 + relevance * 0.12
            if intent in {"planning", "recall_past", "emotional_support"}:
                score += 0.08
            candidates.append(
                ActivatedMemory(
                    text=text,
                    source="rollup",
                    score=_clamp_score(score),
                    expression_mode="silent_influence",
                    reason="高层记忆概括",
                    layer="rollup",
                    recency=0.30,
                    relevance=round(relevance, 3),
                    evidence=_list(item.get("evidence")),
                )
            )
        return candidates

    def _vector_candidates(self, retrieved: Any, current_input: str, *, intent: str) -> list[ActivatedMemory]:
        candidates: list[ActivatedMemory] = []
        for item in getattr(retrieved, "vector_recall", []) or []:
            if not isinstance(item, dict):
                continue
            text_body = _compact(item.get("text"), 180)
            if not text_body:
                continue
            source_type = str(item.get("source_type") or "vector")
            text = f"联想背景.{source_type}：{text_body}"
            retrieval_score = _float(item.get("retrieval_score"))
            relevance = max(_cue_overlap(current_input, text), min(1.0, retrieval_score))
            score = 0.28 + relevance * 0.16
            if source_type in {"relationship_narrative", "daily_summary"}:
                score += 0.06
            candidates.append(
                ActivatedMemory(
                    text=text,
                    source="vector",
                    score=_clamp_score(score),
                    expression_mode="silent_influence",
                    reason="向量联想到的背景",
                    layer="vector",
                    recency=0.15,
                    relevance=round(relevance, 3),
                    evidence=[source_type, str(item.get("source_id") or "")],
                )
            )
        return candidates

    def _self_memory_candidates(self, retrieved: Any, current_input: str, *, intent: str) -> list[ActivatedMemory]:
        daily = getattr(retrieved, "daily_context", {}) or {}
        items = daily.get("self_memory") if isinstance(daily.get("self_memory"), list) else []
        candidates: list[ActivatedMemory] = []
        for age, item in enumerate(items[:5]):
            if not isinstance(item, dict):
                continue
            content = _compact(item.get("content"), 160)
            if not content:
                continue
            kind = str(item.get("kind") or "assistant_initiated")
            date = str(item.get("local_date") or "最近")
            text = f"{date} 的自传体线索（{kind}）：{content}"
            recency = max(0.0, 0.9 - age * 0.12)
            relevance = _cue_overlap(current_input, text)
            score = 0.48 + recency * 0.16 + relevance * 0.12
            candidates.append(
                ActivatedMemory(
                    text=text,
                    source="self_memory",
                    score=_clamp_score(score),
                    expression_mode="light_reference" if intent != "task_request" else "silent_influence",
                    reason="Bot 自己最近主动做过的事",
                    layer="daily.self",
                    recency=round(recency, 3),
                    relevance=round(relevance, 3),
                    evidence=[kind, date],
                )
            )
        return candidates

    def _continuity_items(self, selected: list[ActivatedMemory]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for item in selected:
            if item.source not in self.CONTINUITY_SOURCES:
                continue
            items.append(
                {
                    "source": item.source,
                    "text": item.text,
                    "score": item.score,
                    "expression_mode": item.expression_mode,
                    "reason": item.reason,
                }
            )
        return items

    def _activation_floor(self, intent: str, source: str) -> float:
        if source in self.source_floors:
            return max(0.0, min(1.0, self.source_floors[source]))
        if source in self.CONTINUITY_SOURCES:
            return 0.46
        if intent == "task_request":
            return 0.54 if source in {"episodic", "relationship"} else 0.46
        if intent in {"recall_past", "relationship_repair", "emotional_support"}:
            return 0.42
        return 0.44

    def _apply_configured_bias(self, candidates: list[ActivatedMemory]):
        if not self.source_bias:
            return
        for item in candidates:
            bias = self.source_bias.get(item.source)
            if bias is None:
                continue
            item.score = _clamp_score(item.score + bias)

    def _strategy(self, intent: str, has_active: bool) -> str:
        if not has_active:
            return "没有强激活记忆时，只让长期理解轻微影响语气。"
        if intent == "task_request":
            return "先完成任务，近期上下文只用于保持连续和偏好一致。"
        if intent in {"recall_past", "relationship_repair", "emotional_support"}:
            return "用被激活的记忆承接情绪和关系分寸，避免把记忆当资料展示。"
        return "把近期连续性当作自然背景，只有顺手、有帮助时提到细节。"


def _message_turns(messages: list[dict]) -> list[list[dict]]:
    turns: list[list[dict]] = []
    current: list[dict] = []
    for item in messages:
        role = item.get("role")
        if role == "user" and current:
            turns.append(current)
            current = [item]
        else:
            current.append(item)
    if current:
        turns.append(current)
    return turns


def _format_turn(prefix: str, turn: list[dict], *, max_chars: int) -> str:
    parts: list[str] = []
    for item in turn:
        role = "用户" if item.get("role") == "user" else "助手"
        content = _compact(item.get("content"), 140)
        if content:
            parts.append(f"{role}: {content}")
    if not parts:
        return ""
    return _compact(f"{prefix}：" + " / ".join(parts), max_chars)


def _message_evidence(turn: list[dict]) -> list[str]:
    evidence: list[str] = []
    for item in turn:
        if item.get("created_at"):
            evidence.append(str(item.get("created_at")))
    return evidence


def _section_values(value: object) -> list[str]:
    if isinstance(value, dict):
        return [
            f"{str(key).strip()}: {str(val).strip()}"
            for key, val in value.items()
            if str(key).strip() and str(val).strip()
        ]
    return _list(value)


def _list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _cue_overlap(current_input: str, text: str, cue_tags: list[str] | None = None) -> float:
    source = str(current_input or "").lower()
    target = str(text or "").lower()
    cues = set(_short_cues(source))
    tags = {str(tag).strip().lower() for tag in cue_tags or [] if str(tag).strip()}
    if not cues and not tags:
        return 0.0
    overlap = sum(1 for cue in cues if cue and cue in target)
    overlap += sum(1 for cue in tags if cue and cue in source)
    return min(1.0, overlap / max(3, min(8, len(cues) + len(tags))))


def _short_cues(text: str) -> list[str]:
    compact = "".join(str(text or "").split())
    cues: list[str] = []
    for size in (4, 3, 2):
        for idx in range(0, max(0, len(compact) - size + 1)):
            chunk = compact[idx : idx + size]
            if _is_meaningful_cue(chunk):
                cues.append(chunk)
    ascii_word = []
    for ch in compact:
        if ch.isascii() and ch.isalnum():
            ascii_word.append(ch.lower())
        else:
            if len(ascii_word) >= 3:
                cues.append("".join(ascii_word))
            ascii_word = []
    if len(ascii_word) >= 3:
        cues.append("".join(ascii_word))
    return _dedupe_strings(cues)[:24]


def _is_meaningful_cue(value: str) -> bool:
    if not value:
        return False
    stop = {
        "我想", "你说", "我们", "这个", "那个", "一个", "还是", "就是", "什么",
        "怎么", "可以", "不是", "今天", "明天", "之前", "上次", "现在", "然后",
        "有点", "一下", "感觉", "没有", "知道", "觉得",
    }
    return value not in stop and any("\u4e00" <= ch <= "\u9fff" or ch.isalnum() for ch in value)


def _dedupe_active_memories(items: list[ActivatedMemory]) -> list[ActivatedMemory]:
    seen: set[str] = set()
    result: list[ActivatedMemory] = []
    for item in sorted(items, key=lambda candidate: candidate.score, reverse=True):
        normalized = _memory_key(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        item.text = " ".join(str(item.text or "").split())
        result.append(item)
    return result


def _memory_key(item: ActivatedMemory) -> str:
    return " ".join(str(item.text or "").split()).lower()


def _source_counts(items: list[ActivatedMemory]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item.source] = counts.get(item.source, 0) + 1
    return counts


def _dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _compact(value: object, max_chars: int) -> str:
    text = " ".join(str(value or "").strip().split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)


def _is_committed_relationship(label: object) -> bool:
    text = str(label or "").strip()
    return any(token in text for token in ("恋人", "情侣", "伴侣", "男朋友", "女朋友", "恋爱中"))
