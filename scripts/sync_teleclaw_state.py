#!/usr/bin/env python3
"""Sync TeleClaw login state into this project's private local directory."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEST_PATH = REPO_ROOT / ".local" / "teleclaw" / "state.json"
REQUIRED_FIELDS = ("token", "deviceId", "installId")


def system_state_candidates() -> list[Path]:
    env_path = os.environ.get("TELECLAW_AUTH_STATE_FILE") or os.environ.get("SUPER_AGENT_AUTH_STATE_FILE")
    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path).expanduser())

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "TeleClaw" / "app-auth" / "state.json")
        candidates.append(Path.home() / "AppData" / "Roaming" / "TeleClaw" / "app-auth" / "state.json")
    elif sys.platform == "darwin":
        candidates.append(Path.home() / "Library" / "Application Support" / "TeleClaw" / "app-auth" / "state.json")
    else:
        xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config_home:
            candidates.append(Path(xdg_config_home) / "TeleClaw" / "app-auth" / "state.json")
        candidates.append(Path.home() / ".config" / "TeleClaw" / "app-auth" / "state.json")

    deduped: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key not in seen:
            seen.add(key)
            deduped.append(path)
    return deduped


def resolve_source(explicit_source: str | None) -> Path:
    if explicit_source:
        return Path(explicit_source).expanduser().resolve()
    for candidate in system_state_candidates():
        if candidate.exists():
            return candidate
    tried = "\n".join(f"  - {path}" for path in system_state_candidates())
    raise FileNotFoundError(f"未找到 TeleClaw state.json。已尝试:\n{tried}")


def validate_state_file(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("state.json 必须是 JSON 对象")
    missing = [field for field in REQUIRED_FIELDS if not str(data.get(field) or "").strip()]
    if missing:
        raise ValueError(f"state.json 缺少字段: {', '.join(missing)}")
    return data


def copy_state(source: Path, destination: Path, force: bool = False) -> Path:
    validate_state_file(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not force:
        backup = destination.with_name(f"state.{datetime.now().strftime('%Y%m%d-%H%M%S')}.json.bak")
        shutil.copy2(destination, backup)
        try:
            os.chmod(backup, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    shutil.copy2(source, destination)
    try:
        os.chmod(destination, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="同步 TeleClaw 登录态 state.json 到项目私有目录。")
    parser.add_argument("--source", help="手动指定 state.json 来源路径；默认自动查找当前机器 TeleClaw 登录态。")
    parser.add_argument("--dest", default=str(DEST_PATH), help="目标路径，默认 .local/teleclaw/state.json。")
    parser.add_argument("--force", action="store_true", help="覆盖目标文件时不生成备份。")
    args = parser.parse_args()

    try:
        source = resolve_source(args.source)
        destination = Path(args.dest).expanduser()
        if not destination.is_absolute():
            destination = REPO_ROOT / destination
        written = copy_state(source, destination, force=args.force)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(f"[OK] 已同步 TeleClaw 登录态: {written}")
    print("     该文件包含登录 token，请不要提交或公开分享。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
