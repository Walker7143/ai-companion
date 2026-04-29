"""Shared data path resolution for gateway/admin code."""

from pathlib import Path


def user_bots_dir() -> Path:
    return Path.home() / ".ai-companion" / "data" / "bots"


def project_bots_dir() -> Path:
    return Path(__file__).parent.parent.parent / "data" / "bots"


def iter_bot_roots() -> tuple[Path, Path]:
    """Return bot data roots in runtime priority order."""
    return user_bots_dir(), project_bots_dir()


def get_data_dir() -> Path:
    """Return the bot data root used by runtime code."""
    user_dir = user_bots_dir()
    if user_dir.exists():
        return user_dir
    return project_bots_dir()


def discover_bots() -> list[dict]:
    """Discover bots from user data first, then bundled project data."""
    seen: set[str] = set()
    bots: list[dict] = []
    for base_dir in iter_bot_roots():
        if not base_dir.exists():
            continue
        for bot_dir in base_dir.iterdir():
            if not bot_dir.is_dir() or bot_dir.name in seen:
                continue
            name = bot_dir.name
            description = ""
            persona_file = bot_dir / "persona" / "profile.json"
            if persona_file.exists():
                try:
                    import json

                    profile = json.loads(persona_file.read_text(encoding="utf-8"))
                    name = profile.get("name", name)
                    description = profile.get("description", description)
                except Exception:
                    pass
            seen.add(bot_dir.name)
            bots.append({"id": bot_dir.name, "name": name, "description": description})
    return bots


def get_memory_db_path(bot_id: str, db_name: str) -> Path | None:
    """Return a memory DB path using the same priority as runtime bot data."""
    for base in iter_bot_roots():
        db_path = base / bot_id / "memory" / db_name
        if db_path.exists():
            return db_path
    return None
