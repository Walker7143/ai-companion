"""
Model Adapter - 模型适配器抽象基类

所有模型适配器必须实现此接口：
- chat(): 发送对话，返回回复文本
- embeddings(): 获取文本嵌入向量
- close(): 关闭连接（可选）
"""

from abc import ABC, abstractmethod
from typing import Optional


class ModelAdapter(ABC):
    """模型适配器抽象基类"""

    @property
    def provider(self) -> str:
        """提供商名称：minimax / openai / claude / mimo / ollama / custom"""
        return "unknown"

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        **kwargs
    ) -> str:
        """
        发送对话，返回回复文本

        Args:
            messages: [{"role": "user", "content": "..."}]
            system_prompt: 系统提示词
            **kwargs: temperature, max_tokens 等

        Returns:
            回复文本字符串
        """
        pass

    @abstractmethod
    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        获取文本嵌入向量

        Args:
            texts: 文本列表

        Returns:
            嵌入向量列表 [[0.1, 0.2, ...], ...]
        """
        pass

    async def close(self):
        """关闭连接（可选实现）"""
        pass
