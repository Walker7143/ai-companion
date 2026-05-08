"""Builtin skill registration and runtime capability status updates."""

from __future__ import annotations

import importlib.util
import os
from copy import deepcopy
from typing import Any

from .dispatcher import SkillDispatcher
from .image_generation import ImageGenerationSkill
from .image_understanding import ImageUnderstandingSkill
from .tts import TTSSkill


class BuiltinSkillManager:
    """Register builtin skills and fill runtime capability status."""

    _BUILTINS: dict[str, type] = {
        "image_generation": ImageGenerationSkill,
        "image_understanding": ImageUnderstandingSkill,
        "tts": TTSSkill,
    }

    _AUTO_DEFAULTS: dict[str, bool] = {
        "image_generation": True,
        "image_understanding": True,
        "tts": False,
    }

    def __init__(self, dispatcher: SkillDispatcher):
        self.dispatcher = dispatcher

    def register(
        self,
        skill_config: dict[str, Any] | None,
        capability_statuses: dict[str, dict[str, Any]] | None,
    ) -> dict[str, dict[str, Any]]:
        skill_config = skill_config if isinstance(skill_config, dict) else {}
        statuses: dict[str, dict[str, Any]] = deepcopy(capability_statuses or {})

        for skill_name, skill_cls in self._BUILTINS.items():
            raw_cfg = skill_config.get(skill_name)
            if not isinstance(raw_cfg, dict):
                statuses[skill_name] = self._build_unconfigured_status(skill_name)
                continue

            cfg = dict(raw_cfg)
            enabled = bool(cfg.get("enabled", True))
            provider = str(cfg.get("provider", "") or statuses.get(skill_name, {}).get("provider", "")).strip()
            model = str(cfg.get("model", "") or statuses.get(skill_name, {}).get("model", "")).strip()
            auto = bool(cfg.get("auto", statuses.get(skill_name, {}).get("auto", self._AUTO_DEFAULTS.get(skill_name, False))))

            status = statuses.get(skill_name) or {}
            status.update(
                {
                    "name": skill_name,
                    "source": "builtin",
                    "enabled": enabled,
                    "auto": auto,
                    "registered": False,
                    "available": False,
                    "reason": "disabled_by_config" if not enabled else "",
                    "provider": provider,
                    "model": model,
                }
            )

            if not enabled:
                statuses[skill_name] = status
                continue

            try:
                skill = skill_cls(cfg)
                self.dispatcher.register(skill)
                available = bool(skill.is_available())
                status["registered"] = True
                status["available"] = available
                status["reason"] = "" if available else self._infer_unavailable_reason(skill_name, skill, cfg, provider)
                status["provider"] = provider or getattr(skill, "default_model", "") or ""
                status["model"] = model or getattr(skill, "default_model", "") or ""
            except Exception as exc:
                status["registered"] = False
                status["available"] = False
                status["reason"] = f"registration_failed:{type(exc).__name__}"

            statuses[skill_name] = status

        return statuses

    def _build_unconfigured_status(self, skill_name: str) -> dict[str, Any]:
        return {
            "name": skill_name,
            "source": "builtin",
            "enabled": False,
            "auto": self._AUTO_DEFAULTS.get(skill_name, False),
            "registered": False,
            "available": False,
            "reason": "not_configured",
            "provider": "",
            "model": "",
        }

    def _infer_unavailable_reason(self, skill_name: str, skill: Any, cfg: dict[str, Any], provider: str) -> str:
        provider_name = (provider or cfg.get("model") or getattr(skill, "default_model", "") or "").strip()
        if provider_name and provider_name not in getattr(skill, "supported_models", []):
            return f"provider_not_supported:{provider_name}"

        if skill_name == "image_generation":
            has_key = bool(
                os.environ.get("MINIMAX_API_KEY")
                or cfg.get("api_key")
                or (cfg.get("minimax") or {}).get("api_key")
            )
            if not has_key:
                return "missing_api_key:MINIMAX_API_KEY"
            return "unavailable_runtime_check"

        if skill_name == "tts":
            provider_name = provider_name or "edge_tts"
            if provider_name == "edge_tts":
                if importlib.util.find_spec("edge_tts") is None:
                    return "missing_dependency:edge_tts"
                return "unavailable_runtime_check"
            if provider_name == "minimax":
                has_key = bool(
                    os.environ.get("MINIMAX_API_KEY")
                    or cfg.get("api_key")
                    or (cfg.get("minimax") or {}).get("api_key")
                )
                if not has_key:
                    return "missing_api_key:MINIMAX_API_KEY"
                return "unavailable_runtime_check"
            if provider_name in {"azure_tts", "openai_tts"}:
                model_cfg = cfg.get(provider_name) if isinstance(cfg.get(provider_name), dict) else {}
                if not model_cfg.get("api_url") or not model_cfg.get("api_key"):
                    return f"missing_provider_config:{provider_name}"
                return "unavailable_runtime_check"
            return "unavailable_runtime_check"

        if skill_name == "image_understanding":
            provider_name = (provider_name or "openai").lower()
            if provider_name == "openai":
                has_key = bool(
                    os.environ.get("OPENAI_API_KEY")
                    or cfg.get("api_key")
                    or (cfg.get("openai") or {}).get("api_key")
                )
                if not has_key:
                    return "missing_api_key:OPENAI_API_KEY"
                return "unavailable_runtime_check"
            if provider_name == "minimax":
                has_key = bool(
                    os.environ.get("MINIMAX_API_KEY")
                    or cfg.get("api_key")
                    or (cfg.get("minimax") or {}).get("api_key")
                )
                if not has_key:
                    return "missing_api_key:MINIMAX_API_KEY"
                return "unavailable_runtime_check"
            if provider_name == "custom":
                custom_cfg = cfg.get("custom") if isinstance(cfg.get("custom"), dict) else {}
                api_url = custom_cfg.get("api_url") or custom_cfg.get("base_url") or cfg.get("api_url") or cfg.get("base_url")
                auth_type = str(custom_cfg.get("auth_type", cfg.get("auth_type", "bearer")) or "bearer").strip().lower()
                if not api_url:
                    return "missing_provider_config:custom.api_url"
                if auth_type != "none" and not (custom_cfg.get("api_key") or cfg.get("api_key")):
                    return "missing_provider_config:custom.api_key"
                return "unavailable_runtime_check"
            return f"provider_not_supported:{provider_name}"

        return "unavailable_runtime_check"
