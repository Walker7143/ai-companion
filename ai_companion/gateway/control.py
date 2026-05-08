"""
Gateway process management: start, stop, restart, status and logs.
"""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import psutil

# Project root
_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))

GATEWAY_PID_FILE = Path(os.environ.get("AI_COMPANION_GATEWAY_PID_FILE", Path.home() / ".ai-companion" / "gateway.pid"))
GATEWAY_LOG_FILE = Path(os.environ.get("AI_COMPANION_LOG_DIR", Path.home() / ".ai-companion" / "logs")) / "gateway.log"

_GATEWAY_PROCESS_PATTERNS = (
    "ai_companion.gateway",
    "ai_companion\\gateway",
    "ai_companion/gateway",
)


def get_gateway_pid() -> int | None:
    """Return the PID from the PID file only when it is still a gateway."""
    pid = _read_pid_file()
    if pid is None:
        return None
    if _is_gateway_pid(pid):
        return pid
    remove_gateway_pid()
    return None


def save_gateway_pid(pid: int) -> None:
    """Save gateway PID."""
    GATEWAY_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    GATEWAY_PID_FILE.write_text(str(pid), encoding="utf-8")


def remove_gateway_pid() -> None:
    """Remove gateway PID file."""
    GATEWAY_PID_FILE.unlink(missing_ok=True)


def is_gateway_running() -> bool:
    """Check whether any gateway process is running."""
    return bool(_find_gateway_pids())


