"""
Gateway 进程管理 - 启动、停止、重启网关服务
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# 项目根目录
_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))

GATEWAY_PID_FILE = Path(os.environ.get("AI_COMPANION_GATEWAY_PID_FILE", Path.home() / ".ai-companion" / "gateway.pid"))
GATEWAY_LOG_FILE = Path(os.environ.get("AI_COMPANION_LOG_DIR", Path.home() / ".ai-companion" / "logs")) / "gateway.log"


def get_gateway_pid() -> int | None:
    """获取 gateway 进程 PID"""
    if not GATEWAY_PID_FILE.exists():
        return None
    try:
        pid = int(GATEWAY_PID_FILE.read_text(encoding="utf-8").strip())
        # 检查进程是否存在
        os.kill(pid, 0)
        return pid
    except (ValueError, FileNotFoundError, ProcessLookupError, OSError):
        # 清理无效的 PID 文件
        GATEWAY_PID_FILE.unlink(missing_ok=True)
        return None


def save_gateway_pid(pid: int) -> None:
    """保存 gateway PID"""
    GATEWAY_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    GATEWAY_PID_FILE.write_text(str(pid), encoding="utf-8")


def remove_gateway_pid() -> None:
    """删除 gateway PID 文件"""
    GATEWAY_PID_FILE.unlink(missing_ok=True)


def is_gateway_running() -> bool:
    """检查 gateway 是否在运行"""
    return get_gateway_pid() is not None


def ensure_log_dir() -> None:
    """确保日志目录存在"""
    GATEWAY_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def stop_gateway(silent: bool = False) -> bool:
    """停止 gateway 进程及其子进程（包括 UI）"""
    # 读取 PID 文件，不依赖 os.kill 验证
    pid = None
    if GATEWAY_PID_FILE.exists():
        try:
            pid = int(GATEWAY_PID_FILE.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            pass

    # 尝试杀死进程（不管 os.kill 验证结果如何）
    if pid:
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
            else:
                os.kill(-pid, signal.SIGTERM)
        except FileNotFoundError:
            pass  # 进程已不存在
        except ProcessLookupError:
            pass
        except OSError:
            pass

    # 等待进程退出
    for _ in range(5):
        if pid is None or not is_gateway_running():
            break
        time.sleep(0.5)
    else:
        # 强制杀死
        if pid:
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
                else:
                    os.kill(-pid, signal.SIGKILL)
            except (FileNotFoundError, ProcessLookupError, OSError):
                pass
        time.sleep(1)

    if pid is not None and is_gateway_running():
        if not silent:
            print(f"[ERROR] 无法停止 Gateway (PID: {pid})，请手动结束进程")
        elif not silent:
            print("[ERROR] Gateway 未运行")
        return False

    remove_gateway_pid()
    if not silent:
        print("[OK] Gateway 已停止")
    return True


def start_gateway(sync: bool = False) -> int | None:
    """启动 gateway 进程"""
    # 检查是否已在运行
    if is_gateway_running():
        print("[ERROR] Gateway 已在运行")
        print(f"   PID: {get_gateway_pid()}")
        print("   使用 'ai-companion gateway stop' 停止")
        return None

    ensure_log_dir()

    # 启动进程
    cmd = [sys.executable, "-m", "ai_companion.gateway"]

    if sync:
        # 前台模式：直接在当前进程运行，显示日志
        print("正在启动 Gateway（前台模式）...")
        from ai_companion.gateway.cmd import run_gateway
        import asyncio
        asyncio.run(run_gateway(daemon=False))
        return None
    else:
        # 守护进程模式（默认）：后台运行
        cmd.append("--daemon")
        with open(GATEWAY_LOG_FILE, "a", encoding="utf-8") as log_file:
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True
            )

        save_gateway_pid(process.pid)
        print(f"[OK] Gateway 已启动 (PID: {process.pid})")
        print(f"  日志文件: {GATEWAY_LOG_FILE}")
        print("  使用 'ai-companion gateway logs' 查看日志")
        return process.pid


def restart_gateway(sync: bool = False) -> bool:
    """重启 gateway"""
    was_running = is_gateway_running()

    if was_running:
        print("正在停止 Gateway...")
        stop_gateway(silent=True)
        time.sleep(2)

    print("正在启动 Gateway...")
    result = start_gateway(sync=sync)
    return result is not None


def replace_gateway(sync: bool = False) -> bool:
    """替换 gateway（先停止旧实例，再启动新实例）"""
    print("正在替换 Gateway...")

    # 先停止旧实例
    if is_gateway_running():
        print("正在停止旧 Gateway...")
        stop_gateway(silent=True)
        time.sleep(2)

    # 再启动新实例
    print("正在启动新 Gateway...")
    result = start_gateway(sync=sync)
    return result is not None


def show_gateway_status() -> None:
    """显示 gateway 状态"""
    pid = get_gateway_pid()
    if pid:
        print(f"[OK] Gateway 运行中 (PID: {pid})")
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
    """输出 gateway 最新日志"""
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
