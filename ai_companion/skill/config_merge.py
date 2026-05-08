"""Helpers for merging global and bot-level skill config."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def merge_skill_config(
    global_skills: dict[str, Any] | None,
    bot_skills: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Merge global and bot-level skill configs.

    Bot-level fields override global defaults recursively.
    """
    global_skills = global_skills if isinstance(global_skills, dict) else {}
    bot_skills = bot_skills if isinstance(bot_skills, dict) else {}
    return _deep_merge(global_skills, bot_skills)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged

