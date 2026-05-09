"""Cross-process runtime locks for proactive/life schedulers."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


_IS_WINDOWS = sys.platform == "win32"


class BotSchedulerRuntimeLock:
    """A non-blocking lock that elects one scheduler owner for a bot."""

    _WINDOWS_LOCK_OFFSET = 0
    _WINDOWS_RECORD_OFFSET = 1

    def __init__(self, lock_path: Path, *, bot_id: str, metadata: Optional[dict[str, Any]] = None):
        self.lock_path = Path(lock_path)
        self.bot_id = bot_id
        self.metadata = metadata or {}
        self._handle = None

    @property
    def acquired(self) -> bool:
        return self._handle is not None

    def acquire(self) -> bool:
        if self._handle is not None:
            return True

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        handle = os.fdopen(fd, "r+b", buffering=0)
        if not self._try_lock(handle):
            handle.close()
            return False

        self._handle = handle
        self._write_record()
        return True

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        self._unlock(handle)
        try:
            handle.close()
        except OSError:
            pass

    def read_owner(self) -> Optional[dict[str, Any]]:
        try:
            with open(self.lock_path, "rb") as handle:
                if _IS_WINDOWS:
                    handle.seek(self._WINDOWS_RECORD_OFFSET)
                raw = handle.read().decode("utf-8", errors="replace").strip()
        except OSError:
            return None
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _write_record(self) -> None:
        if self._handle is None:
            return
        record = {
            "kind": "ai-companion-bot-scheduler",
            "bot_id": self.bot_id,
            "pid": os.getpid(),
            "argv": list(sys.argv),
            "cwd": os.getcwd(),
            "acquired_at": datetime.now(timezone.utc).isoformat(),
            "metadata": self.metadata,
        }
        offset = self._WINDOWS_RECORD_OFFSET if _IS_WINDOWS else 0
        self._handle.seek(offset)
        self._handle.truncate(offset)
        self._handle.write(json.dumps(record, ensure_ascii=False).encode("utf-8"))
        self._handle.flush()
        try:
            os.fsync(self._handle.fileno())
        except OSError:
            pass

    def _try_lock(self, handle) -> bool:
        try:
            if _IS_WINDOWS:
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\n")
                    handle.flush()
                handle.seek(self._WINDOWS_LOCK_OFFSET)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (BlockingIOError, OSError):
            return False

    def _unlock(self, handle) -> None:
        try:
            if _IS_WINDOWS:
                handle.seek(self._WINDOWS_LOCK_OFFSET)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
