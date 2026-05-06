"""
Anthropic Claude 模型适配器
"""

import aiohttp
import asyncio
import logging
from typing import Optional

from .base import ModelAdapter

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30)
MAX_RETRIES = 3
RETRY_BACKOFF = [1, 2, 4]  # seconds


class ClaudeAdapter(ModelAdapter):
    """Anthropic Claude 系列模型适配器"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.anthropic.com/v1",
        model: str = "claude-sonnet-4-20250514",
        timeout: aiohttp.ClientTimeout = DEFAULT_TIMEOUT
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def provider(self) -> str:
        return "claude"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        **kwargs
    ) -> str:
        """调用 Anthropic Messages API"""
        url = f"{self.base_url}/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        # 构建消息格式
        claude_messages = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "assistant"
            claude_messages.append({"role": role, "content": msg["content"]})

        payload = {
            "model": self.model,
            "messages": claude_messages,
            "temperature": kwargs.get("temperature", 0.8),
            "max_tokens": kwargs.get("max_tokens", 1024),
        }

        if system_prompt:
            payload["system"] = system_prompt

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                session = await self._get_session()
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise RuntimeError(f"Claude API error {resp.status}: {text}")
                    data = await resp.json()
                    return data["content"][0]["text"]
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_BACKOFF[attempt]
                    logger.debug(f"[Claude] 请求失败 (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                    await asyncio.sleep(wait_time)
                continue

        raise RuntimeError(f"网络不稳定，Claude 请求失败（已重试 {MAX_RETRIES} 次），最后错误: {last_error!r}")

    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        """Claude 不提供 Embeddings API，默认返回空"""
        logger.warning("[Claude] Claude 不支持 embeddings API")
        return [[0.0] * 384 for _ in texts]  # 返回虚拟向量
