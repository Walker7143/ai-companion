"""
DeepSeek 模型适配器

DeepSeek 提供 OpenAI-compatible Chat Completions API，
支持 reasoning_content 字段（推理模型如 deepseek-reasoner）。
"""

import aiohttp
import asyncio
import logging
from typing import Optional

from .base import ModelAdapter
from .response_parsing import user_visible_message_content

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=60)
MAX_RETRIES = 3
RETRY_BACKOFF = [1, 2, 4]


class DeepSeekAdapter(ModelAdapter):
    """DeepSeek 大模型适配器"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-v4-pro",
        timeout: aiohttp.ClientTimeout = DEFAULT_TIMEOUT,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def provider(self) -> str:
        return "deepseek"

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
        """调用 DeepSeek OpenAI-compatible Chat Completions API"""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        payload = {
            "model": self.model,
            "messages": full_messages,
            "temperature": kwargs.get("temperature", 0.8),
            "max_tokens": kwargs.get("max_tokens", 1024),
            "stream": False,
        }
        if "top_p" in kwargs:
            payload["top_p"] = kwargs["top_p"]

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                session = await self._get_session()
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise RuntimeError(f"DeepSeek API error {resp.status}: {text}")
                    data = await resp.json()
                    choice = data["choices"][0]["message"]
                    return user_visible_message_content(choice, provider="DeepSeek")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_BACKOFF[attempt]
                    logger.debug(f"[DeepSeek] 请求失败 (attempt {attempt + 1}/{MAX_RETRIES}): {e}, {wait_time}s 后重试")
                    await asyncio.sleep(wait_time)
                continue

        raise RuntimeError(f"网络不稳定，DeepSeek 请求失败（已重试 {MAX_RETRIES} 次），最后错误: {last_error!r}")

    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        """DeepSeek embeddings 暂未接入，返回占位向量。"""
        logger.warning("[DeepSeek] DeepSeek 适配器暂不支持 embeddings API")
        return [[0.0] * 384 for _ in texts]