def ensure_log_dir() -> None:
    """Ensure log directory exists."""
    GATEWAY_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def _read_pid_file() -> int | None:
    if not GATEWAY_PID_FILE.exists():
        return None
    try:
        pid = int(GATEWAY_PID_FILE.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        remove_gateway_pid()
        return None
    return pid if pid > 0 else None


def _process_cmdline(proc: psutil.Process) -> str:
    try:
        return " ".join(proc.cmdline())
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return ""


def _looks_like_gateway_cmdline(cmdline: str) -> bool:
    if not cmdline:
        return False
    normalized = cmdline.replace("/", "\\") if sys.platform == "win32" else cmdline
    return any(pattern in cmdline or pattern in normalized for pattern in _GATEWAY_PROCESS_PATTERNS)


def _is_gateway_pid(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        proc = psutil.Process(pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False
    return _looks_like_gateway_cmdline(_process_cmdline(proc)) and _process_in_current_scope(proc)


def _process_in_current_scope(proc: psutil.Process) -> bool:
    """Respect explicit PID-file overrides so tests/profiles do not stop each other."""
    expected_pid_file = os.getenv("AI_COMPANION_GATEWAY_PID_FILE")
    if not expected_pid_file:
        return True

    try:
        proc_env = proc.environ()
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return False

    actual_pid_file = proc_env.get("AI_COMPANION_GATEWAY_PID_FILE")
    if not actual_pid_file:
        return False

    try:
        return Path(actual_pid_file).resolve() == Path(expected_pid_file).resolve()
    except OSError:
        return actual_pid_file == expected_pid_file


def _find_gateway_pids() -> list[int]:
    """Find gateway processes even if the PID file is stale or missing."""
    pids: set[int] = set()
    file_pid = _read_pid_file()
    if file_pid and _is_gateway_pid(file_pid):
        pids.add(file_pid)

    current_pid = os.getpid()
    for proc in psutil.process_iter(["pid", "cmdline"]):
        pid = proc.info.get("pid")
        if not isinstance(pid, int) or pid == current_pid:
            continue
        try:
            cmdline = " ".join(proc.info.get("cmdline") or [])
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
        if _looks_like_gateway_cmdline(cmdline) and _process_in_current_scope(proc):
            pids.add(pid)

    return sorted(pids)


def _wait_for_exit(pids: list[int], timeout: float) -> list[int]:
    deadline = time.time() + timeout
    remaining = list(dict.fromkeys(pids))
    while remaining and time.time() < deadline:
        remaining = [pid for pid in remaining if psutil.pid_exists(pid)]
        if remaining:
            time.sleep(0.2)
    return [pid for pid in remaining if psutil.pid_exists(pid)]


def _terminate_process_tree(pid: int, *, force: bool = False) -> None:
    if pid == os.getpid():
        return

    if sys.platform == "win32":
        args = ["taskkill", "/T", "/PID", str(pid)]
        if force:
            args.insert(1, "/F")
        try:
            subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            return
        except (FileNotFoundError, subprocess.SubprocessError):
            pass

    try:
        proc = psutil.Process(pid)
        targets = proc.children(recursive=True) + [proc]
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return

    for target in targets:
        try:
            if force:
                target.kill()
            else:
                target.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def stop_gateway(silent: bool = False) -> bool:
    """Stop all gateway processes and their child process trees."""
    pids = _find_gateway_pids()
    if not pids:
        remove_gateway_pid()
        if not silent:
            print("[OK] Gateway 已停止")
        return True

    for pid in pids:
        _terminate_process_tree(pid, force=False)

    remaining = _wait_for_exit(pids, timeout=5)
    if remaining:
        for pid in remaining:
            _terminate_process_tree(pid, force=True)
        remaining = _wait_for_exit(remaining, timeout=5)

    # A final scan catches detached children or processes hidden by a stale PID file.
    remaining = sorted(set(remaining) | set(_find_gateway_pids()))
    if remaining:
        if not silent:
            pid_text = ", ".join(str(pid) for pid in remaining)
            print(f"[ERROR] 无法停止 Gateway (PID: {pid_text})，请手动结束进程")
        return False

    remove_gateway_pid()
    if not silent:
        print("[OK] Gateway 已停止")
    return True


def start_gateway(sync: bool = False) -> int | None:
    """Start gateway process."""
    running_pids = _find_gateway_pids()
    if running_pids:
        print("[ERROR] Gateway 已在运行")
        print(f"   PID: {', '.join(str(pid) for pid in running_pids)}")
        print("   使用 'ai-companion gateway stop' 停止")
        return None

    ensure_log_dir()
    cmd = [sys.executable, "-m", "ai_companion.gateway"]

    if sync:
        print("正在启动 Gateway（前台模式）...")
        from ai_companion.gateway.cmd import run_gateway

        asyncio.run(run_gateway(daemon=False))
        return None

    cmd.append("--daemon")
    with open(GATEWAY_LOG_FILE, "a", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    save_gateway_pid(process.pid)
    print(f"[OK] Gateway 已启动 (PID: {process.pid})")
    print(f"  日志文件: {GATEWAY_LOG_FILE}")
    print("  使用 'ai-companion gateway logs' 查看日志")
    return process.pid


def restart_gateway(sync: bool = False) -> bool:
    """Restart gateway."""
    was_running = is_gateway_running()

    if was_running:
        print("正在停止 Gateway...")
        stop_gateway(silent=True)
        time.sleep(2)

    print("正在启动 Gateway...")
    result = start_gateway(sync=sync)
    return result is not None


def replace_gateway(sync: bool = False) -> bool:
    """Replace gateway by stopping old instances before starting a new one."""
    print("正在替换 Gateway...")

    if is_gateway_running():
        print("正在停止旧 Gateway...")
        stop_gateway(silent=True)
        time.sleep(2)

    print("正在启动新 Gateway...")
    result = start_gateway(sync=sync)
    return result is not None


def show_gateway_status() -> None:
    """Show gateway status."""
    pids = _find_gateway_pids()
    if pids:
        pid_text = ", ".join(str(pid) for pid in pids)
        print(f"[OK] Gateway 运行中 (PID: {pid_text})")
        print(f"  日志文件: {GATEWAY_LOG_FILE}")
        try:
            from ai_companion.gateway.status import read_runtime_status

            runtime = read_runtime_status() or {}
        except Exception:
            runtime = {}
        platforms = runtime.get("platforms") if isinstance(runtime, dict) else {}
        if isinstance(platforms, dict) and platforms:
            print("  平台状态:")
            for name, status in sorted(platforms.items()):
                if not isinstance(status, dict):
                    continue
                state = status.get("state") or "unknown"
                detail = _format_platform_status_detail(name, status)
                suffix = f" ({detail})" if detail else ""
                print(f"    - {name}: {state}{suffix}")
    else:
        print("[ERROR] Gateway 未运行")


def _format_platform_status_detail(name: str, status: dict[str, Any]) -> str:
    parts = []
    if name == "weixin":
        account = status.get("account_id_hint") or status.get("account_id")
        if account:
            parts.append(f"account={account}")
    error = status.get("error_message")
    if error:
        parts.append(f"last_error={error}")
    return ", ".join(str(part) for part in parts if part)


def tail_logs(lines: int = 50) -> None:
    """Print latest gateway log lines."""
    if not GATEWAY_LOG_FILE.exists():
        print("[ERROR] 日志文件不存在")
        return

    print(f"=== Gateway 最新 {lines} 行日志 ===")
    try:
        with open(GATEWAY_LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            for line in all_lines[-lines:]:
                print(line, end="")
    except KeyboardInterrupt:
        pass
