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
        if not runtime:
            return profile, backstory
        profile = dict(profile or {})
        backstory = dict(backstory or {})

        if runtime.get("relationship_to_user"):
            profile["relationship_to_user"] = runtime["relationship_to_user"]
        if runtime.get("attitude_score") is not None:
            profile["attitude_score"] = runtime["attitude_score"]

        runtime_moments = runtime.get("key_moments") or []
        if runtime_moments:
            key_moments = list(backstory.get("key_moments", []) or [])
            for moment in runtime_moments:
                if moment not in key_moments:
                    key_moments.append(moment)
            backstory["key_moments"] = key_moments

        return profile, backstory
