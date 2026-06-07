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

    GENERIC_ACTION_LABELS = {
        "消息",
        "打字",
        "停顿",
        "小声",
        "又发一条",
        "又发了一条",
    }

    ACTION_TEXT_RE = re.compile(r"[（(]([^（）()\n]{1,40})[）)]")
    GENERIC_ACTION_TEXT_RE = re.compile(r"[（(]\s*(?:消息|打字|停顿|小声|又发(?:了)?(?:一)?条)\s*[）)]")

    INLINE_REASONING_RE = re.compile(
        r"<\s*(?:think|thinking|reasoning|thought|REASONING_SCRATCHPAD)\s*>.*?"
        r"<\s*/\s*(?:think|thinking|reasoning|thought|REASONING_SCRATCHPAD)\s*>",
        re.IGNORECASE | re.DOTALL,
    )
    ANALYSIS_PREFIXES = (
        "\u7528\u6237\u5728",      # 用户在
        "\u7528\u6237\u7684",      # 用户的
        "\u7528\u6237\u8981\u6c42",  # 用户要求
        "\u7528\u6237\u8bf7\u6c42",  # 用户请求
        "\u89d2\u8272\u5206\u6790",  # 角色分析
        "\u6027\u683c\u5206\u6790",  # 性格分析
        "\u56de\u590d\u7b56\u7565",  # 回复策略
        "\u5206\u6790\u8bf7\u6c42",  # 分析请求
        "\u5206\u6790\u7528\u6237",  # 分析用户
        "\u6211\u9700\u8981\u5148",  # 我需要先
        "\u6211\u9700\u8981\u5206\u6790",  # 我需要分析
    )
    ANALYSIS_MARKERS = (
        "\u89d2\u8272\u5206\u6790",  # 角色分析
        "\u6027\u683c\u5206\u6790",  # 性格分析
        "\u56de\u590d\u7b56\u7565",  # 回复策略
        "\u5206\u6790\u8bf7\u6c42",  # 分析请求
        "\u5206\u6790\u7528\u6237",  # 分析用户
        "\u5206\u6790\u573a\u666f",  # 分析场景
        "\u5185\u90e8\u63a8\u7406",  # 内部推理
        "\u63a8\u7406\u8fc7\u7a0b",  # 推理过程
        "\u7528\u6237\u5728",      # 用户在
        "\u7528\u6237\u7684\u8bf7\u6c42",  # 用户的请求
        "\u7528\u6237\u8981\u6c42",  # 用户要求
        "\u6211\u9700\u8981\u5148",  # 我需要先
        "\u6211\u9700\u8981\u5206\u6790",  # 我需要分析
        "\u5e94\u8be5\u56de\u7b54",  # 应该回答
        "\u6700\u7ec8\u56de\u590d",  # 最终回复
    )
    _OPEN_TO_CLOSE = {
        "(": ")",
        "（": "）",
        "[": "]",
        "【": "】",
        "「": "」",
        "『": "』",
        "《": "》",
        "〈": "〉",
        '"': '"',
        "“": "”",
        "‘": "’",
    }
    _CLOSERS = set(_OPEN_TO_CLOSE.values())

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
        return self._close_unbalanced_wrappers(text.strip())

    def list_recent_actions(self, recent_replies: list[str], *, limit: int = 6) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for reply in recent_replies[-limit:]:
            for match in self.ACTION_TEXT_RE.finditer(str(reply or "")):
                normalized = self._normalize_action(match.group(1))
                if not normalized or self._is_generic_action_label(normalized):
                    continue
                if normalized not in seen:
                    seen.add(normalized)
                    ordered.append(str(match.group(1) or "").strip())
        return ordered

    def clean_generation_context(self, text: str) -> str:
        """Remove failed action-label examples before they are shown to the LLM again."""
        text = str(text or "")
        if not text:
            return text
        text = self.strip_reasoning_artifacts(text)
        text = self.GENERIC_ACTION_TEXT_RE.sub("", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def strip_reasoning_artifacts(self, text: str) -> str:
        """Remove reasoning traces that providers may place in text content."""
        text = str(text or "")
        if not text:
            return ""
        text = self.INLINE_REASONING_RE.sub("", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def looks_like_reasoning_artifact(self, text: str) -> bool:
        """Heuristic guard for analysis text accidentally returned as a reply."""
        cleaned = self.strip_reasoning_artifacts(text)
        if not cleaned:
            return True

        start = cleaned.lstrip("#* \t\r\n:：.-")
        if any(start.startswith(prefix) for prefix in self.ANALYSIS_PREFIXES):
            return True

        marker_count = sum(1 for marker in self.ANALYSIS_MARKERS if marker in cleaned)
        if marker_count >= 2:
            return True
        markdown_headings = len(re.findall(r"(?m)^\s{0,3}#{1,6}\s+", cleaned))
        bold_labels = len(re.findall(
            r"\*\*[^*\n]{1,24}(?:\u5206\u6790|\u7b56\u7565|\u6027\u683c|\u89d2\u8272|\u5224\u65ad)[^*\n]{0,12}\*\*",
            cleaned,
        ))
        return markdown_headings + bold_labels >= 2

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
        if intent == "proactive_generation" and len(text) > 120:
            text = self._first_sentences(text, max_sentences=2)
        return text

    def _first_sentences(self, text: str, max_sentences: int) -> str:
        from ..gateway.sentence_splitter import SentenceSplitter

        parts = SentenceSplitter.split(text)
        selected = parts[:max_sentences]
        return "".join(selected) if selected else text

    def _close_unbalanced_wrappers(self, text: str) -> str:
        text = str(text or "").strip()
        if not text:
            return text

        stack: list[str] = []
        for char in text:
            if char in self._OPEN_TO_CLOSE:
                if char == '"' and stack and stack[-1] == '"':
                    stack.pop()
                else:
                    stack.append(char)
                continue
            if char not in self._CLOSERS or not stack:
                continue
            expected = self._OPEN_TO_CLOSE.get(stack[-1])
            if char == expected:
                stack.pop()

        if not stack:
            return text
        return text + "".join(self._OPEN_TO_CLOSE[ch] for ch in reversed(stack))

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

    def _is_generic_action_label(self, action_text: str) -> bool:
        normalized = self._normalize_action(action_text)
        return bool(normalized) and (
            normalized in self.GENERIC_ACTION_LABELS
            or re.fullmatch(r"又发(?:了)?(?:一)?条", normalized) is not None
        )


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
