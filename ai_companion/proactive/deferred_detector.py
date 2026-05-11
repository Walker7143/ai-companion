from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class DeferredReplyDetection:
    delay_minutes: int
    topic_summary: str


class DeferredReplyDetector:
    PROMISE_PATTERNS = (
        re.compile(r"(?<!不)(?<!没)(?<!别)(一会儿|一会|等会|待会|晚点|稍后|过会儿).{0,20}(回复|告诉|跟你说|和你说|回你|发消息|给你发消息|发给你|发你)"),
        re.compile(r"(?<!不)(?<!没)(?<!别)(我想想|我想一下|我考虑一下|我查一下|我看一下|我研究一下|我整理一下).{0,24}(回复你|告诉你|再说|再跟你说|发消息|给你发消息|发给你|发你)"),
        re.compile(r"(?<!不)(?<!没)(?<!别)(想好了|想好后|查到了|看完了|弄完了|忙完了|整理好).{0,20}(回复你|告诉你|跟你说|发消息|给你发消息|发给你|发你|回你)"),
    )
    USER_REQUEST_PATTERNS = (
        re.compile(r"(一会儿|一会|等会|待会|晚点|稍后|过会儿|想好了|想好后|忙完|忙完了|做好|弄完|整理好).{0,30}(告诉我|跟我说|和我说|回我|回复我|给我发消息|发消息|发我)"),
        re.compile(r"记得.{0,24}(告诉我|跟我说|和我说|回我|回复我|给我发消息|发消息|发我)"),
    )
    BOT_ACCEPT_PATTERNS = (
        re.compile(r"(知道了|记着呢|记住了|会的|我会)(?!吗|么).{0,40}(告诉你|跟你说|回复你|回你|给你发消息|发消息|发你)?"),
        re.compile(r"(行|好|可以|没问题|放心)(?!吗|么).{0,40}(告诉你|跟你说|回复你|回你|给你发消息|发消息|发你)"),
        re.compile(r"(想好了|想好后|弄完了|忙完了|整理好).{0,24}(告诉你|跟你说|回复你|回你|给你发消息|发消息|发你)"),
    )
    DONE_HINTS = ("我想了一下", "我查到了", "结论是", "所以我觉得", "可以先", "我建议")
    CANCEL_HINTS = ("不用了", "不用告诉", "不用回复", "不用等", "别告诉", "别回", "算了", "现在就说")

    def __init__(self, default_delay_minutes: int, min_delay_minutes: int, max_delay_minutes: int):
        self.default_delay_minutes = default_delay_minutes
        self.min_delay_minutes = min_delay_minutes
        self.max_delay_minutes = max_delay_minutes

    def detect(self, user_message: str, bot_message: str) -> DeferredReplyDetection | None:
        user_text = str(user_message or "").strip()
        text = str(bot_message or "").strip()
        if not text:
            return None
        combined = f"{user_text}\n{text}"
        if any(hint in combined for hint in self.CANCEL_HINTS):
            return None
        if any(hint in text for hint in self.DONE_HINTS) and not self._has_delay_marker(text):
            return None
        bot_promised = any(pattern.search(text) for pattern in self.PROMISE_PATTERNS)
        user_requested_and_bot_accepted = (
            any(pattern.search(user_text) for pattern in self.USER_REQUEST_PATTERNS)
            and any(pattern.search(text) for pattern in self.BOT_ACCEPT_PATTERNS)
        )
        if not bot_promised and not user_requested_and_bot_accepted:
            return None
        delay = self._extract_delay_minutes(combined)
        summary = f"稍后回复：用户说「{str(user_message or '')[:80]}」，Bot 承诺「{text[:80]}」"
        return DeferredReplyDetection(delay_minutes=delay, topic_summary=summary)

    def _has_delay_marker(self, text: str) -> bool:
        return any(marker in text for marker in ("一会", "等会", "待会", "晚点", "稍后", "过会", "想好了", "想好后", "忙完", "弄完", "整理好"))

    def _extract_delay_minutes(self, text: str) -> int:
        match = re.search(r"(\d{1,3})\s*分钟", text)
        if match:
            value = int(match.group(1))
        elif re.search(r"半小时|三十分钟", text):
            value = 30
        else:
            value = self.default_delay_minutes
        return max(self.min_delay_minutes, min(self.max_delay_minutes, value))
