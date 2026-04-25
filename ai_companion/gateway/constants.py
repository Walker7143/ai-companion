"""
Gateway 常量与路径工具。

提供 get_hermes_home() / get_hermes_dir() / display_hermes_home() 等接口，
供 gateway 各模块统一使用 AI Companion 的主目录路径。
"""

import os
from pathlib import Path


def get_hermes_home() -> Path:
    """获取 AI Companion 主目录。

    优先使用环境变量 AI_COMPANION_HOME，否则默认 ~/.ai-companion/
    """
    return Path(os.environ.get("AI_COMPANION_HOME", Path.home() / ".ai-companion"))


def get_hermes_dir(*paths) -> Path:
    """获取 AI Companion 下的子目录路径

    Args:
        *paths: 相对于 home 的路径组件

    Example:
        get_hermes_dir("cache", "images") -> ~/.ai-companion/cache/images
    """
    result = get_hermes_home()
    for p in paths:
        result = result / p
    return result


def display_hermes_home() -> str:
    """返回人类可读的 home 路径"""
    return str(get_hermes_home())


def is_truthy_value(value, default=False):
    """判断值是否为真值"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
    return default
