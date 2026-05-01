"""
MiniMax 模型适配器
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


class MiniMaxAdapter(ModelAdapter):
    """MiniMax M2.7 模型适配器，支持超时和重试"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.minimax.chat/v1",
        model: str = "MiniMax-M2.7",
        timeout: aiohttp.ClientTimeout = DEFAULT_TIMEOUT
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def provider(self) -> str:
        return "minimax"

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建共享的 ClientSession（连接池）"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self):
        """关闭 ClientSession"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        **kwargs
    ) -> str:
        """
        调用 MiniMax 聊天 API，带重试逻辑
        messages: [{"role": "user", "content": "..."}]
        """
        url = f"{self.base_url}/text/chatcompletion_v2"
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
                        raise RuntimeError(f"MiniMax API error {resp.status}: {text}")
                    data = await resp.json()
                    choice = data["choices"][0]["message"]
                    # MiniMax-M2.7:
                    # content = 实际回复（发给用户的话）
                    # reasoning_content = 内部推理过程（角色内心独白等）
                    # 优先用 content，reasoning_content 仅在 content 为空时降级使用
                    ct = choice.get("content") or ""
                    rc = choice.get("reasoning_content") or ""
                    return ct if ct.strip() else rc
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_BACKOFF[attempt]
                    logger.debug(f"[MiniMax] 请求失败 (attempt {attempt + 1}/{MAX_RETRIES}): {e}, {wait_time}s 后重试")
                    await asyncio.sleep(wait_time)
                continue

        # 所有重试都失败后，保留真实异常，避免长任务只能看到泛化提示。
        raise RuntimeError(f"网络不稳定，MiniMax 请求失败（已重试 {MAX_RETRIES} 次），最后错误: {last_error!r}")

    async def embeddings(self, texts: list[str], type: str = "db") -> list[list[float]]:
        """
        调用 MiniMax embeddings API，带重试

        Args:
            texts: 文本列表
            type: embedding 类型，"db" 用于存储，"query" 用于查询
        """
        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": "embo-01", "texts": texts, "type": type}

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                session = await self._get_session()
                async with session.post(url, headers=headers, json=payload) as resp:
                    data = await resp.json()
                    # 检查 API 返回状态
                    if base_resp := data.get("base_resp"):
                        status_code = base_resp.get("status_code", 0)
                        if status_code != 0:
                            status_msg = base_resp.get("status_msg", "unknown error")
                            raise RuntimeError(f"MiniMax embeddings API error {status_code}: {status_msg}")
                    # 解析 vectors
                    vectors = data.get("vectors")
                    if vectors is None:
                        raise RuntimeError("MiniMax embeddings API returned no vectors")
                    return [item["embedding"] for item in vectors]
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_BACKOFF[attempt]
                    logger.debug(f"[MiniMax] embeddings 失败 (attempt {attempt + 1}/{MAX_RETRIES}): {e}, {wait_time}s 后重试")
                    await asyncio.sleep(wait_time)
                continue

        raise RuntimeError(f"[MiniMax] embeddings 达到最大重试次数 ({MAX_RETRIES}), 最后错误: {last_error}")
