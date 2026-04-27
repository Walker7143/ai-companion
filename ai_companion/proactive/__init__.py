"""
主动唤醒模块 - Proactive Wake-up System

支持：
- LLM 推理判断是否应该主动联系
- LLM 生成符合人格的主动消息
- 可配置触发条件（长时间不联系 / 情绪触发）
- 限流、冷却、生气降级
- 多平台支持（CLI / 飞书 / Webhook）
- 每个 Bot 独立调度
"""

from .config import ProactiveConfig
from .state import ProactiveState
from .engine import ProactiveEngine, ProactiveDecision
from .scheduler import ProactiveScheduler
from .platform import ProactivePlatform, CLIPlatform, FeishuPlatform, WebhookPlatform, create_platform
from .life_config import LifeConfig
from .life_state import LifeEvent, MajorLifeEvent, LifeState
from .life_engine import LifeEngine
from .life_scheduler import LifeScheduler

__all__ = [
    "ProactiveConfig",
    "ProactiveState",
    "ProactiveEngine",
    "ProactiveDecision",
    "ProactiveScheduler",
    "ProactivePlatform",
    "CLIPlatform",
    "FeishuPlatform",
    "WebhookPlatform",
    "create_platform",
    "LifeConfig",
    "LifeEvent",
    "MajorLifeEvent",
    "LifeState",
    "LifeEngine",
    "LifeScheduler",
]