"""
ProactiveScheduler - 主动唤醒调度器

后台运行，定期检查是否需要发送主动消息。
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import ProactiveEngine
    from .config import ProactiveConfig

logger = logging.getLogger(__name__)


class ProactiveScheduler:
    """主动唤醒调度器（后台运行）"""

    def __init__(self, engine: "ProactiveEngine"):
        self.engine = engine
        self.config = engine.config
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """启动调度器（后台协程）"""
        if self._running:
            logger.warning("[ProactiveScheduler] 调度器已在运行")
            return

        if not self.config.is_active:
            logger.info(f"[ProactiveScheduler] Bot {self.engine.bot_id} 处于静默模式，不启动调度")
            return

        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info(f"[ProactiveScheduler] 启动调度器，间隔 {self.config.check_interval} 秒")

    async def stop(self):
        """停止调度器"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[ProactiveScheduler] 调度器已停止")

    async def _run(self):
        """调度器主循环"""
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[ProactiveScheduler] 调度异常: {e}")

            # 等待下一次检查
            await asyncio.sleep(self.config.check_interval)

    async def _tick(self):
        """执行一次检查"""
        if not self.config.is_active:
            return

        # 更新最后检查时间
        self.engine.state._state["last_check_time"] = datetime.now().isoformat()

        # 检查空闲触发
        if self.config.idle_reminder_enabled:
            message = await self.engine.check_and_maybe_remind()
            if message:
                logger.info(f"[ProactiveScheduler] 已发送主动消息: {message[:30]}...")
                # 通知平台发送（通过回调）
                await self._notify_platform(message)

        # 检查情绪触发（这个在 handle_message 中触发，这里只做延迟检查）
        # ...

    async def _notify_platform(self, message: str):
        """通知平台发送消息（由平台适配器实现具体发送）"""
        # 如果有平台适配器，调用它
        if hasattr(self.engine, "_platform_sender"):
            try:
                await self.engine._platform_sender(message)
            except Exception as e:
                logger.error(f"[ProactiveScheduler] 平台发送失败: {e}")

    def get_status(self) -> dict:
        """获取调度器状态"""
        return {
            "running": self._running,
            "check_interval": self.config.check_interval,
            "is_active": self.config.is_active,
        }