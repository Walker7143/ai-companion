"""
AI Companion 模型模块

提供统一的模型接口和多种模型适配器
"""

from .factory import ModelFactory
from .adapters import (
    ModelAdapter,
    MiniMaxAdapter,
    OpenAIAdapter,
    ClaudeAdapter,
    MimoAdapter,
    OllamaAdapter,
    CustomAdapter,
)

# 向后兼容
from .minimax_adapter import MiniMaxAdapter

__all__ = [
    "ModelFactory",
    "ModelAdapter",
    "MiniMaxAdapter",
    "OpenAIAdapter",
    "ClaudeAdapter",
    "MimoAdapter",
    "OllamaAdapter",
    "CustomAdapter",
]
