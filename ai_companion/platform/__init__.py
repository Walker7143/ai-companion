"""
Platform - 平台接入模块

支持飞书、WebSocket 等平台的消息接入
"""

from .feishu.server import FeishuServer

__all__ = ["FeishuServer"]
