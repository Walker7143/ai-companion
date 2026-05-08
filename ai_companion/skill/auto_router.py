"""Automatic skill router for runtime text/media input."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .base import SkillContext, SkillResult
from .command import format_skill_result
from .dispatcher import SkillDispatcher

logger = logging.getLogger(__name__)


_DRAW_KEYWORDS = (
    "帮我画",
    "给我画",
    "画一张",
    "画个",
    "生成一张图",
    "生成图片",
    "来张图",
    "做一张图",
    "draw",
    "create image",
    "generate image",
    "make an image",
)

_PHOTO_CAPTURE_KEYWORDS = (
    "拍照",
    "拍一张",
    "拍张",
    "拍个照",
    "拍个照片",
    "拍照片",
    "来张照片",
    "来张相片",
    "给我拍",
    "帮我拍",
    "take a photo",
    "take photo",
    "shoot a photo",
    "snap a photo",
)

_PHOTO_CAPTURE_STYLE_SUFFIX = (
    "风格要求：模拟聊天对象当下随手拍的真实照片效果，"
    "手机摄影质感，自然光，不过度修图，非插画。"
)

_ACTIONABLE_HINTS = (
    "帮我",
    "请",
    "能不能",
    "可以",
    "查询",
    "查一下",
    "搜索",
    "生成",
    "翻译",
    "总结",
    "分析",
    "计算",
    "读取",
    "提取",
    "执行",
    "提醒",
    "weather",
    "search",
    "translate",
    "summarize",
    "calculate",
)

InstalledSkillPlanner = Callable[[str, list[dict[str, Any]], SkillContext], Awaitable[dict[str, Any] | None]]


@dataclass
class AutoSkillRouteResult:
    """Result returned by auto router."""

    handled: bool = False
    direct_response: str = ""
    bot_visible_context: str = ""
    user_facing_hint: str = ""
    route: str = ""


class AutoSkillRouter:
    """Rule-based auto skill router (Phase 8.3)."""

    def __init__(
        self,
        dispatcher: SkillDispatcher,
        installed_skill_planner: InstalledSkillPlanner | None = None,
    ):
        self.dispatcher = dispatcher
        self.installed_skill_planner = installed_skill_planner

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

        # Rule 1: image message first
        if media_urls and self._has_image_media(media_types):
            image_route = await self._route_image_understanding(text, media_urls, context, capability_statuses)
            if image_route is not None:
                return image_route

        # Rule 2: draw intent
        if self._is_draw_intent(text):
            draw_route = await self._route_image_generation(text, context, capability_statuses)
            if draw_route is not None:
                return draw_route

        # Rule 3: installed skills (keyword + planner)
        installed_route = await self._route_installed_skill(text, context, capability_statuses)
        if installed_route is not None:
            return installed_route

        # Rule 4: no interception
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
            logger.debug("[AutoSkillRouter] image_understanding auto disabled")
            return None

        if not bool(status.get("enabled", False)):
            logger.info("[AutoSkillRouter] image_understanding disabled by config")
            return AutoSkillRouteResult(
                handled=False,
                user_facing_hint="当前未启用图片理解能力。",
                route="image_understanding",
            )

        skill = self.dispatcher.get("image_understanding")
        if skill is None or not skill.is_available():
            logger.info("[AutoSkillRouter] image_understanding unavailable")
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
            logger.warning("[AutoSkillRouter] image_understanding failed, fallback to chat: %s", exc)
            return AutoSkillRouteResult(route="image_understanding")

        if not result.success:
            logger.info("[AutoSkillRouter] image_understanding result failed: %s", result.content)
            return AutoSkillRouteResult(route="image_understanding")

        bot_context = self._format_image_understanding_context(result)
        return AutoSkillRouteResult(
            handled=False,
            bot_visible_context=bot_context,
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
            logger.debug("[AutoSkillRouter] image_generation auto disabled")
            return None

        if not bool(status.get("enabled", False)):
            logger.info("[AutoSkillRouter] image_generation disabled by config")
            return AutoSkillRouteResult(
                handled=True,
                direct_response="当前未启用图片生成能力。",
                route="image_generation",
            )

        skill = self.dispatcher.get("image_generation")
        if skill is None or not skill.is_available():
            logger.info("[AutoSkillRouter] image_generation unavailable")
            return AutoSkillRouteResult(
                handled=True,
                direct_response="当前未启用图片生成能力。",
                route="image_generation",
            )

        try:
            prompt = self._build_generation_prompt(text)
            result = await self.dispatcher.execute(
                "image_generation",
                {"prompt": prompt},
                context,
            )
        except Exception as exc:
            logger.warning("[AutoSkillRouter] image_generation failed, fallback to error text: %s", exc)
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
        return any(keyword in lowered for keyword in _DRAW_KEYWORDS) or self._is_photo_capture_intent(text)

    def _is_photo_capture_intent(self, text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        return any(keyword in lowered for keyword in _PHOTO_CAPTURE_KEYWORDS)

    def _build_generation_prompt(self, text: str) -> str:
        raw = (text or "").strip()
        if not raw:
            return raw
        if self._is_photo_capture_intent(raw):
            return f"{raw}\n{_PHOTO_CAPTURE_STYLE_SUFFIX}"
        return raw

    async def _route_installed_skill(
        self,
        text: str,
        context: SkillContext,
        capability_statuses: dict[str, dict[str, Any]],
    ) -> AutoSkillRouteResult | None:
        text = (text or "").strip()
        if not text or text.startswith("/"):
            return None

        candidates: list[dict[str, Any]] = []
        for skill_name, status in capability_statuses.items():
            if status.get("source") != "installed":
                continue
            if not bool(status.get("enabled", False)):
                continue
            if not bool(status.get("auto", False)):
                continue
            if not bool(status.get("available", False)):
                continue

            keywords = self._normalize_keywords(status.get("routing_keywords") or status.get("auto_keywords"))
            threshold = self._normalize_threshold(status.get("confidence_threshold"))
            candidates.append(
                {
                    "name": skill_name,
                    "description": str(status.get("description", "") or ""),
                    "capabilities": status.get("capabilities") if isinstance(status.get("capabilities"), list) else [],
                    "keywords": keywords,
                    "confidence_threshold": threshold,
                }
            )

        if not candidates:
            return None

        keyword_candidate = self._match_keyword_candidate(text, candidates)
        if keyword_candidate:
            return await self._execute_installed_skill(
                keyword_candidate["name"],
                {"input": text, "text": text, "prompt": text},
                context,
                route=f"installed:{keyword_candidate['name']}:keyword",
            )

        if not self.installed_skill_planner:
            return None
        if not self._looks_actionable_text(text):
            return None

        try:
            plan = await self.installed_skill_planner(text, candidates, context)
        except Exception as exc:
            logger.warning("[AutoSkillRouter] installed skill planner failed: %s", exc)
            return None

        if not isinstance(plan, dict):
            return None
        selected = str(plan.get("skill") or "").strip()
        if not selected:
            return None

        candidate_map = {item["name"]: item for item in candidates}
        candidate = candidate_map.get(selected)
        if candidate is None:
            logger.info("[AutoSkillRouter] planner selected unknown installed skill: %s", selected)
            return None

        confidence = self._normalize_confidence(plan.get("confidence"))
        threshold = float(candidate.get("confidence_threshold", 0.72))
        if confidence < threshold:
            logger.info(
                "[AutoSkillRouter] planner confidence too low for %s: %.2f < %.2f",
                selected,
                confidence,
                threshold,
            )
            return None

        params = plan.get("params") if isinstance(plan.get("params"), dict) else {}
        params = dict(params)
        if not params:
            params = {"input": text, "text": text, "prompt": text}
        else:
            if "input" not in params:
                params["input"] = text

        return await self._execute_installed_skill(
            selected,
            params,
            context,
            route=f"installed:{selected}:planner",
        )

    async def _execute_installed_skill(
        self,
        skill_name: str,
        params: dict[str, Any],
        context: SkillContext,
        route: str,
    ) -> AutoSkillRouteResult:
        result = await self.dispatcher.execute(skill_name, params, context)
        return AutoSkillRouteResult(
            handled=True,
            direct_response=format_skill_result(result),
            route=route,
        )

    def _normalize_keywords(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip().lower() for item in value if str(item).strip()]

    def _normalize_threshold(self, value: Any) -> float:
        try:
            threshold = float(value)
        except (TypeError, ValueError):
            threshold = 0.72
        if threshold < 0:
            return 0.0
        if threshold > 1:
            return 1.0
        return threshold

    def _normalize_confidence(self, value: Any) -> float:
        try:
            conf = float(value)
        except (TypeError, ValueError):
            return 0.0
        if conf < 0:
            return 0.0
        if conf > 1:
            return 1.0
        return conf

    def _match_keyword_candidate(self, text: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        lowered = text.lower()
        for candidate in candidates:
            keywords = candidate.get("keywords") or []
            if any(keyword in lowered for keyword in keywords):
                return candidate
        return None

    def _looks_actionable_text(self, text: str) -> bool:
        lowered = (text or "").lower()
        if any(hint in lowered for hint in _ACTIONABLE_HINTS):
            return True
        if lowered.endswith(("?", "？", "!", "！")):
            return True
        return False

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
        return "" if len(lines) == 1 else "\n".join(lines)
