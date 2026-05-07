"""Shared helpers for gateway platform adapters."""

from __future__ import annotations

import time
from typing import Dict


class MessageDeduplicator:
    """TTL-based message ID deduplication cache."""

    def __init__(self, max_size: int = 2000, ttl_seconds: float = 300):
        self._seen: Dict[str, float] = {}
        self._max_size = max_size
        self._ttl = ttl_seconds

    def is_duplicate(self, msg_id: str) -> bool:
        """Return True when ``msg_id`` was seen within the TTL window."""
        if not msg_id:
            return False
        now = time.time()
        if msg_id in self._seen:
            if now - self._seen[msg_id] < self._ttl:
                return True
            del self._seen[msg_id]
        self._seen[msg_id] = now
        if len(self._seen) > self._max_size:
            cutoff = now - self._ttl
            self._seen = {key: seen_at for key, seen_at in self._seen.items() if seen_at > cutoff}
        return False

    def clear(self) -> None:
        self._seen.clear()
