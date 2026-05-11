"""
LifeState - Bot 人生轨迹状态管理（支持持久化）

Bot 的人生事件分为两类：
- 日常小事（LifeEvent）：保存在 life_events 列表中，可遗忘
- 人生大事（MajorLifeEvent）：永久保存，更新到人格文件
"""

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict, fields
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger(__name__)

MAX_DAILY_LIFE_EVENTS = 100


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
    scenario_key: str = ""
    scenario_category: str = ""
    source: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LifeEvent":
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in allowed})


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
            "life_journal": [],
            "scenario_history": {},
            "major_scenario_history": {},
            "bot_mood": "平静",
            "bot_current_activity": "在家休息",
            "bot_age_days": 0,
            "last_daily_tick": None,
            "last_major_tick": None,
            "last_daily_event_date": None,
            "last_major_event_date": None,
            "last_major_probability_check_date": None,
            "last_unexpected_event_date": None,
            # 季节和日期系统
            "current_season": "春",
            "current_month": 1,
            "birthday_month": 1,
            "birth_date": None,
            "current_date": None,
            "day_of_week": "周一",
            "year": 2024,
            "is_weekend": False,
            # 里程碑系统
            "last_checked_age": 0,
            "triggered_milestones": [],
            # 内部状态
            "_initial_age": None,
        }

    def load(self):
        """从文件加载状态"""
        if self.state_file.exists():
            try:
                with open(self.state_file, encoding="utf-8") as f:
                    self._state = json.load(f)
                if self._enforce_life_events_hard_limit():
                    self.save()
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
        self._enforce_life_events_hard_limit()
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

    @property
    def last_daily_event_date(self) -> Optional[str]:
        return self._state.get("last_daily_event_date")

    @last_daily_event_date.setter
    def last_daily_event_date(self, value: Optional[str]):
        self._state["last_daily_event_date"] = value
        self.save()

    @property
    def last_major_event_date(self) -> Optional[str]:
        return self._state.get("last_major_event_date")

    @last_major_event_date.setter
    def last_major_event_date(self, value: Optional[str]):
        self._state["last_major_event_date"] = value
        self.save()

    @property
    def last_major_probability_check_date(self) -> Optional[str]:
        return self._state.get("last_major_probability_check_date")

    @last_major_probability_check_date.setter
    def last_major_probability_check_date(self, value: Optional[str]):
        self._state["last_major_probability_check_date"] = value
        self.save()

    @property
    def last_unexpected_event_date(self) -> Optional[str]:
        return self._state.get("last_unexpected_event_date")

    @last_unexpected_event_date.setter
    def last_unexpected_event_date(self, value: Optional[str]):
        self._state["last_unexpected_event_date"] = value
        self.save()

    @property
    def current_season(self) -> str:
        return self._state.get("current_season", "春")

    @current_season.setter
    def current_season(self, value: str):
        self._state["current_season"] = value
        self.save()

    @property
    def current_month(self) -> int:
        return self._state.get("current_month", 1)

    @current_month.setter
    def current_month(self, value: int):
        self._state["current_month"] = value
        self.save()

    @property
    def birthday_month(self) -> int:
        return self._state.get("birthday_month", 1)

    @birthday_month.setter
    def birthday_month(self, value: int):
        self._state["birthday_month"] = value
        self.save()

    @property
    def birth_date(self) -> Optional[str]:
        return self._state.get("birth_date")

    @birth_date.setter
    def birth_date(self, value: Optional[str]):
        self._state["birth_date"] = value
        self.save()

    @property
    def current_date(self) -> Optional[str]:
        return self._state.get("current_date")

    @current_date.setter
    def current_date(self, value: Optional[str]):
        self._state["current_date"] = value
        self.save()

    @property
    def day_of_week(self) -> str:
        return self._state.get("day_of_week", "周一")

    @day_of_week.setter
    def day_of_week(self, value: str):
        self._state["day_of_week"] = value
        self.save()

    @property
    def year(self) -> int:
        return self._state.get("year", 2024)

    @year.setter
    def year(self, value: int):
        self._state["year"] = value
        self.save()

    @property
    def is_weekend(self) -> bool:
        return self._state.get("is_weekend", False)

    @is_weekend.setter
    def is_weekend(self, value: bool):
        self._state["is_weekend"] = value
        self.save()

    @property
    def last_checked_age(self) -> int:
        return self._state.get("last_checked_age", 0)

    @last_checked_age.setter
    def last_checked_age(self, value: int):
        self._state["last_checked_age"] = value
        self.save()

    @property
    def triggered_milestones(self) -> list:
        return self._state.get("triggered_milestones", [])

    @triggered_milestones.setter
    def triggered_milestones(self, value: list):
        self._state["triggered_milestones"] = value
        self.save()

    @property
    def initial_age(self) -> Optional[int]:
        return self._state.get("_initial_age")

    @initial_age.setter
    def initial_age(self, value: Optional[int]):
        self._state["_initial_age"] = value
        self.save()

    def add_event(self, event: LifeEvent):
        """添加日常事件"""
        events = self._state.get("life_events", [])
        events.append(event.to_dict())
        if len(events) > MAX_DAILY_LIFE_EVENTS:
            del events[:len(events) - MAX_DAILY_LIFE_EVENTS]
        self._state["life_events"] = events
        if self.current_date:
            self._state["last_daily_event_date"] = self.current_date
        self.record_scenario(event.scenario_key, major=False)
        self._append_journal_record(
            record_type="daily_event",
            description=event.description,
            event_id=event.id,
            metadata={
                "importance": event.importance,
                "shareable": event.shareable,
                "mood_before": event.mood_before,
                "mood_after": event.mood_after,
                "scenario_key": event.scenario_key,
                "scenario_category": event.scenario_category,
                "source": event.source,
            },
        )
        self.save()

    def add_major_event(self, event: MajorLifeEvent):
        """添加人生大事"""
        events = self._state.get("major_life_events", [])
        events.append(event.to_dict())
        self._state["major_life_events"] = events
        if self.current_date:
            self._state["last_major_event_date"] = self.current_date
        self.record_scenario(event.scenario_key, major=True)
        self._append_journal_record(
            record_type="major_event",
            description=event.description,
            event_id=event.id,
            metadata={
                "importance": event.importance,
                "mood_before": event.mood_before,
                "mood_after": event.mood_after,
                "mood_tags": event.mood_tags,
                "scenario_key": event.scenario_key,
                "scenario_category": event.scenario_category,
                "source": event.source,
            },
        )
        self.save()

    @property
    def life_journal(self) -> list[dict[str, Any]]:
        return self._state.get("life_journal", [])

    def add_daily_progress_record(
        self,
        date_str: str,
        day_of_week: str,
        is_weekend: bool,
        month: int,
        season: str,
    ):
        description = f"度过了 {date_str}（{day_of_week}）"
        self._append_journal_record(
            record_type="day_passed",
            description=description,
            date_str=date_str,
            metadata={
                "day_of_week": day_of_week,
                "is_weekend": is_weekend,
                "month": month,
                "season": season,
            },
        )
        self.save()

    def _append_journal_record(
        self,
        record_type: str,
        description: str,
        date_str: Optional[str] = None,
        event_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ):
        records = self._state.get("life_journal", [])
        record = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "record_type": record_type,
            "date": date_str or self._state.get("current_date"),
            "description": description,
        }
        if event_id:
            record["event_id"] = event_id
        if metadata:
            record["metadata"] = metadata
        records.append(record)
        self._state["life_journal"] = records

    def days_since_last_daily_event(self, current_date: Optional[str]) -> Optional[int]:
        if not current_date:
            return None
        last_date = self._state.get("last_daily_event_date")
        if not last_date:
            return None
        try:
            current = date.fromisoformat(current_date)
            last = date.fromisoformat(last_date)
            return (current - last).days
        except ValueError:
            return None

    def _scenario_history_key(self, major: bool = False) -> str:
        return "major_scenario_history" if major else "scenario_history"

    def get_scenario_history(self, major: bool = False) -> dict:
        key = self._scenario_history_key(major)
        value = self._state.get(key)
        if not isinstance(value, dict):
            value = {}
            self._state[key] = value
        return value

    def record_scenario(self, scenario_key: Optional[str], major: bool = False):
        if not scenario_key:
            return
        history = self.get_scenario_history(major=major)
        current = self._state.get("current_date") or datetime.now().strftime("%Y-%m-%d")
        item = history.get(scenario_key, {})
        history[scenario_key] = {
            "last_date": current,
            "count": int(item.get("count", 0)) + 1,
            "last_timestamp": datetime.now().isoformat(),
        }
        self._state[self._scenario_history_key(major)] = history

    def days_since_scenario(self, scenario_key: str, current_date: Optional[str], major: bool = False) -> Optional[int]:
        if not scenario_key or not current_date:
            return None
        item = self.get_scenario_history(major=major).get(scenario_key)
        if not item:
            return None
        last_date = item.get("last_date")
        if not last_date:
            return None
        try:
            current = date.fromisoformat(current_date)
            last = date.fromisoformat(last_date)
            return (current - last).days
        except ValueError:
            return None

    def is_scenario_on_cooldown(
        self,
        scenario_key: str,
        current_date: Optional[str],
        cooldown_days: int,
        major: bool = False,
    ) -> bool:
        if not scenario_key or cooldown_days <= 0:
            return False
        gap_days = self.days_since_scenario(scenario_key, current_date, major=major)
        return gap_days is not None and gap_days < cooldown_days

    def prune_events(self, max_events: int = 20, max_context_bits: int = 2000):
        """清理低重要性事件，保留最近的事件"""
        try:
            max_events = min(MAX_DAILY_LIFE_EVENTS, max(1, int(max_events)))
        except (TypeError, ValueError):
            max_events = MAX_DAILY_LIFE_EVENTS
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

    def _enforce_life_events_hard_limit(self) -> bool:
        events = self._state.get("life_events", [])
        if not isinstance(events, list) or len(events) <= MAX_DAILY_LIFE_EVENTS:
            return False
        self._state["life_events"] = events[-MAX_DAILY_LIFE_EVENTS:]
        return True

    def get_recent_shareable_events(self, limit: int = 2) -> list:
        """获取最近可分享的事件"""
        shareable = [
            e for e in self.life_events
            if e.shareable and not self._event_shared_at(e.id)
        ]
        return shareable[-limit:]

    def mark_event_shared(self, event_id: str, shared_at: Optional[datetime] = None) -> bool:
        """Mark a daily life event as already shared with the user."""
        if not event_id:
            return False
        events = self._state.get("life_events", [])
        for event in events:
            if not isinstance(event, dict) or event.get("id") != event_id:
                continue
            event["shared_at"] = (shared_at or datetime.now()).isoformat()
            self._state["life_events"] = events
            self._append_journal_record(
                record_type="daily_event_shared",
                description=event.get("description", ""),
                event_id=event_id,
                metadata={"scenario_key": event.get("scenario_key")},
            )
            self.save()
            return True
        return False

    def _event_shared_at(self, event_id: str) -> Optional[str]:
        if not event_id:
            return None
        for event in self._state.get("life_events", []):
            if isinstance(event, dict) and event.get("id") == event_id:
                value = event.get("shared_at")
                return str(value) if value else None
        return None

    def to_dict(self) -> dict:
        return self._state.copy()
