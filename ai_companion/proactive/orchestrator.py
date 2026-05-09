from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .conversation_task_store import ConversationTaskStore
from .motives import ConversationTask, ConversationTaskType, ProactiveMotive, ProactiveMotiveType

logger = logging.getLogger(__name__)


class ProactiveOrchestrator:
    def __init__(self, engine, task_store: ConversationTaskStore):
        self.engine = engine
        self.config = engine.config
        self.task_store = task_store

    async def tick(self, now: datetime | None = None) -> bool:
        now = now or datetime.now()
        if not self.config.continuity_enabled:
            return False
        motive = self._select_motive(now)
        if motive is None:
            return False
        sent = await self.engine.send_contextual_proactive_message(motive)
        if sent and motive.task:
            self.task_store.mark_completed(motive.task.id, completed_at=now)
        return bool(sent)

    def _select_motive(self, now: datetime) -> ProactiveMotive | None:
        candidates = self._due_task_motives(now)
        topic = self._topic_continuation_motive(now)
        if topic:
            candidates.append(topic)
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: (-item.priority, item.task.due_at if item.task else now))[0]

    def _due_task_motives(self, now: datetime) -> list[ProactiveMotive]:
        motives: list[ProactiveMotive] = []
        if self.task_store is None:
            return motives
        for task in self.task_store.list_due(self.engine.bot_id, now=now, limit=10):
            if task.type == ConversationTaskType.DEFERRED_REPLY and not self.config.deferred_reply_enabled:
                continue
            motive_type = ProactiveMotiveType(task.type.value)
            motives.append(
                ProactiveMotive(
                    type=motive_type,
                    priority=task.priority,
                    reason=self._reason_for_task(task),
                    prompt_context=self._context_for_task(task),
                    task=task,
                    target=task.target,
                    bypass_idle_threshold=(
                        task.type == ConversationTaskType.DEFERRED_REPLY
                        and self.config.deferred_reply_bypass_idle_threshold
                    ),
                )
            )
        return motives

    def _topic_continuation_motive(self, now: datetime) -> ProactiveMotive | None:
        if not getattr(self.config, "topic_continuation_enabled", False):
            return None

        state = getattr(self.engine, "state", None)
        if state is not None:
            today_count = getattr(state, "today_proactive_count", 0)
            max_daily = getattr(self.config, "max_daily", 5)
            if today_count >= max_daily:
                return None
            if hasattr(state, "is_cooldown_active") and state.is_cooldown_active("idle_reminder"):
                return None
            last_message_time = getattr(state, "last_message_time", None)
            if last_message_time is not None:
                idle_minutes = (now - last_message_time).total_seconds() / 60
                if idle_minutes < getattr(self.config, "topic_continuation_idle_after_minutes", 45):
                    return None

        memory = getattr(self.engine, "memory", None)
        working = getattr(memory, "working", None)
        if working is None:
            return None

        current_session = getattr(working, "current_session", None)
        try:
            recent = working.get_recent(session_id=current_session, turns=3)
        except TypeError:
            recent = working.get_recent(current_session, turns=3)
        if not recent:
            return None

        latest = self._latest_unresolved_topic(recent)
        if latest is None:
            return None
        text, score = latest
        if score < float(getattr(self.config, "topic_continuation_min_score", 0.55)):
            return None

        prompt_context = (
            "最近对话里还有未完成的话题，适合接着聊：\n"
            f"{text}"
        )
        return ProactiveMotive(
            type=ProactiveMotiveType.TOPIC_CONTINUATION,
            priority=70,
            reason="接上之前未完成的话题",
            prompt_context=prompt_context,
        )

    def _latest_unresolved_topic(self, recent: list[dict[str, Any]]) -> tuple[str, float] | None:
        if not recent:
            return None

        reversed_lines: list[str] = []
        unresolved_score = 0.0
        unresolved_markers = ("吗", "？", "?", "怎么看", "怎么办", "要不要", "该不该", "继续", "选择", "项目", "计划", "想法")

        for message in reversed(recent):
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "")
            content = str(message.get("content") or "").strip()
            if not content:
                continue
            reversed_lines.append(f"{role}：{content}")
            if role == "user" and any(marker in content for marker in unresolved_markers):
                unresolved_score += 0.4
            if role == "assistant" and any(marker in content for marker in ("我想", "我们可以", "之后", "再说", "可以", "有点想")):
                unresolved_score += 0.3

        if not reversed_lines:
            return None

        text = "\n".join(reversed_lines)
        if not any(marker in text for marker in unresolved_markers):
            return None

        unresolved_score = min(1.0, unresolved_score + 0.3)
        return text, unresolved_score

    def _reason_for_task(self, task: ConversationTask) -> str:
        if task.type == ConversationTaskType.DEFERRED_REPLY:
            return "继续刚才承诺的稍后回复"
        if task.type == ConversationTaskType.TOPIC_CONTINUATION:
            return "接上之前未完成的话题"
        if task.type == ConversationTaskType.EMOTION_FOLLOWUP:
            return "关心用户之前提到的情绪状态"
        return "继续之前的对话"

    def _context_for_task(self, task: ConversationTask) -> str:
        return (
            f"上一段话题摘要：{task.topic_summary}\n"
            f"用户当时说：{task.source_user_message}\n"
            f"Bot 当时说：{task.source_bot_message}\n"
            f"平台：{task.platform}\n"
            f"会话：{task.session_id}"
        )
