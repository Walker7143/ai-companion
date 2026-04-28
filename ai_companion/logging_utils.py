import logging
import re
import sys
from pathlib import Path
from typing import Optional

LOG_DIR = Path.home() / ".ai-companion" / "logs"
_HANDLER_TAG_KEY = "_ai_companion_handler_type"


def _safe_name(name: str) -> str:
    """将 bot 名称转换为安全文件名（保留中文，替换路径非法字符）。"""
    safe = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", (name or "").strip())
    return safe or "unknown"


def _tag_handler(handler: logging.Handler, handler_type: str) -> None:
    setattr(handler, _HANDLER_TAG_KEY, handler_type)


def _remove_tagged_handlers(logger: logging.Logger, handler_type: str) -> None:
    for handler in list(logger.handlers):
        if getattr(handler, _HANDLER_TAG_KEY, None) == handler_type:
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass


def _build_file_handler(path: Path, handler_type: str) -> logging.FileHandler:
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    _tag_handler(handler, handler_type)
    return handler


class _PrefixAllowFilter(logging.Filter):
    def __init__(self, prefixes: tuple[str, ...]):
        super().__init__()
        self.prefixes = prefixes

    def filter(self, record: logging.LogRecord) -> bool:
        return any(record.name.startswith(p) for p in self.prefixes)


class _PrefixDenyFilter(logging.Filter):
    def __init__(self, prefixes: tuple[str, ...]):
        super().__init__()
        self.prefixes = prefixes

    def filter(self, record: logging.LogRecord) -> bool:
        return not any(record.name.startswith(p) for p in self.prefixes)


def _build_console_handler() -> logging.StreamHandler:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.WARNING)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    _tag_handler(handler, "console")
    return handler


def setup_logging(bot_name: Optional[str] = None) -> None:
    """配置日志输出；传入 bot_name 时按 bot 名称分文件。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Windows UTF-8 支持
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    suffix = f".{_safe_name(bot_name)}" if bot_name else ""
    cli_log_file = LOG_DIR / f"cli{suffix}.log"
    life_log_file = LOG_DIR / f"life{suffix}.log"
    proactive_log_file = LOG_DIR / f"proactive{suffix}.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    _remove_tagged_handlers(root_logger, "cli-file")
    if not any(getattr(h, _HANDLER_TAG_KEY, None) == "console" for h in root_logger.handlers):
        root_logger.addHandler(_build_console_handler())
    root_logger.addHandler(_build_file_handler(cli_log_file, "cli-file"))

    proactive_logger = logging.getLogger("ai_companion.proactive")
    proactive_logger.setLevel(logging.INFO)
    _remove_tagged_handlers(proactive_logger, "life-file")
    _remove_tagged_handlers(proactive_logger, "proactive-file")

    life_handler = _build_file_handler(life_log_file, "life-file")
    life_handler.addFilter(_PrefixAllowFilter(("ai_companion.proactive.life_",)))
    proactive_logger.addHandler(life_handler)

    proactive_handler = _build_file_handler(proactive_log_file, "proactive-file")
    proactive_handler.addFilter(_PrefixDenyFilter(("ai_companion.proactive.life_",)))
    proactive_logger.addHandler(proactive_handler)


def configure_bot_log_files(bot_name: str) -> None:
    """运行时切换到按 bot 名称分文件日志。"""
    setup_logging(bot_name=bot_name)
