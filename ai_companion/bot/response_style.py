"""Response style polishing to reduce generic AI tone."""

from __future__ import annotations

import re
from typing import Any


class ResponseStylePolisher:
    """Lightweight post-processing for generated replies.

    This is intentionally local and conservative. It removes common assistant
    boilerplate and nudges structure toward natural chat without inventing new
    content.
    """

    AI_PHRASES = [
        "作为一个AI",
        "作为AI",
        "作为一个人工智能",
        "作为人工智能",
        "我能理解你的感受",
        "我理解你的感受",
        "这听起来很",
        "以下是一些建议",
        "以下是几点建议",
        "希望这能帮到你",
        "如果你需要，我可以",
        "总之，",
    ]

    ACTION_TEXT_RE = re.compile(r"[（(]([^（）()\n]{1,40})[）)]")

    def polish(
        self,
        text: str,
        *,
        intent: str = "casual_chat",
        relationship_state: dict[str, Any] | None = None,
        user_understanding: dict[str, Any] | None = None,
    ) -> str:
        text = str(text or "").strip()
        if not text:
            return text

        text = self._remove_ai_disclaimers(text)
        text = self._remove_memory_exposition(text)
        text = self._soften_numbered_lists(text, intent=intent)
        text = self._apply_interaction_style(text, user_understanding or {})
        text = self._apply_intent_pacing(text, intent=intent, relationship_state=relationship_state or {})
        return text.strip()

    def list_recent_actions(self, recent_replies: list[str], *, limit: int = 6) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for reply in recent_replies[-limit:]:
            for match in self.ACTION_TEXT_RE.finditer(str(reply or "")):
                normalized = self._normalize_action(match.group(1))
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    ordered.append(str(match.group(1) or "").strip())
        return ordered

    def _remove_ai_disclaimers(self, text: str) -> str:
        for phrase in self.AI_PHRASES:
            text = text.replace(phrase, "")
        text = re.sub(r"^\s*[，,。.!！]\s*", "", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    def _remove_memory_exposition(self, text: str) -> str:
        patterns = [
            r"根据你(?:之前|刚才)?(?:说过|提到|告诉我)的[^，。,.!！]*[，,]",
            r"我记得你(?:之前)?(?:说过|提到)[^，。,.!！]*[，,]",
            r"从你的资料里看[^，。,.!！]*[，,]",
            r"根据你的记忆[^，。,.!！]*[，,]",
        ]
        for pattern in patterns:
            text = re.sub(pattern, "", text)
        return text.strip()

    def _soften_numbered_lists(self, text: str, *, intent: str) -> str:
        if intent == "task_request":
            return text
        lines = text.splitlines()
        numbered = [line for line in lines if re.match(r"^\s*(?:\d+[\.、)]|[-*])\s+", line)]
        if len(numbered) < 2:
            return text
        cleaned = []
        for line in lines:
            line = re.sub(r"^\s*(?:\d+[\.、)]|[-*])\s+", "", line).strip()
            if line:
                cleaned.append(line)
        return "。".join(cleaned[:3]) + ("。" if cleaned else "")

    def _apply_interaction_style(self, text: str, understanding: dict[str, Any]) -> str:
        style = self._interaction_style(understanding)
        disliked = style.get("disliked_phrases", [])
        for phrase in disliked if isinstance(disliked, list) else []:
            text = text.replace(str(phrase), "")
        avoid_patterns = style.get("avoid_patterns", [])
        if isinstance(avoid_patterns, list) and any("先总结再列点" in str(p) for p in avoid_patterns):
            text = self._soften_numbered_lists(text, intent="casual_chat")
        preferred_length = str(style.get("preferred_reply_length") or "")
        if "短" in preferred_length and len(text) > 180:
            text = self._first_sentences(text, max_sentences=2)
        return text.strip()

    def _apply_intent_pacing(self, text: str, *, intent: str, relationship_state: dict[str, Any]) -> str:
        tension = _float(relationship_state.get("tension_score"))
        if tension >= 45 and len(text) > 220:
            text = self._first_sentences(text, max_sentences=2)
        if intent == "emotional_support" and len(text) > 260:
            text = self._first_sentences(text, max_sentences=3)
        return text

    def _first_sentences(self, text: str, max_sentences: int) -> str:
        parts = re.split(r"(?<=[。！？!?])", text)
        selected = [part.strip() for part in parts if part.strip()][:max_sentences]
        return "".join(selected) if selected else text

    def _interaction_style(self, understanding: dict[str, Any]) -> dict[str, Any]:
        manual = understanding.get("manual") if isinstance(understanding.get("manual"), dict) else {}
        auto = understanding.get("auto") if isinstance(understanding.get("auto"), dict) else {}
        manual_style = manual.get("interaction_style") if isinstance(manual.get("interaction_style"), dict) else {}
        auto_style = auto.get("interaction_style") if isinstance(auto.get("interaction_style"), dict) else {}
        return {**auto_style, **manual_style}

    def _normalize_action(self, action_text: str) -> str:
        raw = str(action_text or "").strip().lower()
        raw = re.sub(r"[，。,.!！?？:：;；~～…·\s]+", "", raw)
        return raw


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
