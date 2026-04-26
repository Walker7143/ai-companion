import os
import sys
import yaml
from pathlib import Path
from typing import Optional


class Config:
    """配置加载器，支持用户目录和项目目录两级查找"""

    def __init__(self, config_dir: Path = None):
        if config_dir:
            self.config_dir = config_dir
        elif sys.platform == "win32":
            self.config_dir = Path.home() / ".ai-companion" / "config"
        else:
            self.config_dir = Path.home() / ".ai-companion" / "config"

        self._bots = None
        self._models = None
        self._config = None

    def _find_file(self, filename: str) -> Optional[Path]:
        """从用户目录或项目目录查找配置文件"""
        # 优先用户目录
        user_path = self.config_dir / filename
        if user_path.exists():
            return user_path
        # 其次项目目录
        project_path = Path(__file__).parent.parent.parent / "config" / filename
        if project_path.exists():
            return project_path
        return None

    def _load_yaml(self, filename: str) -> dict:
        path = self._find_file(filename)
        if not path:
            return {}
        with open(path, encoding="utf-8") as f:
            content = f.read()
        data = yaml.safe_load(content) or {}
        self._expand_env_vars(data)
        return data

    def _expand_env_vars(self, d: dict):
        for k, v in d.items():
            if isinstance(v, str):
                d[k] = os.path.expandvars(v)
            elif isinstance(v, dict):
                self._expand_env_vars(v)

    @property
    def bots(self) -> dict:
        if self._bots is None:
            self._bots = self._load_yaml("bots.yaml")
        return self._bots

    @property
    def models(self) -> dict:
        if self._models is None:
            self._models = self._load_yaml("models.yaml")
        return self._models

    def get_enabled_bots(self) -> list[dict]:
        return [b for b in self.bots.get("bots", []) if b.get("enabled", True)]

    def get_model_config(self, provider: str = None) -> dict:
        """
        获取模型配置

        Args:
            provider: 指定 provider，None 则使用配置的默认 provider

        Returns:
            包含 api_key, base_url, model 等的配置字典
        """
        # 获取默认 provider
        if provider is None:
            provider = self.models.get("model", {}).get("provider", "minimax")

        # 获取该 provider 的配置
        provider_config = self.models.get(provider, {})

        # 基础配置
        config = {
            "provider": provider,
            "api_key": provider_config.get("api_key", ""),
            "base_url": provider_config.get("base_url", ""),
            "model": provider_config.get("model", ""),
        }

        # 添加全局默认参数（如果没有在 provider 配置中指定）
        global_config = self.models.get("model", {})
        for key in ("temperature", "max_tokens"):
            if key not in provider_config and key in global_config:
                config[key] = global_config[key]

        # 移除空值
        return {k: v for k, v in config.items() if v}

    def get_provider_config(self, provider: str) -> dict:
        """获取指定 provider 的完整配置"""
        return self.models.get(provider, {})

    @property
    def default_provider(self) -> str:
        """获取默认 provider"""
        return self.models.get("model", {}).get("provider", "minimax")

    @property
    def config(self) -> dict:
        if self._config is None:
            self._config = self._load_yaml("config.yaml")
        return self._config

    def get_platform_config(self, platform: str) -> dict:
        """获取指定平台的配置"""
        return self.config.get("platforms", {}).get(platform, {})
