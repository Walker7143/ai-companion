from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from .deferred_detector import DeferredReplyDetector

logger = logging.getLogger(__name__)

CLOSEOUT_ANALYSIS_PROMPT = """\
你是对话分析助手。分析以下对话片段，判断是否存在以下情况：

1. 延迟回复承诺：Bot 是否明确承诺稍后回复/告知/查找某事，或用户要求 Bot 稍后告诉/提醒/发消息且 Bot 接受？
2. 未完成话题：对话是否在某个话题中途结束，用户的核心问题未被充分回答？
3. 情绪关怀需要：用户是否表达了明显的负面情绪（难过/焦虑/压力/生气/沮丧）需要后续关心？

【对话内容】
{conversation}

【判断规则】
- "我想想也是"、"我觉得可以"等表示赞同/思考的话，不算延迟回复承诺
- 用户说"一会告诉我/想好了告诉我/记得告诉我/忙完告诉我"，Bot 回答"行/知道了/好/我想好了给你发消息/我会告诉你"，算延迟回复承诺
- Bot 不一定要主动说"稍后"才算承诺；只要上下文中用户提出延迟回告要求，Bot 接受或确认会后续发消息，也算
- 如果 Bot 已经当场给出完整答案，或只是礼貌结束（"去忙吧"）且没有接受后续回告要求，不算延迟回复承诺
- 否定句（"我不会稍后回复"、"不用等我"）不算承诺
- 用户说了"好的/明白了/谢谢/嗯嗯/知道了"表示话题已结束，不算未完成话题
- 反问句和修辞性问题不算未完成话题
- 只有明确的负面情绪才需要情绪跟进，日常吐槽（"今天好累啊"后面接了正常聊天）不算
- 如果 Bot 已经对情绪做了充分回应和安慰，不需要再跟进

【输出】
只输出 JSON，不要其他内容：
{{"deferred_reply": {{"detected": false, "summary": "", "delay_minutes": 0}}, "unresolved_topic": {{"detected": false, "summary": "", "confidence": 0.0}}, "emotion_followup": {{"detected": false, "emotion": "", "summary": ""}}}}
"""


@dataclass
class DeferredSignal:
    summary: str
    delay_minutes: int


@dataclass
class TopicSignal:
    summary: str
    confidence: float


@dataclass
class EmotionSignal:
    emotion: str
    summary: str


@dataclass
class CloseoutResult:
    deferred_reply: DeferredSignal | None = None
    unresolved_topic: TopicSignal | None = None
    emotion_followup: EmotionSignal | None = None


class CloseoutAnalyzer:
    def __init__(self, model, config):
        self.model = model
        self.config = config
        self._fallback_detector = DeferredReplyDetector(
            default_delay_minutes=config.deferred_reply_default_delay_minutes,
            min_delay_minutes=config.deferred_reply_min_delay_minutes,
            max_delay_minutes=config.deferred_reply_max_delay_minutes,
        )

    async def analyze(
        self,
        user_message: str,
        bot_message: str,
        recent_turns: list[dict[str, Any]] | None = None,
    ) -> CloseoutResult:
        if not self.config.closeout_analyzer_enabled or self.model is None:
            return self._fallback_analyze(user_message, bot_message)

        conversation_text = self._format_conversation(user_message, bot_message, recent_turns)
        prompt = CLOSEOUT_ANALYSIS_PROMPT.format(conversation=conversation_text)

        try:
            response = await self.model.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=None,
                max_tokens=self.config.closeout_analyzer_max_tokens,
            )
            result = self._parse_response(response)
            if self.config.closeout_analyzer_fallback_to_regex and not result.deferred_reply:
                fallback = self._fallback_analyze(user_message, bot_message)
                if fallback.deferred_reply:
                    result.deferred_reply = fallback.deferred_reply
                    logger.info(
                        "[CloseoutAnalyzer] LLM 未命中延迟回复，规则兜底命中: %s",
                        fallback.deferred_reply.summary,
                    )
            logger.info(
                "[CloseoutAnalyzer] 判定结果 deferred=%s unresolved=%s emotion=%s raw=%s",
                bool(result.deferred_reply),
                bool(result.unresolved_topic),
                bool(result.emotion_followup),
                str(response or "").strip()[:500],
            )
            return result
        except Exception as e:
            logger.warning("[CloseoutAnalyzer] LLM 分析失败: %s，降级为规则检测", e)
            if self.config.closeout_analyzer_fallback_to_regex:
                return self._fallback_analyze(user_message, bot_message)
            return CloseoutResult()

    def _format_conversation(
        self,
        user_message: str,
        bot_message: str,
        recent_turns: list[dict[str, Any]] | None,
    ) -> str:
        lines: list[str] = []
        if recent_turns:
            for turn in recent_turns[-4:]:
                role = turn.get("role", "")
                content = str(turn.get("content", ""))[:200]
                if role == "user":
                    lines.append(f"用户：{content}")
                elif role == "assistant":
                    lines.append(f"Bot：{content}")
        lines.append(f"用户：{user_message[:200]}")
        lines.append(f"Bot：{bot_message[:200]}")
        return "\n".join(lines)

    def _parse_response(self, response: str) -> CloseoutResult:
        text = str(response or "").strip()
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if not json_match:
            return CloseoutResult()

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            return CloseoutResult()

        result = CloseoutResult()

        dr = data.get("deferred_reply")
        if isinstance(dr, dict) and dr.get("detected"):
            result.deferred_reply = DeferredSignal(
                summary=str(dr.get("summary", "")),
                delay_minutes=int(dr.get("delay_minutes") or self.config.deferred_reply_default_delay_minutes),
            )

        ut = data.get("unresolved_topic")
        if isinstance(ut, dict) and ut.get("detected"):
            confidence = float(ut.get("confidence", 0.0))
            if confidence >= self.config.topic_continuation_min_score:
                result.unresolved_topic = TopicSignal(
                    summary=str(ut.get("summary", "")),
                    confidence=confidence,
                )

        ef = data.get("emotion_followup")
        if isinstance(ef, dict) and ef.get("detected"):
            result.emotion_followup = EmotionSignal(
                emotion=str(ef.get("emotion", "")),
                summary=str(ef.get("summary", "")),
            )

        return result

    def _fallback_analyze(self, user_message: str, bot_message: str) -> CloseoutResult:
        result = CloseoutResult()
        detected = self._fallback_detector.detect(user_message, bot_message)
        if detected:
            result.deferred_reply = DeferredSignal(
                summary=detected.topic_summary,
                delay_minutes=detected.delay_minutes,
            )
        return result
