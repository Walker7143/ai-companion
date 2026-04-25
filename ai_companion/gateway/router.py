"""
飞书消息路由器 - 根据配置将消息路由到不同的 Bot
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .platforms.base import MessageEvent

logger = logging.getLogger(__name__)


class PlatformRouter:
    """飞书消息路由"""

    def __init__(self, routing_config: dict):
        self.routing_config = routing_config or {}
        self.mode = self.routing_config.get("mode", "dedicated")
        self._group_bot_map = self.routing_config.get("group_bot_map", {})
        self._default_bot = self.routing_config.get("default_bot", "")
        self._bot_id = self.routing_config.get("bot_id", "")

    def route(self, event: "MessageEvent") -> str:
        """根据路由模式返回 bot_id"""
        if self.mode == "dedicated":
            return self._bot_id

        if self.mode == "chat_routed":
            chat_id = event.source.chat_id if event.source else ""
            if chat_id and chat_id in self._group_bot_map:
                return self._group_bot_map[chat_id]
            return self._default_bot

        # Fallback: return default bot
        return self._default_bot
