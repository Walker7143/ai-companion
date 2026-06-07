from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


DEFAULT_RUNTIME_EXPERIENCE_LIMIT = 20


def runtime_profile_path_from_persona_dir(persona_dir: str | Path | None) -> Optional[Path]:
    if not persona_dir:
        return None
    return Path(persona_dir) / "runtime_profile.json"


def runtime_profile_path_from_backstory_path(backstory_path: str | Path | None) -> Optional[Path]:
    if not backstory_path:
        return None
    return Path(backstory_path).parent / "runtime_profile.json"


def load_runtime_profile(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    runtime_path = Path(path)
    if not runtime_path.exists():
        return {}
    try:
        return json.loads(runtime_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_runtime_profile(path: str | Path | None, data: dict[str, Any]) -> bool:
    if not path:
        return False
    runtime_path = Path(path)
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data or {})
    payload["updated_at"] = datetime.now().isoformat()
    tmp_path = runtime_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(runtime_path)
    return True


def dedupe_runtime_items(items: list[Any], limit: int = DEFAULT_RUNTIME_EXPERIENCE_LIMIT) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = compact_runtime_text(item)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def compact_runtime_text(value: object) -> str:
    return " ".join(str(value or "").split())


def apply_runtime_profile_overlay(
    profile: dict[str, Any] | None,
    backstory: dict[str, Any] | None,
    runtime: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not runtime:
        return dict(profile or {}), dict(backstory or {})

    merged_profile = dict(profile or {})
    merged_backstory = dict(backstory or {})

    if runtime.get("relationship_to_user"):
        merged_profile["relationship_to_user"] = runtime["relationship_to_user"]
    if runtime.get("attitude_score") is not None:
        merged_profile["attitude_score"] = runtime["attitude_score"]

    runtime_moments = runtime.get("key_moments") or []
    if runtime_moments:
        key_moments = list(merged_backstory.get("key_moments", []) or [])
        for moment in runtime_moments:
            if moment not in key_moments:
                key_moments.append(moment)
        merged_backstory["key_moments"] = key_moments

    runtime_shared = runtime.get("shared_experiences") or []
    if runtime_shared:
        shared_experiences = list(merged_backstory.get("shared_experiences", []) or [])
        for item in runtime_shared:
            if item not in shared_experiences:
                shared_experiences.append(item)
        merged_backstory["shared_experiences"] = shared_experiences

    if runtime.get("shared_growth_summary"):
        merged_backstory["shared_growth_summary"] = runtime["shared_growth_summary"]

    runtime_life = runtime.get("life_experiences") or []
    if runtime_life:
        life_experiences = list(merged_backstory.get("life_experiences", []) or [])
        for item in runtime_life:
            if item not in life_experiences:
                life_experiences.append(item)
        merged_backstory["life_experiences"] = life_experiences

    if runtime.get("life_growth_summary"):
        merged_backstory["life_growth_summary"] = runtime["life_growth_summary"]

    return merged_profile, merged_backstory


def merge_runtime_profile(
    runtime_profile: dict[str, Any] | None,
    patch: dict[str, Any] | None,
    *,
    list_limits: dict[str, int] | None = None,
) -> tuple[dict[str, Any], bool]:
    merged = dict(runtime_profile or {})
    changed = False
    list_limits = dict(list_limits or {})

    for key, value in (patch or {}).items():
        if key in list_limits:
            current = list(merged.get(key, []) or [])
            new_items = list(value or [])
            combined = dedupe_runtime_items([*current, *new_items], list_limits[key])
            if current != combined or key not in merged:
                merged[key] = combined
                changed = True
            continue

        if value is None:
            continue
        if isinstance(value, str):
            value = compact_runtime_text(value)
        if merged.get(key) != value:
            merged[key] = value
            changed = True

    return merged, changed
