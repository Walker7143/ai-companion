"""
ImageGenerationSkill - 图片生成技能

默认按 OpenAI-compatible Images API 调用：
  POST {base_url}/images/generations

用户只需要配置 base_url、model、api_key。旧 MiniMax provider 配置仍兼容。
"""

from __future__ import annotations

import base64
import logging
import os
import uuid
from pathlib import Path
from typing import Any

import aiohttp

from .base import Skill, SkillContext, SkillResult

logger = logging.getLogger(__name__)

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_IMAGE_MODEL = "gpt-image-1"
DEFAULT_MINIMAX_BASE_URL = "https://api.minimax.chat/v1"


def _clean_base_url(value: str | None, default: str) -> str:
    return str(value or default).strip().rstrip("/")


def _endpoint_url(base_url: str, endpoint: str) -> str:
    base = base_url.strip().rstrip("/")
    normalized_endpoint = "/" + endpoint.strip("/")
    if base.endswith(normalized_endpoint):
        return base
    return f"{base}{normalized_endpoint}"


def _first_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


class ImageGenerationSkill(Skill):
    """根据文字描述生成图片。"""

    name = "image_generation"
    description = "根据文字描述生成图片"
    capabilities = ["image_generation"]
    supported_models = ["openai_compatible", "minimax"]

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.output_dir = Path(self.config.get("output_dir", "data/bots/_images"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if not self.default_model:
            self.default_model = self._resolve_model_name({})

    def _resolve_provider(self) -> str:
        provider = str(self.config.get("provider", "") or "").strip().lower()
        if provider in {"minimax"}:
            return "minimax"
        if provider in {"openai", "custom", "compatible", "openai_compatible", "openai-compatible"}:
            return "openai_compatible"

        model_hint = str(self.config.get("model", "") or "").strip().lower()
        if model_hint == "minimax" or isinstance(self.config.get("minimax"), dict):
            return "minimax"

        return "openai_compatible"

    def _resolve_model_name(self, params: dict[str, Any]) -> str:
        for value in (
            params.get("model"),
            self.config.get("model"),
            (self.config.get("openai") or {}).get("model") if isinstance(self.config.get("openai"), dict) else "",
        ):
            text = _first_text(value)
            if text and text not in {"openai", "custom", "compatible", "openai_compatible"}:
                return text
        return DEFAULT_IMAGE_MODEL

    def _resolve_api_key(self, provider: str, params: dict[str, Any]) -> str:
        provider_cfg = self.config.get(provider) if isinstance(self.config.get(provider), dict) else {}
        openai_cfg = self.config.get("openai") if isinstance(self.config.get("openai"), dict) else {}
        minimax_cfg = self.config.get("minimax") if isinstance(self.config.get("minimax"), dict) else {}

        candidates = [
            params.get("api_key"),
            self.config.get("api_key"),
            provider_cfg.get("api_key"),
        ]
        if provider == "minimax":
            candidates.extend([minimax_cfg.get("api_key"), os.environ.get("MINIMAX_API_KEY")])
        else:
            candidates.extend([openai_cfg.get("api_key"), os.environ.get("OPENAI_API_KEY")])

        model_adapter = params.get("model_adapter")
        if model_adapter is not None and hasattr(model_adapter, "api_key"):
            candidates.append(getattr(model_adapter, "api_key"))

        for value in candidates:
            text = _first_text(value)
            if text and not text.startswith("${"):
                return text
        return ""

    def _resolve_base_url(self, provider: str, params: dict[str, Any]) -> str:
        provider_cfg = self.config.get(provider) if isinstance(self.config.get(provider), dict) else {}
        openai_cfg = self.config.get("openai") if isinstance(self.config.get("openai"), dict) else {}
        minimax_cfg = self.config.get("minimax") if isinstance(self.config.get("minimax"), dict) else {}
        default = DEFAULT_MINIMAX_BASE_URL if provider == "minimax" else DEFAULT_OPENAI_BASE_URL

        candidates = [
            params.get("base_url"),
            self.config.get("base_url"),
            provider_cfg.get("base_url"),
        ]
        if provider == "minimax":
            candidates.append(minimax_cfg.get("base_url"))
        else:
            candidates.append(openai_cfg.get("base_url"))

        model_adapter = params.get("model_adapter")
        if model_adapter is not None and hasattr(model_adapter, "base_url"):
            candidates.append(getattr(model_adapter, "base_url"))

        for value in candidates:
            text = _first_text(value)
            if text:
                return _clean_base_url(text, default)
        return default

    def _check_config(self) -> bool:
        """检查配置是否完整。"""
        provider = self._resolve_provider()
        if provider not in self.supported_models:
            return False
        return bool(self._resolve_api_key(provider, {}))

    async def execute(self, params: dict, context: SkillContext) -> SkillResult:
        """执行图片生成。"""
        prompt = str(params.get("prompt") or params.get("text") or params.get("input") or "").strip()
        if not prompt:
            return SkillResult(success=False, content="缺少 prompt 参数")

        provider = self._resolve_provider()
        try:
            if provider == "minimax":
                return await self._generate_minimax(prompt, params)
            return await self._generate_openai_compatible(prompt, params)
        except Exception as exc:
            logger.error("[ImageGenerationSkill] 生成失败: %s", exc)
            return SkillResult(success=False, content=str(exc))

    async def _generate_openai_compatible(self, prompt: str, params: dict[str, Any]) -> SkillResult:
        """OpenAI-compatible Images API - POST /images/generations."""
        api_key = self._resolve_api_key("openai_compatible", params)
        if not api_key:
            return SkillResult(success=False, content="图片生成 API Key 未配置")

        base_url = self._resolve_base_url("openai_compatible", params)
        url = _endpoint_url(base_url, "/images/generations")
        model_name = self._resolve_model_name(params)

        payload: dict[str, Any] = {
            "model": model_name,
            "prompt": prompt,
            "n": int(params.get("n") or params.get("num") or self.config.get("num") or 1),
            "size": str(params.get("size") or self.config.get("size") or "1024x1024"),
        }
        response_format = params.get("response_format") or self.config.get("response_format")
        if response_format:
            payload["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status not in (200, 201):
                    error_text = await resp.text()
                    raise RuntimeError(f"Image API error {resp.status}: {error_text}")
                data = await resp.json()

            output_file, image_url = await self._save_first_image_from_response(session, data, "image")

        logger.info("[ImageGenerationSkill] OpenAI-compatible 生成成功: %s", output_file)
        return SkillResult(
            success=True,
            content=str(output_file),
            content_type="image",
            metadata={
                "provider": "openai_compatible",
                "model": model_name,
                "prompt": prompt,
                "image_url": image_url,
            },
        )

    async def _generate_minimax(self, prompt: str, params: dict[str, Any]) -> SkillResult:
        """MiniMax 图片生成 API - POST /image_generation."""
        api_key = self._resolve_api_key("minimax", params)
        if not api_key:
            return SkillResult(success=False, content="MiniMax API Key 未配置")

        base_url = self._resolve_base_url("minimax", params)
        url = _endpoint_url(base_url, "/image_generation")
        minimax_cfg = self.config.get("minimax") if isinstance(self.config.get("minimax"), dict) else {}
        model_name = (
            _first_text(params.get("model"))
            or _first_text(self.config.get("minimax_model"))
            or _first_text(minimax_cfg.get("model"))
            or _first_text(self.config.get("model"))
            or "image-01"
        )
        if model_name == "minimax":
            model_name = "image-01"

        payload = {
            "model": model_name,
            "prompt": prompt,
            "image_size": params.get("size", self.config.get("size", "1:1")),
            "image_num": int(params.get("num") or params.get("n") or self.config.get("num") or 1),
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"MiniMax image API error {resp.status}: {error_text}")
                data = await resp.json()

            output_file, image_url = await self._save_first_image_from_response(session, data, "minimax")

        logger.info("[ImageGenerationSkill] MiniMax 生成成功: %s", output_file)
        return SkillResult(
            success=True,
            content=str(output_file),
            content_type="image",
            metadata={
                "provider": "minimax",
                "model": model_name,
                "prompt": prompt,
                "image_url": image_url,
            },
        )

    async def _save_first_image_from_response(
        self,
        session: aiohttp.ClientSession,
        data: Any,
        filename_prefix: str,
    ) -> tuple[Path, str]:
        image_url, image_b64 = self._extract_image_payload(data)
        output_file = self.output_dir / f"{filename_prefix}_{uuid.uuid4().hex[:8]}.png"

        if image_b64:
            output_file.write_bytes(base64.b64decode(image_b64))
            return output_file, ""

        if image_url:
            async with session.get(image_url) as img_resp:
                if img_resp.status != 200:
                    raise RuntimeError(f"下载图片失败: {img_resp.status}")
                output_file.write_bytes(await img_resp.read())
            return output_file, image_url

        raise RuntimeError("未获取到图片 URL 或 base64 数据")

    def _extract_image_payload(self, data: Any) -> tuple[str, str]:
        """Return (url, b64) from common OpenAI-compatible and MiniMax shapes."""
        if not isinstance(data, dict):
            return "", ""

        candidates: list[Any] = []
        raw_data = data.get("data")
        if isinstance(raw_data, list):
            candidates.extend(raw_data)
        elif isinstance(raw_data, dict):
            for key in ("image_urls", "images"):
                value = raw_data.get(key)
                if isinstance(value, list):
                    candidates.extend(value)
            candidates.append(raw_data)

        for key in ("images", "image_urls"):
            value = data.get(key)
            if isinstance(value, list):
                candidates.extend(value)

        for item in candidates:
            if isinstance(item, str):
                if item.startswith(("http://", "https://")):
                    return item, ""
                return "", item
            if not isinstance(item, dict):
                continue
            url = _first_text(item.get("url") or item.get("image_url"))
            b64 = _first_text(item.get("b64_json") or item.get("base64") or item.get("image_base64"))
            if url or b64:
                return url, b64

        url = _first_text(data.get("url") or data.get("image_url"))
        b64 = _first_text(data.get("b64_json") or data.get("base64") or data.get("image_base64"))
        return url, b64
