from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any


class RunLogger:
    """Append-only JSONL run log for long imports."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def alog(self, event: str, **fields: Any) -> None:
        async with self._lock:
            self._write(event, **fields)

    def log(self, event: str, **fields: Any) -> None:
        self._write(event, **fields)

    def _write(self, event: str, **fields: Any) -> None:
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            **fields,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


class AsyncRateLimiter:
    """Simple process-local request start limiter."""

    def __init__(self, requests_per_minute: float = 0):
        self.requests_per_minute = max(0.0, float(requests_per_minute or 0))
        self._interval = 60.0 / self.requests_per_minute if self.requests_per_minute > 0 else 0.0
        self._next_at = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> float:
        if self._interval <= 0:
            return 0.0
        async with self._lock:
            now = time.monotonic()
            wait_seconds = max(0.0, self._next_at - now)
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
                now = time.monotonic()
            self._next_at = max(now, self._next_at) + self._interval
            return wait_seconds
