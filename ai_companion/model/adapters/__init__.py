"""
模型适配器包

提供统一的模型接口，支持多种 Provider:
- minimax: MiniMax M2.7
- openai: OpenAI GPT 系列
- claude: Anthropic Claude 系列
- mimo: Xiaomi MiMo 大模型
- tele: TeleClaw GLM-5 Turbo
- ollama: Ollama 本地模型
- custom: 自定义 HTTP API
"""

from .base import ModelAdapter
from .minimax_adapter import MiniMaxAdapter
from .openai_adapter import OpenAIAdapter
from .claude_adapter import ClaudeAdapter
from .mimo_adapter import MimoAdapter
from .tele_adapter import TeleAdapter
from .ollama_adapter import OllamaAdapter
from .custom_adapter import CustomAdapter

__all__ = [
    "ModelAdapter",
    "MiniMaxAdapter",
    "OpenAIAdapter",
    "ClaudeAdapter",
    "MimoAdapter",
    "TeleAdapter",
    "OllamaAdapter",
    "CustomAdapter",
]
