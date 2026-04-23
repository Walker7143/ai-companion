import os
import yaml
from pathlib import Path
from typing import Optional


class Config:
    def __init__(self, config_dir: Path = Path("config")):
        self.config_dir = Path(config_dir)
        self.bots = self._load_yaml("bots.yaml")
        self.models = self._load_yaml("models.yaml")
        self._expand_env_vars(self.bots)
        self._expand_env_vars(self.models)

    def _load_yaml(self, filename: str) -> dict:
        path = self.config_dir / filename
        if not path.exists():
            return {}
        with open(path) as f:
            content = f.read()
        return yaml.safe_load(content) or {}

    def _expand_env_vars(self, d: dict):
        for k, v in d.items():
            if isinstance(v, str):
                d[k] = os.path.expandvars(v)
            elif isinstance(v, dict):
                self._expand_env_vars(v)

    def get_enabled_bots(self) -> list[dict]:
        return [b for b in self.bots.get("bots", []) if b.get("enabled", True)]

    def get_model_config(self) -> dict:
        cfg = self.models.get("minimax", {})
        return {
            "api_key": cfg.get("api_key", ""),
            "base_url": cfg.get("base_url", "https://api.minimax.chat/v1"),
            "model": cfg.get("model", "MiniMax-m2.7"),
        }
