"""
Skill 模块 - 技能系统

支持图片生成、语音合成、语音识别等多媒体技能。
配合 Channel 系统实现多模态消息发送。
"""

from .base import Skill, SkillContext, SkillResult, SkillInfo
from .dispatcher import SkillDispatcher
from .image_generation import ImageGenerationSkill
from .image_understanding import ImageUnderstandingSkill
from .tts import TTSSkill
from .builtin_manager import BuiltinSkillManager
from .auto_router import AutoSkillRouter, AutoSkillRouteResult
from .channel import (
    Channel,
    ChannelCapability,
    CLIChannel,
    FeishuChannel,
    WebhookChannel,
    create_channel,
)
from .multimodal import MultimodalSender

__all__ = [
    "Skill",
    "SkillContext",
    "SkillResult",
    "SkillInfo",
    "SkillDispatcher",
    "ImageGenerationSkill",
    "ImageUnderstandingSkill",
    "TTSSkill",
    "BuiltinSkillManager",
    "AutoSkillRouter",
    "AutoSkillRouteResult",
    "Channel",
    "ChannelCapability",
    "CLIChannel",
    "FeishuChannel",
    "WebhookChannel",
    "create_channel",
    "MultimodalSender",
]
