import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Persona:
    profile: dict
    backstory: dict
    values: dict
    speaking_style: dict


class PersonaLoader:
    """加载人格文件"""

    def __init__(self, persona_dir: Path):
        self.dir = Path(persona_dir)

    def load(self) -> Persona:
        return Persona(
            profile=self._load_json("profile.json"),
            backstory=self._load_json("backstory.json"),
            values=self._load_json("values.json"),
            speaking_style=self._load_json("speaking_style.json"),
        )

    def _load_json(self, filename: str) -> dict:
        path = self.dir / filename
        if not path.exists():
            return {}
        with open(path) as f:
            return json.load(f)
