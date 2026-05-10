"""Gateway module entry point."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
_vendor_dir = _project_root / "ai_companion" / "_vendor"
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_vendor_dir))

from ai_companion.gateway.cmd import run_gateway
from ai_companion.logging_utils import (
    build_tail_preserving_file_handler,
    get_log_dir,
    get_log_max_bytes,
    start_log_limit_maintenance,
)


class AiohttpAccessFilter(logging.Filter):
    """Filter noisy aiohttp access INFO logs from gateway.log."""

    def filter(self, record):
        if record.name == "aiohttp.access" and record.levelno == logging.INFO:
            return False
        return True


def setup_logging():
    """Log to stdout plus capped gateway/life log files."""
    log_dir = get_log_dir()
    max_bytes = get_log_max_bytes()
    log_dir.mkdir(parents=True, exist_ok=True)
    start_log_limit_maintenance(log_dir, max_bytes=max_bytes)

    gateway_file_handler = build_tail_preserving_file_handler(
        log_dir / "gateway.log",
        max_bytes=max_bytes,
        level=logging.DEBUG,
    )
    gateway_file_handler.addFilter(AiohttpAccessFilter())

    life_file_handler = build_tail_preserving_file_handler(
        log_dir / "life.log",
        max_bytes=max_bytes,
        level=logging.INFO,
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[console_handler, gateway_file_handler],
        force=True,
    )

    life_logger = logging.getLogger("ai_companion.proactive.life_engine")
    life_logger.addHandler(life_file_handler)
    life_logger.setLevel(logging.INFO)

    return log_dir


if __name__ == "__main__":
    if sys.platform == "win32":
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="AI Companion Gateway")
    parser.add_argument("--daemon", action="store_true", help="Run as a daemon process")
    args = parser.parse_args()

    setup_logging()
    asyncio.run(run_gateway(daemon=args.daemon))
