"""Structured continuity contract for generation-time memory safety."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .turn_roles import (
    has_explicit_authority_grant,
    infer_turn_role_signal,
    mentions_business_asset_of_assistant,
)


COMMITTED_RELATIONSHIP_LABELS = {"恋人", "男女朋友", "男朋友", "女朋友", "伴侣", "爱人", "老婆", "老公"}


@dataclass
class ContinuityFact:
    kind: str
    text: str
    source: str
    priority: int = 100
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContinuityContract:
    hard_facts: list[ContinuityFact] = field(default_factory=list)
    active_boundaries: list[ContinuityFact] = field(default_factory=list)
    soft_context: list[ContinuityFact] = field(default_factory=list)
    style_freedom: list[ContinuityFact] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hard_facts": [item.to_dict() for item in self.hard_facts],
            "active_boundaries": [item.to_dict() for item in self.active_boundaries],
            "soft_context": [item.to_dict() for item in self.soft_context],
            "style_freedom": [item.to_dict() for item in self.style_freedom],
            "risk_flags": list(self.risk_flags),
        }


def is_committed_relationship_label(label: object) -> bool:
    value = str(label or "").strip()
    return value in COMMITTED_RELATIONSHIP_LABELS


class ContinuityContractBuilder:
    """Derive hard/soft generation constraints from retrieved memory."""

    def build(self, *, current_input: str, retrieved: Any) -> ContinuityContract:
        contract = ContinuityContract()
        relationship = getattr(retrieved, "relationship_state", {}) or {}
        label = str(relationship.get("relationship_label") or relationship.get("relationship_level") or "").strip()
        narrative = str(relationship.get("relationship_narrative") or "").strip()
        guidance = str(relationship.get("interaction_guidance") or "").strip()
        posture = str(relationship.get("current_posture") or "").strip()

        if label:
            contract.hard_facts.append(
                ContinuityFact(
                    kind="relationship_label",
                    text=f"当前已确认关系：{label}",
                    source="relationship_state",
                    priority=5,
                    metadata={"label": label},
                )
            )
        if is_committed_relationship_label(label):
            contract.hard_facts.append(
                ContinuityFact(
                    kind="relationship_committed",
                    text="你和用户已经确认恋人/男女朋友关系；可以嘴硬或害羞，但不能否认、回退或装作未确认。",
                    source="relationship_state",
                    priority=1,
                )
            )
            contract.risk_flags.append("committed_relationship")
        if narrative:
            contract.soft_context.append(
                ContinuityFact(
                    kind="relationship_narrative",
                    text=narrative,
                    source="relationship_state",
                    priority=20,
                )
            )
        if posture:
            contract.soft_context.append(
                ContinuityFact(
                    kind="relationship_posture",
                    text=posture,
                    source="relationship_state",
                    priority=25,
                )
            )
        if guidance:
            contract.active_boundaries.append(
                ContinuityFact(
                    kind="relationship_guidance",
                    text=guidance,
                    source="relationship_state",
                    priority=10,
                )
            )

        for item in getattr(retrieved, "turn_constraints", []) or []:
            value = str(item.get("value") or item.get("text") or item.get("key") or "").strip()
            if not value:
                continue
            contract.active_boundaries.append(
                ContinuityFact(
                    kind="turn_constraint",
                    text=value,
                    source="turn_constraints",
                    priority=15,
                    metadata={"key": item.get("key"), "category": item.get("category")},
                )
            )

        for state in getattr(retrieved, "session_state", []) or []:
            subject = str(state.get("subject") or "").strip()
            predicate = str(state.get("predicate") or "").strip()
            value = str(state.get("value") or "").strip()
            if not value:
                continue
            rendered_value = _session_state_text(subject, value)
            if predicate in {"relationship_explicit_status"} and is_committed_relationship_label(label):
                contract.soft_context.append(
                    ContinuityFact(
                        kind="relationship_expression_state",
                        text=f"当前表达状态：{rendered_value}",
                        source="session_state",
                        priority=30,
                        metadata={"predicate": predicate, "subject": subject, "downgraded": True},
                    )
                )
                continue
            if "boundary" in predicate or "constraint" in predicate:
                contract.active_boundaries.append(
                    ContinuityFact(
                        kind="session_boundary",
                        text=rendered_value,
                        source="session_state",
                        priority=18,
                        metadata={"predicate": predicate, "subject": subject},
                    )
                )
            else:
                contract.soft_context.append(
                    ContinuityFact(
                        kind="session_state",
                        text=rendered_value,
                        source="session_state",
                        priority=35,
                        metadata={"predicate": predicate, "subject": subject},
                    )
                )

        daily_context = getattr(retrieved, "daily_context", {}) or {}
        for thread in daily_context.get("open_threads") or []:
            thread_text = str(thread).strip()
            if not thread_text:
                continue
            contract.soft_context.append(
                ContinuityFact(
                    kind="daily_open_thread",
                    text=thread_text,
                    source="daily_context",
                    priority=40,
                )
            )

        current_text = str(current_input or "").strip()
        if current_text and any(token in current_text for token in ("男朋友", "女朋友", "关系", "忘了", "记得")):
            contract.risk_flags.append("relationship_direct_query")
        turn_role_signal = infer_turn_role_signal(current_text)
        if turn_role_signal is not None:
            actor_label = "用户" if turn_role_signal.actor == "user" else "你"
            owner_label = "你的" if turn_role_signal.owner == "assistant" else "我的"
            contract.hard_facts.append(
                ContinuityFact(
                    kind="turn_role_signal",
                    text=(
                        f"本轮事实：是{actor_label}在{turn_role_signal.raw_action}{owner_label}{turn_role_signal.asset}，"
                        "不要把施事者、资产归属或权限关系写反。"
                    ),
                    source="current_input",
                    priority=4,
                    metadata={
                        "actor": turn_role_signal.actor,
                        "owner": turn_role_signal.owner,
                        "action_family": turn_role_signal.action_family,
                        "asset": turn_role_signal.asset,
                    },
                )
            )
            contract.risk_flags.append("turn_role_signal")
        if (
            ((turn_role_signal is not None and turn_role_signal.owner == "assistant") or mentions_business_asset_of_assistant(current_text))
            and not has_explicit_authority_grant(current_text)
        ):
            contract.active_boundaries.append(
                ContinuityFact(
                    kind="authority_boundary",
                    text="除非用户明确确认受雇、上下级或管理关系，否则不要把用户写成你的员工、下属或可被你发工资、扣工资、排班、批假、开除的对象。",
                    source="current_input",
                    priority=8,
                )
            )
            contract.risk_flags.append("authority_relation_unguarded")

        contract.style_freedom.append(
            ContinuityFact(
                kind="style_rule",
                text="允许保留熟悉、傲娇、害羞、调情等语气，但这些语气只能修饰表达，不能改变已确认事实。",
                source="continuity_policy",
                priority=60,
            )
        )
        return contract


def _session_state_text(subject: str, value: str) -> str:
    label = _session_state_subject_label(subject)
    if not label:
        return value
    return f"{label}：{value}"


def _session_state_subject_label(subject: str) -> str:
    subject = str(subject or "").strip()
    if subject == "user":
        return "用户当前状态"
    if subject == "assistant":
        return "你自己当前状态"
    if subject == "shared":
        return "双方当前状态"
    return ""


class RelationshipProjectionService:
    """Single-source projection for relationship prompt-facing layers."""

    def build_projection(self, relationship: dict[str, Any] | None) -> dict[str, list[str] | str]:
        state = relationship if isinstance(relationship, dict) else {}
        label = str(state.get("relationship_label") or "").strip()
        narrative = str(state.get("relationship_narrative") or "").strip()
        posture = str(state.get("current_posture") or "").strip()
        guidance = str(state.get("interaction_guidance") or "").strip()
        open_threads = [str(item).strip() for item in state.get("open_emotional_threads") or [] if str(item).strip()]

        need_from_bot: list[str] = []
        repair_preferences: list[str] = []
        if narrative:
            need_from_bot.append(narrative)
        if posture:
            need_from_bot.append(posture)
        if guidance:
            repair_preferences.append(guidance)
        if is_committed_relationship_label(label):
            need_from_bot.append("当前已确认恋人/男女朋友关系，后续互动必须承接这个事实，不能回退成未确认状态。")

        return {
            "label": label,
            "need_from_bot": need_from_bot,
            "repair_preferences": repair_preferences,
            "open_threads": open_threads,
        }
