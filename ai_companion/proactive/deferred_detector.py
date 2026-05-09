from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class DeferredReplyDetection:
    delay_minutes: int
    topic_summary: str


class DeferredReplyDetector:
    PROMISE_PATTERNS = (
        re.compile(r"(一会儿|一会|等会|待会|晚点|稍后|过会儿).{0,12}(回复|告诉|跟你说|和你说|回你)"),
        re.compile(r"(我想想|我想一下|我考虑一下|我查一下|我看一下).{0,16}(回复你|告诉你|再说|再跟你说)?"),
    )
    DONE_HINTS = ("我想了一下", "我查到了", "结论是", "所以我觉得", "可以先", "我建议")

    def __init__(self, default_delay_minutes: int, min_delay_minutes: int, max_delay_minutes: int):
        self.default_delay_minutes = default_delay_minutes
        self.min_delay_minutes = min_delay_minutes
        self.max_delay_minutes = max_delay_minutes

    def detect(self, user_message: str, bot_message: str) -> DeferredReplyDetection | None:
        text = str(bot_message or "").strip()
        if not text:
            return None
        if any(hint in text for hint in self.DONE_HINTS) and "一会" not in text and "晚点" not in text and "稍后" not in text:
            return None
        if not any(pattern.search(text) for pattern in self.PROMISE_PATTERNS):
            return None
        delay = self._extract_delay_minutes(text)
        summary = f"稍后回复：用户说「{str(user_message or '')[:80]}」，Bot 承诺「{text[:80]}」"
        return DeferredReplyDetection(delay_minutes=delay, topic_summary=summary)

    def _extract_delay_minutes(self, text: str) -> int:
        match = re.search(r"(\d{1,3})\s*分钟", text)
        if match:
            value = int(match.group(1))
        elif re.search(r"半小时|三十分钟", text):
            value = 30
        else:
            value = self.default_delay_minutes
        return max(self.min_delay_minutes, min(self.max_delay_minutes, value))
