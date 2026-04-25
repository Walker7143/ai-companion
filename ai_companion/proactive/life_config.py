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

DEFAULT_CONFIG = {
    "daily_interval_seconds": 3600,      # 1h Bot 时间（秒）
    "major_interval_seconds": 21600,    # 6h Bot 时间（秒）
    "time_ratio": 1,                    # 默认 1:1
    "time_ratio_warning_threshold": 500,
    "max_events": 20,
    "max_context_bits": 2000,
}


@dataclass
class LifeConfig:
    """Bot 人生轨迹配置"""
    daily_interval_seconds: int = 3600
    major_interval_seconds: int = 21600
    time_ratio: int = 1
    time_ratio_warning_threshold: int = 500
    max_events: int = 20
    max_context_bits: int = 2000

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
                with open(self._config_path) as f:
                    self._config = self._deep_merge(DEFAULT_CONFIG.copy(), json.load(f))
                logger.info(f"[LifeConfig] 加载配置: {self._config_path}")

                # 应用配置到字段
                self.daily_interval_seconds = self._config.get("daily_interval_seconds", 3600)
                self.major_interval_seconds = self._config.get("major_interval_seconds", 21600)
                self.time_ratio = self._config.get("time_ratio", 1)
                self.time_ratio_warning_threshold = self._config.get("time_ratio_warning_threshold", 500)
                self.max_events = self._config.get("max_events", 20)
                self.max_context_bits = self._config.get("max_context_bits", 2000)

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
            with open(self._config_path, "w") as f:
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
        """检查日常事件是否到期"""
        if last_tick is None:
            return True
        elapsed = (datetime.now() - last_tick).total_seconds()
        return elapsed >= self.daily_interval

    def is_major_due(self, last_tick: Optional[datetime]) -> bool:
        """检查人生大事是否到期"""
        if last_tick is None:
            return True
        elapsed = (datetime.now() - last_tick).total_seconds()
        return elapsed >= self.major_interval
