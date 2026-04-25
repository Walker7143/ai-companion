"""
自定义 HTTP API 适配器

支持任意 OpenAI-compatible 或自定义格式的 HTTP API
"""

import aiohttp
import asyncio
import json
import logging
import re
from typing import Any, Optional

from .base import ModelAdapter

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30)
MAX_RETRIES = 3
RETRY_BACKOFF = [1, 2, 4]


class CustomAdapter(ModelAdapter):
    """
    支持任意 HTTP API 的自定义模型适配器

    支持的认证方式:
    - bearer: Authorization: Bearer {api_key}
    - api_key: X-API-Key: {api_key}
    - none: 无认证

    支持自定义请求模板和响应字段路径解析
    """

    def __init__(
        self,
        api_url: str,
        model: str,
        auth_type: str = "bearer",
        api_key: str = None,
        headers: dict = None,
        request_template: dict = None,
        response_field: str = "choices.0.message.content",
        timeout: aiohttp.ClientTimeout = DEFAULT_TIMEOUT,
    ):
        self.api_url = api_url
        self.model = model
        self.auth_type = auth_type.lower()
        self.api_key = api_key or ""
        self.headers = headers or {}
        self.request_template = request_template or {}
        self.response_field = response_field
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def provider(self) -> str:
        return "custom"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _build_headers(self) -> dict:
        """构建请求头"""
        headers = dict(self.headers)

        if self.auth_type == "bearer" and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        elif self.auth_type == "api_key" and self.api_key:
            headers["X-API-Key"] = self.api_key

        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        return headers

    def _build_request_body(
        self,
        messages: list[dict],
        system_prompt: str,
        **kwargs
    ) -> dict:
        """构建请求体，支持模板替换"""

        def interpolate(value: Any, **context) -> Any:
            """递归替换模板变量"""
            if isinstance(value, str):
                # 支持 {{model}}, {{messages}}, {{temperature}} 等
                result = value
                result = result.replace("{{model}}", str(context.get("model", self.model)))
                result = result.replace("{{temperature}}", str(context.get("temperature", kwargs.get("temperature", 0.8))))
                result = result.replace("{{max_tokens}}", str(context.get("max_tokens", kwargs.get("max_tokens", 1024))))

                # 特殊处理 {{messages}} - 序列化为 JSON
                if "{{messages}}" in result:
                    result = result.replace("{{messages}}", json.dumps(context.get("messages", messages)))

                # 处理 {{system_prompt}}
                result = result.replace("{{system_prompt}}", str(context.get("system_prompt", system_prompt)))

                return result

            elif isinstance(value, dict):
                return {k: interpolate(v, **context) for k, v in value.items()}

            elif isinstance(value, list):
                return [interpolate(v, **context) for v in value]

            return value

        # 如果有模板，使用模板
        if self.request_template:
            body = interpolate(self.request_template, model=self.model, messages=messages,
                              system_prompt=system_prompt, temperature=kwargs.get("temperature", 0.8),
                              max_tokens=kwargs.get("max_tokens", 1024))
            return body

        # 默认 OpenAI-compatible 格式
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        return {
            "model": self.model,
            "messages": full_messages,
            "temperature": kwargs.get("temperature", 0.8),
            "max_tokens": kwargs.get("max_tokens", 1024),
        }

    def _extract_response(self, data: dict) -> str:
        """根据字段路径解析响应"""

        def get_by_path(obj: dict, path: str) -> Any:
            """支持 a.b.c 或 a.0.b 格式的路径"""
            parts = re.split(r'\.(?!\d)', path)  # 分割，排除数字前的点
            for part in parts:
                if isinstance(obj, dict):
                    obj = obj.get(part)
                elif isinstance(obj, list):
                    try:
                        obj = obj[int(part)]
                    except (ValueError, IndexError):
                        return None
                else:
                    return None
                if obj is None:
                    return None
            return obj

        # 尝试从路径获取
        result = get_by_path(data, self.response_field)
        if result is not None:
            return str(result)

        # 降级：尝试常见格式
        if "choices" in data and len(data["choices"]) > 0:
            choice = data["choices"][0]
            if "message" in choice:
                return choice["message"].get("content", "")
            if "text" in choice:
                return choice["text"]

        raise ValueError(f"无法从响应中解析字段 '{self.response_field}': {data}")

    async def chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        **kwargs
    ) -> str:
        """发送自定义 API 请求"""
        url = self.api_url
        headers = self._build_headers()
        body = self._build_request_body(messages, system_prompt, **kwargs)

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                session = await self._get_session()
                async with session.post(url, headers=headers, json=body) as resp:
                    if resp.status not in (200, 201):
                        text = await resp.text()
                        raise RuntimeError(f"Custom API error {resp.status}: {text}")
                    data = await resp.json()
                    return self._extract_response(data)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_BACKOFF[attempt]
                    logger.debug(f"[Custom] 请求失败 (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                    await asyncio.sleep(wait_time)
                continue
            except (ValueError, KeyError, IndexError) as e:
                raise ValueError(f"Custom API 响应解析失败: {e}")

        raise RuntimeError(f"网络不稳定，Custom API 请求失败（已重试 {MAX_RETRIES} 次）")

    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        """默认不支持 embeddings"""
        logger.warning("[Custom] 自定义适配器默认不支持 embeddings")
        return [[0.0] * 384 for _ in texts]
