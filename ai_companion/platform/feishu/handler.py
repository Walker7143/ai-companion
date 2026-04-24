"""
FeishuHandler - 飞书消息处理器

处理飞书消息，路由到对应的 Bot
"""

import asyncio
import logging
from typing import Dict, Callable, Awaitable, Optional

from .models import FeishuMessage, FeishuBot

logger = logging.getLogger(__name__)

# 消息处理器类型
MessageHandler = Callable[[str, FeishuMessage], Awaitable[None]]


class FeishuHandler:
    """飞书消息处理器"""

    def __init__(self):
        # open_id -> Bot 实例 ID 的映射
        self._user_bot_map: Dict[str, str] = {}
        # Bot 实例 ID -> 消息处理回调
        self._bot_handlers: Dict[str, MessageHandler] = {}
        # Bot 配置
        self._bots: Dict[str, FeishuBot] = {}

    def register_bot(self, bot: FeishuBot):
        """注册 Bot 配置"""
        self._bots[bot.bot_id] = bot
        logger.info(f"[FeishuHandler] 注册 Bot: {bot.bot_id} (app_id: {bot.app_id})")

    def register_user_bot_mapping(self, open_id: str, bot_id: str):
        """注册用户到 Bot 的映射"""
        self._user_bot_map[open_id] = bot_id
        logger.debug(f"[FeishuHandler] 用户映射: {open_id} -> {bot_id}")

    def register_handler(self, bot_id: str, handler: MessageHandler):
        """注册 Bot 的消息处理器"""
        self._bot_handlers[bot_id] = handler
        logger.info(f"[FeishuHandler] 注册处理器: {bot_id}")

    def get_bot_for_user(self, open_id: str) -> Optional[str]:
        """获取用户对应的 Bot ID"""
        return self._user_bot_map.get(open_id)

    def get_bot_config(self, bot_id: str) -> Optional[FeishuBot]:
        """获取 Bot 配置"""
        return self._bots.get(bot_id)

    async def handle_message(self, event: dict) -> bool:
        """
        处理收到的飞书消息

        Args:
            event: 飞书事件

        Returns:
            bool: 是否处理成功
        """
        try:
            # 解析消息
            message = FeishuMessage.from_feishu_event(event)
            if not message:
                logger.warning(f"[FeishuHandler] 消息解析失败")
                return False

            # 忽略自己发送的消息
            if message.sender_type == "bot":
                logger.debug(f"[FeishuHandler] 忽略 Bot 自己的消息")
                return True

            # 查找对应的 Bot
            bot_id = self.get_bot_for_user(message.sender_id)
            if not bot_id:
                logger.warning(f"[FeishuHandler] 未找到用户对应的 Bot: {message.sender_id}")
                return False

            # 调用处理器
            handler = self._bot_handlers.get(bot_id)
            if not handler:
                logger.warning(f"[FeishuHandler] Bot {bot_id} 未注册处理器")
                return False

            await handler(bot_id, message)
            return True

        except Exception as e:
            logger.error(f"[FeishuHandler] 处理消息失败: {e}", exc_info=True)
            return False

    def create_reply_handler(self, bot_instance_getter) -> MessageHandler:
        """
        创建回复处理器

        Args:
            bot_instance_getter: 获取 BotInstance 的回调，签名为 (bot_id: str) -> BotInstance
        """
        async def handler(bot_id: str, message: FeishuMessage):
            bot = bot_instance_getter(bot_id)
            if not bot:
                logger.error(f"[FeishuHandler] 未找到 Bot: {bot_id}")
                return

            # 根据消息类型获取内容
            if message.msg_type == "text":
                user_input = message.get_text_content()
            elif message.msg_type == "image":
                user_input = "[图片]"
            elif message.msg_type == "audio":
                user_input = "[语音]"
            else:
                user_input = f"[{message.msg_type} 消息]"

            if not user_input:
                return

            # 调用 Bot 处理
            try:
                response = await bot.handle_message(user_input)
                if response:
                    # 通过飞书平台发送回复
                    await bot.multimodal_sender.send_proactive(
                        content=response,
                        content_type="text",
                        user_id=message.sender_id
                    )
            except Exception as e:
                logger.error(f"[FeishuHandler] Bot 处理失败: {e}")

        return handler
