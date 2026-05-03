"""
Channel - 通道能力

定义不同平台支持的媒体类型和能力检测
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ChannelCapability:
    """通道能力"""
    supported_types: list[str] = field(default_factory=lambda: ["text"])
    # 支持的类型: text, image, voice, video, card
    max_message_length: int = 4000
    image_formats: list[str] = field(default_factory=lambda: ["png", "jpg", "gif"])
    audio_formats: list[str] = field(default_factory=lambda: ["mp3", "wav", "ogg"])
    video_formats: list[str] = field(default_factory=lambda: ["mp4"])

    def supports_type(self, content_type: str) -> bool:
        """检查是否支持指定类型"""
        return content_type in self.supported_types

    def supports_image_format(self, fmt: str) -> bool:
        return fmt.lower() in self.image_formats

    def supports_audio_format(self, fmt: str) -> bool:
        return fmt.lower() in self.audio_formats


class Channel(ABC):
    """通道基类"""

    name: str = ""
    capability: ChannelCapability = field(default_factory=ChannelCapability)

    @abstractmethod
    async def send_text(self, bot_id: str, content: str) -> bool:
        """发送文字消息"""
        pass

    @abstractmethod
    async def send_image(self, bot_id: str, image_path: str, caption: str = "") -> bool:
        """发送图片消息"""
        pass

    @abstractmethod
    async def send_voice(self, bot_id: str, audio_path: str, caption: str = "") -> bool:
        """发送语音消息"""
        pass

    @abstractmethod
    async def send_card(self, bot_id: str, card_data: dict) -> bool:
        """发送卡片消息"""
        pass

    async def send_proactive(self, bot_id: str, content: str, content_type: str = "text", **kwargs) -> bool:
        """根据内容类型自动选择发送方式"""
        if content_type == "voice":
            audio_path = kwargs.get("audio_path")
            if audio_path and self.capability.supports_type("voice"):
                return await self.send_voice(bot_id, audio_path, kwargs.get("caption", ""))
            # 降级为文字
            return await self.send_text(bot_id, f"[语音] {content}")

        elif content_type == "image":
            image_path = kwargs.get("image_path")
            if image_path and self.capability.supports_type("image"):
                return await self.send_image(bot_id, image_path, kwargs.get("caption", content))
            # 降级为文字
            return await self.send_text(bot_id, f"[图片描述] {content}")

        else:
            return await self.send_text(bot_id, content)


class CLIChannel(Channel):
    """CLI 通道（终端）"""

    name = "cli"
    capability = ChannelCapability(
        supported_types=["text", "image"],
        max_message_length=4000,
    )

    def __init__(self, output_callback=None):
        self._output_callback = output_callback

    async def send_text(self, bot_id: str, content: str) -> bool:
        output = f"\n[{bot_id}] {content}\n"
        if self._output_callback:
            try:
                await self._output_callback(output)
            except Exception:
                print(output)
        else:
            print(output)
        return True

    async def send_image(self, bot_id: str, image_path: str, caption: str = "") -> bool:
        caption = caption or "图片"
        output = f"\n[{bot_id}] [图片] {caption}\n路径: {image_path}\n"
        if self._output_callback:
            await self._output_callback(output)
        else:
            print(output)
        return True

    async def send_voice(self, bot_id: str, audio_path: str, caption: str = "") -> bool:
        caption = caption or "语音"
        output = f"\n[{bot_id}] [语音] {caption}\n路径: {audio_path}\n"
        if self._output_callback:
            await self._output_callback(output)
        else:
            print(output)
        return True

    async def send_card(self, bot_id: str, card_data: dict) -> bool:
        output = f"\n[{bot_id}] [卡片] {card_data.get('title', '')}\n"
        if self._output_callback:
            await self._output_callback(output)
        else:
            print(output)
        return True


class FeishuChannel(Channel):
    """飞书通道"""

    name = "feishu"
    capability = ChannelCapability(
        supported_types=["text", "card"],
        max_message_length=4000,
    )

    def __init__(self, webhook_url: str, bot_id: str = None):
        self.webhook_url = webhook_url
        self.bot_id = bot_id

    async def send_text(self, bot_id: str, content: str) -> bool:
        """通过飞书 Webhook 发送文字"""
        import aiohttp
        try:
            payload = {
                "msg_type": "text",
                "content": {"text": f"[{bot_id}] {content}"}
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.error(f"[FeishuChannel] 发送失败: {e}")
            return False

    async def send_image(self, bot_id: str, image_path: str, caption: str = "") -> bool:
        """通过飞书 Webhook 发送图片"""
        import aiohttp
        try:
            # 飞书图片消息需要先上传图片获取 key
            # 这里简化为发送 text 消息告知图片路径
            payload = {
                "msg_type": "text",
                "content": {"text": f"[{bot_id}] [图片] {caption}\n{image_path}"}
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.error(f"[FeishuChannel] 发送图片失败: {e}")
            return False

    async def send_voice(self, bot_id: str, audio_path: str, caption: str = "") -> bool:
        """通过飞书发送语音"""
        import aiohttp
        try:
            payload = {
                "msg_type": "text",
                "content": {"text": f"[{bot_id}] [语音] {caption}\n{audio_path}"}
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.error(f"[FeishuChannel] 发送语音失败: {e}")
            return False

    async def send_card(self, bot_id: str, card_data: dict) -> bool:
        """通过飞书发送卡片"""
        import aiohttp
        try:
            payload = {
                "msg_type": "interactive",
                "card": card_data
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.error(f"[FeishuChannel] 发送卡片失败: {e}")
            return False


class WebhookChannel(Channel):
    """通用 Webhook 通道"""

    name = "webhook"
    capability = ChannelCapability(
        supported_types=["text", "image", "voice", "card"],
        max_message_length=8000,
    )

    def __init__(self, webhook_url: str, headers: dict = None):
        self.webhook_url = webhook_url
        self.headers = headers or {}

    async def send_text(self, bot_id: str, content: str) -> bool:
        import aiohttp
        try:
            payload = {
                "bot_id": bot_id,
                "message": content,
                "message_type": "text"
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload, headers=self.headers) as resp:
                    return resp.status in (200, 201, 204)
        except Exception as e:
            logger.error(f"[WebhookChannel] 发送失败: {e}")
            return False

    async def send_image(self, bot_id: str, image_path: str, caption: str = "") -> bool:
        import aiohttp
        try:
            payload = {
                "bot_id": bot_id,
                "message": caption,
                "message_type": "image",
                "image_path": image_path
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload, headers=self.headers) as resp:
                    return resp.status in (200, 201, 204)
        except Exception as e:
            logger.error(f"[WebhookChannel] 发送图片失败: {e}")
            return False

    async def send_voice(self, bot_id: str, audio_path: str, caption: str = "") -> bool:
        import aiohttp
        try:
            payload = {
                "bot_id": bot_id,
                "message": caption,
                "message_type": "voice",
                "audio_path": audio_path
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload, headers=self.headers) as resp:
                    return resp.status in (200, 201, 204)
        except Exception as e:
            logger.error(f"[WebhookChannel] 发送语音失败: {e}")
            return False

    async def send_card(self, bot_id: str, card_data: dict) -> bool:
        import aiohttp
        try:
            payload = {
                "bot_id": bot_id,
                "message_type": "card",
                "card": card_data
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload, headers=self.headers) as resp:
                    return resp.status in (200, 201, 204)
        except Exception as e:
            logger.error(f"[WebhookChannel] 发送卡片失败: {e}")
            return False


def create_channel(channel_type: str, **kwargs) -> Channel:
    """工厂方法：创建通道"""
    if channel_type == "cli":
        return CLIChannel(kwargs.get("output_callback"))
    elif channel_type == "feishu":
        return FeishuChannel(
            webhook_url=kwargs.get("webhook_url", ""),
            bot_id=kwargs.get("bot_id")
        )
    elif channel_type == "webhook":
        return WebhookChannel(
            webhook_url=kwargs.get("webhook_url", ""),
            headers=kwargs.get("headers")
        )
    else:
        logger.warning(f"[Channel] 未知通道类型: {channel_type}，使用 CLI")
        return CLIChannel()
