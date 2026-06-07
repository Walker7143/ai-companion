import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from .runtime_profile import apply_runtime_profile_overlay


@dataclass
class Persona:
    profile: dict
    backstory: dict
    values: dict
    speaking_style: dict
    persona_dir: Path = None  # 用于 PersonaEngine 动态读取最新文件


class PersonaLoader:
    """加载人格文件"""

    def __init__(self, persona_dir: Path):
        self.dir = Path(persona_dir)

    def load(self) -> Persona:
        profile = self._load_json("profile.json")
        backstory = self._load_json("backstory.json")
        runtime = self._load_json("runtime_profile.json")
        profile, backstory = self._apply_runtime_profile(profile, backstory, runtime)
        return Persona(
            profile=profile,
            backstory=backstory,
            values=self._load_json("values.json"),
            speaking_style=self._load_json("speaking_style.json"),
            persona_dir=self.dir,
        )

    def _load_json(self, filename: str) -> dict:
        path = self.dir / filename
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _apply_runtime_profile(self, profile: dict, backstory: dict, runtime: dict) -> tuple[dict, dict]:
        return apply_runtime_profile_overlay(profile, backstory, runtime)
