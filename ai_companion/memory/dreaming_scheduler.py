"""Background scheduler for automatic dreaming runs."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .dreaming import DreamingOrchestrator

logger = logging.getLogger(__name__)


class DreamingScheduler:
    """Lightweight background scheduler for user-facing memory organization."""

    def __init__(self, orchestrator: "DreamingOrchestrator"):
        self.orchestrator = orchestrator
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run(), name="dreaming-scheduler")
        logger.info("[DreamingScheduler] 启动自动整理调度器，间隔 %s 秒", self.orchestrator.auto_check_interval_seconds)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("[DreamingScheduler] 自动整理调度器已停止")

    async def _run(self):
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("[DreamingScheduler] 调度异常: %s", exc)
            await asyncio.sleep(self.orchestrator.auto_check_interval_seconds)

    async def _tick(self):
        if not self.orchestrator.config.get("enabled"):
            return
        if not self.orchestrator.config.get("auto_run_enabled"):
            return
        if not await self.orchestrator.should_auto_run():
            return
        logger.info("[DreamingScheduler] 命中自动整理条件，开始执行 dreaming.run")
        await self.orchestrator.run(trigger_source="auto_scheduler", trigger_reason="auto_dreaming_tick")

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "check_interval_seconds": self.orchestrator.auto_check_interval_seconds,
            "enabled": bool(self.orchestrator.config.get("enabled")),
            "auto_run_enabled": bool(self.orchestrator.config.get("auto_run_enabled")),
            "last_tick_at": datetime.now().isoformat() if self._running else None,
        }
