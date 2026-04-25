"""
Token 估算工具

中英文混合文本的 Token 数量估算。
"""

import logging

logger = logging.getLogger(__name__)


class TokenEstimator:
    """中英文混合文本 Token 估算

    估算规则：
    - 中文约 1.5 chars/token
    - 英文约 4 chars/token
    - 其他字符约 4 chars/token
    """

    @staticmethod
    def estimate(text: str) -> int:
        """估算单个文本的 token 数量

        Args:
            text: 输入文本

        Returns:
            估算的 token 数量
        """
        if not text:
            return 0

        # 统计各类字符
        chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        english = sum(1 for c in text if c.isascii() and c.isalpha())
        other = len(text) - chinese - english

        # 估算 token
        tokens = int(chinese / 1.5 + english / 4 + other / 4)
        return max(1, tokens)

    @staticmethod
    def estimate_messages(messages: list) -> int:
        """估算消息列表的总 token 数

        Args:
            messages: 消息列表，每个消息包含 'content' 字段

        Returns:
            估算的总 token 数
        """
        return sum(
            TokenEstimator.estimate(m.get('content', ''))
            for m in messages
        )

    @staticmethod
    def estimate_conversation_length(messages: list) -> dict:
        """估算对话长度，返回详细信息

        Args:
            messages: 消息列表

        Returns:
            包含各类统计的字典
        """
        if not messages:
            return {
                "total_chars": 0,
                "total_tokens": 0,
                "message_count": 0,
                "chinese_chars": 0,
                "english_chars": 0,
            }

        total_chars = sum(len(m.get('content', '')) for m in messages)
        chinese_chars = sum(
            sum(1 for c in m.get('content', '') if '\u4e00' <= c <= '\u9fff')
            for m in messages
        )
        english_chars = sum(
            sum(1 for c in m.get('content', '') if c.isascii() and c.isalpha())
            for m in messages
        )

        return {
            "total_chars": total_chars,
            "total_tokens": TokenEstimator.estimate_messages(messages),
            "message_count": len(messages),
            "chinese_chars": chinese_chars,
            "english_chars": english_chars,
            "other_chars": total_chars - chinese_chars - english_chars,
        }
