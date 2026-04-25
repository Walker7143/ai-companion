"""
OpenAI 模型适配器
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


class OpenAIAdapter(ModelAdapter):
    """OpenAI GPT 系列模型适配器"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o",
        timeout: aiohttp.ClientTimeout = DEFAULT_TIMEOUT
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def provider(self) -> str:
        return "openai"

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
        """调用 OpenAI Chat Completions API"""
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
        }

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                session = await self._get_session()
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise RuntimeError(f"OpenAI API error {resp.status}: {text}")
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"]
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_BACKOFF[attempt]
                    logger.debug(f"[OpenAI] 请求失败 (attempt {attempt + 1}/{MAX_RETRIES}): {e}, {wait_time}s 后重试")
                    await asyncio.sleep(wait_time)
                continue

        raise RuntimeError(f"网络不稳定，OpenAI 请求失败（已重试 {MAX_RETRIES} 次）")

    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        """调用 OpenAI Embeddings API"""
        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": "text-embedding-3-small", "input": texts}

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                session = await self._get_session()
                async with session.post(url, headers=headers, json=payload) as resp:
                    data = await resp.json()
                    return [item["embedding"] for item in data["data"]]
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_BACKOFF[attempt]
                    logger.debug(f"[OpenAI] embeddings 失败 (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                    await asyncio.sleep(wait_time)
                continue

        raise RuntimeError(f"[OpenAI] embeddings 达到最大重试次数 ({MAX_RETRIES})")
