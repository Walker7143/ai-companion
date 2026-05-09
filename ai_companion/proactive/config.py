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
            "contact_probability": 0.3,  # 每次检查通过矜持概率
            "force_contact": False,  # 测试用：跳过 LLM 是否联系判断
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
        "conversation_continuity": {
            "enabled": True,
            "deferred_reply": {
                "enabled": True,
                "default_delay_minutes": 8,
                "min_delay_minutes": 2,
                "max_delay_minutes": 60,
                "expires_hours": 24,
                "bypass_idle_threshold": True,
            },
            "topic_continuation": {
                "enabled": True,
                "idle_after_minutes": 45,
                "expires_hours": 12,
                "min_score": 0.55,
            },
            "emotion_followup": {
                "enabled": True,
                "delay_minutes": 20,
                "expires_hours": 24,
            },
            "life_event": {
                "enabled": True,
            },
            "idle_ping": {
                "enabled": True,
            },
        },
        # 黄金时段配置
        "preferred_contact_times": ["09:00-23:00"],
        "timezone": "Asia/Shanghai",
        # 随机触发配置
        "random_trigger_prob": 0.05,  # 5% 概率随机提前
        "random_trigger_min_ratio": 0.5,  # 至少达到 idle_threshold 的 50% 才可能随机触发
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
                content = self.config_path.read_text(encoding="utf-8")
                # 空文件或只有空白字符
                if not content.strip():
                    raise ValueError("文件为空")
                # 尝试 JSON 格式（原生 JSON 兼容 YAML 子集）
                try:
                    loaded = json.loads(content)
                except json.JSONDecodeError:
                    # 尝试 YAML 格式（setup.py 写入的是 YAML）
                    import yaml
                    loaded = yaml.safe_load(content)
                    if loaded is None:
                        raise ValueError("YAML 内容为空")
                loaded = self._normalize_legacy_config(loaded)
                self._config = self._deep_merge(self.DEFAULT_CONFIG, loaded)
                logger.info(f"[ProactiveConfig] 加载配置: {self.config_path}")
            except Exception as e:
                logger.warning(f"[ProactiveConfig] 加载配置失败: {e}，使用默认配置")
                self._config = self.DEFAULT_CONFIG.copy()
                self.save()  # 用默认配置覆盖损坏的文件
        else:
            self._config = self.DEFAULT_CONFIG.copy()
            self.save()  # 创建默认配置

    def _normalize_legacy_config(self, loaded: dict) -> dict:
        """兼容旧版扁平 proactive.json 结构，规范为当前嵌套结构。"""
        if not isinstance(loaded, dict):
            return {}

        cfg = dict(loaded)

        # 兼容旧枚举：idle -> silent
        if cfg.get("mode") == "idle":
            cfg["mode"] = "silent"

        scheduler = cfg.get("scheduler")
        if not isinstance(scheduler, dict):
            scheduler = {}

        flat_scheduler_map = {
            "check_interval_seconds": ("check_interval_seconds", "check_interval"),
            "idle_threshold_hours": ("idle_threshold_hours",),
            "max_daily": ("max_daily",),
            "min_interval_hours": ("min_interval_hours",),
            "max_idle_days": ("max_idle_days",),
        }
        for target_key, aliases in flat_scheduler_map.items():
            if target_key in scheduler:
                continue
            for alias in aliases:
                if alias in cfg and cfg.get(alias) is not None:
                    scheduler[target_key] = cfg.get(alias)
                    break
        cfg["scheduler"] = scheduler

        triggers = cfg.get("triggers")
        if not isinstance(triggers, dict):
            triggers = {}

        idle_reminder = triggers.get("idle_reminder")
        if not isinstance(idle_reminder, dict):
            idle_reminder = {}
        if "enabled" not in idle_reminder and "idle_reminder_enabled" in cfg:
            idle_reminder["enabled"] = cfg.get("idle_reminder_enabled")
        if "idle_hours" not in idle_reminder:
            if cfg.get("idle_reminder_hours") is not None:
                idle_reminder["idle_hours"] = cfg.get("idle_reminder_hours")
            elif cfg.get("idle_threshold_hours") is not None:
                idle_reminder["idle_hours"] = cfg.get("idle_threshold_hours")
        if idle_reminder:
            triggers["idle_reminder"] = idle_reminder

        emotion_trigger = triggers.get("emotion_trigger")
        if not isinstance(emotion_trigger, dict):
            emotion_trigger = {}
        if "enabled" not in emotion_trigger and "emotion_trigger_enabled" in cfg:
            emotion_trigger["enabled"] = cfg.get("emotion_trigger_enabled")
        if "keywords" not in emotion_trigger and cfg.get("emotion_keywords") is not None:
            emotion_trigger["keywords"] = cfg.get("emotion_keywords")
        if "response_delay_minutes" not in emotion_trigger and cfg.get("emotion_response_delay_minutes") is not None:
            emotion_trigger["response_delay_minutes"] = cfg.get("emotion_response_delay_minutes")
        if emotion_trigger:
            triggers["emotion_trigger"] = emotion_trigger
        cfg["triggers"] = triggers

        platform = cfg.get("platform")
        if not isinstance(platform, dict):
            platform = {}
        if "type" not in platform and cfg.get("platform_type"):
            platform["type"] = cfg.get("platform_type")
        if "webhook_url" not in platform and cfg.get("webhook_url") is not None:
            platform["webhook_url"] = cfg.get("webhook_url")
        cfg["platform"] = platform

        return cfg

    def save(self):
        """保存配置到文件"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
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
    def min_interval_hours(self) -> float:
        return self._config.get("scheduler", {}).get("min_interval_hours", 4)

    @property
    def max_idle_days(self) -> int:
        return self._config.get("scheduler", {}).get("max_idle_days", 7)

    @property
    def contact_probability(self) -> float:
        raw = self._config.get("scheduler", {}).get("contact_probability", 0.3)
        try:
            return max(0.0, min(1.0, float(raw)))
        except (TypeError, ValueError):
            return 0.3

    @property
    def force_contact(self) -> bool:
        return bool(self._config.get("scheduler", {}).get("force_contact", False))

    def _continuity_section(self, *keys: str) -> dict:
        current = self._config.get("conversation_continuity", {})
        for key in keys:
            current = current.get(key, {}) if isinstance(current, dict) else {}
        return current if isinstance(current, dict) else {}

    @property
    def continuity_enabled(self) -> bool:
        return bool(self._continuity_section().get("enabled", True))

    @property
    def deferred_reply_enabled(self) -> bool:
        return bool(self._continuity_section("deferred_reply").get("enabled", True))

    @property
    def deferred_reply_default_delay_minutes(self) -> int:
        return int(self._continuity_section("deferred_reply").get("default_delay_minutes", 8))

    @property
    def deferred_reply_min_delay_minutes(self) -> int:
        return int(self._continuity_section("deferred_reply").get("min_delay_minutes", 2))

    @property
    def deferred_reply_max_delay_minutes(self) -> int:
        return int(self._continuity_section("deferred_reply").get("max_delay_minutes", 60))

    @property
    def deferred_reply_expires_hours(self) -> int:
        return int(self._continuity_section("deferred_reply").get("expires_hours", 24))

    @property
    def deferred_reply_bypass_idle_threshold(self) -> bool:
        return bool(self._continuity_section("deferred_reply").get("bypass_idle_threshold", True))

    @property
    def topic_continuation_enabled(self) -> bool:
        return bool(self._continuity_section("topic_continuation").get("enabled", True))

    @property
    def topic_continuation_idle_after_minutes(self) -> int:
        return int(self._continuity_section("topic_continuation").get("idle_after_minutes", 45))

    @property
    def topic_continuation_expires_hours(self) -> int:
        return int(self._continuity_section("topic_continuation").get("expires_hours", 12))

    @property
    def topic_continuation_min_score(self) -> float:
        return float(self._continuity_section("topic_continuation").get("min_score", 0.55))

    @property
    def emotion_followup_enabled(self) -> bool:
        return bool(self._continuity_section("emotion_followup").get("enabled", True))

    @property
    def emotion_followup_delay_minutes(self) -> int:
        return int(self._continuity_section("emotion_followup").get("delay_minutes", 20))

    @property
    def emotion_followup_expires_hours(self) -> int:
        return int(self._continuity_section("emotion_followup").get("expires_hours", 24))

    @property
    def life_event_motive_enabled(self) -> bool:
        return bool(self._continuity_section("life_event").get("enabled", True))

    @property
    def idle_ping_enabled(self) -> bool:
        return bool(self._continuity_section("idle_ping").get("enabled", True))

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

    @property
    def preferred_contact_times(self) -> list:
        return self._config.get("preferred_contact_times", ["19:00-22:00", "12:00-13:00"])

    @property
    def timezone(self) -> str:
        return self._config.get("timezone", "Asia/Shanghai")

    @property
    def random_trigger_prob(self) -> float:
        return self._config.get("random_trigger_prob", 0.05)

    @property
    def random_trigger_min_ratio(self) -> float:
        return self._config.get("random_trigger_min_ratio", 0.5)

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
