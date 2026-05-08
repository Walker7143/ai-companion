"""Resolve skill configuration and build baseline capability status."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


_AUTO_DEFAULTS: dict[str, bool] = {
    "image_generation": True,
    "image_understanding": True,
    "tts": False,
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _infer_provider(skill_name: str, cfg: dict[str, Any]) -> str:
    provider = str(cfg.get("provider", "") or "").strip()
    if provider:
        return provider

    model_hint = str(cfg.get("model", "") or "").strip()
    if model_hint and isinstance(cfg.get(model_hint), dict):
        return model_hint

    if skill_name == "image_generation":
        for candidate in ("minimax", "dalle", "stable_diffusion"):
            if isinstance(cfg.get(candidate), dict):
                return candidate
    if skill_name == "tts":
        for candidate in ("edge_tts", "minimax", "azure_tts", "openai_tts"):
            if isinstance(cfg.get(candidate), dict):
                return candidate
    return model_hint or "unknown"


def resolve_skill_config(
    global_skills: dict[str, Any] | None,
    bot_skills: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge global and bot-level skill configs, bot config wins."""
    global_skills = global_skills if isinstance(global_skills, dict) else {}
    bot_skills = bot_skills if isinstance(bot_skills, dict) else {}
    return _deep_merge(global_skills, bot_skills)


def build_capability_statuses(resolved_skills: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """
    Build baseline capability status from merged skill config.

    This only reflects config state. Runtime registration/availability is filled
    later by BotInstance when concrete skill instances are created.
    """
    statuses: dict[str, dict[str, Any]] = {}
    for skill_name, raw_cfg in (resolved_skills or {}).items():
        if not isinstance(raw_cfg, dict):
            continue
        enabled = bool(raw_cfg.get("enabled", True))
        auto_default = _AUTO_DEFAULTS.get(skill_name, False)
        auto = bool(raw_cfg.get("auto", auto_default))
        provider = _infer_provider(skill_name, raw_cfg)
        model = str(raw_cfg.get("model", "") or "").strip()

        statuses[skill_name] = {
            "name": skill_name,
            "source": "builtin",
            "enabled": enabled,
            "auto": auto,
            "registered": False,
            "available": False,
            "reason": "" if enabled else "disabled_by_config",
            "provider": provider,
            "model": model,
        }
    return statuses

