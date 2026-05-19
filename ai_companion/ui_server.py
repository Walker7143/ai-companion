"""Shared frontend dev server lifecycle helpers."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from typing import Any, Iterator

from ai_companion.logging_utils import get_log_max_bytes, start_log_limit_maintenance, trim_log_file


UI_PORT = int(os.environ.get("AI_COMPANION_UI_PORT", "14210"))
UI_URL = f"http://localhost:{UI_PORT}"
_STATE_DIR = Path.home() / ".ai-companion"
UI_PID_FILE = Path(os.environ.get("AI_COMPANION_UI_PID_FILE", _STATE_DIR / "ui.pid"))
UI_OWNER_FILE = Path(
    os.environ.get("AI_COMPANION_UI_OWNER_FILE", UI_PID_FILE.with_suffix(".owners.json"))
)
UI_LOCK_FILE = Path(os.environ.get("AI_COMPANION_UI_LOCK_FILE", UI_PID_FILE.with_suffix(".lock")))


@dataclass
class UIStartResult:
    ok: bool
    url: str = UI_URL
    pid: int | None = None
    started: bool = False
    reused: bool = False
    owner_id: str | None = None
    message: str = ""


def should_start_ui(default: bool = True) -> bool:
    """Return whether automatic UI startup is enabled."""
    raw = os.environ.get("START_UI")
    if raw is None:
        raw = os.environ.get("AI_COMPANION_START_UI")
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", "disable", "disabled"}


def ensure_ui_server(owner_name: str = "process") -> UIStartResult:
    """Ensure one shared Vite dev server is available.

    The function is safe for multiple CLI/gateway processes starting at the
    same time. A file lock serializes the check/start sequence, while the
    Vite command uses --strictPort so a race cannot silently create a second
    server on a different port.
    """
    owner_id = f"{owner_name}:{os.getpid()}"
    if not should_start_ui(default=True):
        return UIStartResult(ok=False, owner_id=owner_id, message="UI startup disabled")

    with _startup_lock():
        _prune_dead_owners()

        existing_pid = _read_pid()
        if existing_pid and _is_process_running(existing_pid):
            deadline = time.time() + 2
            while time.time() < deadline and not _is_port_open(UI_PORT):
                time.sleep(0.1)
            if _is_port_open(UI_PORT):
                _add_owner(owner_id, owner_name)
                return UIStartResult(
                    ok=True,
                    pid=existing_pid,
                    reused=True,
                    owner_id=owner_id,
                    message=f"UI already running (PID: {existing_pid})",
                )
            _terminate_process_tree(existing_pid)

        if existing_pid:
            UI_PID_FILE.unlink(missing_ok=True)

        if _is_port_open(UI_PORT):
            _add_owner(owner_id, owner_name)
            return UIStartResult(
                ok=True,
                reused=True,
                owner_id=owner_id,
                message=f"UI already available at {UI_URL}",
            )

        ui_dir = _find_ui_dir()
        if ui_dir is None:
            return UIStartResult(ok=False, owner_id=owner_id, message="ai-companion-ui not found")

        npm_path = shutil.which("npm")
        if not npm_path:
            return UIStartResult(ok=False, owner_id=owner_id, message="npm not found")

        install_error = _ensure_dependencies(ui_dir, npm_path)
        if install_error:
            return UIStartResult(ok=False, owner_id=owner_id, message=install_error)

        process = _spawn_ui(ui_dir, npm_path)
        UI_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        UI_PID_FILE.write_text(str(process.pid), encoding="utf-8")
        _add_owner(owner_id, owner_name)

        deadline = time.time() + 10
        while time.time() < deadline:
            if process.poll() is not None:
                UI_PID_FILE.unlink(missing_ok=True)
                _remove_owner(owner_id)
                return UIStartResult(
                    ok=False,
                    owner_id=owner_id,
                    message=f"UI exited immediately with code {process.returncode}",
                )
            if _is_port_open(UI_PORT):
                return UIStartResult(
                    ok=True,
                    pid=process.pid,
                    started=True,
                    owner_id=owner_id,
                    message=f"UI started (PID: {process.pid})",
                )
            time.sleep(0.25)

        return UIStartResult(
            ok=True,
            pid=process.pid,
            started=True,
            owner_id=owner_id,
            message=f"UI starting (PID: {process.pid})",
        )


def release_ui_server(result: UIStartResult | None) -> None:
    """Release this process' UI ownership and stop the UI if no owner remains."""
    if not result or not result.ok or not result.owner_id:
        return

    with _startup_lock():
        _remove_owner(result.owner_id)
        _prune_dead_owners()
        if _read_owners():
            return

        pid = _read_pid()
        if pid and _is_process_running(pid):
            _terminate_process_tree(pid)
        UI_PID_FILE.unlink(missing_ok=True)


def _find_ui_dir() -> Path | None:
    project_root = Path(__file__).resolve().parent.parent
    candidates = [
        project_root / "ai-companion-ui",
        Path.cwd() / "ai-companion-ui",
    ]
    for candidate in candidates:
        if (candidate / "package.json").exists():
            return candidate
    return None


