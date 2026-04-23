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
            self.config_dir = Path.home() / "ai-companion" / "config"

        self._bots = None
        self._models = None

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
        with open(path) as f:
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

    def get_model_config(self) -> dict:
        cfg = self.models.get("minimax", {})
        return {
            "api_key": cfg.get("api_key", ""),
            "base_url": cfg.get("base_url", "https://api.minimax.chat/v1"),
            "model": cfg.get("model", "MiniMax-m2.7"),
        }
