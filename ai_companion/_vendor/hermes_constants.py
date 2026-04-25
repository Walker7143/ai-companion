"""
Hermes constants compatibility shim.

This module exists to satisfy relative imports from gw_cli modules
(e.g. ``from ..hermes_constants import get_hermes_home``).
All symbols are re-exported from gw_constants.
"""

from ai_companion._vendor.gw_constants import (
    get_hermes_home,
    get_default_hermes_root,
    get_optional_skills_dir,
    get_hermes_dir,
    display_hermes_home,
    get_subprocess_home,
    parse_reasoning_effort,
    is_termux,
    is_wsl,
    is_container,
    get_config_path,
    get_skills_dir,
    get_env_path,
    apply_ipv4_preference,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODELS_URL,
    AI_GATEWAY_BASE_URL,
)

__all__ = [
    "get_hermes_home",
    "get_default_hermes_root",
    "get_optional_skills_dir",
    "get_hermes_dir",
    "display_hermes_home",
    "get_subprocess_home",
    "parse_reasoning_effort",
    "is_termux",
    "is_wsl",
    "is_container",
    "get_config_path",
    "get_skills_dir",
    "get_env_path",
    "apply_ipv4_preference",
    "OPENROUTER_BASE_URL",
    "OPENROUTER_MODELS_URL",
    "AI_GATEWAY_BASE_URL",
]
