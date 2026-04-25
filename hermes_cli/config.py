"""Configuration management for Hermes Agent - minimal re-export."""

import os
import sys
from pathlib import Path
from typing import Any

# Re-export from hermes_constants — canonical definition lives there.
from hermes_constants import get_hermes_home  # noqa: F811,E402


def get_config_path() -> Path:
    """Return the path to ``config.yaml`` under HERMES_HOME."""
    return get_hermes_home() / "config.yaml"


def get_env_path() -> Path:
    """Return the path to the ``.env`` file under HERMES_HOME."""
    return get_hermes_home() / ".env"


def get_sessions_dir() -> Path:
    """Return the path to the sessions directory."""
    return get_hermes_home() / "sessions"
