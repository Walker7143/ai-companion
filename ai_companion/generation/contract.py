"""Unified generation context contracts.

The contract is intentionally small: it gives chat and proactive generation a
shared ordering of truth without replacing the existing prompt builders.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class GenerationContract:
    """The runtime context that should govern one generation."""

    mode: str
    intent: str = "casual_chat"
    motive: dict[str, Any] = field(default_factory=dict)
    scene_anchor: dict[str, Any] = field(default_factory=dict)
    life_anchor: dict[str, Any] = field(default_factory=dict)
    memory_awareness: dict[str, Any] = field(default_factory=dict)
    relationship_posture: str = ""
    emotion_state: dict[str, Any] = field(default_factory=dict)
    constraints: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def render_for_prompt(self, *, max_chars: int = 2600) -> str:
        lines: list[str] = ["【统一生成合同】"]
        lines.append("- 优先级：当前真实现场 > 本轮输入/主动动机 > Bot 当前生活锚点 > 被激活记忆 > 长期人格背景。")
        lines.append(f"- 生成模式：{self.mode}")
        if self.intent:
            lines.append(f"- 当前意图：{self.intent}")
        motive_type = self.motive.get("type") if isinstance(self.motive, dict) else None
        motive_reason = self.motive.get("reason") if isinstance(self.motive, dict) else None
        if motive_type or motive_reason:
            lines.append(f"- 主动动机：{motive_type or '未标注'}；{motive_reason or '无'}")

        scene_summary = _first_text(
            self.scene_anchor.get("summary"),
            self.scene_anchor.get("recent_scene_anchor"),
            self.scene_anchor.get("text"),
        )
        if scene_summary:
            lines.append(f"- 当前真实现场：{scene_summary}")

        life_summary = _first_text(
            self.life_anchor.get("summary"),
            self.life_anchor.get("current_life_context"),
        )
        if life_summary:
            lines.append(f"- Bot 当前生活锚点：{life_summary}")

        mood = _first_text(
            self.emotion_state.get("current_mood"),
            self.life_anchor.get("bot_mood"),
            self.life_anchor.get("interaction_mood"),
        )
        if mood:
            lines.append(f"- 当前心情：{mood}")

        if self.relationship_posture:
            lines.append(f"- 关系姿态：{self.relationship_posture}")

        active = self.memory_awareness.get("active_memories")
        if isinstance(active, list) and active:
            lines.append("- 本轮只允许自然浮起的记忆：")
            for item in active[:4]:
                text = str(item.get("text") if isinstance(item, dict) else item).strip()
                if text:
                    lines.append(f"  - {text[:140]}")

        if self.constraints:
            lines.append("- 必须遵守：")
            for item in self.constraints[:8]:
                text = str(item or "").strip()
                if text:
                    lines.append(f"  - {text}")

        rendered = "\n".join(lines)
        if len(rendered) > max_chars:
            return rendered[: max_chars - 3].rstrip() + "..."
        return rendered


class GenerationContextBuilder:
    """Build shared generation contracts from existing subsystem outputs."""

    def build_chat_contract(
        self,
        *,
        intent: str,
        current_input: str,
        memory_awareness: dict[str, Any] | None = None,
        life_anchor: dict[str, Any] | None = None,
        scene_anchor: dict[str, Any] | None = None,
        relationship_state: dict[str, Any] | None = None,
    ) -> GenerationContract:
        memory_awareness = memory_awareness or {}
        life_anchor = life_anchor or {}
        scene_anchor = scene_anchor or {}
        relationship_state = relationship_state or {}
        return GenerationContract(
            mode="chat",
            intent=intent or "casual_chat",
            scene_anchor=scene_anchor,
            life_anchor=life_anchor,
            memory_awareness=memory_awareness,
            relationship_posture=_relationship_posture(memory_awareness, relationship_state),
            emotion_state=_emotion_state(life_anchor, relationship_state),
            constraints=self._base_constraints(current_input=current_input, proactive=False),
            diagnostics={
                "current_input_chars": len(str(current_input or "")),
                "has_life_anchor": bool(life_anchor),
                "has_memory_awareness": bool(memory_awareness),
                "has_scene_anchor": bool(scene_anchor),
            },
        )

    def build_proactive_contract(
        self,
        *,
        motive: Any,
        intent: str = "proactive_generation",
        memory_awareness: dict[str, Any] | None = None,
        life_anchor: dict[str, Any] | None = None,
        scene_anchor: dict[str, Any] | None = None,
        relationship_state: dict[str, Any] | None = None,
    ) -> GenerationContract:
        motive_dict = _motive_to_dict(motive)
        memory_awareness = memory_awareness or {}
        life_anchor = life_anchor or {}
        scene_anchor = scene_anchor or {}
        relationship_state = relationship_state or {}
        return GenerationContract(
            mode="proactive",
            intent=intent,
            motive=motive_dict,
            scene_anchor=scene_anchor,
            life_anchor=life_anchor,
            memory_awareness=memory_awareness,
            relationship_posture=_relationship_posture(memory_awareness, relationship_state),
            emotion_state=_emotion_state(life_anchor, relationship_state),
            constraints=self._base_constraints(current_input=motive_dict.get("reason", ""), proactive=True),
            diagnostics={
                "motive_type": motive_dict.get("type"),
                "has_life_anchor": bool(life_anchor),
                "has_memory_awareness": bool(memory_awareness),
                "has_scene_anchor": bool(scene_anchor),
            },
        )

    def _base_constraints(self, *, current_input: str, proactive: bool) -> list[str]:
        constraints = [
            "当前真实现场高于旧摘要、长期记忆、旧生活事件。",
            "记忆只影响语气、分寸和承接方式，不要像读资料。",
            "Bot 自己的生活事件只能说成自己的经历，不要说成用户状态。",
        ]
        if proactive:
            constraints.append("这是主动发起的一句话，不要写成刚收到用户消息后的回复。")
            constraints.append("若上一条未回复主动消息已覆盖同主题，不要复读催促。")
        if any(marker in str(current_input or "") for marker in ("不要", "别", "不许", "刚才", "现在")):
            constraints.append("本轮用户显式约束优先于历史偏好。")
        return constraints


def _motive_to_dict(motive: Any) -> dict[str, Any]:
    if motive is None:
        return {}
    motive_type = getattr(getattr(motive, "type", None), "value", getattr(motive, "type", ""))
    return {
        "type": str(motive_type or ""),
        "priority": getattr(motive, "priority", None),
        "reason": str(getattr(motive, "reason", "") or ""),
        "prompt_context": str(getattr(motive, "prompt_context", "") or ""),
        "metadata": dict(getattr(motive, "metadata", {}) or {}),
    }


def _relationship_posture(memory_awareness: dict[str, Any], relationship_state: dict[str, Any]) -> str:
    for key in ("relationship_posture", "relationship_guidance"):
        value = str(memory_awareness.get(key) or "").strip()
        if value:
            return value
    parts = [
        str(relationship_state.get("relationship_narrative") or "").strip(),
        str(relationship_state.get("current_posture") or "").strip(),
        str(relationship_state.get("interaction_guidance") or "").strip(),
    ]
    parts = [item for item in parts if item]
    if parts:
        return "；".join(parts[:3])
    label = str(relationship_state.get("relationship_label") or relationship_state.get("relationship_level") or "").strip()
    return label


def _emotion_state(life_anchor: dict[str, Any], relationship_state: dict[str, Any]) -> dict[str, Any]:
    state = {
        "current_mood": life_anchor.get("bot_mood") or life_anchor.get("interaction_mood") or "",
        "interaction_mood": life_anchor.get("interaction_mood") or "",
    }
    for key in ("tension_score", "intimacy_score", "trust_score"):
        if key in relationship_state:
            state[key] = relationship_state.get(key)
    return state


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
