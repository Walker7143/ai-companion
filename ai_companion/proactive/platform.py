"""
ProactivePlatform - 主动消息平台适配器

抽象平台发送接口，支持 CLI / 飞书 / Webhook 等。
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class ProactivePlatform(ABC):
    """主动消息平台适配器基类"""

    @abstractmethod
    async def send(self, bot_id: str, message: str) -> bool:
        """
        发送主动消息
        返回 True 表示发送成功
        """
        pass

    @abstractmethod
    async def get_user_status(self, user_id: str) -> bool:
        """
        获取用户在线状态
        返回 True 表示用户在线
        """
        pass


class CLIPlatform(ProactivePlatform):
    """CLI 平台适配器（打印到终端）"""

    def __init__(self, output_callback=None):
        """
        output_callback: 消息输出回调函数
        如果不提供，默认打印到 stdout
        """
        self._output_callback = output_callback

    async def send(self, bot_id: str, message: str) -> bool:
        """CLI 模式下打印消息到终端"""
        output = f"\n[主动消息 {bot_id}] {message}\n"
        if self._output_callback:
            try:
                await self._output_callback(output)
            except Exception:
                print(output)
        else:
            print(output)
        return True

    async def get_user_status(self, user_id: str) -> bool:
        """CLI 模式下假设用户总是在线"""
        return True


class FeishuPlatform(ProactivePlatform):
    """飞书平台适配器"""

    def __init__(self, webhook_url: str, bot_id: str = None):
        self.webhook_url = webhook_url
        self.bot_id = bot_id

    async def send(self, bot_id: str, message: str) -> bool:
        """通过飞书 Webhook 发送消息"""
        import aiohttp

        try:
            payload = {
                "msg_type": "text",
                "content": {"text": f"[{bot_id}] {message}"}
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.error(f"[FeishuPlatform] 发送失败: {e}")
            return False

    async def get_user_status(self, user_id: str) -> bool:
        """飞书平台需要调用 API 获取用户状态"""
        # TODO: 实现飞书用户状态查询
        return True


class WebhookPlatform(ProactivePlatform):
    """通用 Webhook 平台适配器"""

    def __init__(self, webhook_url: str, headers: dict = None):
        self.webhook_url = webhook_url
        self.headers = headers or {}

    async def send(self, bot_id: str, message: str) -> bool:
        """通过通用 Webhook 发送消息"""
        import aiohttp

        try:
            payload = {
                "bot_id": bot_id,
                "message": message,
                "timestamp": None,
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    headers=self.headers
                ) as resp:
                    return resp.status in (200, 201, 204)
        except Exception as e:
            logger.error(f"[WebhookPlatform] 发送失败: {e}")
            return False

    async def get_user_status(self, user_id: str) -> bool:
        """通用 Webhook 无法获取用户状态，默认返回 True"""
        return True


def create_platform(platform_type: str, **kwargs) -> ProactivePlatform:
    """工厂方法：创建平台适配器"""
    if platform_type == "cli":
        return CLIPlatform(kwargs.get("output_callback"))
    elif platform_type == "feishu":
        return FeishuPlatform(
            webhook_url=kwargs.get("webhook_url", ""),
            bot_id=kwargs.get("bot_id")
        )
    elif platform_type == "webhook":
        return WebhookPlatform(
            webhook_url=kwargs.get("webhook_url", ""),
            headers=kwargs.get("headers")
        )
    else:
        logger.warning(f"[ProactivePlatform] 未知平台类型: {platform_type}，使用 CLI")
        return CLIPlatform()