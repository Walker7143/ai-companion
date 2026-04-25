"""
Ollama 本地模型适配器
"""

import aiohttp
import asyncio
import logging
from typing import Optional

from .base import ModelAdapter

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=60)
MAX_RETRIES = 2
RETRY_BACKOFF = [1, 2]


class OllamaAdapter(ModelAdapter):
    """Ollama 本地模型适配器"""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:7b",
        timeout: aiohttp.ClientTimeout = DEFAULT_TIMEOUT
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def provider(self) -> str:
        return "ollama"

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
        """调用 Ollama Chat API"""
        url = f"{self.base_url}/api/chat"

        # 构建消息格式
        ollama_messages = []
        if system_prompt:
            ollama_messages.append({"role": "system", "content": system_prompt})
        for msg in messages:
            role = "user" if msg["role"] == "user" else "assistant"
            ollama_messages.append({"role": role, "content": msg["content"]})

        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": False,
        }

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                session = await self._get_session()
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise RuntimeError(f"Ollama API error {resp.status}: {text}")
                    data = await resp.json()
                    return data["message"]["content"]
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_BACKOFF[attempt]
                    logger.debug(f"[Ollama] 请求失败 (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                    await asyncio.sleep(wait_time)
                continue

        raise RuntimeError(f"网络不稳定，Ollama 请求失败（已重试 {MAX_RETRIES} 次）")

    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        """调用 Ollama Embeddings API"""
        url = f"{self.base_url}/api/embeddings"

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                results = []
                session = await self._get_session()
                for text in texts:
                    payload = {"model": self.model, "prompt": text}
                    async with session.post(url, json=payload) as resp:
                        data = await resp.json()
                        results.append(data["embedding"])
                return results
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BACKOFF[attempt])
                continue

        raise RuntimeError(f"[Ollama] embeddings 达到最大重试次数 ({MAX_RETRIES})")
