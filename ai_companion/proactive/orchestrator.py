from __future__ import annotations

import logging
from datetime import datetime

from ..temporal_guard import build_local_time_context, is_event_visible_at_current_time
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
        if not self._is_continuity_active():
            return False
        if self.task_store is not None:
            self.task_store.expire_overdue(now)
        motive = self._select_motive(now)
        if motive is None:
            return False
        if not self._can_dispatch(motive, now):
            return False
        sent = await self.engine.send_contextual_proactive_message(motive)
        if sent and motive.task:
            self.task_store.mark_completed(motive.task.id, completed_at=now)
        if sent and motive.type == ProactiveMotiveType.LIFE_EVENT:
            self._mark_life_event_shared(motive, now)
        return bool(sent)

    def _select_motive(self, now: datetime) -> ProactiveMotive | None:
        candidates = self._due_task_motives(now)
        life = self._life_event_motive(now)
        if life:
            candidates.append(life)
        idle_ping = self._idle_ping_motive(now)
        if idle_ping:
            candidates.append(idle_ping)
        idle_reminder = self._idle_reminder_motive(now)
        if idle_reminder:
            candidates.append(idle_reminder)
        if not candidates:
            return None
        return sorted(candidates, key=lambda m: (-m.priority, m.task.due_at if m.task else now))[0]

    def _is_continuity_active(self) -> bool:
        return bool(getattr(self.config, "continuity_enabled", True)) and bool(
            getattr(self.config, "is_active", True)
        )

    def _can_dispatch(self, motive: ProactiveMotive, now: datetime) -> bool:
        if not getattr(self.config, "is_active", True):
            logger.debug("[ProactiveOrchestrator] 跳过主动 motive：Bot 非 active 模式")
            return False

        state = getattr(self.engine, "state", None)
        if state is not None:
            annoyance_level = self._safe_int(getattr(state, "annoyance_level", 0), default=0)
            if annoyance_level >= 9:
                logger.info("[ProactiveOrchestrator] 跳过主动 motive：用户反感度过高")
                return False

            max_daily = self._safe_int(getattr(self.config, "max_daily", 5), default=5)
            today_count = self._safe_int(getattr(state, "today_proactive_count", 0), default=0)
            if today_count >= max_daily:
                logger.info(
                    "[ProactiveOrchestrator] 跳过主动 motive：已达每日上限 type=%s count=%s max=%s",
                    self._motive_type_value(motive),
                    today_count,
                    max_daily,
                )
                return False

            if self._is_cooldown_active(state, now):
                logger.info(
                    "[ProactiveOrchestrator] 跳过主动 motive：仍在最小间隔冷却中 type=%s",
                    self._motive_type_value(motive),
                )
                return False

        if not self._is_preferred_contact_time(now):
            logger.info(
                "[ProactiveOrchestrator] 跳过主动 motive：不在可主动联系时段 type=%s",
                self._motive_type_value(motive),
            )
            return False

        return True

    def _is_cooldown_active(self, state, now: datetime) -> bool:
        min_interval_hours = self._safe_float(getattr(self.config, "min_interval_hours", 0.0), default=0.0)
        if min_interval_hours <= 0:
            return False

        if hasattr(state, "get_cooldown"):
            cooldown_end = state.get_cooldown("idle_reminder")
            if cooldown_end is None:
                return False
            cooldown_end = self._parse_datetime(cooldown_end)
            if cooldown_end is None:
                return False
            return self._datetime_lt(now, cooldown_end)

        if hasattr(state, "is_cooldown_active"):
            return bool(state.is_cooldown_active("idle_reminder"))

        return False

    def _is_preferred_contact_time(self, now: datetime) -> bool:
        preferred_times = getattr(self.config, "preferred_contact_times", None)
        if not preferred_times:
            return True

        current_minute = now.hour * 60 + now.minute
        saw_valid_range = False
        for time_range in preferred_times:
            parsed = self._parse_time_range(str(time_range))
            if parsed is None:
                continue
            saw_valid_range = True
            start_minute, end_minute = parsed
            if self._minute_in_range(current_minute, start_minute, end_minute):
                return True

        if not saw_valid_range:
            logger.warning("[ProactiveOrchestrator] preferred_contact_times 无有效时段，放行主动 motive")
            return True
        return False

    def _parse_time_range(self, value: str) -> tuple[int, int] | None:
        if "-" not in value:
            return None
        start_raw, end_raw = value.split("-", 1)
        start = self._parse_clock_minute(start_raw)
        end = self._parse_clock_minute(end_raw)
        if start is None or end is None:
            return None
        return start, end

    def _parse_clock_minute(self, value: str) -> int | None:
        parts = str(value or "").strip().split(":")
        if not parts or len(parts) > 2:
            return None
        try:
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) == 2 else 0
        except ValueError:
            return None
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        return hour * 60 + minute

    def _minute_in_range(self, current: int, start: int, end: int) -> bool:
        if start == end:
            return True
        if start < end:
            return start <= current <= end
        return current >= start or current <= end

    def _parse_datetime(self, value) -> datetime | None:
        if value is None or isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None

    def _datetime_lt(self, left: datetime, right: datetime) -> bool:
        try:
            return left < right
        except TypeError:
            return left.replace(tzinfo=None) < right.replace(tzinfo=None)

    def _safe_int(self, value, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _safe_float(self, value, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _motive_type_value(self, motive: ProactiveMotive) -> str:
        return str(getattr(getattr(motive, "type", None), "value", getattr(motive, "type", "")))

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
            status = life_engine.get_status() if hasattr(life_engine, "get_status") else build_local_time_context(now)
            visible_events = [
                event for event in life_engine.state.get_recent_shareable_events(limit=10)
                if is_event_visible_at_current_time(event, status)
            ]
        except Exception:
            return None
        if not visible_events:
            return None
        event = visible_events[-1]
        prompt_context = self._context_for_life_event(event)
        return ProactiveMotive(
            type=ProactiveMotiveType.LIFE_EVENT,
            priority=60,
            reason="想把今天发生的一件小事随手讲给对方听",
            prompt_context=prompt_context,
            metadata={"life_event_id": event.id},
        )

    def _idle_ping_motive(self, now: datetime) -> ProactiveMotive | None:
        if not getattr(self.config, "idle_ping_enabled", False):
            return None
        if not self._idle_hours_reached():
            return None
        scene_anchor_checker = getattr(self.engine, "has_scene_anchor_for_idle_ping", None)
        has_scene_anchor = bool(scene_anchor_checker()) if callable(scene_anchor_checker) else False
        if not has_scene_anchor and getattr(self.config, "idle_ping_requires_scene_anchor", True):
            return None
        if not getattr(self.engine, "can_send_idle_ping_now", lambda _now: True)(now):
            return None
        return ProactiveMotive(
            type=ProactiveMotiveType.IDLE_PING,
            priority=20,
            reason="想轻轻冒个泡，顺着最近的关系温度和现场发一句",
            prompt_context="这是一条轻量陪伴型主动消息。像熟人顺手发来的一句话，不催生活安排，不强行盘问状态。",
        )

    def _idle_reminder_motive(self, now: datetime) -> ProactiveMotive | None:
        if not getattr(self.config, "idle_reminder_enabled", True):
            return None
        if not self._idle_hours_reached():
            return None
        grounded_scene = bool(getattr(self.engine, "has_grounded_idle_reminder_scene", lambda: False)())
        recent_scene_anchor = bool(getattr(self.engine, "has_scene_anchor_for_idle_ping", lambda: False)())
        if not grounded_scene and not recent_scene_anchor:
            return None
        if grounded_scene:
            reason = "最近现场里有明确的作息/安排线索，可以做一条低频兜底提醒"
            prompt_context = "这是一条最后兜底的提醒型主动消息。只有在最近现场已经明确出现作息、吃饭、上班、休息等线索时，才允许轻轻提醒一次。"
        else:
            reason = "虽然最近没有明确作息线索，但刚发生过真实对话，可以发一条低频的承接式问候"
            prompt_context = "这是一条低频兜底的承接型主动消息。最近已经有过真实对话，但没有明确作息安排，不要装作知道对方在做什么，只能顺着最近聊天留下的温度轻轻接一句。"
        return ProactiveMotive(
            type=ProactiveMotiveType.IDLE_REMINDER,
            priority=10,
            reason=reason,
            prompt_context=prompt_context,
        )

    def _idle_hours_reached(self) -> bool:
        calc = getattr(self.engine, "_calc_idle_hours", None)
        if calc is None:
            return False
        try:
            idle_hours = float(calc())
        except Exception:
            return False
        return idle_hours >= float(getattr(self.config, "idle_threshold_hours", 24))

    def _context_for_life_event(self, event) -> str:
        lines = [
            "你准备主动发一条日常小事。",
            f"这件事是你自己刚经历的，不要说成 Bot 状态：{event.description}",
        ]
        topic_prompt = str(getattr(event, "topic_prompt", "") or "").strip()
        if topic_prompt:
            lines.append(f"可以借这个切入口，但不要照抄：{topic_prompt}")
        mood_before = str(getattr(event, "mood_before", "") or "").strip()
        mood_after = str(getattr(event, "mood_after", "") or "").strip()
        if mood_before or mood_after:
            lines.append(f"你的情绪变化：{mood_before or '没特别起伏'} -> {mood_after or '没特别起伏'}")
        mood_tags = getattr(event, "mood_tags", None)
        if isinstance(mood_tags, list) and mood_tags:
            lines.append(f"情绪标签：{'、'.join(str(item) for item in mood_tags[:5])}")
        lines.append("写法：像熟人聊天里突然想起这事，短一点，有你的脾气和口吻；不要总结道理。")
        return "\n".join(lines)

    def _mark_life_event_shared(self, motive: ProactiveMotive, now: datetime) -> None:
        event_id = (motive.metadata or {}).get("life_event_id")
        if not event_id:
            return
        life_engine = getattr(self.engine, "life_engine", None)
        if not life_engine:
            return
        try:
            life_engine.state.mark_event_shared(str(event_id), shared_at=now)
        except Exception as exc:
            logger.warning("[ProactiveOrchestrator] 标记生活事件已分享失败: %s", exc)

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
