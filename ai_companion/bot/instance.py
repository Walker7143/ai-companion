import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from ..memory.engine import MemoryEngine
from ..persona.loader import PersonaLoader
from ..persona.engine import PersonaEngine
from ..persona.refusal_engine import RefusalEngine
from ..persona.refusal_category import RefusalCategory
from ..proactive import ProactiveConfig, ProactiveState, ProactiveEngine, ProactiveScheduler, create_platform
from ..proactive.life_config import LifeConfig
from ..proactive.life_state import LifeState
from ..proactive.life_engine import LifeEngine
from ..proactive.life_scheduler import LifeScheduler
from ..proactive.runtime_lock import BotSchedulerRuntimeLock
from ..skill import SkillDispatcher, SkillRegistry, ImageGenerationSkill, TTSSkill, MultimodalSender, create_channel
from ..skill.base import SkillContext
from ..skill.command import (
    contains_sensitive_token,
    execute_skill_command,
    is_skill_command,
    is_skill_management_command,
    redact_sensitive_tokens,
)
from .response_style import ResponseStylePolisher

if TYPE_CHECKING:
    from ..model.adapters.base import ModelAdapter

logger = logging.getLogger(__name__)


class BotInstance:
    """单个 Bot 的运行实例"""

    def __init__(self, config: dict, model: "ModelAdapter" = None,
                 memory_config: dict = None, data_dir: Path = None,
                 refusal_enabled: bool = True):
        self.id = config["id"]
        self.name = config["name"]
        self.description = config.get("description", "")
        self.skill_config = config.get("skills", {}) if isinstance(config.get("skills", {}), dict) else {}

        # 解析 data_dir：优先使用参数，其次使用 config 中的值
        if data_dir is None and "data_dir" in config:
            data_dir = Path(config["data_dir"])

        # 统一保存 data_dir 供后续使用
        self._data_dir = data_dir if data_dir else (Path(config["data_dir"]) if "data_dir" in config else Path(__file__).parent.parent.parent / "data" / "bots")

        # 人格文件目录：优先用户目录，不存在则用项目目录
        if data_dir:
            persona_dir = data_dir / self.id / "persona"
        else:
            persona_dir = Path(__file__).parent.parent.parent / "data" / "bots" / self.id / "persona"

        # 如果路径不存在，回退到项目内嵌的人格目录
        if not persona_dir.exists():
            persona_dir = Path(__file__).parent.parent.parent / "data" / "bots" / self.id / "persona"

        self.persona_loader = PersonaLoader(persona_dir)
        self.persona = self.persona_loader.load()
        self.persona_engine = PersonaEngine(self.persona)

        # 拒绝引擎（默认开启）
        self.refusal_engine = RefusalEngine(
            bot_id=self.id,
            persona_dir=persona_dir,
            enabled=refusal_enabled
        )

        # 模型（由 BotManager 注入）
        self.model: "ModelAdapter" = model
        self._initialized = False
        self._last_model_error: str | None = None

        # 如果模型已注入，立即设置到拒绝引擎
        if model is not None:
            self.refusal_engine.set_model(model)

        # 记忆引擎
        self.memory: Optional[MemoryEngine] = None
        if memory_config is not None:
            # 构建人格文件路径（供记忆引擎写回关键变化）
            persona_backstory_path = str(persona_dir / "backstory.json")
            self.memory = MemoryEngine(
                bot_id=self.id,
                memory_dir=self._data_dir,
                config=memory_config,
                persona_backstory_path=persona_backstory_path,
            )

        # 对话历史（用于快速回复，暂时保留）
        self.conversation_history: list[dict] = []

        # ── 主动唤醒系统 ─────────────────────────────────────
        self.proactive_config = ProactiveConfig(persona_dir)
        self.proactive_state = ProactiveState(self.id, self._data_dir)
        self.proactive_engine = ProactiveEngine(
            bot_id=self.id,
            config=self.proactive_config,
            state=self.proactive_state,
            model=model,
            memory=self.memory,
            personality_type=self._detect_personality_type(),
        )
        self.proactive_scheduler: Optional[ProactiveScheduler] = None
        self._proactive_platform = None
        self._schedulers_started = False
        self._proactive_scheduler_lock: Optional[BotSchedulerRuntimeLock] = None
        self._proactive_scheduler_lock_owner: Optional[dict] = None
        self._life_scheduler_lock: Optional[BotSchedulerRuntimeLock] = None
        self._life_scheduler_lock_owner: Optional[dict] = None
        self._allowed_proactive_scheduler_platforms: Optional[set[str]] = None
        self._background_tasks: set[asyncio.Task] = set()

        # ── 人生轨迹系统 ─────────────────────────────────────
        self.life_config = LifeConfig(_persona_dir=persona_dir)
        self.life_config.load()
        self.life_state = LifeState(self.id, self._data_dir)
        self.life_engine = LifeEngine(
            bot_id=self.id,
            config=self.life_config,
            state=self.life_state,
            model=model,
            memory=self.memory,
            persona_dir=persona_dir,
        )
        self.proactive_engine.set_life_engine(self.life_engine)
        self.life_scheduler: Optional[LifeScheduler] = None

        # 初始化日期和年龄（从 profile.json 读取）
        self._init_life_from_profile()

        # ── 技能系统 ─────────────────────────────────────
        self.skill_dispatcher = SkillDispatcher()
        self._register_skills()

        self.multimodal_sender: Optional[MultimodalSender] = None
        self._channel = None
        self.response_polisher = ResponseStylePolisher()

    def _register_skills(self):
        """注册可用技能（内置 + 已安装的）"""
        image_config = dict(self.skill_config.get("image_generation", {}) or {})
        tts_config = dict(self.skill_config.get("tts", {}) or {})

        # 图片生成技能
        self.skill_dispatcher.register(ImageGenerationSkill(image_config))
        # TTS 技能
        self.skill_dispatcher.register(TTSSkill(tts_config))

        # 从注册中心加载已安装的 Skills
        self.skill_registry = SkillRegistry()
        for skill_info in self.skill_registry.list_installed():
            if skill_info.get("enabled", True):
                skill = self.skill_registry.load_skill(skill_info["name"])
                if skill:
                    self.skill_dispatcher.register(skill)
                    logger.info(f"[BotInstance] 加载已安装技能: {skill_info['name']}")

    def _detect_personality_type(self) -> str:
        """检测性格类型"""
        return self._detect_personality_type_from_profile(self.persona.profile)

    def _detect_personality_type_from_profile(self, profile: dict) -> str:
        tags = "".join(profile.get("personality_tags", []))
        if "傲娇" in tags or "外冷内热" in tags:
            return "傲娇"
        elif "活泼" in tags or "开朗" in tags:
            return "活泼"
        elif "高冷" in tags:
            return "高冷"
        elif "温柔" in tags:
            return "温柔"
        return "默认"

    def _sync_runtime_profile(self, profile: dict):
        """把最新 profile.json 同步到依赖人格字段的运行时对象。"""
        if not isinstance(profile, dict):
            return

        self.name = profile.get("name", self.name)
        initial_age = profile.get("age", self.life_state.initial_age or 20)
        birth_date = profile.get("birth_date")
        if birth_date:
            self.life_state.birth_date = birth_date
            self.life_config.birth_date = birth_date
            try:
                dt = datetime.strptime(birth_date, "%Y-%m-%d")
                self.life_state.birthday_month = dt.month
                self.life_config.season_birthday_month = dt.month
            except Exception:
                pass

        self.life_engine.refresh_bot_info_from_profile(profile)

        self.proactive_engine.bot_name = profile.get("name", self.id)
        self.proactive_engine.age = self.life_engine.get_status().get("bot_real_age", initial_age)
        self.proactive_engine.occupation = profile.get("occupation", "未知")
        self.proactive_engine.personality_type = self._detect_personality_type_from_profile(profile)

    def _refresh_runtime_settings(self):
        """重新读取 persona/config，保证本轮对话使用最新 Bot 设置。"""
        try:
            self.persona = self.persona_loader.load()
            self.persona_engine.persona = self.persona
            self._sync_runtime_profile(self.persona.profile)
        except Exception as e:
            logger.warning(f"[BotInstance] 刷新 persona 失败，沿用上一次运行时设置: {e}")

        try:
            self.refusal_engine.reload()
        except Exception as e:
            logger.debug(f"[BotInstance] 刷新拒绝引擎缓存失败（忽略）: {e}")

        try:
            self.proactive_config.load()
            self.life_config.load()
            if self.life_state.birth_date:
                self.life_config.birth_date = self.life_state.birth_date
        except Exception as e:
            logger.warning(f"[BotInstance] 刷新 proactive/life 配置失败，沿用当前配置: {e}")

    def _init_life_from_profile(self):
        """从 profile.json 初始化 Bot 的出生日期和初始年龄"""
        profile = self.persona.profile
        if not profile:
            return

        # 设置初始年龄
        initial_age = profile.get("age", 20)
        if self.life_state.initial_age is None:
            self.life_state.initial_age = initial_age

        # 设置生日月份
        birth_date = profile.get("birth_date")
        if birth_date:
            self.life_state.birth_date = birth_date
            self.life_config.birth_date = birth_date
            # 从 birth_date 提取月份
            try:
                from datetime import datetime
                dt = datetime.strptime(birth_date, "%Y-%m-%d")
                self.life_state.birthday_month = dt.month
                self.life_config.season_birthday_month = dt.month
            except Exception:
                pass
        else:
            # 如果没有 birth_date，从 age 和当前日期反推
            from datetime import datetime
            current_year = datetime.now().year
            birth_year = current_year - initial_age
            # 假设生日在配置的月份
            birthday_month = self.life_config.season_birthday_month or 6
            self.life_state.birth_date = f"{birth_year}-{birthday_month:02d}-15"
            self.life_state.birthday_month = birthday_month

        # 初始化当前日期（如果是新 Bot 或 bot_age_days 为 0）
        # 这样重装后 bot 会从今天开始新的人生
        if not self.life_state.current_date or self.life_state.bot_age_days == 0:
            self.life_state.current_date = datetime.now().strftime("%Y-%m-%d")
            self.life_state.year = datetime.now().year
            self.life_state.day_of_week = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][datetime.now().weekday()]
            self.life_state.is_weekend = datetime.now().weekday() >= 5

            # 初始化季节
            current_month = datetime.now().month
            self.life_state.current_month = current_month
            self.life_state.current_season = self.life_engine._get_season(current_month)

        # 设置依赖 profile 的运行时信息（用于事件生成和主动消息）
        self._sync_runtime_profile(profile)

        logger.info(f"[BotInstance] 初始化人生轨迹: initial_age={initial_age}, birth_date={self.life_state.birth_date}")

    def set_model(self, model: "ModelAdapter"):
        self.model = model
        self.refusal_engine.set_model(model)
        self.proactive_engine.set_model(model)
        self.life_engine.set_model(model)
        if self.memory:
            self.memory.set_summarizer(model)

    def set_proactive_platform(self, platform_type: str = None, feishu_adapter=None, gateway_adapter=None, **kwargs):
        """设置主动消息发送平台"""
        if gateway_adapter:
            adapter_platform = getattr(gateway_adapter, "platform", None)
            ptype = platform_type or (
                adapter_platform.value if hasattr(adapter_platform, "value") else str(adapter_platform or "gateway")
            )
            self._proactive_platform = gateway_adapter
            self.proactive_engine._platform_sender = lambda msg: self._wrap_gateway_send(msg, gateway_adapter, str(ptype).lower())
            return

        if feishu_adapter:
            self._proactive_platform = feishu_adapter
            self.proactive_engine._platform_sender = lambda msg: self._wrap_gateway_send(msg, feishu_adapter, "feishu")
            return

        ptype = platform_type or self.proactive_config.platform_type
        self._proactive_platform = create_platform(ptype, **kwargs)
        # 设置回调
        self.proactive_engine._platform_sender = lambda msg: self._proactive_platform.send(self.id, msg)

    def set_allowed_proactive_scheduler_platforms(self, platforms: Optional[set[str] | list[str] | tuple[str, ...]]):
        """限制当前运行入口允许启动哪些平台的主动唤醒调度器。"""
        if platforms is None:
            self._allowed_proactive_scheduler_platforms = None
            return
        self._allowed_proactive_scheduler_platforms = {str(item).lower() for item in platforms}

    def _ensure_proactive_platform_sender(self):
        """确保主动唤醒有发送通道；CLI 默认打印到终端。"""
        if self.proactive_engine._platform_sender:
            return

        ptype = self.proactive_config.platform_type
        if ptype == "webhook":
            webhook_url = self.proactive_config.webhook_url
            if webhook_url:
                self.set_proactive_platform("webhook", webhook_url=webhook_url)
            else:
                logger.warning("[BotInstance] proactive platform=webhook 但未配置 webhook_url")
            return

        if ptype in {"feishu", "weixin"}:
            # Gateway 会注入对应 adapter；没有注入时不伪装发送成功。
            logger.warning("[BotInstance] proactive platform=%s 但未注入 gateway adapter", ptype)
            return

        self.set_proactive_platform("cli")

    async def _wrap_gateway_send(self, message: str, adapter, platform_type: str) -> bool:
        """包装 gateway adapter 发送（适配 proactive 引擎的接口）"""
        try:
            chat_id = getattr(self, f"_{platform_type}_chat_id", None)
            proactive_cfg = self.proactive_config.to_dict() if hasattr(self.proactive_config, "to_dict") else {}
            if not chat_id:
                home_channel = proactive_cfg.get("home_channel")
                if isinstance(home_channel, dict):
                    chat_id = home_channel.get("chat_id") or home_channel.get("group_id")
                else:
                    chat_id = home_channel
            if not chat_id:
                platform_cfg = proactive_cfg.get("platform", {}) if isinstance(proactive_cfg, dict) else {}
                chat_id = (
                    platform_cfg.get("home_channel")
                    or platform_cfg.get("chat_id")
                    or platform_cfg.get("group_id")
                )
            if not chat_id:
                logger.warning("[BotInstance] %s 未配置 home_channel，无法发送主动消息", platform_type)
                return False
            result = await adapter.send(chat_id=chat_id, content=message)
            success = result.success if hasattr(result, 'success') else result
            if not success:
                error = getattr(result, "error", "unknown") if result is not None else "unknown"
                logger.warning("[BotInstance] %s 主动消息发送失败: %s", platform_type, error)
            return success
        except Exception as e:
            logger.error("[BotInstance] %s 发送失败: %s", platform_type, e)
            return False

    def set_channel(self, channel_type: str = "cli", **kwargs):
        """设置消息通道（用于多模态发送）"""
        self._channel = create_channel(channel_type, **kwargs)
        self.multimodal_sender = MultimodalSender(
            bot_id=self.id,
            channel=self._channel,
            skill_dispatcher=self.skill_dispatcher
        )

    async def init(self, start_schedulers: bool = True):
        """初始化 Bot 运行时。

        Args:
            start_schedulers: 是否同时启动后台调度器（proactive/life）。
        """
        if self.memory:
            await self.memory.init()
            if self.model:
                self.memory.set_summarizer(self.model)
            self.proactive_engine.set_memory(self.memory)
            self.memory.start_session()
        self._initialized = True
        if start_schedulers:
            await self._ensure_schedulers_started()
        else:
            logger.info(f"[BotInstance] {self.name} 已初始化（延迟启动调度器）")

    async def _ensure_schedulers_started(self):
        """按需启动后台调度器（只启动一次）。"""
        if self.proactive_scheduler and self.life_scheduler:
            return

        await self._ensure_proactive_scheduler_started()
        await self._ensure_life_scheduler_started()
        self._schedulers_started = bool(self.proactive_scheduler or self.life_scheduler)

    async def _ensure_proactive_scheduler_started(self):
        if self.proactive_scheduler:
            return

        if not self.proactive_config.is_active:
            logger.info(f"[BotInstance] {self.name} 处于静默模式，跳过主动唤醒调度器")
            return

        platform_type = (self.proactive_config.platform_type or "cli").lower()
        allowed = self._allowed_proactive_scheduler_platforms
        if allowed is not None and platform_type not in allowed:
            logger.info(
                "[BotInstance] 当前入口不接管 %s 平台的主动唤醒调度器，跳过 %s",
                platform_type,
                self.name,
            )
            return

        self._ensure_proactive_platform_sender()
        if not self.proactive_engine._platform_sender:
            logger.info(f"[BotInstance] {self.name} 未配置可用主动消息发送通道，跳过主动唤醒调度器")
            return

        if not self._acquire_scheduler_runtime_lock("proactive"):
            self._log_scheduler_lock_skip("主动唤醒", self._proactive_scheduler_lock_owner)
            return

        try:
            self.proactive_scheduler = ProactiveScheduler(self.proactive_engine)
            self.proactive_scheduler.set_dependencies(self.model, self.memory)
            await self.proactive_scheduler.start()
            logger.info(f"[BotInstance] 主动唤醒配置: idle_threshold={self.proactive_config.idle_threshold_hours}h, max_daily={self.proactive_config.max_daily}, 黄金时段={self.proactive_config.preferred_contact_times}")
        except Exception:
            self._release_scheduler_runtime_lock("proactive")
            self.proactive_scheduler = None
            raise

    async def _ensure_life_scheduler_started(self):
        if self.life_scheduler:
            return

        if not self._acquire_scheduler_runtime_lock("life"):
            self._log_scheduler_lock_skip("人生轨迹", self._life_scheduler_lock_owner)
            return

        try:
            self.life_scheduler = LifeScheduler(
                life_engine=self.life_engine,
                life_config=self.life_config,
                life_state=self.life_state,
            )
            self.life_engine.set_model(self.model)
            if self.memory:
                self.life_engine.set_memory(self.memory)
            self.life_engine.set_persona_loader(self.persona_loader)
            await self.life_scheduler.start()
            print(f"[OK] {self.name} 人生轨迹已启动")
            print(f"     日常事件间隔: {self.life_config.daily_interval}s, 人生大事间隔: {self.life_config.major_interval}s")
        except Exception:
            self._release_scheduler_runtime_lock("life")
            self.life_scheduler = None
            raise

    def _acquire_scheduler_runtime_lock(self, kind: str) -> bool:
        attr = f"_{kind}_scheduler_lock"
        owner_attr = f"_{kind}_scheduler_lock_owner"
        current_lock = getattr(self, attr)
        if current_lock and current_lock.acquired:
            return True

        lock_path = Path(self._data_dir) / self.id / "runtime" / f"{kind}_scheduler.lock"
        lock = BotSchedulerRuntimeLock(
            lock_path,
            bot_id=self.id,
            metadata={"bot_name": self.name, "scheduler": kind},
        )
        if lock.acquire():
            setattr(self, attr, lock)
            setattr(self, owner_attr, None)
            logger.info("[BotInstance] 已获得 %s 的 %s 调度器锁: %s", self.name, kind, lock_path)
            return True

        setattr(self, attr, None)
        setattr(self, owner_attr, lock.read_owner())
        return False

    def _release_scheduler_runtime_lock(self, kind: str) -> None:
        attr = f"_{kind}_scheduler_lock"
        owner_attr = f"_{kind}_scheduler_lock_owner"
        current_lock = getattr(self, attr)
        if current_lock:
            current_lock.release()
        setattr(self, attr, None)
        setattr(self, owner_attr, None)

    def _release_scheduler_runtime_locks(self) -> None:
        self._release_scheduler_runtime_lock("proactive")
        self._release_scheduler_runtime_lock("life")

    def _log_scheduler_lock_skip(self, label: str, owner: Optional[dict]) -> None:
        owner = owner or {}
        owner_pid = owner.get("pid")
        owner_text = f"PID {owner_pid}" if owner_pid else "其他进程"
        logger.info(
            "[BotInstance] %s 的%s调度器已由 %s 持有，当前进程跳过",
            self.name,
            label,
            owner_text,
        )

    async def ensure_schedulers_started(self):
        """公开方法：确保后台调度器已启动。"""
        await self._ensure_schedulers_started()

    def _build_system_prompt(self, adjustment_note: str = "", memory_suffix: str | None = None) -> str:
        life_context = self.life_engine.get_status() if self.life_engine else None
        system_prompt = self.persona_engine.build_system_prompt(life_context=life_context)
        if memory_suffix:
            system_prompt = system_prompt + "\n\n" + memory_suffix
        if adjustment_note:
            system_prompt = system_prompt + adjustment_note
        return system_prompt

    async def handle_message(self, user_input: str, memory_turn_context: dict | None = None) -> str:
        """处理用户消息，返回回复"""
        if self.model is None:
            return "[Error] 模型未初始化"
        if not self._initialized:
            logger.warning("[BotInstance] handle_message called before init(), initializing now...")
            await self.init()
        elif not self._schedulers_started:
            # CLI 延迟启动模式下，在首次对话时再启动后台调度器。
            await self._ensure_schedulers_started()

        self._refresh_runtime_settings()

        # 0. 用户发消息了，通知主动唤醒系统
        self.proactive_engine.on_user_message_received()

        if is_skill_management_command(user_input):
            response = await self._handle_skill_command(user_input)
            self._record_skill_command_history(user_input, response)
            return response

        # 1. 拒绝检查（如果启用）
        relationship_state = None
        if self.memory:
            relationship_state = await self.memory.relationship.get_state(
                bot_id=self.id,
                user_id=getattr(self.memory, "user_id", "default_user"),
            )

        refusal_response = await self.refusal_engine.check(
            user_request=user_input,
            memory_context=None,
            relationship_state=relationship_state
        )

        if refusal_response.refuse:
            # 拒绝时直接返回，不调用 LLM
            logger.info(f"[Refusal] 拒绝请求: {refusal_response.reason} | {refusal_response.category.value}")
            return refusal_response.reply or "抱歉，我无法帮你处理这个请求。"

        # 2. 软边界调整（不拒绝但返回调整后的回复）
        if refusal_response.category == RefusalCategory.SOFT_BOUNDARY and refusal_response.reply:
            logger.info(f"[Refusal] 软边界调整: {refusal_response.reason}")
            adjustment_note = f"\n\n[态度提示: {refusal_response.adjustment}]"
        else:
            adjustment_note = ""

        if is_skill_command(user_input):
            response = await self._handle_skill_command(user_input)
            self._record_skill_command_history(user_input, response)
            return response

        # 3. 情绪触发检测
        emotion_triggered = self._check_emotion_trigger(user_input)
        if emotion_triggered:
            logger.info(f"[Proactive] 情绪触发: {user_input[:30]}...")

        # 如果有记忆引擎，使用记忆上下文
        if self.memory:
            # 1. 检查并触发压缩
            await self.memory.maybe_compress()

            # 2. 加载上下文
            ctx = await self.memory.load_context(user_input)

            # 3. 构建带人格的记忆增强 system prompt
            system_prompt = self._build_system_prompt(
                adjustment_note=adjustment_note,
                memory_suffix=ctx.get("system_suffix"),
            )

            # 4. 构建 messages
            messages = ctx.get("working_history", [])
            messages.append({"role": "user", "content": user_input})

            # 5. 对话
            response = await self._chat_with_fallback(messages, system_prompt)
            if response is None:
                return self._format_model_failure_message()
            response = self._polish_response(response, ctx, relationship_state)

            # 6. 异步写入记忆
            self._track_background_task(
                self.memory.on_message(user_input, response, turn_context=memory_turn_context),
                name="memory.on_message",
            )
        else:
            system_prompt = self._build_system_prompt(adjustment_note=adjustment_note)
            messages = [{"role": "user", "content": user_input}]
            response = await self._chat_with_fallback(messages, system_prompt)
            if response is None:
                return self._format_model_failure_message()
            response = self._polish_response(response, {}, relationship_state)

        # 记录历史
        self.conversation_history.append({"role": "user", "content": user_input})
        self.conversation_history.append({"role": "assistant", "content": response})

        return response

    async def _handle_skill_command(self, user_input: str) -> str:
        context = SkillContext(
            bot_id=self.id,
            user_id=getattr(self.memory, "user_id", "default_user") if self.memory else "default_user",
            conversation_history=list(self.conversation_history),
            personality_tags=self.persona.profile.get("personality_tags", []) if self.persona else [],
        )
        return await execute_skill_command(self.skill_dispatcher, user_input, context, self.skill_registry)

    def _record_skill_command_history(self, user_input: str, response: str) -> None:
        history_input = redact_sensitive_tokens(user_input) if contains_sensitive_token(user_input) else user_input
        self.conversation_history.append({"role": "user", "content": history_input})
        self.conversation_history.append({"role": "assistant", "content": response})

    def _polish_response(self, response: str, memory_context: dict | None, relationship_state: dict | None) -> str:
        return self.response_polisher.polish(
            response,
            intent=(memory_context or {}).get("memory_intent", "casual_chat"),
            relationship_state=relationship_state or {},
            user_understanding=(memory_context or {}).get("user_understanding") or {},
        )

    async def _chat_with_fallback(self, messages: list[dict], system_prompt: str = "") -> Optional[str]:
        """调用模型聊天，失败时返回 None（由调用者处理友好提示）"""
        try:
            self._last_model_error = None
            return await self.model.chat(messages, system_prompt)
        except RuntimeError as e:
            self._last_model_error = self._sanitize_model_error(e)
            logger.error(f"[BotInstance] 对话失败: {self._last_model_error}")
            return None
        except Exception as e:
            self._last_model_error = self._sanitize_model_error(e)
            logger.exception("[BotInstance] 对话异常: %s", e)
            return None

    def _sanitize_model_error(self, error: Exception) -> str:
        detail = str(error) or type(error).__name__
        api_key = getattr(self.model, "api_key", "") if self.model else ""
        if api_key:
            detail = detail.replace(str(api_key), "[REDACTED_SECRET]")
        detail = redact_sensitive_tokens(detail)
        if len(detail) > 500:
            detail = detail[:500] + "...[truncated]"
        return detail

    def _format_model_failure_message(self) -> str:
        provider = getattr(self.model, "provider", "unknown") if self.model else "unknown"
        model_name = getattr(self.model, "model", "unknown") if self.model else "unknown"
        detail = self._last_model_error or "未知错误"
        return (
            "抱歉，模型请求失败，不一定是网络问题。\n"
            f"当前模型: {provider} / {model_name}\n"
            f"错误信息: {detail}\n"
            "请检查 API Key、base_url、模型名和代理配置；在飞书中可用 /status 或 /models 查看当前配置。"
        )

    def _check_emotion_trigger(self, user_input: str) -> bool:
        """检查是否触发了情绪关键词"""
        if not self.proactive_config.emotion_trigger_enabled:
            return False

        keywords = self.proactive_config.emotion_keywords
        for kw in keywords:
            if kw in user_input:
                # 设置延迟触发（等用户冷静一下再关心）
                delay = timedelta(minutes=self.proactive_config.emotion_response_delay_minutes)
                self.proactive_state.set_cooldown(f"emotion_{kw}", datetime.now() + delay)
                return True
        return False

    def get_proactive_status(self) -> dict:
        """获取主动唤醒状态"""
        return {
            "config": {
                "enabled": self.proactive_config.enabled,
                "mode": self.proactive_config.mode,
                "is_active": self.proactive_config.is_active,
                "check_interval": self.proactive_config.check_interval,
                "idle_threshold_hours": self.proactive_config.idle_threshold_hours,
            },
            "state": self.proactive_engine.get_status(),
            "scheduler": self.proactive_scheduler.get_status() if self.proactive_scheduler else None,
            "scheduler_lock": {
                "proactive": {
                    "held": bool(self._proactive_scheduler_lock and self._proactive_scheduler_lock.acquired),
                    "owner": self._proactive_scheduler_lock_owner,
                },
                "life": {
                    "held": bool(self._life_scheduler_lock and self._life_scheduler_lock.acquired),
                    "owner": self._life_scheduler_lock_owner,
                },
            },
        }

    def get_skill_capabilities(self) -> dict:
        """获取技能和通道能力"""
        capabilities = {
            "skills": {},
            "channel": None,
            "multimodal_sender": None,
        }
        for skill in self.skill_dispatcher._skills.values():
            capabilities["skills"][skill.name] = {
                "name": skill.name,
                "description": skill.description,
                "capabilities": skill.capabilities,
                "is_available": skill.is_available(),
                "supported_models": getattr(skill, "supported_models", []),
            }
        if self.multimodal_sender:
            capabilities["channel"] = self.multimodal_sender.get_capabilities()
            capabilities["multimodal_sender"] = {
                "enabled": True,
            }
        return capabilities

    def reset_history(self):
        """清空对话历史（同时重置工作记忆会话）"""
        self.conversation_history = []
        if self.memory:
            self.memory.start_session()

    def _track_background_task(self, coro, name: str = "background") -> asyncio.Task:
        task = asyncio.create_task(coro, name=f"{self.id}:{name}")
        self._background_tasks.add(task)

        def _done(t: asyncio.Task):
            self._background_tasks.discard(t)
            if t.cancelled():
                return
            try:
                exc = t.exception()
            except asyncio.CancelledError:
                return
            if exc is not None:
                logger.error(f"[BotInstance] 后台任务异常 ({name}): {exc}")

        task.add_done_callback(_done)
        return task

    async def _drain_background_tasks(self, timeout: float = 5.0):
        if not self._background_tasks:
            return
        done, pending = await asyncio.wait(self._background_tasks, timeout=timeout)
        for task in done:
            self._background_tasks.discard(task)
        if pending:
            logger.warning(f"[BotInstance] 取消未完成后台任务: {len(pending)}")
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            self._background_tasks.difference_update(pending)

    async def close(self):
        """关闭时清理资源"""
        if self.proactive_scheduler:
            await self.proactive_scheduler.stop()
        if self.life_scheduler:
            await self.life_scheduler.stop()
        self._schedulers_started = False
        self._release_scheduler_runtime_locks()
        await self._drain_background_tasks()
        if self.memory:
            await self.memory.close()
        # 关闭 MiniMax adapter 的 session
        if self.model and hasattr(self.model, 'close'):
            await self.model.close()
