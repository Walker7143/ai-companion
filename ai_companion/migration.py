"""Portable backup and restore helpers for user runtime data."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable

from .paths import get_app_home


MANIFEST_NAME = "ai-companion-migration.json"
ARCHIVE_FORMAT = "ai-companion-runtime-migration"
ARCHIVE_VERSION = 1

DEFAULT_EXCLUDE_PATTERNS = (
    "logs/**",
    "migration-backups/**",
    "source/**",
    "*.pid",
    "*.lock",
    "*.tmp",
    "**/*.lock",
    "**/__pycache__/**",
    "**/*.pyc",
    "**/.DS_Store",
)


@dataclass(frozen=True)
class MigrationResult:
    archive: Path | None
    home: Path
    file_count: int
    total_bytes: int
    backup_dir: Path | None = None


def export_runtime_data(
    output: Path | None = None,
    *,
    home: Path | None = None,
    include_logs: bool = False,
    extra_excludes: Iterable[str] = (),
) -> MigrationResult:
    """Pack the AI Companion user home into a portable zip archive."""

    app_home = _resolve_home(home)
    if not app_home.exists():
        raise FileNotFoundError(f"AI Companion home does not exist: {app_home}")
    if not app_home.is_dir():
        raise NotADirectoryError(f"AI Companion home is not a directory: {app_home}")

    if output is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = Path.cwd() / f"ai-companion-migration-{stamp}.zip"
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    if include_logs:
        excludes = [pattern for pattern in DEFAULT_EXCLUDE_PATTERNS if pattern != "logs/**"]
    else:
        excludes = list(DEFAULT_EXCLUDE_PATTERNS)
    excludes.extend(extra_excludes)

    files = list(_iter_export_files(app_home, output, excludes))
    total_bytes = sum(path.stat().st_size for path, _ in files)
    manifest = {
        "format": ARCHIVE_FORMAT,
        "version": ARCHIVE_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_home_name": app_home.name,
        "file_count": len(files),
        "total_bytes": total_bytes,
        "includes": ["config", "data", ".env", "platform state files"],
        "excluded_patterns": excludes,
        "python": sys.version.split()[0],
    }

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))
        for path, rel in files:
            info = zipfile.ZipInfo.from_file(path, rel.as_posix())
            info.compress_type = zipfile.ZIP_DEFLATED
            with path.open("rb") as f:
                zf.writestr(info, f.read())

    return MigrationResult(archive=output, home=app_home, file_count=len(files), total_bytes=total_bytes)


def import_runtime_data(
    archive: Path,
    *,
    home: Path | None = None,
    overwrite: bool = True,
    backup_existing: bool = True,
) -> MigrationResult:
    """Restore a migration archive into the AI Companion user home."""

    archive = archive.expanduser().resolve()
    if not archive.exists():
        raise FileNotFoundError(f"Migration archive does not exist: {archive}")

    app_home = _resolve_home(home)
    app_home.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive, "r") as zf:
        manifest = _read_manifest(zf)
        entries = [info for info in zf.infolist() if not info.is_dir() and info.filename != MANIFEST_NAME]
        destinations = [(info, _safe_destination(app_home, info.filename)) for info in entries]

        existing = [dest for _, dest in destinations if dest.exists()]
        if existing and not overwrite:
            sample = ", ".join(str(path) for path in existing[:5])
            raise FileExistsError(f"Target files already exist. Re-run with overwrite enabled. Examples: {sample}")

        backup_dir = None
        if existing and backup_existing:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_dir = app_home / "migration-backups" / stamp
            for dest in existing:
                rel = dest.relative_to(app_home)
                backup_path = backup_dir / rel
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, backup_path)

        restored_count = 0
        total_bytes = 0
        for info, dest in destinations:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, dest.open("wb") as out:
                shutil.copyfileobj(src, out)
            _restore_permissions(dest, info)
            restored_count += 1
            total_bytes += info.file_size

    return MigrationResult(
        archive=archive,
        home=app_home,
        file_count=restored_count or int(manifest.get("file_count", 0) or 0),
        total_bytes=total_bytes or int(manifest.get("total_bytes", 0) or 0),
        backup_dir=backup_dir,
    )


def add_migration_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("migrate", help="Export or import AI Companion runtime data")
    migration_subparsers = parser.add_subparsers(dest="migration_command")

    export_parser = migration_subparsers.add_parser("export", help="Create a portable migration archive")
    export_parser.add_argument("-o", "--output", type=Path, help="Archive path. Defaults to ./ai-companion-migration-<time>.zip")
    export_parser.add_argument("--home", type=Path, help="Override AI_COMPANION_HOME for this command")
    export_parser.add_argument("--include-logs", action="store_true", help="Include logs in the migration archive")
    export_parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Additional glob pattern to exclude, relative to AI_COMPANION_HOME",
    )

    import_parser = migration_subparsers.add_parser("import", help="Restore a migration archive")
    import_parser.add_argument("archive", type=Path, help="Archive created by 'ai-companion migrate export'")
    import_parser.add_argument("--home", type=Path, help="Override AI_COMPANION_HOME for this command")
    import_parser.add_argument("--no-overwrite", action="store_true", help="Fail if target files already exist")
    import_parser.add_argument("--no-backup", action="store_true", help="Do not back up overwritten files")


def handle_migration_command(command: str | None, args: argparse.Namespace) -> int:
    if command == "export":
        result = export_runtime_data(
            args.output,
            home=args.home,
            include_logs=args.include_logs,
            extra_excludes=args.exclude,
        )
        print(f"Migration archive created: {result.archive}")
        print(f"Source home: {result.home}")
        print(f"Files: {result.file_count}, size: {_format_bytes(result.total_bytes)}")
        return 0
    if command == "import":
        result = import_runtime_data(
            args.archive,
            home=args.home,
            overwrite=not args.no_overwrite,
            backup_existing=not args.no_backup,
        )
        print(f"Migration archive restored: {result.archive}")
        print(f"Target home: {result.home}")
        print(f"Files: {result.file_count}, size: {_format_bytes(result.total_bytes)}")
        if result.backup_dir:
            print(f"Previous files backed up to: {result.backup_dir}")
        return 0

    print("Usage: ai-companion migrate export|import")
    return 2


def _resolve_home(home: Path | None) -> Path:
    return Path(home).expanduser().resolve() if home is not None else get_app_home().expanduser().resolve()


def _iter_export_files(home: Path, output: Path, excludes: list[str]) -> Iterable[tuple[Path, PurePosixPath]]:
    for path in sorted(home.rglob("*")):
        if not path.is_file():
            continue
        if path.resolve() == output:
            continue
        rel = PurePosixPath(path.relative_to(home).as_posix())
        if _is_excluded(rel, excludes):
            continue
        yield path, rel


def _is_excluded(rel: PurePosixPath, patterns: Iterable[str]) -> bool:
    text = rel.as_posix()
    return any(fnmatch.fnmatch(text, pattern) for pattern in patterns)


def _read_manifest(zf: zipfile.ZipFile) -> dict:
    try:
        raw = zf.read(MANIFEST_NAME)
    except KeyError as exc:
        raise ValueError(f"Archive is missing {MANIFEST_NAME}") from exc
    manifest = json.loads(raw.decode("utf-8"))
    if manifest.get("format") != ARCHIVE_FORMAT:
        raise ValueError("Archive is not an AI Companion migration archive")
    if int(manifest.get("version", 0)) > ARCHIVE_VERSION:
        raise ValueError("Archive was created by a newer migration format")
    return manifest


def _safe_destination(home: Path, member_name: str) -> Path:
    rel = PurePosixPath(member_name)
    if rel.is_absolute() or any(part in ("", ".", "..") for part in rel.parts):
        raise ValueError(f"Unsafe archive path: {member_name}")
    dest = (home / Path(*rel.parts)).resolve()
    if not _is_relative_to(dest, home):
        raise ValueError(f"Archive path escapes target home: {member_name}")
    return dest


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _restore_permissions(path: Path, info: zipfile.ZipInfo) -> None:
    if os.name == "nt":
        return
    mode = (info.external_attr >> 16) & 0o777
    if mode:
        path.chmod(mode)


def _format_bytes(size: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"
