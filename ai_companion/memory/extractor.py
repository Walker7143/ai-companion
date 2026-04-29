"""Memory candidate extraction.

The extractor turns one user/bot exchange into structured candidates.  It is
intentionally conservative: when extraction is uncertain or malformed, the
conversation still remains in working memory, but no long-term memory is written.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class MemoryCandidate:
    """A candidate memory item before governor approval."""

    type: str
    key: str = ""
    value: str = ""
    category: str = "general"
    summary: str = ""
    content: str = ""
    title: str = ""
    confidence: float = 0.7
    importance: float = 0.5
    source: str = "auto"
    ttl_days: Optional[int] = None
    evidence: list[str] = field(default_factory=list)
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> "MemoryCandidate":
        self.type = str(self.type or "").strip()
        self.key = str(self.key or "").strip()
        self.value = str(self.value or "").strip()
        self.category = str(self.category or "general").strip() or "general"
        self.summary = str(self.summary or "").strip()
        self.content = str(self.content or "").strip()
        self.title = str(self.title or "").strip()
        self.source = str(self.source or "auto").strip() or "auto"
        self.reason = str(self.reason or "").strip()
        self.confidence = _clamp_float(self.confidence, 0.0, 1.0, 0.7)
        self.importance = _clamp_float(self.importance, 0.0, 1.0, 0.5)
        return self


class MemoryExtractor:
    """Extract structured memory candidates from a single exchange."""

    EXTRACT_PROMPT = """对话：
用户：{user_input}
助手：{bot_output}

最近几轮上下文：
{conversation_context}

请只根据用户亲口表达和这轮互动，抽取可能值得保存的记忆候选。
重点判断用户画像信息、沟通偏好、边界、近期压力源、计划、共同经历、关系变化。

输出一个 JSON 对象，字段如下：
{{
  "facts": [
    {{
      "key": "事实key",
      "value": "事实value",
      "category": "identity|preferences|dislikes|boundaries|communication_style|life_context|goals|important_people|routines|general",
      "confidence": 0.0到1.0,
      "importance": 0.0到1.0,
      "ttl_days": null或整数,
      "reason": "为什么值得记"
    }}
  ],
  "episodes": [
    {{
      "title": "短标题",
      "summary": "30-80字情景摘要",
      "importance": 0.0到1.0,
      "confidence": 0.0到1.0,
      "topics": ["主题"],
      "emotion_tags": ["情绪"],
      "reason": "为什么是长期共同经历"
    }}
  ],
  "relationship": {{
    "label": "朋友|好朋友|暧昧中|恋人|疏远|紧张",
    "intimacy_delta": -1.0到1.0,
    "trust_delta": -1.0到1.0,
    "tension_delta": -1.0到1.0,
    "affection_delta": -1.0到1.0,
    "attitude_delta": -5到5,
    "key_moment": "关键关系时刻或空字符串",
    "open_thread": "未完成情绪话题或空字符串"
  }},
  "open_threads": ["后续值得关心的话题"]
}}

