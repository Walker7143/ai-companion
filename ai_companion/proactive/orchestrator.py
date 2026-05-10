from __future__ import annotations

import logging
from datetime import datetime

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
        self.task_store.expire_overdue(now)
        motive = self._select_motive(now)
        if motive is None:
            return False
        sent = await self.engine.send_contextual_proactive_message(motive)
        if sent and motive.task:
            self.task_store.mark_completed(motive.task.id, completed_at=now)
        return bool(sent)

    def _select_motive(self, now: datetime) -> ProactiveMotive | None:
        candidates = self._due_task_motives(now)
        life = self._life_event_motive(now)
        if life:
            candidates.append(life)
        if not candidates:
            return None
        return sorted(candidates, key=lambda m: (-m.priority, m.task.due_at if m.task else now))[0]

    def _due_task_motives(self, now: datetime) -> list[ProactiveMotive]:
        motives: list[ProactiveMotive] = []
        if self.task_store is None:
            return motives
        for task in self.task_store.list_due(self.engine.bot_id, now=now, limit=10):
            if task.type == ConversationTaskType.DEFERRED_REPLY and not self.config.deferred_reply_enabled:
                continue
            if task.type == ConversationTaskType.TOPIC_CONTINUATION and not self.config.topic_continuation_enabled:
                continue
            if task.type == ConversationTaskType.EMOTION_FOLLOWUP and not self.config.emotion_followup_enabled:
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

    def _life_event_motive(self, now: datetime) -> ProactiveMotive | None:
        if not getattr(self.config, "life_event_motive_enabled", False):
            return None
        life_engine = getattr(self.engine, "life_engine", None)
        if not life_engine:
            return None
        try:
            life_engine.state.load()
            events = life_engine.state.get_recent_shareable_events(limit=1)
        except Exception:
            return None
        if not events:
            return None
        event = events[0]
        prompt_context = f"Bot 最近发生了一件事想分享：{event.description}"
        if getattr(event, "topic_prompt", None):
            prompt_context += f"\n可以这样提起：{event.topic_prompt}"
        return ProactiveMotive(
            type=ProactiveMotiveType.LIFE_EVENT,
            priority=60,
            reason="想分享最近发生的事",
            prompt_context=prompt_context,
        )

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
