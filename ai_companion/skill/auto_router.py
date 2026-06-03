"""Automatic router for built-in multimodal capabilities."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .base import SkillContext, SkillResult
from .command import format_skill_result
from .dispatcher import SkillDispatcher

logger = logging.getLogger(__name__)


_DRAW_KEYWORDS = (
    "甯垜鐢?",
    "缁欐垜鐢?",
    "鐢讳竴寮?",
    "鐢讳釜",
    "鐢熸垚涓€寮犲浘",
    "鐢熸垚鍥剧墖",
    "鏉ュ紶鍥?",
    "鍋氫竴寮犲浘",
    "draw",
    "create image",
    "generate image",
    "make an image",
)

_PHOTO_CAPTURE_KEYWORDS = (
    "鎷嶇収",
    "鎷嶄竴寮?",
    "鎷嶅紶",
    "鎷嶄釜鐓?",
    "鎷嶄釜鐓х墖",
    "鎷嶇収鐗?",
    "鏉ュ紶鐓х墖",
    "鏉ュ紶鐩哥墖",
    "缁欐垜鎷?",
    "甯垜鎷?",
    "take a photo",
    "take photo",
    "shoot a photo",
    "snap a photo",
)

_PHOTO_CAPTURE_STYLE_SUFFIX = (
    "椋庢牸瑕佹眰锛氭ā鎷熻亰澶╁璞″綋涓嬮殢鎵嬫媿鐨勭湡瀹炵収鐗囨晥鏋滐紝"
    "鎵嬫満鎽勫奖璐ㄦ劅锛岃嚜鐒跺厜锛屼笉杩囧害淇浘锛岄潪鎻掔敾銆"
)


@dataclass
class AutoSkillRouteResult:
    handled: bool = False
    direct_response: str = ""
    bot_visible_context: str = ""
    user_facing_hint: str = ""
    route: str = ""


class AutoSkillRouter:
    def __init__(self, dispatcher: SkillDispatcher):
        self.dispatcher = dispatcher

    async def try_handle(
        self,
        runtime_input: dict[str, Any],
        context: SkillContext,
        capability_statuses: dict[str, dict[str, Any]] | None,
    ) -> AutoSkillRouteResult:
        capability_statuses = capability_statuses or {}
        media_urls = runtime_input.get("media_urls") if isinstance(runtime_input.get("media_urls"), list) else []
        media_types = runtime_input.get("media_types") if isinstance(runtime_input.get("media_types"), list) else []
        text = str(runtime_input.get("text") or "").strip()

        if media_urls and self._has_image_media(media_types):
            image_route = await self._route_image_understanding(text, media_urls, context, capability_statuses)
            if image_route is not None:
                return image_route

        if self._is_draw_intent(text):
            draw_route = await self._route_image_generation(text, context, capability_statuses)
            if draw_route is not None:
                return draw_route

        return AutoSkillRouteResult()

    async def _route_image_understanding(
        self,
        text: str,
        media_urls: list[str],
        context: SkillContext,
        capability_statuses: dict[str, dict[str, Any]],
    ) -> AutoSkillRouteResult | None:
        status = capability_statuses.get("image_understanding") or {}
        if not bool(status.get("auto", False)):
            return None

        if not bool(status.get("enabled", False)):
            return None

        skill = self.dispatcher.get("image_understanding")
        if skill is None or not skill.is_available():
            return AutoSkillRouteResult(
                handled=False,
                user_facing_hint="当前未启用图片理解能力。",
                route="image_understanding",
            )

        try:
            result = await self.dispatcher.execute(
                "image_understanding",
                {
                    "media_urls": media_urls,
                    "prompt": text or "请理解图片内容并提取关键信息。",
                },
                context,
            )
        except Exception as exc:
            logger.warning("[AutoSkillRouter] image_understanding failed: %s", exc)
            return AutoSkillRouteResult(route="image_understanding")

        if not result.success:
            return AutoSkillRouteResult(route="image_understanding")

        return AutoSkillRouteResult(
            handled=False,
            bot_visible_context=self._format_image_understanding_context(result),
            route="image_understanding",
        )

    async def _route_image_generation(
        self,
        text: str,
        context: SkillContext,
        capability_statuses: dict[str, dict[str, Any]],
    ) -> AutoSkillRouteResult | None:
        status = capability_statuses.get("image_generation") or {}
        if not bool(status.get("auto", False)):
            return None

        if not bool(status.get("enabled", False)):
            return None

        skill = self.dispatcher.get("image_generation")
        if skill is None or not skill.is_available():
            return AutoSkillRouteResult(
                handled=True,
                direct_response="当前未启用图片生成功能。",
                route="image_generation",
            )

        try:
            prompt = self._build_generation_prompt(text)
            result = await self.dispatcher.execute("image_generation", {"prompt": prompt}, context)
        except Exception as exc:
            logger.warning("[AutoSkillRouter] image_generation failed: %s", exc)
            return AutoSkillRouteResult(
                handled=True,
                direct_response="[Skill Error] 图片生成失败",
                route="image_generation",
            )

        return AutoSkillRouteResult(
            handled=True,
            direct_response=format_skill_result(result),
            route="image_generation",
        )

    def _has_image_media(self, media_types: list[str]) -> bool:
        if not media_types:
            return True
        return any(str(mime).startswith("image/") for mime in media_types)

    def _is_draw_intent(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        return (
            any(keyword in lowered for keyword in _DRAW_KEYWORDS)
            or "draw" in lowered
            or "image" in lowered
            or self._contains_any_char(text, "画圖图")
            or self._is_photo_capture_intent(text)
        )

    def _is_photo_capture_intent(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        return (
            any(keyword in lowered for keyword in _PHOTO_CAPTURE_KEYWORDS)
            or "photo" in lowered
            or self._contains_any_char(text, "拍照摄")
        )

    def _contains_any_char(self, text: str, chars: str) -> bool:
        return any(ch in text for ch in chars)

    def _build_generation_prompt(self, text: str) -> str:
        raw = (text or "").strip()
        if not raw:
            return raw
        if self._is_photo_capture_intent(raw):
            return f"{raw}\n{_PHOTO_CAPTURE_STYLE_SUFFIX}"
        return raw

    def _format_image_understanding_context(self, result: SkillResult) -> str:
        content = result.content if isinstance(result.content, dict) else {}
        summary = str(content.get("summary", "") or "").strip()
        objects = content.get("objects") if isinstance(content.get("objects"), list) else []
        objects = [str(item).strip() for item in objects if str(item).strip()]
        text_ocr = str(content.get("text_ocr", "") or "").strip()
        safety_notes = content.get("safety_notes") if isinstance(content.get("safety_notes"), list) else []
        safety_notes = [str(item).strip() for item in safety_notes if str(item).strip()]
        confidence = content.get("confidence")
        confidence_text = ""
        if isinstance(confidence, (int, float)):
            confidence_text = f"{float(confidence):.2f}"

        lines: list[str] = ["[图片理解结果]"]
        if summary:
            lines.append(f"图片摘要: {summary}")
        if objects:
            lines.append(f"识别到元素: {', '.join(objects)}")
        if text_ocr:
            lines.append(f"OCR文本: {text_ocr}")
        if confidence_text:
            lines.append(f"置信度: {confidence_text}")
        if safety_notes:
            lines.append(f"注意事项: {'; '.join(safety_notes)}")
        lines.append("使用方式：这是对用户发送图片的自动分析结果。当你提到图片中的内容时，请说明\"从你发的图片里我看到...\"，不要表现得像你本来就知道这些信息。")
        return "" if len(lines) == 1 else "\n".join(lines)
