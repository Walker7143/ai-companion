"""
LifeScheduler - 人生轨迹独立调度器

独立于 ProactiveScheduler，自己管理 LifeEngine 的 tick 周期。
不受黄金时段限制，生命自然流动。
"""

import asyncio
import logging
from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .life_engine import LifeEngine
    from .life_config import LifeConfig
    from .life_state import LifeState

logger = logging.getLogger(__name__)


class LifeScheduler:
    """人生轨迹独立调度器"""

    def __init__(self, life_engine: "LifeEngine", life_config: "LifeConfig", life_state: "LifeState"):
        self.life_engine = life_engine
        self.config = life_config
        self.state = life_state
        self._task: asyncio.Task = None
        self._running = False

    async def start(self):
        """启动调度器"""
        if self._running:
            logger.warning("[LifeScheduler] 调度器已在运行")
            return

        self._running = True
        self._task = asyncio.create_task(self._run())
        daily_interval = self.config.daily_interval
        major_interval = self.config.major_interval
        logger.info(f"[LifeScheduler] 启动，daily_interval={daily_interval}s, major_interval={major_interval}s, time_ratio={self.config.time_ratio}")

    async def stop(self):
        """停止调度器"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[LifeScheduler] 调度器已停止")

    async def _run(self):
        """调度器主循环"""
        logger.info("[LifeScheduler] 开始运行")

        while self._running:
            try:
                now = self._get_now()

                # 检查日常事件
                should_run_daily, daily_reason = self._should_run_daily(now)
                if should_run_daily:
                    logger.info(f"[LifeScheduler] 执行 tick_daily reason={daily_reason}")
                    await self.life_engine.tick_daily()
                else:
                    elapsed = (now - (self.state.last_daily_tick or datetime.fromtimestamp(0))).total_seconds()
                    logger.info(f"[LifeScheduler] 检查日常事件: elapsed={elapsed:.1f}s, daily_interval={self.config.daily_interval}s")
                    remaining = self.config.daily_interval - elapsed
                    logger.debug(f"[LifeScheduler] 日常事件 {remaining:.0f}s 后到期")

                # 检查人生大事
                elapsed = (now - (self.state.last_major_tick or datetime.fromtimestamp(0))).total_seconds()
                if elapsed >= self.config.major_interval:
                    logger.debug(f"[LifeScheduler] 人生大事到期，执行 tick_major")
                    await self.life_engine.tick_major()
                else:
                    remaining = self.config.major_interval - elapsed
                    logger.debug(f"[LifeScheduler] 人生大事 {remaining:.0f}s 后到期")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[LifeScheduler] 调度异常: {e}")
                import traceback
                logger.error(f"[LifeScheduler] 堆栈: {traceback.format_exc()}")

            # 自适应轮询：默认不超过 300s，极速测试可降到 1s。
            poll_interval = max(1, min(300, self.config.daily_interval, self.config.major_interval))
            await asyncio.sleep(poll_interval)

    def _get_now(self) -> datetime:
        return datetime.now()

    def _get_local_date(self) -> date:
        local_now_getter = getattr(self.life_engine, "_get_local_now", None)
        if callable(local_now_getter):
            return local_now_getter().date()
        return datetime.now().astimezone().date()

    def _parse_state_current_date(self) -> date | None:
        current_date = getattr(self.state, "current_date", None)
        if not current_date:
            return None
        try:
            return datetime.strptime(current_date, "%Y-%m-%d").date()
        except Exception:
            return None

    def _should_run_daily(self, now: datetime) -> tuple[bool, str]:
        if self._should_run_daily_on_local_rollover():
            local_date = self._get_local_date()
            current_date = self._parse_state_current_date()
            if current_date and local_date > current_date:
                return True, f"local_date_rollover:{current_date.isoformat()}->{local_date.isoformat()}"

        elapsed = (now - (self.state.last_daily_tick or datetime.fromtimestamp(0))).total_seconds()
        if elapsed >= self.config.daily_interval:
            return True, f"interval_elapsed:{elapsed:.1f}s"
        return False, "not_due"

    def _should_run_daily_on_local_rollover(self) -> bool:
        return (
            int(getattr(self.config, "time_ratio", 1) or 1) == 1
            and bool(getattr(self.config, "sync_with_local_time_when_realtime", True))
        )

    def get_status(self) -> dict:
        """获取调度器状态"""
        return {
            "running": self._running,
            "daily_interval": self.config.daily_interval,
            "major_interval": self.config.major_interval,
            "time_ratio": self.config.time_ratio,
            "last_daily_tick": self.state.last_daily_tick.isoformat() if self.state.last_daily_tick else None,
            "last_major_tick": self.state.last_major_tick.isoformat() if self.state.last_major_tick else None,
        }
