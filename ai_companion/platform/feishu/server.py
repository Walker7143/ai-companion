"""
FeishuServer - 飞书 WebSocket 服务

使用飞书官方 lark-oapi SDK 实现 WebSocket 长连接
"""

import asyncio
import logging
from typing import Dict, Optional, Callable

logger = logging.getLogger(__name__)

# lark-oapi SDK
try:
    from lark_oapi import ws
    from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
    _LARK_AVAILABLE = True
except ImportError:
    _LARK_AVAILABLE = False
    logger.warning("[FeishuServer] lark-oapi 未安装，请运行: pip install lark-oapi")


class FeishuServer:
    """
    飞书 WebSocket 服务

    使用官方 lark-oapi SDK 的 WebSocket 模式接入飞书
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        event_handler: Optional[EventDispatcherHandler] = None
    ):
        """
        初始化飞书服务

        Args:
            app_id: 飞书应用 ID
            app_secret: 飞书应用 Secret
            event_handler: 事件处理器
        """
        if not _LARK_AVAILABLE:
            raise RuntimeError("lark-oapi 未安装，请运行: pip install lark-oapi")

        self.app_id = app_id
        self.app_secret = app_secret
        self._client: Optional[ws.Client] = None
        self._event_handler = event_handler
        self._running = False

    def register_event_handler(self, event_handler: EventDispatcherHandler):
        """注册事件处理器"""
        self._event_handler = event_handler

    def start(self):
        """启动 WebSocket 服务（同步方法，内部处理异步）"""
        if self._running:
            logger.warning("[FeishuServer] 服务已在运行")
            return

        try:
            # 创建 WebSocket 客户端
            self._client = ws.Client(
                app_id=self.app_id,
                app_secret=self.app_secret,
                event_handler=self._event_handler,
            )

            # 启动
            self._client.start()
            self._running = True
            logger.info(f"[FeishuServer] WebSocket 服务已启动 (app_id: {self.app_id})")

        except Exception as e:
            logger.error(f"[FeishuServer] 启动失败: {e}", exc_info=True)
            raise

    def stop(self):
        """停止 WebSocket 服务"""
        if not self._running:
            return

        try:
            if self._client:
                self._client.stop()
            self._running = False
            logger.info("[FeishuServer] WebSocket 服务已停止")
        except Exception as e:
            logger.error(f"[FeishuServer] 停止失败: {e}", exc_info=True)

    def is_running(self) -> bool:
        """检查服务是否运行中"""
        return self._running


class FeishuServerManager:
    """
    飞书服务管理器

    管理多个飞书应用的 WebSocket 连接
    """

    def __init__(self):
        self._servers: Dict[str, FeishuServer] = {}

    def create_server(
        self,
        name: str,
        app_id: str,
        app_secret: str,
        event_handler=None
    ) -> FeishuServer:
        """
        创建飞书服务

        Args:
            name: 服务名称（对应 bot_id）
            app_id: 飞书应用 ID
            app_secret: 飞书应用 Secret
            event_handler: 事件处理器

        Returns:
            FeishuServer 实例
        """
        if name in self._servers:
            logger.warning(f"[FeishuServerManager] 服务 {name} 已存在，将被替换")

        server = FeishuServer(app_id, app_secret, event_handler)
        self._servers[name] = server
        return server

    def get_server(self, name: str) -> Optional[FeishuServer]:
        """获取服务"""
        return self._servers.get(name)

    def start_all(self):
        """启动所有服务"""
        for name, server in self._servers.items():
            try:
                server.start()
            except Exception as e:
                logger.error(f"[FeishuServerManager] 启动 {name} 失败: {e}")

    def stop_all(self):
        """停止所有服务"""
        for name, server in self._servers.items():
            try:
                server.stop()
            except Exception as e:
                logger.error(f"[FeishuServerManager] 停止 {name} 失败: {e}")


# 全局管理器实例
_manager: Optional[FeishuServerManager] = None


def get_manager() -> FeishuServerManager:
    """获取全局管理器"""
    global _manager
    if _manager is None:
        _manager = FeishuServerManager()
    return _manager