def _ensure_dependencies(ui_dir: Path, npm_path: str) -> str | None:
    if (ui_dir / "node_modules").exists():
        return None

    log_path = _prepare_ui_log_file()
    with open(log_path, "a", encoding="utf-8") as log_file:
        try:
            result = subprocess.run(
                [npm_path, "install"],
                cwd=str(ui_dir),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            return f"npm install timed out; run manually in {ui_dir}"
        except Exception as exc:
            return f"npm install failed: {exc}"

    if result.returncode != 0:
        return f"npm install failed; see {_ui_log_file()}"
    return None


def _spawn_ui(ui_dir: Path, npm_path: str) -> subprocess.Popen[Any]:
    log_file = open(_prepare_ui_log_file(), "a", encoding="utf-8")
    cmd = [
        npm_path,
        "run",
        "dev",
        "--",
        "--host",
        "0.0.0.0",
        "--port",
        str(UI_PORT),
        "--strictPort",
    ]
    try:
        kwargs: dict[str, Any] = {
            "cwd": str(ui_dir),
            "stdout": log_file,
            "stderr": subprocess.STDOUT,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP
                | getattr(subprocess, "DETACHED_PROCESS", 0)
            )
        else:
            kwargs["start_new_session"] = True
        return subprocess.Popen(cmd, **kwargs)
    finally:
        log_file.close()


def _ui_log_file() -> Path:
    log_dir = Path(os.environ.get("AI_COMPANION_LOG_DIR", _STATE_DIR / "logs"))
    return log_dir / "ui.log"


def _prepare_ui_log_file() -> Path:
    log_path = _ui_log_file()
    max_bytes = get_log_max_bytes()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    trim_log_file(log_path, max_bytes=max_bytes)
    start_log_limit_maintenance(log_path.parent, max_bytes=max_bytes)
    return log_path


def _is_port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def _read_pid() -> int | None:
    try:
        pid = int(UI_PID_FILE.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError, OSError):
        return None
    return pid if pid > 0 else None


def _is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _terminate_process_tree(pid: int) -> None:
    if pid == os.getpid():
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            return

        current_pgrp = os.getpgrp()
        try:
            target_pgrp = os.getpgid(pid)
        except OSError:
            target_pgrp = None

        if target_pgrp and target_pgrp != current_pgrp:
            os.killpg(target_pgrp, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)

        deadline = time.time() + 5
        while time.time() < deadline:
            if not _is_process_running(pid):
                return
            time.sleep(0.2)

        if target_pgrp and target_pgrp != current_pgrp:
            os.killpg(target_pgrp, signal.SIGKILL)
        else:
            os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, OSError, subprocess.SubprocessError):
        return


def _read_owners() -> list[dict[str, Any]]:
    try:
        data = json.loads(UI_OWNER_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    owners = data.get("owners", []) if isinstance(data, dict) else []
    return [owner for owner in owners if isinstance(owner, dict)]


def _write_owners(owners: list[dict[str, Any]]) -> None:
    UI_OWNER_FILE.parent.mkdir(parents=True, exist_ok=True)
    UI_OWNER_FILE.write_text(
        json.dumps({"owners": owners}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _add_owner(owner_id: str, owner_name: str) -> None:
    owners = [owner for owner in _read_owners() if owner.get("id") != owner_id]
    owners.append(
        {
            "id": owner_id,
            "name": owner_name,
            "pid": os.getpid(),
            "started_at": int(time.time()),
        }
    )
    _write_owners(owners)


def _remove_owner(owner_id: str) -> None:
    owners = [owner for owner in _read_owners() if owner.get("id") != owner_id]
    if owners:
        _write_owners(owners)
    else:
        UI_OWNER_FILE.unlink(missing_ok=True)


def _prune_dead_owners() -> None:
    owners = []
    for owner in _read_owners():
        try:
            pid = int(owner.get("pid", 0))
        except (TypeError, ValueError):
            continue
        if _is_process_running(pid):
            owners.append(owner)

    if owners:
        _write_owners(owners)
    else:
        UI_OWNER_FILE.unlink(missing_ok=True)


@contextmanager
def _startup_lock() -> Iterator[None]:
    UI_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        with _windows_lock():
            yield
        return

    import fcntl

    with open(UI_LOCK_FILE, "a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@contextmanager
def _windows_lock() -> Iterator[None]:
    lock_dir = UI_LOCK_FILE.with_suffix(".lockdir")
    while True:
        try:
            lock_dir.mkdir(parents=True)
            break
        except FileExistsError:
            try:
                age = time.time() - lock_dir.stat().st_mtime
            except OSError:
                age = 0
            if age > 30:
                try:
                    lock_dir.rmdir()
                except OSError:
                    pass
            time.sleep(0.1)
    try:
        yield
    finally:
        try:
            lock_dir.rmdir()
        except OSError:
            pass
