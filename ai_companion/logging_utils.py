from __future__ import annotations

import logging
import os
import re
import sys
import threading
from pathlib import Path
from typing import Any, Optional

import yaml

DEFAULT_LOG_MAX_BYTES = 50 * 1024 * 1024
LOG_DIR = Path(os.environ.get("AI_COMPANION_LOG_DIR", Path.home() / ".ai-companion" / "logs"))
_HANDLER_TAG_KEY = "_ai_companion_handler_type"
_SIZE_UNITS = {
    "": 1,
    "b": 1,
    "k": 1024,
    "kb": 1024,
    "kib": 1024,
    "m": 1024 * 1024,
    "mb": 1024 * 1024,
    "mib": 1024 * 1024,
    "g": 1024 * 1024 * 1024,
    "gb": 1024 * 1024 * 1024,
    "gib": 1024 * 1024 * 1024,
}

_LIMITER_LOCK = threading.Lock()
_LIMITER_STOP = threading.Event()
_LIMITER_THREAD: threading.Thread | None = None
_LIMITED_LOG_DIRS: dict[Path, int] = {}
_ACTIVE_HANDLER_FILES: dict[Path, int] = {}


def get_log_dir() -> Path:
    return Path(os.environ.get("AI_COMPANION_LOG_DIR", Path.home() / ".ai-companion" / "logs"))


