"""
MultimodalSender - 多模态主动发送器

协调技能系统和通道能力，按需发送多媒体内容
"""

import logging
from pathlib import Path
from typing import Optional

from .base import SkillContext, SkillResult
from .dispatcher import SkillDispatcher
from .channel import Channel, create_channel

logger = logging.getLogger(__name__)


class MultimodalSender:
    """多模态主动发送器"""

    def __init__(
        self,
        bot_id: str,
        channel: Channel,
        skill_dispatcher: SkillDispatcher = None
    ):
        self.bot_id = bot_id
        self.channel = channel
        self.skill_dispatcher = skill_dispatcher or SkillDispatcher()

    def set_skill_dispatcher(self, dispatcher: SkillDispatcher):
        self.skill_dispatcher = dispatcher

    async def send_proactive(
        self,
        content: str,
        content_type: str = "text",
        skill_name: str = None,
        **kwargs
    ) -> bool:
        """
        发送主动消息（支持多媒体）

        Args:
            content: 消息内容
            content_type: 内容类型 ("text", "image", "voice")
            skill_name: 可选，指定使用的技能
            **kwargs: 额外参数（如 prompt 用于图片生成，text 用于 TTS）

        Returns:
            bool: 发送是否成功
        """
        try:
            # 1. 检查通道能力
            if not self.channel.capability.supports_type(content_type):
                logger.info(f"[MultimodalSender] 通道不支持 {content_type}，降级为 text")
                content_type = "text"

            # 2. 根据内容类型处理
            if content_type == "voice":
                return await self._send_voice(content, skill_name, **kwargs)
            elif content_type == "image":
                return await self._send_image(content, skill_name, **kwargs)
            elif content_type == "text":
                return await self._send_text(content)
            else:
                logger.warning(f"[MultimodalSender] 未知内容类型: {content_type}")
                return await self._send_text(content)

        except Exception as e:
            logger.error(f"[MultimodalSender] 发送失败: {e}")
            return False

    async def _send_text(self, content: str) -> bool:
        """发送文字"""
        return await self.channel.send_text(self.bot_id, content)

    async def _send_image(self, prompt_or_description: str, skill_name: str = None, **kwargs) -> bool:
        """发送图片（生成或直接发送）"""
        # 如果提供了 image_path，直接发送
        image_path = kwargs.get("image_path")
        if image_path and Path(image_path).exists():
            caption = kwargs.get("caption", prompt_or_description)
            return await self.channel.send_image(self.bot_id, image_path, caption)

        # 否则尝试生成图片
        if not self.skill_dispatcher:
            logger.warning("[MultimodalSender] 无技能调度器，无法生成图片")
            return await self._send_text(f"[图片] {prompt_or_description}")

        skill_name = skill_name or "image_generation"
        context = SkillContext(
            bot_id=self.bot_id,
            user_id=kwargs.get("user_id", "unknown"),
            conversation_history=[],
            personality_tags=kwargs.get("personality_tags", []),
        )

        result = await self.skill_dispatcher.execute(
            skill_name,
            {"prompt": prompt_or_description},
            context
        )

        if result.success and result.content:
            return await self.channel.send_image(
                self.bot_id,
                result.content,
                result.metadata.get("caption", prompt_or_description)
            )
        else:
            logger.warning(f"[MultimodalSender] 图片生成失败: {result.content}")
            return await self._send_text(f"[图片生成失败] {prompt_or_description}")

    async def _send_voice(self, text: str, skill_name: str = None, **kwargs) -> bool:
        """发送语音（生成或直接发送）"""
        # 如果提供了 audio_path，直接发送
        audio_path = kwargs.get("audio_path")
        if audio_path and Path(audio_path).exists():
            caption = kwargs.get("caption", text[:50])
            return await self.channel.send_voice(self.bot_id, audio_path, caption)

        # 否则尝试生成语音
        if not self.skill_dispatcher:
            logger.warning("[MultimodalSender] 无技能调度器，无法生成语音")
            return await self._send_text(f"[语音] {text}")

        skill_name = skill_name or "tts"
        context = SkillContext(
            bot_id=self.bot_id,
            user_id=kwargs.get("user_id", "unknown"),
            conversation_history=[],
            personality_tags=kwargs.get("personality_tags", []),
        )

        result = await self.skill_dispatcher.execute(
            skill_name,
            {"text": text, "model": kwargs.get("tts_model", "edge_tts")},
            context
        )

        if result.success and result.content:
            return await self.channel.send_voice(
                self.bot_id,
                result.content,
                result.metadata.get("caption", text[:50])
            )
        else:
            logger.warning(f"[MultimodalSender] 语音生成失败: {result.content}")
            return await self._send_text(f"[语音生成失败] {text}")

    def get_capabilities(self) -> dict:
        """获取通道能力"""
        return {
            "supported_types": self.channel.capability.supported_types,
            "max_message_length": self.channel.capability.max_message_length,
        }