"""Shared helpers for extracting user-visible model output."""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


def coerce_content_text(value: Any) -> str:
    """Return text from common chat content shapes without treating reasoning as text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                elif isinstance(item.get("content"), str):
                    parts.append(str(item["content"]))
        return "".join(parts)
    return str(value)


def user_visible_message_content(message: dict[str, Any], *, provider: str) -> str:
    """Extract only the assistant reply intended for the user.

    Some reasoning models return their private trace in ``reasoning_content`` when
    ``content`` is empty. That field must never be promoted to the user-visible
    reply path.
    """
    content = coerce_content_text(message.get("content"))
    reasoning = coerce_content_text(message.get("reasoning_content"))
    if not content.strip() and reasoning.strip():
        logger.warning(
            "[%s] Suppressed reasoning_content because response content was empty",
            provider,
        )
    return content
