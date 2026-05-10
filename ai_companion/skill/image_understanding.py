"""Image understanding skill with structured vision output."""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
from pathlib import Path
from typing import Any

import aiohttp

from .base import Skill, SkillContext, SkillResult

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30)
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MINIMAX_BASE_URL = "https://api.minimax.chat/v1"


def _clean_base_url(value: str | None, default: str) -> str:
    return str(value or default).strip().rstrip("/")


def _endpoint_url(base_url: str, endpoint: str) -> str:
    base = base_url.strip().rstrip("/")
    normalized_endpoint = "/" + endpoint.strip("/")
    if base.endswith(normalized_endpoint):
        return base
    return f"{base}{normalized_endpoint}"


class ImageUnderstandingSkill(Skill):
    """Understand image content and return normalized JSON result."""

    name = "image_understanding"
    description = "理解图片内容并输出结构化结果"
    capabilities = ["image_understanding", "vision"]
    supported_models = ["openai_compatible", "openai", "minimax", "custom"]

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.max_image_size_mb = int(self.config.get("max_image_size_mb", 8) or 8)
        self.max_images_per_message = int(self.config.get("max_images_per_message", 3) or 3)
        self.timeout = DEFAULT_TIMEOUT
        self._session: aiohttp.ClientSession | None = None

    def _resolve_provider(self) -> str:
        provider = str(self.config.get("provider", "") or "").strip().lower()
        if provider in {"openai", "custom", "compatible", "openai_compatible", "openai-compatible"}:
            return "openai_compatible" if provider != "custom" else "custom"
        if provider:
            return provider

        # old-style compatibility: model is provider key and provider block exists
        model_hint = str(self.config.get("model", "") or "").strip().lower()
        if model_hint in {"openai", "minimax", "custom"} and isinstance(self.config.get(model_hint), dict):
            return "openai_compatible" if model_hint == "openai" else model_hint

        for candidate in ("openai", "minimax", "custom"):
            if isinstance(self.config.get(candidate), dict):
                return "openai_compatible" if candidate == "openai" else candidate

        # default to openai-compatible path for common vision models (e.g. gpt-4o)
        return "openai_compatible"

    def _resolve_model_name(self, provider: str, params: dict[str, Any]) -> str:
        model_from_params = str(params.get("model", "") or "").strip()
        if model_from_params:
            return model_from_params

        model_from_config = str(self.config.get("model", "") or "").strip()
        provider_tokens = {"openai", "minimax", "custom", "compatible", "openai_compatible", "openai-compatible"}
        if model_from_config and model_from_config not in provider_tokens:
            return model_from_config

        provider_cfg = self.config.get(provider) if isinstance(self.config.get(provider), dict) else {}
        if provider == "openai_compatible" and not provider_cfg:
            provider_cfg = self.config.get("openai") if isinstance(self.config.get("openai"), dict) else {}
        provider_model = str(provider_cfg.get("model", "") or "").strip()
        if provider_model:
            return provider_model

        if provider == "minimax":
            return "MiniMax-M2.7"
        return "gpt-4o"

    def _check_config(self) -> bool:
        provider = self._resolve_provider()
        if provider not in self.supported_models:
            return False
        if provider == "openai_compatible":
            openai_cfg = self.config.get("openai") if isinstance(self.config.get("openai"), dict) else {}
            return bool(os.environ.get("OPENAI_API_KEY") or self.config.get("api_key") or openai_cfg.get("api_key"))
        if provider == "minimax":
            return bool(os.environ.get("MINIMAX_API_KEY") or self.config.get("api_key") or (self.config.get("minimax") or {}).get("api_key"))
        if provider == "custom":
            custom_cfg = self.config.get("custom") if isinstance(self.config.get("custom"), dict) else {}
            api_url = custom_cfg.get("api_url") or custom_cfg.get("base_url") or self.config.get("api_url") or self.config.get("base_url")
            auth_type = str(custom_cfg.get("auth_type", self.config.get("auth_type", "bearer")) or "bearer").strip().lower()
            if auth_type == "none":
                return bool(api_url)
            return bool(api_url and (custom_cfg.get("api_key") or self.config.get("api_key")))
        return False

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def execute(self, params: dict, context: SkillContext) -> SkillResult:
        provider = self._resolve_provider()
        if provider not in self.supported_models:
            return SkillResult(success=False, content=f"不支持的 provider: {provider}")

        image_inputs = params.get("image_paths") or params.get("image_urls") or params.get("media_urls") or []
        if isinstance(image_inputs, str):
            image_inputs = [image_inputs]
        image_inputs = [str(item).strip() for item in image_inputs if str(item).strip()]
        if not image_inputs:
            return SkillResult(success=False, content="缺少图片输入（image_paths/image_urls）")

        prompt = str(params.get("prompt") or params.get("text") or "请描述图片内容并提取关键细节。").strip()
        if not prompt:
            prompt = "请描述图片内容并提取关键细节。"

        try:
            image_parts, skipped = self._build_image_parts(image_inputs)
        except ValueError as exc:
            return SkillResult(success=False, content=str(exc))

        if not image_parts:
            return SkillResult(success=False, content="没有可用图片可供理解")

        try:
            if provider == "openai_compatible":
                raw = await self._analyze_openai(prompt, image_parts, params)
            elif provider == "minimax":
                raw = await self._analyze_minimax(prompt, image_parts, params)
            else:
                raw = await self._analyze_custom(prompt, image_parts, params)
        except Exception as exc:
            logger.error("[ImageUnderstandingSkill] provider=%s failed: %s", provider, exc)
            return SkillResult(success=False, content=str(exc))

        normalized = self._normalize_output(raw)
        if skipped:
            normalized["safety_notes"].extend(skipped)
        return SkillResult(
            success=True,
            content=normalized,
            content_type="text",
            metadata={
                "provider": provider,
                "model": self._resolve_model_name(provider, params),
                "images": len(image_parts),
            },
        )

    def _build_image_parts(self, image_inputs: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
        image_parts: list[dict[str, Any]] = []
        skipped: list[str] = []
        max_bytes = self.max_image_size_mb * 1024 * 1024

        for raw in image_inputs:
            if len(image_parts) >= self.max_images_per_message:
                skipped.append(f"超过最大图片数量限制，已截断到 {self.max_images_per_message} 张")
                break

            candidate = raw.strip()
            if not candidate:
                continue

            if candidate.startswith("http://") or candidate.startswith("https://"):
                image_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": candidate, "detail": "auto"},
                    }
                )
                continue

            path = Path(candidate).expanduser()
            if not path.exists() or not path.is_file():
                skipped.append(f"图片不存在或不可读: {candidate}")
                continue
            if path.stat().st_size > max_bytes:
                skipped.append(f"图片过大已跳过: {path.name}")
                continue

            mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
            if not mime_type.startswith("image/"):
                skipped.append(f"非图片类型已跳过: {path.name}")
                continue

            b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
            data_url = f"data:{mime_type};base64,{b64}"
            image_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": data_url, "detail": "auto"},
                }
            )

        return image_parts, skipped

    def _vision_prompt(self, prompt: str) -> str:
        return (
            "你是图片理解助手。请严格输出 JSON 对象，不要输出 Markdown。\n"
            "字段：summary(string), objects(array[string]), text_ocr(string), "
            "safety_notes(array[string]), confidence(number 0~1)。\n"
            f"用户问题：{prompt}"
        )

    async def _analyze_openai(self, prompt: str, image_parts: list[dict[str, Any]], params: dict[str, Any]) -> str:
        model_name = self._resolve_model_name("openai_compatible", params)
        openai_cfg = self.config.get("openai") if isinstance(self.config.get("openai"), dict) else {}
        api_key = str(
            params.get("api_key")
            or self.config.get("api_key")
            or openai_cfg.get("api_key")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        ).strip()
        if not api_key:
            raise RuntimeError("图片理解 API Key 未配置")

        base_url = str(
            params.get("base_url")
            or self.config.get("base_url")
            or openai_cfg.get("base_url")
            or DEFAULT_OPENAI_BASE_URL
        ).strip().rstrip("/")
        url = _endpoint_url(base_url, "/chat/completions")

        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": self._vision_prompt(prompt)}, *image_parts],
                }
            ],
            "temperature": 0.2,
            "max_tokens": int(params.get("max_tokens", 800) or 800),
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        session = await self._get_session()
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"OpenAI image understanding error {resp.status}: {text}")
            data = await resp.json()
            return str(data.get("choices", [{}])[0].get("message", {}).get("content", "") or "")

    async def _analyze_minimax(self, prompt: str, image_parts: list[dict[str, Any]], params: dict[str, Any]) -> str:
        model_name = self._resolve_model_name("minimax", params)
        api_key = str(
            params.get("api_key")
            or self.config.get("api_key")
            or (self.config.get("minimax") or {}).get("api_key")
            or os.environ.get("MINIMAX_API_KEY")
            or ""
        ).strip()
        if not api_key:
            raise RuntimeError("MINIMAX_API_KEY 未配置")

        base_url = str(
            params.get("base_url")
            or self.config.get("base_url")
            or (self.config.get("minimax") or {}).get("base_url")
            or DEFAULT_MINIMAX_BASE_URL
        ).strip().rstrip("/")
        url = _endpoint_url(base_url, "/text/chatcompletion_v2")

        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "name": "user",
                    "content": self._vision_prompt(prompt),
                }
            ],
            # 某些 provider 兼容层会支持 images 字段；不支持时服务端返回明确错误并被降级处理
            "images": image_parts,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        session = await self._get_session()
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"MiniMax image understanding error {resp.status}: {text}")
            data = await resp.json()
            choices = data.get("choices") if isinstance(data, dict) else []
            if not choices:
                return ""
            message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
            return str(message.get("content") or message.get("reasoning_content") or "")

    async def _analyze_custom(self, prompt: str, image_parts: list[dict[str, Any]], params: dict[str, Any]) -> str:
        custom_cfg = self.config.get("custom") if isinstance(self.config.get("custom"), dict) else {}
        explicit_api_url = str(params.get("api_url") or custom_cfg.get("api_url") or self.config.get("api_url") or "").strip()
        base_url = str(params.get("base_url") or custom_cfg.get("base_url") or self.config.get("base_url") or "").strip()
        api_url = explicit_api_url.rstrip("/") if explicit_api_url else base_url.rstrip("/")
        if not api_url:
            raise RuntimeError("custom image understanding 缺少 api_url/base_url")
        if not explicit_api_url:
            api_url = _endpoint_url(api_url, "/chat/completions")

        auth_type = str(params.get("auth_type") or custom_cfg.get("auth_type") or self.config.get("auth_type") or "bearer").strip().lower()
        api_key = str(
            params.get("api_key")
            or custom_cfg.get("api_key")
            or self.config.get("api_key")
            or ""
        ).strip()
        model_name = self._resolve_model_name("custom", params)

        headers = {"Content-Type": "application/json"}
        if auth_type == "bearer" and api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        elif auth_type == "api_key" and api_key:
            headers["X-API-Key"] = api_key

        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": self._vision_prompt(prompt)}, *image_parts],
                }
            ],
        }

        session = await self._get_session()
        async with session.post(api_url, headers=headers, json=payload) as resp:
            if resp.status not in (200, 201):
                text = await resp.text()
                raise RuntimeError(f"Custom image understanding error {resp.status}: {text}")
            data = await resp.json()
            return str(
                data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if isinstance(data, dict)
                else ""
            )

    def _normalize_output(self, raw: str) -> dict[str, Any]:
        text = (raw or "").strip()
        payload: dict[str, Any] | None = None
        if text:
            payload = self._try_parse_json(text)
        if payload is None:
            payload = {
                "summary": text[:800] if text else "未能解析结构化结果",
                "objects": [],
                "text_ocr": "",
                "safety_notes": [],
                "confidence": 0.4 if text else 0.0,
            }

        summary = str(payload.get("summary", "") or "").strip()
        objects = payload.get("objects") if isinstance(payload.get("objects"), list) else []
        objects = [str(item).strip() for item in objects if str(item).strip()]
        text_ocr = str(payload.get("text_ocr", "") or "").strip()
        safety_notes = payload.get("safety_notes") if isinstance(payload.get("safety_notes"), list) else []
        safety_notes = [str(item).strip() for item in safety_notes if str(item).strip()]
        try:
            confidence = float(payload.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        return {
            "summary": summary,
            "objects": objects,
            "text_ocr": text_ocr,
            "safety_notes": safety_notes,
            "confidence": confidence,
        }

    def _try_parse_json(self, text: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

        left = text.find("{")
        right = text.rfind("}")
        if left >= 0 and right > left:
            snippet = text[left:right + 1]
            try:
                parsed = json.loads(snippet)
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None
        return None
