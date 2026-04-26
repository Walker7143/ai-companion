"""
Gateway 进程管理 - 启动、停止、重启网关服务
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# 项目根目录
_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))

GATEWAY_PID_FILE = Path.home() / ".ai-companion" / "gateway.pid"
GATEWAY_LOG_FILE = Path.home() / ".ai-companion" / "logs" / "gateway.log"


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
    """停止 gateway 进程"""
    pid = get_gateway_pid()
    if not pid:
        if not silent:
            print("❌ Gateway 未运行")
        return False

    try:
        if sys.platform == "win32":
            # Windows: 使用 taskkill 替代信号
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
            time.sleep(1)
        else:
            os.kill(pid, signal.SIGTERM)
            # 等待进程退出
            for _ in range(10):
                try:
                    os.kill(pid, 0)
                    time.sleep(0.5)
                except ProcessLookupError:
                    break
            else:
                # 强制杀死
                os.kill(pid, signal.SIGKILL)

        remove_gateway_pid()
        if not silent:
            print("✓ Gateway 已停止")
        return True
    except ProcessLookupError:
        remove_gateway_pid()
        if not silent:
            print("✓ Gateway 已停止")
        return True
    except Exception as e:
        if not silent:
            print(f"❌ 停止失败: {e}")
        return False


def start_gateway(sync: bool = False) -> int | None:
    """启动 gateway 进程"""
    # 检查是否已在运行
    if is_gateway_running():
        print("❌ Gateway 已在运行")
        print(f"   PID: {get_gateway_pid()}")
        print("   使用 'python -m ai_companion gateway stop' 停止")
        return None

    ensure_log_dir()

    # 启动进程
    cmd = [sys.executable, "-m", "ai_companion.gateway"]
    with open(GATEWAY_LOG_FILE, "a", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True
        )

    save_gateway_pid(process.pid)

    if sync:
        # 同步模式：等待启动完成，输出日志
        print("正在启动 Gateway...")
        time.sleep(3)

        # 检查是否启动成功
        if not is_gateway_running():
            print("❌ Gateway 启动失败")
            return None

        print(f"✓ Gateway 已启动 (PID: {process.pid})")
        print(f"  日志文件: {GATEWAY_LOG_FILE}")

        # 实时输出日志
        print("\n=== Gateway 日志 ===")
        try:
            with open(GATEWAY_LOG_FILE, "r", encoding="utf-8") as f:
                f.seek(0, 2)  # 跳到末尾
                while is_gateway_running():
                    line = f.readline()
                    if line:
                        print(line, end="")
                    else:
                        time.sleep(0.5)
        except KeyboardInterrupt:
            print("\n停止日志输出...")
            print("Gateway 仍在后台运行，使用 'python -m ai_companion gateway stop' 停止")
        return None
    else:
        # 异步模式：后台运行
        print(f"✓ Gateway 已启动 (PID: {process.pid})")
        print(f"  日志文件: {GATEWAY_LOG_FILE}")
        print("  使用 'python -m ai_companion gateway logs' 查看日志")
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
        print(f"✓ Gateway 运行中 (PID: {pid})")
        print(f"  日志文件: {GATEWAY_LOG_FILE}")
    else:
        print("✗ Gateway 未运行")


def tail_logs(lines: int = 50) -> None:
    """输出 gateway 最新日志"""
    if not GATEWAY_LOG_FILE.exists():
        print("❌ 日志文件不存在")
        return

    print(f"=== Gateway 最新 {lines} 行日志 ===")
    try:
        with open(GATEWAY_LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            for line in all_lines[-lines:]:
                print(line, end="")
    except KeyboardInterrupt:
        pass