def parse_size_to_bytes(value: Any) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return max(0, int(value))

    text = str(value).strip().lower().replace(" ", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([a-z]*)", text)
    if not match:
        return None

    unit = match.group(2)
    if unit not in _SIZE_UNITS:
        return None
    return max(0, int(float(match.group(1)) * _SIZE_UNITS[unit]))


def _read_config_logging() -> dict[str, Any]:
    config_path = Path.home() / ".ai-companion" / "config" / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    logging_config = data.get("logging", {})
    return logging_config if isinstance(logging_config, dict) else {}


def get_log_max_bytes(config: dict[str, Any] | None = None) -> int:
    env_size = os.environ.get("AI_COMPANION_LOG_MAX_SIZE")
    env_bytes = os.environ.get("AI_COMPANION_LOG_MAX_BYTES")
    env_mb = os.environ.get("AI_COMPANION_LOG_MAX_MB")
    env_values = (env_size, env_bytes, f"{env_mb}MB" if env_mb not in (None, "") else None)
    for raw in env_values:
        parsed = parse_size_to_bytes(raw)
        if parsed is not None:
            return parsed

    logging_config: dict[str, Any] = {}
    if isinstance(config, dict):
        maybe_logging = config.get("logging", config)
        logging_config = maybe_logging if isinstance(maybe_logging, dict) else {}
    if not logging_config:
        logging_config = _read_config_logging()

    candidates = (
        logging_config.get("max_file_size"),
        logging_config.get("max_size"),
        logging_config.get("max_bytes"),
        f"{logging_config.get('max_file_size_mb')}MB"
        if logging_config.get("max_file_size_mb") not in (None, "")
        else None,
    )
    for raw in candidates:
        parsed = parse_size_to_bytes(raw)
        if parsed is not None:
            return parsed

    return DEFAULT_LOG_MAX_BYTES


def _drop_partial_utf8_prefix(data: bytes) -> bytes:
    index = 0
    while index < len(data) and (data[index] & 0b1100_0000) == 0b1000_0000:
        index += 1
    return data[index:]


def trim_log_file(path: Path, max_bytes: int | None = None) -> bool:
    """Keep only the newest bytes in a log file."""
    if max_bytes is None:
        max_bytes = get_log_max_bytes()
    if max_bytes <= 0 or not path.exists():
        return False

    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size <= max_bytes:
        return False

    try:
        with path.open("rb+") as file:
            keep_from = size - max_bytes
            drop_first_line = keep_from > 0
            if keep_from > 0:
                file.seek(keep_from - 1)
                drop_first_line = file.read(1) != b"\n"
            file.seek(keep_from)
            data = file.read()
            newline_index = data.find(b"\n") if drop_first_line else -1
            if 0 <= newline_index < len(data) - 1:
                data = data[newline_index + 1 :]
            else:
                data = _drop_partial_utf8_prefix(data)
            file.seek(0)
            file.write(data)
            file.truncate()
        return True
    except OSError:
        return False


def trim_log_dir(
    log_dir: Path,
    max_bytes: int | None = None,
    *,
    skip_active_handlers: bool = True,
) -> None:
    if max_bytes is None:
        max_bytes = get_log_max_bytes()
    if max_bytes <= 0 or not log_dir.exists():
        return
    active_files: set[Path] = set()
    if skip_active_handlers:
        with _LIMITER_LOCK:
            active_files = set(_ACTIVE_HANDLER_FILES)
    for log_file in log_dir.glob("*.log"):
        if skip_active_handlers:
            try:
                if log_file.resolve() in active_files:
                    continue
            except OSError:
                continue
        trim_log_file(log_file, max_bytes=max_bytes)


def _log_limiter_loop(interval_seconds: float) -> None:
    while not _LIMITER_STOP.wait(interval_seconds):
        with _LIMITER_LOCK:
            dirs = dict(_LIMITED_LOG_DIRS)
        for log_dir, max_bytes in dirs.items():
            trim_log_dir(log_dir, max_bytes=max_bytes)


def start_log_limit_maintenance(
    log_dir: Path | None = None,
    *,
    max_bytes: int | None = None,
    interval_seconds: float = 30.0,
) -> None:
    if log_dir is None:
        log_dir = get_log_dir()
    if max_bytes is None:
        max_bytes = get_log_max_bytes()
    if max_bytes <= 0:
        return

    log_dir.mkdir(parents=True, exist_ok=True)
    trim_log_dir(log_dir, max_bytes=max_bytes)

    global _LIMITER_THREAD
    with _LIMITER_LOCK:
        _LIMITED_LOG_DIRS[log_dir.resolve()] = max_bytes
        if _LIMITER_THREAD and _LIMITER_THREAD.is_alive():
            return
        _LIMITER_STOP.clear()
        _LIMITER_THREAD = threading.Thread(
            target=_log_limiter_loop,
            args=(interval_seconds,),
            name="ai-companion-log-limiter",
            daemon=True,
        )
        _LIMITER_THREAD.start()


class TailPreservingFileHandler(logging.FileHandler):
    """File handler that caps one log file by discarding old content."""

    def __init__(self, filename: Path, *, max_bytes: int, encoding: str = "utf-8"):
        self.max_bytes = max_bytes
        super().__init__(filename, mode="a", encoding=encoding)
        self._active_path = Path(self.baseFilename).resolve()
        self._active_registered = True
        with _LIMITER_LOCK:
            _ACTIVE_HANDLER_FILES[self._active_path] = _ACTIVE_HANDLER_FILES.get(self._active_path, 0) + 1
        self._trim_if_needed()

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self._trim_if_needed()

    def close(self) -> None:
        try:
            super().close()
        finally:
            active_path = getattr(self, "_active_path", None)
            if active_path is not None and getattr(self, "_active_registered", False):
                self._active_registered = False
                with _LIMITER_LOCK:
                    count = _ACTIVE_HANDLER_FILES.get(active_path, 0)
                    if count <= 1:
                        _ACTIVE_HANDLER_FILES.pop(active_path, None)
                    else:
                        _ACTIVE_HANDLER_FILES[active_path] = count - 1

    def _trim_if_needed(self) -> None:
        if self.max_bytes <= 0:
            return
        try:
            self.flush()
            filename = Path(self.baseFilename)
            if not filename.exists() or filename.stat().st_size <= self.max_bytes:
                return
            if self.stream:
                self.stream.close()
                self.stream = None
            keep_bytes = max(1, int(self.max_bytes * 0.9))
            trim_log_file(filename, max_bytes=keep_bytes)
            if not self.delay:
                self.stream = self._open()
        except Exception:
            if self.stream is None and not self.delay:
                try:
                    self.stream = self._open()
                except Exception:
                    pass


def _safe_name(name: str) -> str:
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


def build_tail_preserving_file_handler(
    path: Path,
    *,
    max_bytes: int | None = None,
    level: int = logging.INFO,
    formatter: logging.Formatter | None = None,
    handler_type: str | None = None,
) -> logging.FileHandler:
    if max_bytes is None:
        max_bytes = get_log_max_bytes()
    handler = TailPreservingFileHandler(path, max_bytes=max_bytes, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(
        formatter or logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    if handler_type:
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


def setup_logging(bot_name: Optional[str] = None, config: dict[str, Any] | None = None) -> None:
    """Configure CLI logging, optionally split by bot name."""
    log_dir = get_log_dir()
    max_bytes = get_log_max_bytes(config)
    log_dir.mkdir(parents=True, exist_ok=True)
    start_log_limit_maintenance(log_dir, max_bytes=max_bytes)

    if sys.platform == "win32":
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    suffix = f".{_safe_name(bot_name)}" if bot_name else ""
    cli_log_file = log_dir / f"cli{suffix}.log"
    life_log_file = log_dir / f"life{suffix}.log"
    proactive_log_file = log_dir / f"proactive{suffix}.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    _remove_tagged_handlers(root_logger, "cli-file")
    if not any(getattr(h, _HANDLER_TAG_KEY, None) == "console" for h in root_logger.handlers):
        root_logger.addHandler(_build_console_handler())
    root_logger.addHandler(
        build_tail_preserving_file_handler(cli_log_file, max_bytes=max_bytes, handler_type="cli-file")
    )

    proactive_logger = logging.getLogger("ai_companion.proactive")
    proactive_logger.setLevel(logging.INFO)
    _remove_tagged_handlers(proactive_logger, "life-file")
    _remove_tagged_handlers(proactive_logger, "proactive-file")

    life_handler = build_tail_preserving_file_handler(
        life_log_file, max_bytes=max_bytes, handler_type="life-file"
    )
    life_handler.addFilter(_PrefixAllowFilter(("ai_companion.proactive.life_",)))
    proactive_logger.addHandler(life_handler)

    proactive_handler = build_tail_preserving_file_handler(
        proactive_log_file, max_bytes=max_bytes, handler_type="proactive-file"
    )
    proactive_handler.addFilter(_PrefixDenyFilter(("ai_companion.proactive.life_",)))
    proactive_logger.addHandler(proactive_handler)


def configure_bot_log_files(bot_name: str) -> None:
    setup_logging(bot_name=bot_name)
