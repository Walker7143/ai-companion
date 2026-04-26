"""
LifeState - Bot 人生轨迹状态管理（支持持久化）

Bot 的人生事件分为两类：
- 日常小事（LifeEvent）：保存在 life_events 列表中，可遗忘
- 人生大事（MajorLifeEvent）：永久保存，更新到人格文件
"""

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class LifeEvent:
    """Bot 日常小事"""
    id: str = ""
    timestamp: str = ""  # ISO datetime (Bot 时间)
    description: str = ""
    mood_before: str = ""
    mood_after: str = ""
    importance: float = 0.0  # 0-10
    shareable: bool = False
    topic_prompt: str = ""
    mood_tags: list = field(default_factory=list)
    related_to_user: bool = False
    context_bits: int = 0

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LifeEvent":
        return cls(**data)


@dataclass
class MajorLifeEvent(LifeEvent):
    """Bot 人生大事，会影响人格文件"""

    def to_major_dict(self) -> dict:
        """返回适合 LLM 分析的字典"""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "description": self.description,
            "mood_before": self.mood_before,
            "mood_after": self.mood_after,
            "importance": self.importance,
            "mood_tags": self.mood_tags,
        }


class LifeState:
    """Bot 人生轨迹状态管理"""

    def __init__(self, bot_id: str, data_dir: Path):
        self.bot_id = bot_id
        self.data_dir = Path(data_dir) / bot_id
        self.state_file = self.data_dir / "life_state.json"
        self._state: dict = {}
        self.load()

    def _default_state(self) -> dict:
        return {
            "life_events": [],
            "major_life_events": [],
            "bot_mood": "平静",
            "bot_current_activity": "在家休息",
            "bot_age_days": 0,
            "last_daily_tick": None,
            "last_major_tick": None,
        }

    def load(self):
        """从文件加载状态"""
        if self.state_file.exists():
            try:
                with open(self.state_file, encoding="utf-8") as f:
                    self._state = json.load(f)
                logger.info(f"[LifeState] 加载状态: {self.state_file}")
            except Exception as e:
                logger.warning(f"[LifeState] 加载状态失败: {e}，使用空状态")
                self._state = self._default_state()
        else:
            self._state = self._default_state()

    def save(self):
        """保存状态到文件"""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[LifeState] 保存状态失败: {e}")

    @property
    def life_events(self) -> list:
        return [LifeEvent.from_dict(e) for e in self._state.get("life_events", [])]

    @life_events.setter
    def life_events(self, events: list):
        self._state["life_events"] = [e.to_dict() if isinstance(e, LifeEvent) else e for e in events]
        self.save()

    @property
    def major_life_events(self) -> list:
        return [MajorLifeEvent.from_dict(e) for e in self._state.get("major_life_events", [])]

    @major_life_events.setter
    def major_life_events(self, events: list):
        self._state["major_life_events"] = [e.to_dict() if isinstance(e, (LifeEvent, MajorLifeEvent)) else e for e in events]
        self.save()

    @property
    def bot_mood(self) -> str:
        return self._state.get("bot_mood", "平静")

    @bot_mood.setter
    def bot_mood(self, value: str):
        self._state["bot_mood"] = value
        self.save()

    @property
    def bot_current_activity(self) -> str:
        return self._state.get("bot_current_activity", "在家休息")

    @bot_current_activity.setter
    def bot_current_activity(self, value: str):
        self._state["bot_current_activity"] = value
        self.save()

    @property
    def bot_age_days(self) -> int:
        return self._state.get("bot_age_days", 0)

    @bot_age_days.setter
    def bot_age_days(self, value: int):
        self._state["bot_age_days"] = value
        self.save()

    @property
    def last_daily_tick(self) -> Optional[datetime]:
        ts = self._state.get("last_daily_tick")
        return datetime.fromisoformat(ts) if ts else None

    @last_daily_tick.setter
    def last_daily_tick(self, value: datetime):
        self._state["last_daily_tick"] = value.isoformat() if value else None
        self.save()

    @property
    def last_major_tick(self) -> Optional[datetime]:
        ts = self._state.get("last_major_tick")
        return datetime.fromisoformat(ts) if ts else None

    @last_major_tick.setter
    def last_major_tick(self, value: datetime):
        self._state["last_major_tick"] = value.isoformat() if value else None
        self.save()

    def add_event(self, event: LifeEvent):
        """添加日常事件"""
        events = self._state.get("life_events", [])
        events.append(event.to_dict())
        self._state["life_events"] = events
        self.save()

    def add_major_event(self, event: MajorLifeEvent):
        """添加人生大事"""
        events = self._state.get("major_life_events", [])
        events.append(event.to_dict())
        self._state["major_life_events"] = events
        self.save()

    def prune_events(self, max_events: int = 20, max_context_bits: int = 2000):
        """清理低重要性事件，保留最近的事件"""
        events = self._state.get("life_events", [])

        # 计算总 context bits
        total_bits = sum(len(e.get("description", "")) for e in events)

        # 优先保留最新的事件（按 timestamp 倒序）
        # 保留至少 3 个最新事件
        while len(events) > max_events or total_bits > max_context_bits:
            if len(events) <= 3:
                break
            removed = events.pop(0)
            total_bits -= len(removed.get("description", ""))

        self._state["life_events"] = events
        self.save()

    def get_recent_shareable_events(self, limit: int = 2) -> list:
        """获取最近可分享的事件"""
        shareable = [e for e in self.life_events if e.shareable]
        return shareable[-limit:]

    def to_dict(self) -> dict:
        return self._state.copy()
