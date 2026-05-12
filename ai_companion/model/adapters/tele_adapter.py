"""
TeleClaw 模型适配器

TeleClaw 的远端接口是 OpenAI-compatible Chat Completions，但还要求带上
桌面端登录态里的 X-Token、设备 ID 和安装 ID。
"""

import aiohttp
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

from .base import ModelAdapter
from .response_parsing import user_visible_message_content

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://agent.teleai.com.cn/superCowork/sapi/api/v1"
DEFAULT_MODEL = "glm-5-turbo"
DEFAULT_AUTH_STATE_FILE = ""
DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=600)
MAX_RETRIES = 3
RETRY_BACKOFF = [1, 2, 4]
PROJECT_AUTH_STATE_FILE = Path(__file__).resolve().parents[3] / ".local" / "teleclaw" / "state.json"


def default_auth_state_file() -> Path:
    """Resolve TeleClaw's Electron userData auth state path across platforms."""
    env_path = os.environ.get("TELECLAW_AUTH_STATE_FILE") or os.environ.get("SUPER_AGENT_AUTH_STATE_FILE")
    if env_path:
        return Path(env_path).expanduser()

    candidates = platform_auth_state_candidates()
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def platform_auth_state_candidates() -> list[Path]:
    """Return TeleClaw system path candidates plus the project-local fallback."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            system_path = Path(appdata) / "TeleClaw" / "app-auth" / "state.json"
        else:
            system_path = Path.home() / "AppData" / "Roaming" / "TeleClaw" / "app-auth" / "state.json"
    elif sys.platform == "darwin":
        system_path = Path.home() / "Library" / "Application Support" / "TeleClaw" / "app-auth" / "state.json"
    else:
        xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config_home:
            system_path = Path(xdg_config_home) / "TeleClaw" / "app-auth" / "state.json"
        else:
            system_path = Path.home() / ".config" / "TeleClaw" / "app-auth" / "state.json"
    return [system_path, PROJECT_AUTH_STATE_FILE]


class TeleAdapter(ModelAdapter):
    """TeleClaw GLM-5 Turbo 模型适配器"""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        auth_state_file: str = DEFAULT_AUTH_STATE_FILE,
        timeout: aiohttp.ClientTimeout = DEFAULT_TIMEOUT,
    ):
        self.api_key = api_key
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.model = DEFAULT_MODEL
        self.auth_state_file = Path(auth_state_file).expanduser() if auth_state_file else default_auth_state_file()
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def provider(self) -> str:
        return "tele"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _load_auth_state(self) -> dict:
        try:
            data = json.loads(self.auth_state_file.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"TeleClaw 登录态文件不存在: {self.auth_state_file}。请先登录 TeleClaw。"
            ) from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"TeleClaw 登录态文件不是有效 JSON: {self.auth_state_file}") from exc

        missing = [
            field
            for field in ("token", "deviceId", "installId")
            if not str(data.get(field) or "").strip()
        ]
        if missing:
            raise RuntimeError(
                f"TeleClaw 登录态缺少字段: {', '.join(missing)}。请重新登录 TeleClaw。"
            )
        return data

    def _build_headers(self) -> dict:
        state = self._load_auth_state()
        headers = {
            "X-Token": str(state["token"]),
            "X-SuperAgent-Timestamp": str(int(time.time())),
            "X-SuperAgent-Nonce": str(uuid.uuid4()),
            "X-SuperAgent-Device-Id": str(state["deviceId"]),
            "X-SuperAgent-Install-Id": str(state["installId"]),
            "Content-Type": "application/json",
        }
        if self.api_key and not str(self.api_key).startswith("${"):
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        **kwargs
    ) -> str:
        """调用 TeleClaw OpenAI-compatible Chat Completions API"""
        url = f"{self.base_url}/chat/completions"
        headers = self._build_headers()

        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        payload = {
            "model": DEFAULT_MODEL,
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
                        raise RuntimeError(f"Tele API error {resp.status}: {text}")
                    data = await resp.json()
                    choice = data["choices"][0]["message"]
                    return user_visible_message_content(choice, provider="Tele")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_BACKOFF[attempt]
                    logger.debug(f"[Tele] 请求失败 (attempt {attempt + 1}/{MAX_RETRIES}): {e}, {wait_time}s 后重试")
                    await asyncio.sleep(wait_time)
                continue

        raise RuntimeError(f"网络不稳定，Tele 请求失败（已重试 {MAX_RETRIES} 次），最后错误: {last_error!r}")

    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        """Tele 当前未在本项目内接入 embeddings，返回占位向量。"""
        logger.warning("[Tele] Tele 适配器暂不支持 embeddings API")
        return [[0.0] * 384 for _ in texts]
