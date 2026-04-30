from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from ai_companion.utils import atomic_yaml_write

from .schema import CORE_PERSONA_FILES


@dataclass(slots=True)
class ApplyResult:
    data_dir: Path
    config_dir: Path
    applied_bot_ids: list[str]
    updated_bots_yaml: bool
    backups: list[Path]


def apply_draft(
    draft_dir: Path,
    *,
    data_dir: Path | None = None,
    config_dir: Path | None = None,
    bot_ids: list[str] | None = None,
    overwrite: bool = False,
    register_bots: bool = True,
    yes: bool = False,
) -> ApplyResult:
    draft_dir = Path(draft_dir).expanduser().resolve()
    manifest_path = draft_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"找不到导入草稿 manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    data_root = Path(data_dir or Path.home() / ".ai-companion" / "data" / "bots").expanduser().resolve()
    config_root = Path(config_dir or Path.home() / ".ai-companion" / "config").expanduser().resolve()

    characters = manifest.get("characters", []) or []
    if bot_ids:
        wanted = set(bot_ids)
        characters = [item for item in characters if item.get("bot_id") in wanted]
    if not characters:
        raise ValueError("没有可应用的角色草稿")

    if not yes:
        names = ", ".join(f"{item.get('name')}({item.get('bot_id')})" for item in characters)
        print(f"即将写入 {data_root}: {names}")
        if overwrite:
            print("overwrite=true：已有 persona 文件会先备份再覆盖。")
        confirmation = input("输入 APPLY 确认应用草稿: ").strip()
        if confirmation != "APPLY":
            raise RuntimeError("已取消应用草稿")

    applied: list[str] = []
    backups: list[Path] = []
    bot_entries: list[dict[str, Any]] = []

    for item in characters:
        bot_id = str(item.get("bot_id") or "").strip()
        name = str(item.get("name") or bot_id).strip()
        if not bot_id:
            continue

        src_persona = draft_dir / "characters" / bot_id / "persona"
        if not src_persona.exists():
            raise FileNotFoundError(f"找不到角色 persona 草稿: {src_persona}")

        dst_persona = data_root / bot_id / "persona"
        conflicts = [filename for filename in CORE_PERSONA_FILES if (dst_persona / filename).exists()]
        if conflicts and not overwrite:
            raise FileExistsError(
                f"{bot_id} 已存在 persona 文件: {', '.join(conflicts)}。"
                "请审核后加 --overwrite 覆盖。"
            )
        if conflicts and overwrite:
            backup = _backup_persona_dir(dst_persona)
            if backup:
                backups.append(backup)

        dst_persona.mkdir(parents=True, exist_ok=True)
        for filename in CORE_PERSONA_FILES:
            src_file = src_persona / filename
            if src_file.exists():
                shutil.copy2(src_file, dst_persona / filename)
        applied.append(bot_id)
        bot_entries.append({
            "id": bot_id,
            "name": name,
            "enabled": True,
            "description": f"Imported from {manifest.get('book', {}).get('title', 'book')}",
        })

    updated = False
    if register_bots and bot_entries:
        updated = _merge_bots_yaml(config_root / "bots.yaml", bot_entries, overwrite=overwrite)

    return ApplyResult(
        data_dir=data_root,
        config_dir=config_root,
        applied_bot_ids=applied,
        updated_bots_yaml=updated,
        backups=backups,
    )


def _backup_persona_dir(persona_dir: Path) -> Path | None:
    if not persona_dir.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = persona_dir.with_name(f"{persona_dir.name}.backup-{timestamp}")
    shutil.copytree(persona_dir, backup)
    return backup


def _merge_bots_yaml(path: Path, entries: list[dict[str, Any]], *, overwrite: bool) -> bool:
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    else:
        data = {}
    bots = data.get("bots")
    if not isinstance(bots, list):
        bots = []

    by_id = {str(item.get("id")): dict(item) for item in bots if isinstance(item, dict) and item.get("id")}
    changed = False
    for entry in entries:
        bot_id = entry["id"]
        if bot_id not in by_id:
            by_id[bot_id] = entry
            changed = True
        elif overwrite:
            merged = dict(by_id[bot_id])
            merged.update({k: v for k, v in entry.items() if v not in (None, "")})
            if merged != by_id[bot_id]:
                by_id[bot_id] = merged
                changed = True

    if changed:
        data["bots"] = list(by_id.values())
        atomic_yaml_write(path, data)
    return changed
