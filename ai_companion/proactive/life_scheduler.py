"""
LifeScheduler - 人生轨迹独立调度器

独立于 ProactiveScheduler，自己管理 LifeEngine 的 tick 周期。
不受黄金时段限制，生命自然流动。
"""

import asyncio
import logging
from datetime import datetime
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
        last_daily_check = 0
        last_major_check = 0

        while self._running:
            try:
                now = datetime.now()

                # 检查日常事件
                elapsed = (now - (self.state.last_daily_tick or datetime.fromtimestamp(0))).total_seconds()
                if elapsed >= self.config.daily_interval:
                    logger.debug(f"[LifeScheduler] 日常事件到期，执行 tick_daily")
                    await self.life_engine.tick_daily()
                else:
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

            # 等待一小段时间后再次检查（避免频繁轮询）
            await asyncio.sleep(10)

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