规则：
- 普通寒暄、一次性闲聊不要放入 episodes。
- 不要从助手回复反推用户事实。
- 短暂情绪只有在用户明确表示持续或重要时才记录为 life_context。
- 不确定就降低 confidence，不要编造。
- 只输出 JSON，不要解释。"""

    CATEGORY_KEYWORDS = [
        ("boundaries", ["不要", "别", "不想聊", "不接受", "雷区", "边界"]),
        ("communication_style", ["先共情", "少讲道理", "怎么回应", "安慰我", "别说教"]),
        ("life_context", ["压力", "失眠", "焦虑", "最近", "准备", "面试", "考试", "作品集"]),
        ("goals", ["想要", "计划", "目标", "明天", "以后", "继续"]),
        ("identity", ["叫我", "我叫", "住在", "城市", "职业"]),
        ("preferences", ["喜欢", "偏好", "爱吃", "爱听"]),
        ("dislikes", ["讨厌", "不喜欢"]),
    ]

    EPISODE_KEYWORDS = [
        "吵架",
        "和好",
        "道歉",
        "承诺",
        "约定",
        "表白",
        "分手",
        "第一次",
        "搬家",
        "考试",
        "面试",
        "失眠",
        "崩溃",
        "重要",
    ]

    def __init__(self, summarizer: Optional[object] = None):
        self._summarizer = summarizer

    def set_summarizer(self, summarizer):
        self._summarizer = summarizer

    async def extract(
        self,
        user_input: str,
        bot_output: str,
        *,
        session_id: str,
        conversation_context: str = "",
    ) -> list[MemoryCandidate]:
        if self._summarizer is None:
            return self._rule_extract(user_input, bot_output, session_id=session_id)

        prompt = self.EXTRACT_PROMPT.format(
            user_input=user_input,
            bot_output=bot_output,
            conversation_context=conversation_context or "无",
        )
        try:
            response = await self._summarizer.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=None,
            )
            raw = _response_text(response)
            candidates = self._parse_structured(raw, user_input, bot_output, session_id)
            if candidates:
                return candidates
        except Exception:
            pass
        return self._rule_extract(user_input, bot_output, session_id=session_id)

    def _parse_structured(
        self,
        raw: str,
        user_input: str,
        bot_output: str,
        session_id: str,
    ) -> list[MemoryCandidate]:
        text = _strip_fences(raw)
        candidates: list[MemoryCandidate] = []

        # Backward-compatible parser for old tests/models that return JSON lines.
        line_facts = self._parse_json_lines(text)
        if line_facts:
            for item in line_facts:
                candidates.append(self._fact_candidate(item, session_id))
            return [c.normalized() for c in candidates if self._valid_candidate(c)]

        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, TypeError, ValueError):
            return []
        if not isinstance(payload, dict):
            return []

        for item in payload.get("facts") or []:
            if isinstance(item, dict):
                candidates.append(self._fact_candidate(item, session_id))

        content = f"用户：{user_input}\n助手：{bot_output}"
        for item in payload.get("episodes") or []:
            if not isinstance(item, dict):
                continue
            topics = item.get("topics") if isinstance(item.get("topics"), list) else []
            emotion_tags = item.get("emotion_tags") if isinstance(item.get("emotion_tags"), list) else []
            candidates.append(
                MemoryCandidate(
                    type="episode",
                    title=str(item.get("title") or "").strip(),
                    summary=str(item.get("summary") or "").strip(),
                    content=content,
                    confidence=_clamp_float(item.get("confidence"), 0.0, 1.0, 0.7),
                    importance=_clamp_float(item.get("importance"), 0.0, 1.0, 0.5),
                    source="auto",
                    evidence=[session_id],
                    reason=str(item.get("reason") or "").strip(),
                    metadata={"topics": topics, "emotion_tags": emotion_tags},
                )
            )

        rel = payload.get("relationship")
        if isinstance(rel, dict):
            candidates.extend(self._relationship_candidates(rel, session_id))

        for thread in payload.get("open_threads") or []:
            thread_text = str(thread).strip()
            if thread_text:
                candidates.append(
                    MemoryCandidate(
                        type="temporary_context",
                        key="open_thread",
                        value=thread_text,
                        category="open_threads",
                        confidence=0.75,
                        importance=0.65,
                        source="auto",
                        ttl_days=30,
                        evidence=[session_id],
                    )
                )

        return [c.normalized() for c in candidates if self._valid_candidate(c)]

    def _parse_json_lines(self, text: str) -> list[dict]:
        if text.strip() in {"", "NO_FACT", "NO_CHANGE", "NO_MOMENT"}:
            return []
        facts: list[dict] = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line in {"NO_FACT", "NO_CHANGE", "NO_MOMENT"}:
                continue
            try:
                item = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(item, dict) and "key" in item and "value" in item:
                facts.append(item)
        return facts

    def _fact_candidate(self, item: dict, session_id: str) -> MemoryCandidate:
        key = str(item.get("key") or "").strip()
        value = str(item.get("value") or "").strip()
        category = str(item.get("category") or self._infer_category(key, value)).strip()
        return MemoryCandidate(
            type="user_fact",
            key=key,
            value=value,
            category=category or "general",
            confidence=_clamp_float(item.get("confidence"), 0.0, 1.0, 0.78),
            importance=_clamp_float(item.get("importance"), 0.0, 1.0, self._default_importance(category)),
            source="user_explicit",
            ttl_days=item.get("ttl_days") if isinstance(item.get("ttl_days"), int) else self._default_ttl(category),
            evidence=[session_id],
            reason=str(item.get("reason") or "").strip(),
        )

    def _relationship_candidates(self, rel: dict, session_id: str) -> list[MemoryCandidate]:
        candidates: list[MemoryCandidate] = []
        numeric_keys = {
            "intimacy_delta",
            "trust_delta",
            "tension_delta",
            "affection_delta",
            "attitude_delta",
        }
        rel_data = {k: rel.get(k) for k in numeric_keys}
        label = str(rel.get("label") or "").strip()
        key_moment = str(rel.get("key_moment") or "").strip()
        open_thread = str(rel.get("open_thread") or "").strip()
        if label or any(_safe_float(v) != 0 for v in rel_data.values()) or key_moment or open_thread:
            candidates.append(
                MemoryCandidate(
                    type="relationship_event",
                    key="relationship_state",
                    value=label,
                    confidence=0.75,
                    importance=0.75 if key_moment else 0.6,
                    source="auto",
                    evidence=[session_id],
                    metadata={**rel_data, "label": label, "key_moment": key_moment, "open_thread": open_thread},
                )
            )
        return candidates

    def _rule_extract(self, user_input: str, bot_output: str, *, session_id: str) -> list[MemoryCandidate]:
        text = user_input.strip()
        candidates: list[MemoryCandidate] = []
        category = self._infer_category(text, text)
        if category != "general" and len(text) >= 6:
            key = self._infer_key(category, text)
            candidates.append(
                MemoryCandidate(
                    type="user_fact",
                    key=key,
                    value=text[:160],
                    category=category,
                    confidence=0.68 if category in {"life_context", "goals"} else 0.76,
                    importance=self._default_importance(category),
                    source="rule",
                    ttl_days=self._default_ttl(category),
                    evidence=[session_id],
                )
            )

        if self._looks_like_episode(text):
            candidates.append(
                MemoryCandidate(
                    type="episode",
                    title=text[:24],
                    summary=text[:100],
                    content=f"用户：{user_input}\n助手：{bot_output}",
                    confidence=0.68,
                    importance=0.72,
                    source="rule",
                    evidence=[session_id],
                    metadata={"topics": [], "emotion_tags": []},
                )
            )
        return [c.normalized() for c in candidates if self._valid_candidate(c)]

    def _infer_category(self, key: str, value: str) -> str:
        haystack = f"{key} {value}"
        for category, keywords in self.CATEGORY_KEYWORDS:
            if any(word in haystack for word in keywords):
                return category
        return "general"

    def _infer_key(self, category: str, value: str) -> str:
        defaults = {
            "boundaries": "聊天边界",
            "communication_style": "希望被怎样回应",
            "life_context": "近期状态",
            "goals": "近期目标",
            "identity": "用户身份信息",
            "preferences": "用户偏好",
            "dislikes": "用户不喜欢的事",
        }
        return defaults.get(category, value[:20])

    def _default_importance(self, category: str) -> float:
        return {
            "boundaries": 0.95,
            "communication_style": 0.9,
            "important_people": 0.82,
            "identity": 0.78,
            "life_context": 0.7,
            "goals": 0.7,
            "preferences": 0.68,
            "dislikes": 0.68,
            "routines": 0.62,
        }.get(category, 0.5)

    def _default_ttl(self, category: str) -> Optional[int]:
        if category == "life_context":
            return 30
        if category == "goals":
            return 60
        return None

    def _looks_like_episode(self, text: str) -> bool:
        if len(text) < 8:
            return False
        return any(keyword in text for keyword in self.EPISODE_KEYWORDS)

    def _valid_candidate(self, candidate: MemoryCandidate) -> bool:
        if candidate.type == "user_fact":
            return bool(candidate.key and candidate.value)
        if candidate.type == "episode":
            return bool(candidate.summary)
        if candidate.type in {"relationship_event", "temporary_context"}:
            return bool(candidate.key or candidate.value or candidate.metadata)
        return False


def _response_text(response: object) -> str:
    if isinstance(response, dict):
        return str(response.get("content") or response.get("reasoning_content") or "")
    if isinstance(response, str):
        return response
    return str(response)


def _strip_fences(text: str) -> str:
    text = re.sub(r"```json\s*", "", text or "")
    text = re.sub(r"```\s*", "", text)
    return text.strip()


def _clamp_float(value: object, low: float, high: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
