"""
Skill - 技能基类

所有技能必须继承 Skill 基类，实现 execute 方法。
技能可以声明自己的能力（capabilities），供调度器判断是否可用。
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class SkillContext:
    """技能执行上下文"""
    bot_id: str
    user_id: str
    conversation_history: list[dict]
    personality_tags: list[str]
    relationship_level: int = 5


@dataclass
class SkillResult:
    """技能执行结果"""
    success: bool
    content: Any = None  # 图片路径、音频路径、文字等
    content_type: str = "text"  # "text", "image", "voice", "video", "card"
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class Skill(ABC):
    """技能基类"""

    name: str = ""
    description: str = ""
    capabilities: list[str] = []  # 如 ["image_generation", "tts"]

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self.default_model = self.config.get("default_model", "")

    @abstractmethod
    async def execute(self, params: dict, context: SkillContext) -> SkillResult:
        """执行技能，返回结果"""
        pass

    def is_available(self) -> bool:
        """技能是否可用（已启用且配置正确）"""
        return self.enabled and self._check_config()

    def _check_config(self) -> bool:
        """检查配置是否完整（子类可重写）"""
        return True

    def get_capabilities(self) -> list[str]:
        """返回此技能支持的能力列表"""
        return self.capabilities


@dataclass
class SkillInfo:
    """技能信息"""
    name: str
    description: str
    capabilities: list[str]
    is_available: bool
    default_model: str
    supported_models: list[str]