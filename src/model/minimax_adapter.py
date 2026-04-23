import aiohttp
import json
from typing import Optional


class MiniMaxAdapter:
    """MiniMax m2.7 模型适配器"""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def chat(
        self, messages: list[dict], system_prompt: str = "", **kwargs
    ) -> str:
        """
        调用 MiniMax 聊天 API
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
            "max_tokens": kwargs.get("max_tokens", 2048),
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"MiniMax API error {resp.status}: {text}")
                data = await resp.json()
                return data["choices"][0]["message"]["content"]

    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        """调用 MiniMax embeddings API"""
        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": "embo-01", "texts": texts}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                data = await resp.json()
                return [item["embedding"] for item in data["data"]]
