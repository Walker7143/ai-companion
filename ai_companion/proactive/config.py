"""
ProactiveConfig - 主动唤醒配置

支持从 persona/proactive.json 加载配置，支持动态修改。
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ProactiveConfig:
    """主动唤醒配置"""

    DEFAULT_CONFIG = {
        "enabled": True,
        "mode": "active",  # "active" | "silent"
        "scheduler": {
            "check_interval_seconds": 600,  # 10分钟
            "idle_threshold_hours": 24,
            "max_daily": 5,
            "min_interval_hours": 4,
            "max_idle_days": 7,
        },
        "triggers": {
            "idle_reminder": {
                "enabled": True,
                "idle_hours": 24,
            },
            "emotion_trigger": {
                "enabled": True,
                "keywords": ["不开心", "难过", "累", "生气", "烦", "郁闷", "沮丧"],
                "response_delay_minutes": 5,
            },
        },
        "platform": {
            "type": "cli",  # "cli" | "feishu" | "webhook"
            "webhook_url": None,
        },
    }

    def __init__(self, persona_dir: Path):
        self.persona_dir = Path(persona_dir)
        self.config_path = self.persona_dir / "proactive.json"
        self._config = None
        self.load()

    def load(self):
        """加载配置文件"""
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    self._config = self._deep_merge(self.DEFAULT_CONFIG, json.load(f))
                logger.info(f"[ProactiveConfig] 加载配置: {self.config_path}")
            except Exception as e:
                logger.warning(f"[ProactiveConfig] 加载配置失败: {e}，使用默认配置")
                self._config = self.DEFAULT_CONFIG.copy()
        else:
            self._config = self.DEFAULT_CONFIG.copy()
            self.save()  # 创建默认配置

    def save(self):
        """保存配置到文件"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w") as f:
                json.dump(self._config, f, ensure_ascii=False, indent=2)
            logger.info(f"[ProactiveConfig] 保存配置: {self.config_path}")
        except Exception as e:
            logger.error(f"[ProactiveConfig] 保存配置失败: {e}")

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
    def enabled(self) -> bool:
        return self._config.get("enabled", True)

    @property
    def mode(self) -> str:
        return self._config.get("mode", "active")

    @property
    def is_active(self) -> bool:
        """Bot 是否处于活跃模式（会主动发消息）"""
        return self.enabled and self.mode == "active"

    @property
    def check_interval(self) -> int:
        return self._config.get("scheduler", {}).get("check_interval_seconds", 600)

    @property
    def idle_threshold_hours(self) -> int:
        return self._config.get("scheduler", {}).get("idle_threshold_hours", 24)

    @property
    def max_daily(self) -> int:
        return self._config.get("scheduler", {}).get("max_daily", 5)

    @property
    def min_interval_hours(self) -> int:
        return self._config.get("scheduler", {}).get("min_interval_hours", 4)

    @property
    def max_idle_days(self) -> int:
        return self._config.get("scheduler", {}).get("max_idle_days", 7)

    @property
    def idle_reminder_enabled(self) -> bool:
        return self._config.get("triggers", {}).get("idle_reminder", {}).get("enabled", True)

    @property
    def idle_reminder_hours(self) -> int:
        return self._config.get("triggers", {}).get("idle_reminder", {}).get("idle_hours", 24)

    @property
    def emotion_trigger_enabled(self) -> bool:
        return self._config.get("triggers", {}).get("emotion_trigger", {}).get("enabled", True)

    @property
    def emotion_keywords(self) -> list:
        return self._config.get("triggers", {}).get("emotion_trigger", {}).get("keywords", [])

    @property
    def emotion_response_delay_minutes(self) -> int:
        return self._config.get("triggers", {}).get("emotion_trigger", {}).get("response_delay_minutes", 5)

    @property
    def platform_type(self) -> str:
        return self._config.get("platform", {}).get("type", "cli")

    @property
    def webhook_url(self) -> Optional[str]:
        return self._config.get("platform", {}).get("webhook_url")

    def update(self, key: str, value):
        """动态更新配置项"""
        keys = key.split(".")
        target = self._config
        for k in keys[:-1]:
            target = target.setdefault(k, {})
        target[keys[-1]] = value
        logger.info(f"[ProactiveConfig] 更新配置: {key} = {value}")

    def to_dict(self) -> dict:
        return self._config.copy()