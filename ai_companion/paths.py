"""Shared runtime path helpers."""

from __future__ import annotations

import os
from pathlib import Path


def get_app_home() -> Path:
    """Return the AI Companion home directory."""
    raw = os.environ.get("AI_COMPANION_HOME")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".ai-companion"


def get_user_bots_dir() -> Path:
    """Return the user data directory for bot runtime files."""
    return get_app_home() / "data" / "bots"


def get_user_skills_dir() -> Path:
    """Return the user-installed skills directory."""
    return get_user_bots_dir() / "_skills"
