"""
Gateway 模块入口 - 支持 ai-companion gateway 直接执行
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# 添加项目根目录和 vendor 目录到 path
_project_root = Path(__file__).parent.parent.parent
_vendor_dir = _project_root / "ai_companion" / "_vendor"
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_vendor_dir))

from ai_companion.gateway.cmd import run_gateway


class AiohttpAccessFilter(logging.Filter):
    """过滤 aiohttp.access 的 INFO 日志，只打印 warn 和 error"""

    def filter(self, record):
        if record.name == "aiohttp.access" and record.levelno == logging.INFO:
            return False
        return True


def setup_logging():
    """设置日志：同时输出到 stdout 和文件"""
    import logging.handlers
    import pathlib

    log_dir = pathlib.Path.home() / ".ai-companion" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Gateway 日志
    gateway_log_file = log_dir / "gateway.log"
    gateway_file_handler = logging.handlers.RotatingFileHandler(
        gateway_log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    gateway_file_handler.setLevel(logging.DEBUG)
    gateway_file_handler.addFilter(AiohttpAccessFilter())

    # 人生轨迹日志（独立文件）
    life_log_file = log_dir / "life.log"
    life_file_handler = logging.handlers.RotatingFileHandler(
        life_log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    life_file_handler.setLevel(logging.INFO)
    life_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    # 配置根日志
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[console_handler, gateway_file_handler],
    )

    # 为人生轨迹模块单独配置日志
    life_logger = logging.getLogger("ai_companion.proactive.life_engine")
    life_logger.addHandler(life_file_handler)
    life_logger.setLevel(logging.INFO)

    return log_dir


if __name__ == "__main__":
    # Windows 控制台需要设置编码
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="AI Companion Gateway")
    parser.add_argument("--daemon", action="store_true", help="守护进程模式（关闭终端后继续运行）")
    args = parser.parse_args()

    log_dir = setup_logging()

    asyncio.run(run_gateway(daemon=args.daemon))
