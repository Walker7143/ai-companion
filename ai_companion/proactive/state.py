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
                with open(self.state_file, encoding="utf-8") as f:
                    self._state = json.load(f)
                # 合并新字段（确保新版本添加的字段有默认值）
                defaults = self._default_state()
                for key, value in defaults.items():
                    if key not in self._state:
                        self._state[key] = value
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
            "last_opening_style": "",  # 开场白 rotation
            # 多维情绪模型
            "miss_level": 5,              # 想念程度 0-10
            "insecurity_level": 3,        # 不安全感 0-10
            "excitement_level": 3,        # 兴奋度 0-10
            # 未回复追踪
            "last_user_reply_time": None,  # 用户最后回复时间
            "unreplied_count": 0,         # 未回复消息数
            # 用户习惯学习
            "user_active_hours": {},       # {"20": 5, "21": 3, ...}
            # 冷落后重新激活
            "previous_absence_days": 0,    # 上次冷落天数（用于判断是否假不在意）
            "just_reactivated": False,     # 是否刚重新激活（需要表现冷淡）
        }

    def save(self):
        """保存状态到文件"""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
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
    def last_opening_style(self) -> str:
        return str(self._state.get("last_opening_style", "") or "")

    @last_opening_style.setter
    def last_opening_style(self, value: str):
        self._state["last_opening_style"] = str(value or "")
        self.save()

    @property
    def last_emotion_trigger_time(self) -> Optional[datetime]:
        ts = self._state.get("last_emotion_trigger_time")
        return datetime.fromisoformat(ts) if ts else None

    @last_emotion_trigger_time.setter
    def last_emotion_trigger_time(self, value: Optional[datetime]):
        self._state["last_emotion_trigger_time"] = value.isoformat() if value else None
        self.save()

    # 多维情绪属性
    @property
    def miss_level(self) -> int:
        return self._state.get("miss_level", 5)

    @miss_level.setter
    def miss_level(self, value: int):
        self._state["miss_level"] = max(0, min(10, value))
        self.save()

    @property
    def insecurity_level(self) -> int:
        return self._state.get("insecurity_level", 3)

    @insecurity_level.setter
    def insecurity_level(self, value: int):
        self._state["insecurity_level"] = max(0, min(10, value))
        self.save()

    @property
    def excitement_level(self) -> int:
        return self._state.get("excitement_level", 3)

    @excitement_level.setter
    def excitement_level(self, value: int):
        self._state["excitement_level"] = max(0, min(10, value))
        self.save()

    # 未回复追踪属性
    @property
    def last_user_reply_time(self) -> Optional[datetime]:
        ts = self._state.get("last_user_reply_time")
        return datetime.fromisoformat(ts) if ts else None

    @last_user_reply_time.setter
    def last_user_reply_time(self, value: Optional[datetime]):
        self._state["last_user_reply_time"] = value.isoformat() if value else None
        self.save()

    @property
    def unreplied_count(self) -> int:
        return self._state.get("unreplied_count", 0)

    @unreplied_count.setter
    def unreplied_count(self, value: int):
        self._state["unreplied_count"] = max(0, value)
        self.save()

    # 用户习惯属性
    @property
    def user_active_hours(self) -> dict:
        return self._state.get("user_active_hours", {})

    @user_active_hours.setter
    def user_active_hours(self, value: dict):
        self._state["user_active_hours"] = value
        self.save()

    # 冷落后重新激活属性
    @property
    def previous_absence_days(self) -> int:
        return self._state.get("previous_absence_days", 0)

    @previous_absence_days.setter
    def previous_absence_days(self, value: int):
        self._state["previous_absence_days"] = max(0, value)
        self.save()

    @property
    def just_reactivated(self) -> bool:
        return self._state.get("just_reactivated", False)

    @just_reactivated.setter
    def just_reactivated(self, value: bool):
        self._state["just_reactivated"] = bool(value)
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

    def decrement_cooldown(self, trigger_name: str, hours: float = 1):
        """缩短触发器冷却时间"""
        cooldown_end = self.get_cooldown(trigger_name)
        if cooldown_end is None:
            return
        # 提前冷却结束时间
        from datetime import timedelta
        new_end = cooldown_end - timedelta(hours=hours)
        if new_end <= datetime.now():
            self.clear_cooldown(trigger_name)
        else:
            cooldowns = self._state.get("cooldowns", {})
            cooldowns[trigger_name] = new_end.isoformat()
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
        """用户发消息时调用：重置生气、记录时间、处理冷落后重新激活"""
        self.last_message_time = datetime.now()

        # 计算上次主动发消息后过了多久（冷落时长）
        if self.last_proactive_time:
            absence = datetime.now() - self.last_proactive_time
            absence_days = absence.total_seconds() / 86400  # 转换为天
        else:
            absence_days = 0

        # 用户发消息，消气
        self.annoyance_level = max(0, self.annoyance_level - 2)
        # 想念程度下降
        self.miss_level = max(0, self.miss_level - 3)

        # 处理冷落后重新激活
        if absence_days > 7:
            # 超过7天没联系，现在用户回复了
            self.previous_absence_days = int(absence_days)
            self.just_reactivated = True
            # 重置不安全感（用户回复了，安心一些）
            self.insecurity_level = max(0, self.insecurity_level - 3)
        else:
            # 正常回复
            self.just_reactivated = False

        # 更新最后回复时间
        self.last_user_reply_time = datetime.now()

        self.save()

    def record_user_activity(self):
        """记录用户活跃时间（用于学习用户习惯）"""
        hour = datetime.now().hour
        hours = self._state.get("user_active_hours", {})
        hours[str(hour)] = hours.get(str(hour), 0) + 1
        self._state["user_active_hours"] = hours
        self.save()

    def to_dict(self) -> dict:
        return self._state.copy()
