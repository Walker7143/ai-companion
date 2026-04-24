"""
Feishu Models - 飞书消息模型

定义飞书消息的解析和封装
"""

from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class FeishuMessage:
    """飞书消息"""
    msg_type: str           # text, image, audio, video, card
    content: str            # 消息内容
    message_id: str         # 消息 ID
    sender_id: str          # 发送者 ID
    sender_type: str         # user, bot, app
    chat_id: str            # 会话 ID
    create_time: str        # 创建时间
    raw: dict               # 原始消息体

    @classmethod
    def from_feishu_event(cls, event: dict) -> Optional["FeishuMessage"]:
        """从飞书事件构造消息对象"""
        try:
            sender = event.get("sender", {})
            message = event.get("message", {})

            return cls(
                msg_type=message.get("msg_type", "text"),
                content=message.get("content", ""),
                message_id=message.get("message_id", ""),
                sender_id=sender.get("sender_id", {}).get("open_id", ""),
                sender_type=sender.get("sender_type", "user"),
                chat_id=message.get("chat_id", ""),
                create_time=message.get("create_time", ""),
                raw=event
            )
        except Exception as e:
            logger.error(f"[Feishu] 解析消息失败: {e}")
            return None

    def get_text_content(self) -> str:
        """获取文本内容"""
        if self.msg_type == "text":
            try:
                import json
                data = json.loads(self.content)
                return data.get("text", "")
            except Exception:
                return self.content
        return ""

    def get_image_key(self) -> Optional[str]:
        """获取图片 key（用于下载图片）"""
        if self.msg_type == "image":
            try:
                import json
                data = json.loads(self.content)
                return data.get("image_key")
            except Exception:
                return None
        return None


@dataclass
class FeishuBot:
    """飞书 Bot 配置"""
    bot_id: str             # 对应的 Bot 实例 ID
    app_id: str             # 飞书应用 ID
    app_secret: str          # 飞书应用 Secret
    bot_name: str = ""      # Bot 名称
