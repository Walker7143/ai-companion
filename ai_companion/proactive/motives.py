from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ConversationTaskType(str, Enum):
    DEFERRED_REPLY = "deferred_reply"
    TOPIC_CONTINUATION = "topic_continuation"
    EMOTION_FOLLOWUP = "emotion_followup"


class ConversationTaskStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ProactiveMotiveType(str, Enum):
    DEFERRED_REPLY = "deferred_reply"
    TOPIC_CONTINUATION = "topic_continuation"
    EMOTION_FOLLOWUP = "emotion_followup"
    LIFE_EVENT = "life_event"
    IDLE_PING = "idle_ping"
    IDLE_REMINDER = "idle_reminder"


def _parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


@dataclass
class ConversationTask:
    id: str
    bot_id: str
    type: ConversationTaskType
    status: ConversationTaskStatus
    session_id: str
    user_id: str
    platform: str
    target: dict[str, Any]
    created_at: datetime
    due_at: datetime
    expires_at: datetime
    source_user_message: str = ""
    source_bot_message: str = ""
    topic_summary: str = ""
    priority: int = 50
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "type": self.type.value,
            "status": self.status.value,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "platform": self.platform,
            "target": self.target,
            "created_at": self.created_at.isoformat(),
            "due_at": self.due_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "source_user_message": self.source_user_message,
            "source_bot_message": self.source_bot_message,
            "topic_summary": self.topic_summary,
            "priority": self.priority,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationTask":
        return cls(
            id=str(data["id"]),
            bot_id=str(data["bot_id"]),
            type=ConversationTaskType(str(data["type"])),
            status=ConversationTaskStatus(str(data["status"])),
            session_id=str(data.get("session_id") or ""),
            user_id=str(data.get("user_id") or "default_user"),
            platform=str(data.get("platform") or ""),
            target=dict(data.get("target") or {}),
            created_at=_parse_dt(data.get("created_at")) or datetime.now(),
            due_at=_parse_dt(data.get("due_at")) or datetime.now(),
            expires_at=_parse_dt(data.get("expires_at")) or datetime.now(),
            source_user_message=str(data.get("source_user_message") or ""),
            source_bot_message=str(data.get("source_bot_message") or ""),
            topic_summary=str(data.get("topic_summary") or ""),
            priority=int(data.get("priority") or 50),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ProactiveMotive:
    type: ProactiveMotiveType
    priority: int
    reason: str
    prompt_context: str
    task: ConversationTask | None = None
    target: dict[str, Any] | None = None
    bypass_idle_threshold: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
