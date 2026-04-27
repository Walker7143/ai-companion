"""
ProactiveScheduler - 主动唤醒调度器

后台运行，定期检查是否需要发送主动消息。
"""

import asyncio
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import ProactiveEngine
    from .config import ProactiveConfig

logger = logging.getLogger(__name__)


class ProactiveScheduler:
    """主动唤醒调度器（后台运行）"""

    def __init__(self, engine: "ProactiveEngine"):
        from .life_config import LifeConfig
        from .life_state import LifeState
        from .life_engine import LifeEngine

        self.engine = engine
        self.config = engine.config
        self._task: Optional[asyncio.Task] = None
        self._running = False

        # 加载 LifeEngine 相关组件
        bot_id = engine.bot_id
        persona_dir = Path(f"data/bots/{bot_id}/persona")
        self.life_config = LifeConfig(_persona_dir=persona_dir)
        self.life_config.load()
        self.life_state = LifeState(bot_id, Path("data/bots"))
        self.life_engine = LifeEngine(
            bot_id=bot_id,
            config=self.life_config,
            state=self.life_state,
            model=None,
            memory=None,
            persona_dir=persona_dir,
        )

    def set_dependencies(self, model, memory):
        """由外部注入 model 和 memory 依赖"""
        self.life_engine.set_model(model)
        self.life_engine.set_memory(memory)
        if hasattr(self.engine, '_persona_loader'):
            self.life_engine.set_persona_loader(self.engine._persona_loader)
        # 注入 life_engine 到 engine
        self.engine.set_life_engine(self.life_engine)

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
        logger.info(f"[ProactiveScheduler] 调度器开始运行，等待 {self.config.check_interval} 秒后首次检查")
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[ProactiveScheduler] 调度异常: {e}")

            # 等待下一次检查
            logger.debug(f"[ProactiveScheduler] 本次检查完成，{self.config.check_interval} 秒后进行下次检查")
            await asyncio.sleep(self.config.check_interval)

    async def _tick(self):
        """执行一次检查"""
        logger.info("[ProactiveScheduler] _tick() 被调用")
        if not self.config.is_active:
            logger.info(f"[ProactiveScheduler] Bot {self.engine.bot_id} 处于静默模式，跳过检查")
            return

        # 更新最后检查时间
        self.engine.state._state["last_check_time"] = datetime.now().isoformat()
        self.engine.state.save()

        # 检查空闲触发（主动消息发送受黄金时段限制）
        if self.config.idle_reminder_enabled and self.config.is_active:
            if self._is_golden_hour():
                logger.info("[ProactiveScheduler] 黄金时段，检查是否需要发送主动消息")
                message = await self.engine.check_and_maybe_remind()
                if message:
                    logger.info(f"[ProactiveScheduler] 已发送主动消息: {message[:30]}...")
                    await self._notify_platform(message)
                else:
                    logger.debug("[ProactiveScheduler] 检查完成，暂无消息需要发送")
            else:
                now = datetime.now()
                logger.debug(f"[ProactiveScheduler] 非黄金时段 ({now.hour}点)，跳过主动触发")

        # Bot 人生轨迹更新（不受黄金时段限制，生命自然流动）
        if self.config.is_active:
            await self._tick_life()

    def _is_golden_hour(self) -> bool:
        """检查当前是否在黄金时段"""
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            from datetime import timezone
            ZoneInfo = None

        if ZoneInfo:
            try:
                tz = ZoneInfo(self.config.timezone)
                now = datetime.now(tz)
            except Exception:
                now = datetime.now()
        else:
            now = datetime.now()

        current_hour = now.hour

        preferred_times = self.config.preferred_contact_times
        if not preferred_times:
            return True  # 没有配置黄金时段，默认通过

        for time_range in preferred_times:
            if '-' not in time_range:
                continue
            start_str, end_str = time_range.split('-')
            start_hour = int(start_str.split(':')[0])
            end_hour = int(end_str.split(':')[0])

            # 处理跨天情况（如 19:00-22:00）
            if start_hour <= end_hour:
                if start_hour <= current_hour < end_hour:
                    return True
            else:  # 跨天（如 22:00-02:00）
                if current_hour >= start_hour or current_hour < end_hour:
                    return True

        return False

    def _should_random_early(self) -> bool:
        """检查是否应该随机提前触发"""
        # 检查空闲时间是否达到最小比例
        idle_hours = self.engine._calc_idle_hours()
        min_ratio = self.config.random_trigger_min_ratio
        idle_threshold = self.config.idle_threshold_hours

        if idle_hours < idle_threshold * min_ratio:
            return False

        # 随机概率检查
        prob = self.config.random_trigger_prob
        if random.random() < prob:
            logger.info(f"[ProactiveScheduler] 随机提前触发！idle_hours={idle_hours:.1f}, prob={prob}")
            return True

        return False

    async def _tick_life(self):
        """Bot 人生轨迹更新（不受黄金时段限制，生命自然流动）"""
        try:
            # 短周期：日常小事（按 time_ratio 缩放）
            if self.life_config.is_daily_due(self.life_state.last_daily_tick):
                logger.debug("[ProactiveScheduler] 日常事件到期，执行 tick_daily")
                await self.life_engine.tick_daily()
            else:
                logger.debug(f"[ProactiveScheduler] 日常事件未到期（last_tick={self.life_state.last_daily_tick}）")

            # 长周期：人生大事（按 time_ratio 缩放）
            if self.life_config.is_major_due(self.life_state.last_major_tick):
                logger.debug("[ProactiveScheduler] 人生大事到期，执行 tick_major")
                await self.life_engine.tick_major()
            else:
                logger.debug(f"[ProactiveScheduler] 人生大事未到期（last_tick={self.life_state.last_major_tick}）")
        except Exception as e:
            logger.error(f"[ProactiveScheduler] _tick_life 异常: {e}")

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