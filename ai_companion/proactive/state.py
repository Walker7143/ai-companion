"""
ProactiveState - 主动唤醒状态管理（支持持久化）
"""

import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ProactiveState:
    """主动唤醒状态管理"""

    def __init__(self, bot_id: str, data_dir: Path):
        self.bot_id = bot_id
        self.data_dir = Path(data_dir) / bot_id
        self.state_file = self.data_dir / "proactive_state.json"
        self._state = {}
        self.load()

    def load(self):
        """从文件加载状态"""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    self._state = json.load(f)
                # 检查是否需要重置每日计数
                self._check_daily_reset()
                logger.info(f"[ProactiveState] 加载状态: {self.state_file}")
            except Exception as e:
                logger.warning(f"[ProactiveState] 加载状态失败: {e}，使用空状态")
                self._state = self._default_state()
        else:
            self._state = self._default_state()

    def _default_state(self) -> dict:
        return {
            "last_message_time": None,
            "last_proactive_time": None,
            "annoyance_level": 0,
            "today_proactive_count": 0,
            "last_reset_date": date.today().isoformat(),
            "total_proactive_sent": 0,
            "last_emotion_trigger_time": None,
            "cooldowns": {},
        }

    def save(self):
        """保存状态到文件"""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, "w") as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[ProactiveState] 保存状态失败: {e}")

    def _check_daily_reset(self):
        """检查是否需要重置每日计数"""
        today = date.today().isoformat()
        last_reset = self._state.get("last_reset_date")
        if last_reset != today:
            self._state["today_proactive_count"] = 0
            self._state["last_reset_date"] = today
            logger.info(f"[ProactiveState] 每日计数已重置: {today}")

    @property
    def last_message_time(self) -> Optional[datetime]:
        ts = self._state.get("last_message_time")
        return datetime.fromisoformat(ts) if ts else None

    @last_message_time.setter
    def last_message_time(self, value: datetime):
        self._state["last_message_time"] = value.isoformat() if value else None
        self.save()

    @property
    def last_proactive_time(self) -> Optional[datetime]:
        ts = self._state.get("last_proactive_time")
        return datetime.fromisoformat(ts) if ts else None

    @last_proactive_time.setter
    def last_proactive_time(self, value: datetime):
        self._state["last_proactive_time"] = value.isoformat() if value else None
        self.save()

    @property
    def annoyance_level(self) -> int:
        return self._state.get("annoyance_level", 0)

    @annoyance_level.setter
    def annoyance_level(self, value: int):
        self._state["annoyance_level"] = max(0, min(10, value))
        self.save()

    @property
    def today_proactive_count(self) -> int:
        self._check_daily_reset()
        return self._state.get("today_proactive_count", 0)

    @today_proactive_count.setter
    def today_proactive_count(self, value: int):
        self._state["today_proactive_count"] = max(0, value)
        self.save()

    @property
    def total_proactive_sent(self) -> int:
        return self._state.get("total_proactive_sent", 0)

    @total_proactive_sent.setter
    def total_proactive_sent(self, value: int):
        self._state["total_proactive_sent"] = value
        self.save()

    @property
    def last_emotion_trigger_time(self) -> Optional[datetime]:
        ts = self._state.get("last_emotion_trigger_time")
        return datetime.fromisoformat(ts) if ts else None

    @last_emotion_trigger_time.setter
    def last_emotion_trigger_time(self, value: Optional[datetime]):
        self._state["last_emotion_trigger_time"] = value.isoformat() if value else None
        self.save()

    def get_cooldown(self, trigger_name: str) -> Optional[datetime]:
        """获取指定触发器的冷却时间"""
        cooldowns = self._state.get("cooldowns", {})
        ts = cooldowns.get(trigger_name)
        return datetime.fromisoformat(ts) if ts else None

    def set_cooldown(self, trigger_name: str, cooldown_end: datetime):
        """设置触发器冷却时间"""
        cooldowns = self._state.get("cooldowns", {})
        cooldowns[trigger_name] = cooldown_end.isoformat()
        self._state["cooldowns"] = cooldowns
        self.save()

    def clear_cooldown(self, trigger_name: str):
        """清除触发器冷却"""
        cooldowns = self._state.get("cooldowns", {})
        cooldowns.pop(trigger_name, None)
        self._state["cooldowns"] = cooldowns
        self.save()

    def is_cooldown_active(self, trigger_name: str) -> bool:
        """检查触发器是否在冷却中"""
        cooldown_end = self.get_cooldown(trigger_name)
        if cooldown_end is None:
            return False
        return datetime.now() < cooldown_end

    def increment_proactive(self):
        """增加主动消息计数"""
        self._check_daily_reset()
        self._state["today_proactive_count"] = self._state.get("today_proactive_count", 0) + 1
        self._state["total_proactive_sent"] = self._state.get("total_proactive_sent", 0) + 1
        self.last_proactive_time = datetime.now()
        self.save()

    def on_user_message(self):
        """用户发消息时调用：重置生气、记录时间"""
        self.last_message_time = datetime.now()
        # 用户发消息，消气
        self.annoyance_level = max(0, self.annoyance_level - 2)
        self.save()

    def to_dict(self) -> dict:
        return self._state.copy()