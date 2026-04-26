"""
Platform - 平台接入模块

支持飞书、WebSocket 等平台的消息接入
"""

try:
    from .feishu.server import FeishuServer
except ImportError:
    FeishuServer = None

__all__ = ["FeishuServer"]
