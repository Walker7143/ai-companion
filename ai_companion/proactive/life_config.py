"""
LifeConfig - Bot 人生轨迹配置

从 persona/life.json 加载配置，支持 time_ratio 加速、周期配置等。
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MAX_DAILY_EVENTS = 100

DEFAULT_CONFIG = {
    "daily_interval_seconds": 3600,      # 1h Bot 时间（秒）
    "major_interval_seconds": 21600,    # 6h Bot 时间（秒）
    "time_ratio": 1,                    # 默认 1:1
    "time_ratio_warning_threshold": 500,
    "daily_event_min_gap_days": 2,      # 至少每 N 天产出 1 个日常事件
    "major_event_fixed_probability": 0.05,  # 每个 Bot 日的大事固定概率（0-1）
    "event_policy": {
        "scenario_cooldown_days": 14,
        "major_scenario_cooldown_days": 180,
        "unexpected_event_probability": 0.01,
        "unexpected_event_cooldown_days": 365,
        "llm_recent_event_limit": 20,
        "llm_forbidden_scenario_limit": 12,
        "disabled_scenarios": [],
        "scenario_weights": {},
        "custom_scenarios": [],
    },
    "max_events": MAX_DAILY_EVENTS,
    "max_context_bits": 2000,
    "season": {
        "hemisphere": "north",         # north | south（南半球季节相反）
        "birthday_month": 1,          # 生日月份，影响季节计算起点
    },
    "milestones": [],                   # 年龄里程碑配置
    "holidays": [                      # 节假日配置
        {"name": "元旦", "month": 1, "day": 1, "type": "法定假日"},
        {"name": "情人节", "month": 2, "day": 14, "type": "西方节日"},
        {"name": "清明节", "month": 4, "day": 5, "type": "传统节日"},
        {"name": "劳动节", "month": 5, "day": 1, "type": "法定假日"},
        {"name": "端午节", "month": 6, "day": 10, "type": "传统节日"},
        {"name": "中秋节", "month": 9, "day": 17, "type": "传统节日"},
        {"name": "国庆节", "month": 10, "day": 1, "type": "法定假日"},
        {"name": "圣诞节", "month": 12, "day": 25, "type": "西方节日"},
    ],
    "birth_date": None,                # Bot 出生日期（YYYY-MM-DD格式）
}


@dataclass
class LifeConfig:
    """Bot 人生轨迹配置"""
    daily_interval_seconds: int = 3600
    major_interval_seconds: int = 21600
    time_ratio: int = 1
    time_ratio_warning_threshold: int = 500
    daily_event_min_gap_days: int = 2
    major_event_fixed_probability: float = 0.05
    scenario_cooldown_days: int = 14
    major_scenario_cooldown_days: int = 180
    unexpected_event_probability: float = 0.01
    unexpected_event_cooldown_days: int = 365
    llm_recent_event_limit: int = 20
    llm_forbidden_scenario_limit: int = 12
    disabled_scenarios: list = field(default_factory=list)
    scenario_weights: dict = field(default_factory=dict)
    custom_scenarios: list = field(default_factory=list)
    max_events: int = MAX_DAILY_EVENTS
    max_context_bits: int = 2000
    season_hemisphere: str = "north"
    season_birthday_month: int = 1
    milestones: list = field(default_factory=list)
    holidays: list = field(default_factory=list)
    birth_date: Optional[str] = None

    # 内部状态
    _persona_dir: Optional[Path] = field(default=None, repr=False)
    _config_path: Optional[Path] = field(default=None, repr=False)
    _config: dict = field(default_factory=dict, repr=False)

    def __post_init__(self):
        if self._persona_dir is not None:
            self._config_path = self._persona_dir / "life.json"

    @property
    def daily_interval(self) -> int:
        """实际每日事件检查间隔（秒），按 time_ratio 缩放"""
        return max(1, self.daily_interval_seconds // max(1, self.time_ratio))

    @property
    def major_interval(self) -> int:
        """实际重大事件检查间隔（秒），按 time_ratio 缩放"""
        return max(1, self.major_interval_seconds // max(1, self.time_ratio))

    def load(self):
        """从文件加载配置"""
        if self._config_path and self._config_path.exists():
            try:
                with open(self._config_path, encoding="utf-8") as f:
                    self._config = self._deep_merge(DEFAULT_CONFIG.copy(), json.load(f))
                logger.info(f"[LifeConfig] 加载配置: {self._config_path}")

                # 应用配置到字段
                self.daily_interval_seconds = self._config.get("daily_interval_seconds", 3600)
                self.major_interval_seconds = self._config.get("major_interval_seconds", 21600)
                self.time_ratio = self._config.get("time_ratio", 1)
                self.time_ratio_warning_threshold = self._config.get("time_ratio_warning_threshold", 500)
                self.daily_event_min_gap_days = max(1, int(self._config.get("daily_event_min_gap_days", 2)))
                self.major_event_fixed_probability = min(
                    1.0,
                    max(0.0, float(self._config.get("major_event_fixed_probability", 0.05))),
                )
                event_policy = self._config.get("event_policy", {})
                self.scenario_cooldown_days = max(0, int(event_policy.get("scenario_cooldown_days", 14)))
                self.major_scenario_cooldown_days = max(0, int(event_policy.get("major_scenario_cooldown_days", 180)))
                self.unexpected_event_probability = min(
                    1.0,
                    max(0.0, float(event_policy.get("unexpected_event_probability", 0.01))),
                )
                self.unexpected_event_cooldown_days = max(0, int(event_policy.get("unexpected_event_cooldown_days", 365)))
                self.llm_recent_event_limit = max(3, int(event_policy.get("llm_recent_event_limit", 20)))
                self.llm_forbidden_scenario_limit = max(0, int(event_policy.get("llm_forbidden_scenario_limit", 12)))
                self.disabled_scenarios = event_policy.get("disabled_scenarios", []) or []
                self.scenario_weights = event_policy.get("scenario_weights", {}) or {}
                self.custom_scenarios = event_policy.get("custom_scenarios", []) or []
                self.max_events = min(
                    MAX_DAILY_EVENTS,
                    max(1, int(self._config.get("max_events", MAX_DAILY_EVENTS))),
                )
                self.max_context_bits = self._config.get("max_context_bits", 2000)

                # 季节配置
                season_cfg = self._config.get("season", {})
                self.season_hemisphere = season_cfg.get("hemisphere", "north")
                self.season_birthday_month = season_cfg.get("birthday_month", 1)

                # 里程碑配置
                self.milestones = self._config.get("milestones", [])

                # 节假日配置
                self.holidays = self._config.get("holidays", DEFAULT_CONFIG["holidays"])

                # 出生日期
                self.birth_date = self._config.get("birth_date")

                # 检查警告阈值
                if self.time_ratio > self.time_ratio_warning_threshold:
                    logger.warning(
                        f"[LifeConfig] time_ratio={self.time_ratio} 较高（>{self.time_ratio_warning_threshold}），"
                        f"可能会影响生成事件的质量。建议不要超过 1000。"
                    )
            except Exception as e:
                logger.warning(f"[LifeConfig] 加载配置失败: {e}，使用默认配置")
                self._config = DEFAULT_CONFIG.copy()
        else:
            self._config = DEFAULT_CONFIG.copy()
            self.save()  # 创建默认配置

    def save(self):
        """保存配置到文件"""
        if not self._config_path:
            return
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, ensure_ascii=False, indent=2)
            logger.info(f"[LifeConfig] 保存配置: {self._config_path}")
        except Exception as e:
            logger.error(f"[LifeConfig] 保存配置失败: {e}")

    def _deep_merge(self, default: dict, override: dict) -> dict:
        """深度合并配置"""
        result = default.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    @property
    def persona_dir(self) -> Optional[Path]:
        return self._persona_dir

    def to_dict(self) -> dict:
        return self._config.copy()

    def is_daily_due(self, last_tick: Optional[datetime]) -> bool:
        """检查日常事件是否到期（Bot 时间 1 天）"""
        if last_tick is None:
            return True
        elapsed = (datetime.now() - last_tick).total_seconds()
        # Bot 时间 1 天 = 86400 秒
        # time_ratio=1: 每 86400 秒触发一次（1:1）
        # time_ratio=24: 每 3600 秒触发一次（24倍速）
        bot_seconds_per_day = 86400
        return elapsed * self.time_ratio >= bot_seconds_per_day

    def is_major_due(self, last_tick: Optional[datetime]) -> bool:
        """检查人生大事是否到期"""
        if last_tick is None:
            return True
        elapsed = (datetime.now() - last_tick).total_seconds()
        return elapsed >= self.major_interval
