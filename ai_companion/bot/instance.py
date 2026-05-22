import asyncio
import copy
import logging
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from ..context.document_reader import (
    DEFAULT_CHUNK_CHARS as DEFAULT_DOCUMENT_CHUNK_CHARS,
    combine_document_texts,
    extract_documents_from_media,
    is_document_media,
    split_text_chunks,
)
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
from ..proactive.conversation_task_store import ConversationTaskStore
from ..proactive.closeout_analyzer import CloseoutAnalyzer
from ..proactive.deferred_detector import DeferredReplyDetector
from ..proactive.motives import ConversationTask, ConversationTaskStatus, ConversationTaskType
from ..proactive.orchestrator import ProactiveOrchestrator
from ..skill import SkillDispatcher, MultimodalSender, create_channel, BuiltinSkillManager
from ..skill.base import SkillContext
from ..skill.capability_resolver import build_capability_statuses, resolve_skill_config
from ..skill.auto_router import AutoSkillRouter
from ..skill.command import (
    contains_sensitive_token,
    execute_skill_command,
    is_skill_command,
    redact_sensitive_tokens,
)
from ..temporal_guard import (
    build_generation_time_constraints,
    build_local_time_context,
    is_event_visible_at_current_time,
)
from .response_style import ResponseStylePolisher

if TYPE_CHECKING:
    from ..model.adapters.base import ModelAdapter

logger = logging.getLogger(__name__)

DEFAULT_DOCUMENT_MEMORY_CHARS = 12_000
DEFAULT_DOCUMENT_TASK_CHARS = 30_000


class BotInstance:
    """单个 Bot 的运行实例"""

    def __init__(self, config: dict, model: "ModelAdapter" = None,
                 memory_config: dict = None, data_dir: Path = None,
                 refusal_enabled: bool = True):
        self.id = config["id"]
        self.name = config["name"]
        self.description = config.get("description", "")
        self.skill_config = config.get("skills", {}) if isinstance(config.get("skills", {}), dict) else {}
        self._capability_statuses: dict[str, dict] = build_capability_statuses(self.skill_config)

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
        self._last_debug_context: dict | None = None
        self._document_sessions: dict[str, dict] = {}

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
        self.conversation_task_store = ConversationTaskStore(self._data_dir / self.id)
        self.proactive_orchestrator = ProactiveOrchestrator(
            engine=self.proactive_engine,
            task_store=self.conversation_task_store,
        )
        self.proactive_engine.orchestrator = self.proactive_orchestrator
        self.proactive_scheduler: Optional[ProactiveScheduler] = None
        self._proactive_platform = None
        self._schedulers_started = False
        self._proactive_scheduler_lock: Optional[BotSchedulerRuntimeLock] = None
        self._proactive_scheduler_lock_owner: Optional[dict] = None
        self._dreaming_scheduler_lock: Optional[BotSchedulerRuntimeLock] = None
        self._dreaming_scheduler_lock_owner: Optional[dict] = None
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
        self.auto_skill_router = AutoSkillRouter(self.skill_dispatcher)

        self.multimodal_sender: Optional[MultimodalSender] = None
        self._channel = None
        self.response_polisher = ResponseStylePolisher()

    def _register_skills(self):
        """Register built-in companion capabilities."""
        builtin_manager = BuiltinSkillManager(self.skill_dispatcher)
        resolved_skill_config = resolve_skill_config({}, self.skill_config)
        self._capability_statuses = builtin_manager.register(resolved_skill_config, self._capability_statuses)

    def _detect_personality_type(self) -> str:
        """检测性格类型"""
        return self._detect_personality_type_from_profile(self.persona.profile)

    def _detect_personality_type_from_profile(self, profile: dict) -> str:
        tags = "".join(profile.get("personality_tags", []))
        if any(marker in tags for marker in ("傲娇", "外冷内热", "嘴硬", "毒舌", "带刺", "敢爱敢恨")):
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
            if self.memory and getattr(self.memory, "dreaming", None):
                self.memory.dreaming.configure((self.memory.config or {}).get("dreaming", {}))
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
            now = datetime.now().astimezone()
            self.life_state.current_date = now.strftime("%Y-%m-%d")
            self.life_state.year = now.year
            self.life_state.day_of_week = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
            self.life_state.is_weekend = now.weekday() >= 5

            # 初始化季节
            current_month = now.month
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
            self.proactive_engine._platform_sender = lambda msg, target=None: self._wrap_gateway_send(
                msg,
                gateway_adapter,
                str(ptype).lower(),
                target=target,
            )
            return

        if feishu_adapter:
            self._proactive_platform = feishu_adapter
            self.proactive_engine._platform_sender = lambda msg, target=None: self._wrap_gateway_send(
                msg,
                feishu_adapter,
                "feishu",
                target=target,
            )
            return

        ptype = platform_type or self.proactive_config.platform_type
        self._proactive_platform = create_platform(ptype, **kwargs)
        # 设置回调
        self.proactive_engine._platform_sender = lambda msg, target=None: self._proactive_platform.send(self.id, msg)

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

    async def _wrap_gateway_send(self, message: str, adapter, platform_type: str, target: dict | None = None) -> bool:
        """包装 gateway adapter 发送（适配 proactive 引擎的接口）"""
        try:
            chat_id = getattr(self, f"_{platform_type}_chat_id", None)
            send_metadata: dict[str, object] = {}
            memory_context: dict[str, object] = {
                "platform": platform_type,
                "user_id": getattr(getattr(self, "memory", None), "user_id", "default_user"),
                "channel_type": None,
                "chat_id": None,
                "metadata": {},
            }
            if isinstance(target, dict):
                explicit_chat_id = target.get("chat_id")
                if explicit_chat_id:
                    chat_id = explicit_chat_id
                explicit_thread_id = target.get("thread_id")
                if explicit_thread_id:
                    send_metadata["thread_id"] = explicit_thread_id
                target_metadata = target.get("metadata")
                if isinstance(target_metadata, dict):
                    send_metadata.update(target_metadata)
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
            chat_id = str(chat_id)
            memory_context["chat_id"] = chat_id
            memory_context["channel_type"] = "group" if chat_id.endswith("@chatroom") else "dm"
            if send_metadata:
                memory_context["metadata"] = dict(send_metadata)
            session_id = getattr(getattr(self, "memory", None), "_session_id", None)
            if platform_type == "weixin":
                session_id = "gw_" + uuid.uuid5(uuid.NAMESPACE_URL, f"agent:main:{platform_type}:{memory_context['channel_type']}:{chat_id}").hex[:24]
            if session_id:
                memory_context["session_id"] = session_id
            send_kwargs = {"chat_id": chat_id, "content": message}
            if send_metadata:
                send_kwargs["metadata"] = send_metadata
            try:
                result = await adapter.send(**send_kwargs)
            except TypeError as exc:
                if "metadata" not in send_kwargs or "unexpected keyword" not in str(exc):
                    raise
                send_kwargs.pop("metadata", None)
                result = await adapter.send(**send_kwargs)
            success = result.success if hasattr(result, 'success') else result
            if not success:
                error = getattr(result, "error", "unknown") if result is not None else "unknown"
                logger.warning("[BotInstance] %s 主动消息发送失败: %s", platform_type, error)
            elif self.proactive_engine:
                self.proactive_engine.set_next_record_context(memory_context)
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
            await self.memory.index_life_state(self.life_state)
            self.memory.start_session()
        self._initialized = True
        if start_schedulers:
            await self._ensure_schedulers_started()
        else:
            logger.info(f"[BotInstance] {self.name} 已初始化（延迟启动调度器）")

    async def _ensure_schedulers_started(self):
        """按需启动后台调度器（只启动一次）。"""
        dreaming_running = bool(
            self.memory
            and getattr(getattr(self.memory, "dreaming", None), "scheduler", None)
            and self.memory.dreaming.scheduler.get_status().get("running")
        )
        if self.proactive_scheduler and self.life_scheduler and dreaming_running:
            return

        await self._ensure_proactive_scheduler_started()
        await self._ensure_dreaming_scheduler_started()
        await self._ensure_life_scheduler_started()
        self._schedulers_started = bool(self.proactive_scheduler or self.life_scheduler or dreaming_running)

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

    async def _ensure_dreaming_scheduler_started(self):
        if not self.memory or not getattr(self.memory, "dreaming", None):
            return

        scheduler = getattr(self.memory.dreaming, "scheduler", None)
        if scheduler and scheduler.get_status().get("running"):
            return

        dreaming_cfg = getattr(self.memory.dreaming, "config", {}) or {}
        if not dreaming_cfg.get("enabled") or not dreaming_cfg.get("auto_run_enabled"):
            return

        if not self._acquire_scheduler_runtime_lock("dreaming"):
            self._log_scheduler_lock_skip("记忆整理", self._dreaming_scheduler_lock_owner)
            return

        try:
            await self.memory.dreaming.start_scheduler()
            logger.info(
                "[BotInstance] %s 的记忆整理自动调度器已启动: interval=%ss min_run_interval=%sm min_new_messages=%s",
                self.name,
                dreaming_cfg.get("auto_check_interval_seconds"),
                dreaming_cfg.get("min_run_interval_minutes"),
                dreaming_cfg.get("min_new_messages"),
            )
        except Exception:
            self._release_scheduler_runtime_lock("dreaming")
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
        self._release_scheduler_runtime_lock("dreaming")
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

    def _build_system_prompt(
        self,
        adjustment_note: str = "",
        memory_suffix: str | None = None,
        *,
        user_input: str = "",
        memory_context: dict | None = None,
        relationship_state: dict | None = None,
    ) -> str:
        life_context = self._get_generation_life_context()
        system_prompt = self.persona_engine.build_system_prompt(life_context=life_context)
        time_constraints = build_generation_time_constraints(life_context)
        if time_constraints:
            system_prompt = system_prompt + "\n\n" + time_constraints
        embodied_prompt = self._build_embodied_expression_prompt(
            user_input=user_input,
            memory_context=memory_context or {},
            relationship_state=relationship_state or {},
        )
        if embodied_prompt:
            system_prompt = system_prompt + "\n\n" + embodied_prompt
        if memory_suffix:
            system_prompt = system_prompt + "\n\n" + memory_suffix
        if adjustment_note:
            system_prompt = system_prompt + adjustment_note
        return system_prompt

    def _get_generation_life_context(self) -> dict:
        if self.life_engine:
            try:
                return self._filter_generation_life_context(self.life_engine.get_status())
            except Exception as exc:
                logger.debug("[BotInstance] 获取当前时间上下文失败，使用本地时钟兜底: %s", exc)
        return build_local_time_context()

    def _filter_generation_life_context(self, life_context: dict | None) -> dict:
        context = dict(life_context or {})
        for key in ("recent_life_events", "recent_major_life_events"):
            events = context.get(key)
            if isinstance(events, list):
                context[key] = [
                    event for event in events
                    if is_event_visible_at_current_time(event, context)
                ]
        return context

    def get_last_debug_context(self) -> dict | None:
        """Return the latest generation-time debug snapshot."""
        if self._last_debug_context is None:
            return None
        return copy.deepcopy(self._last_debug_context)

    def _build_debug_context_snapshot(
        self,
        *,
        system_prompt: str,
        system_suffix: str,
        memory_suffix: str | None,
        memory_context: dict | None,
        relationship_state: dict | None,
        image_context_suffix: str | None,
        adjustment_note: str,
        document_context_suffix: str | None = None,
    ) -> dict:
        ctx = memory_context if isinstance(memory_context, dict) else {}
        working_history = copy.deepcopy(ctx.get("working_history", [])) if isinstance(ctx.get("working_history"), list) else []
        episodic_recall = copy.deepcopy(ctx.get("episodic_recall", [])) if isinstance(ctx.get("episodic_recall"), list) else []
        vector_recall = copy.deepcopy(ctx.get("vector_recall", [])) if isinstance(ctx.get("vector_recall"), list) else []
        semantic_facts = copy.deepcopy(ctx.get("semantic_facts", {})) if isinstance(ctx.get("semantic_facts"), dict) else {}
        retrieved_relationship = copy.deepcopy(ctx.get("relationship_state", {})) if isinstance(ctx.get("relationship_state"), dict) else {}
        daily_context = copy.deepcopy(ctx.get("daily_context", {})) if isinstance(ctx.get("daily_context"), dict) else {}
        user_understanding = copy.deepcopy(ctx.get("user_understanding", {})) if isinstance(ctx.get("user_understanding"), dict) else {}
        conscious_context = copy.deepcopy(ctx.get("conscious_context", {})) if isinstance(ctx.get("conscious_context"), dict) else {}
        prompt_diagnostics = copy.deepcopy(ctx.get("memory_prompt_diagnostics", {})) if isinstance(ctx.get("memory_prompt_diagnostics"), dict) else {}

        retrieved_memory = {
            "working_history": working_history,
            "episodic_recall": episodic_recall,
            "vector_recall": vector_recall,
            "semantic_facts": semantic_facts,
            "relationship_state": retrieved_relationship,
            "daily_context": daily_context,
            "memory_intent": ctx.get("memory_intent", ""),
            "user_understanding": user_understanding,
            "conscious_context": conscious_context,
            "memory_prompt_diagnostics": prompt_diagnostics,
            "system_suffix": ctx.get("system_suffix", ""),
        }
        response_style_trace = {
            "mode": "rule",
            "source": "ResponseStylePolisher",
            "memory_intent": ctx.get("memory_intent", ""),
        }
        if image_context_suffix:
            response_style_trace["image_context_suffix"] = image_context_suffix
        if document_context_suffix:
            response_style_trace["document_context_suffix"] = document_context_suffix
        if adjustment_note:
            response_style_trace["adjustment_note"] = adjustment_note
        return {
            "system_prompt": system_prompt,
            "system_suffix": system_suffix,
            "memory_suffix": memory_suffix or "",
            "working_history": working_history,
            "retrieved_memory": retrieved_memory,
            "response_style_trace": response_style_trace,
            "memory_prompt_diagnostics": prompt_diagnostics,
            "conscious_context": conscious_context,
            "memory_intent": ctx.get("memory_intent", ""),
            "relationship_state": relationship_state or retrieved_relationship,
            "daily_context": daily_context,
            "user_understanding": user_understanding,
        }

    def _build_embodied_expression_prompt(
        self,
        *,
        user_input: str,
        memory_context: dict | None,
        relationship_state: dict | None,
    ) -> str:
        if not self.persona:
            return ""
        recent_assistant_replies = [
            str(item.get("content", "") or "")
            for item in self.conversation_history[-12:]
            if isinstance(item, dict) and item.get("role") == "assistant"
        ]
        recent_actions = self.response_polisher.list_recent_actions(recent_assistant_replies, limit=6)
        memory_intent = str((memory_context or {}).get("memory_intent", "casual_chat") or "casual_chat")
        return self.persona_engine.build_embodied_expression_turn_prompt(
            user_input=user_input,
            intent=memory_intent,
            recent_actions=recent_actions,
            relationship_state=relationship_state or {},
        )

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

        # 0.1 用户回来了，自动取消该 session 的待执行任务
        _session_id = str(
            (memory_turn_context or {}).get("session_id")
            or getattr(getattr(self.memory, "working", None), "current_session", "")
            or ""
        )
        if _session_id and self.conversation_task_store:
            cancelled = self.conversation_task_store.cancel_pending_for_session(
                self.id, _session_id, datetime.now()
            )
            if cancelled:
                logger.info("[BotInstance] 用户回来，自动取消 %d 个待执行任务 session=%s", cancelled, _session_id)

        document_context_suffix, document_user_hint, document_memory_text = self._prepare_document_context(
            user_input,
            memory_turn_context,
        )
        if document_user_hint and not document_context_suffix and not str(user_input or "").strip():
            if self.memory:
                recorded_context = await self.memory.record_turn(
                    "[用户发送了一份文档，等待处理指令]",
                    document_user_hint,
                    turn_context=memory_turn_context,
                )
                self._track_background_task(
                    self.memory.extract_turn_memory("[用户发送了一份文档，等待处理指令]", document_user_hint, turn_context=recorded_context),
                    name="memory.extract_turn_memory.document_received",
                )
            self.conversation_history.append({"role": "user", "content": "[用户发送了一份文档]"})
            self.conversation_history.append({"role": "assistant", "content": document_user_hint})
            return document_user_hint

        runtime_input = self._build_runtime_input(user_input, memory_turn_context)
        effective_user_input = user_input
        if not effective_user_input.strip() and runtime_input.get("media_urls"):
            if self._has_document_media(runtime_input):
                effective_user_input = "[用户发送了一份文档]"
            elif self._has_image_media(runtime_input):
                effective_user_input = "[用户发送了一张图片]"
            else:
                effective_user_input = "[用户发送了一个媒体附件]"
            runtime_input["text"] = effective_user_input

        self._bind_memory_turn_context(memory_turn_context)

        # 1. 拒绝检查（如果启用）
        relationship_state = None
        if self.memory:
            relationship_state = await self.memory.relationship.get_state(
                bot_id=self.id,
                user_id=getattr(self.memory, "user_id", "default_user"),
            )

        refusal_response = await self.refusal_engine.check(
            user_request=effective_user_input,
            memory_context=None,
            relationship_state=relationship_state,
            generation_time_context=self._get_generation_life_context(),
        )

        if refusal_response.refuse:
            # 硬拒绝直接返回，但仍然记录为一轮真实对话，避免 Bot 丢失自己说过的边界。
            logger.info(f"[Refusal] 拒绝请求: {refusal_response.reason} | {refusal_response.category.value}")
            response = refusal_response.reply or "这件事我不能答应你。我们换个别的办法吧。"
            await self._record_refusal_turn(
                effective_user_input,
                response,
                refusal_response,
                memory_turn_context,
            )
            return response

        # 2. 软边界调整（不拒绝但返回调整后的回复）
        if refusal_response.category == RefusalCategory.SOFT_BOUNDARY and refusal_response.reply:
            logger.info(f"[Refusal] 软边界调整: {refusal_response.reason}")
            adjustment_note = (
                "\n\n[角色边界提示: 本轮触及软边界，但不要机械拒绝或停止对话。"
                f"{refusal_response.adjustment}]"
            )
        else:
            adjustment_note = ""

        if is_skill_command(user_input):
            response = await self._handle_skill_command(user_input)
            self._record_skill_command_history(user_input, response)
            return response

        route_result = await self.auto_skill_router.try_handle(
            runtime_input=runtime_input,
            context=self._build_skill_context(),
            capability_statuses=self._capability_statuses,
        )
        if route_result.handled:
            response = route_result.direct_response or "能力调用已完成。"
            self.conversation_history.append({"role": "user", "content": effective_user_input})
            self.conversation_history.append({"role": "assistant", "content": response})
            return response

        image_context_suffix = route_result.bot_visible_context
        image_user_hint = route_result.user_facing_hint
        if image_context_suffix and self.memory and isinstance(self.memory, MemoryEngine):
            logger.info("[BotInstance] 图片理解已注入上下文")

        # 3. 情绪触发检测
        emotion_triggered = self._check_emotion_trigger(effective_user_input)
        if emotion_triggered:
            logger.info(f"[Proactive] 情绪触发: {user_input[:30]}...")

        # 如果有记忆引擎，使用记忆上下文
        if self.memory:
            # 1. 检查并触发压缩
            await self.memory.maybe_compress()

            # 2. 加载上下文
            ctx = await self.memory.load_context(effective_user_input)

            # 3. 构建带人格的记忆增强 system prompt
            realtime_status_query = self._is_realtime_status_query(effective_user_input)
            memory_suffix = None if realtime_status_query else self._prepare_generation_suffix(ctx.get("system_suffix"))
            if image_context_suffix:
                memory_suffix = self._merge_memory_suffix(memory_suffix, image_context_suffix)
            if document_context_suffix:
                memory_suffix = self._merge_memory_suffix(memory_suffix, document_context_suffix)

            system_prompt = self._build_system_prompt(
                adjustment_note=adjustment_note,
                memory_suffix=memory_suffix,
                user_input=effective_user_input,
                memory_context=ctx,
                relationship_state=relationship_state,
            )
            self._last_debug_context = self._build_debug_context_snapshot(
                system_prompt=system_prompt,
                system_suffix=str(ctx.get("system_suffix") or ""),
                memory_suffix=memory_suffix,
                memory_context=ctx,
                relationship_state=relationship_state,
                image_context_suffix=image_context_suffix,
                document_context_suffix=document_context_suffix,
                adjustment_note=adjustment_note,
            )

            # 4. 构建 messages
            history = [] if realtime_status_query else ctx.get("working_history", [])
            messages = self._prepare_generation_messages(history)
            messages.append({"role": "user", "content": effective_user_input})

            # 5. 对话
            response = await self._chat_with_fallback(messages, system_prompt)
            if response is None:
                return self._format_model_failure_message()
            response = self._polish_response(response, ctx, relationship_state)
            self._record_deferred_reply_task_if_detected(effective_user_input, response, memory_turn_context)
            self._track_background_task(
                self._run_proactive_closeout_analysis(effective_user_input, response, memory_turn_context),
                name="closeout_analysis",
            )

            # 6. 先同步写入原始轮次，长记忆抽取放后台，避免用户连发时上一轮还不可见。
            memory_user_input = self._document_memory_user_input(effective_user_input, document_memory_text)
            recorded_context = await self.memory.record_turn(
                memory_user_input,
                response,
                turn_context=memory_turn_context,
            )
            self._track_background_task(
                self.memory.extract_turn_memory(memory_user_input, response, turn_context=recorded_context),
                name="memory.extract_turn_memory",
            )
        else:
            memory_suffix = image_context_suffix if image_context_suffix else None
            if document_context_suffix:
                memory_suffix = self._merge_memory_suffix(memory_suffix, document_context_suffix)
            system_prompt = self._build_system_prompt(
                adjustment_note=adjustment_note,
                memory_suffix=memory_suffix,
                user_input=effective_user_input,
                memory_context={},
                relationship_state=relationship_state,
            )
            self._last_debug_context = self._build_debug_context_snapshot(
                system_prompt=system_prompt,
                system_suffix="",
                memory_suffix=memory_suffix,
                memory_context={},
                relationship_state=relationship_state,
                image_context_suffix=image_context_suffix,
                document_context_suffix=document_context_suffix,
                adjustment_note=adjustment_note,
            )
            messages = [{"role": "user", "content": effective_user_input}]
            response = await self._chat_with_fallback(messages, system_prompt)
            if response is None:
                return self._format_model_failure_message()
            response = self._polish_response(response, {}, relationship_state)
            self._record_deferred_reply_task_if_detected(effective_user_input, response, memory_turn_context)
            self._track_background_task(
                self._run_proactive_closeout_analysis(effective_user_input, response, memory_turn_context),
                name="closeout_analysis",
            )

        if image_user_hint and image_user_hint not in response:
            response = f"{image_user_hint}\n{response}"
        if document_user_hint and document_user_hint not in response:
            response = f"{document_user_hint}\n{response}"

        # 记录历史
        self.conversation_history.append({"role": "user", "content": effective_user_input})
        self.conversation_history.append({"role": "assistant", "content": response})

        return response

    def _prepare_generation_messages(self, messages: list[dict]) -> list[dict]:
        cleaned: list[dict] = []
        source_messages = messages if isinstance(messages, list) else []
        last_message_index = self._last_generation_context_message_index(source_messages)
        life_context = self._get_generation_life_context()
        time_notice = self._build_generation_time_notice(source_messages, life_context)
        if time_notice:
            cleaned.append({"role": "system", "content": time_notice})
        for idx, item in enumerate(source_messages):
            if not isinstance(item, dict):
                continue
            copied = dict(item)
            role = copied.get("role")
            if role in {"assistant", "system"}:
                copied["content"] = self.response_polisher.clean_generation_context(str(copied.get("content", "") or ""))
            cleaned.append({"role": role, "content": copied.get("content", "")})
            if idx == last_message_index and role == "assistant" and self._is_assistant_initiated_memory(copied):
                content = str(copied.get("content", "") or "").strip()
                if content:
                    cleaned.append({
                        "role": "system",
                        "content": (
                            "[连续性提示] 上一条是你主动发给用户的消息，"
                            f"不是用户说给你的：{content}\n"
                            "如果用户追问或质疑这条消息里的称呼/内容，"
                            "要承认这是你刚才主动说的话，再解释、修正或继续互动；"
                            "不要把这条主动消息改归因成用户说过的话。"
                        ),
                    })
        return cleaned

    def _build_generation_time_notice(self, messages: list[dict], life_context: dict | None) -> str:
        context = life_context if isinstance(life_context, dict) else {}
        current_text = str(
            context.get("current_datetime_text")
            or context.get("current_date")
            or ""
        ).strip()
        if not current_text:
            return ""

        parts = [
            "[时间流动提示]",
            f"- 当前回复时刻：{current_text}",
        ]
        last_user_time = self._last_history_timestamp(messages, role="user")
        if last_user_time is not None:
            parts.append(
                f"- 这次回复距离上一条用户消息已经过去：{self._format_elapsed_delta_from_anchor(last_user_time, current_text)}"
            )
        parts.append("- 历史消息里的场景、活动和状态只代表当时，不要默认它们在当前时刻仍然持续。")
        parts.append("- 如果发现已经从中午到下午、从今天到明天，或中间隔了较长时间，请按当前时间重新判断场景，不要沿用旧时刻的临时状态。")
        parts.append("- 回复中提到吃饭、下班后、晚饭后、睡前等生活细节时，必须与当前回复时刻一致；没有明确依据时不要主动编造具体时段活动。")
        history_timeline = self._build_history_timeline(messages, life_context)
        if history_timeline:
            parts.append("- 历史时间线：")
            parts.extend(history_timeline)
        parts.append("- 回复时不要自己带 [HH:MM] 或 [日期 时间] 这类时间前缀，除非用户明确要求。")
        return "\n".join(parts)

    def _last_history_timestamp(self, messages: list[dict], role: str) -> datetime | None:
        source_messages = messages if isinstance(messages, list) else []
        for item in reversed(source_messages):
            if not isinstance(item, dict):
                continue
            if item.get("role") != role:
                continue
            created_at = self._parse_message_created_at(item.get("created_at"))
            if created_at is not None:
                return created_at
        return None

    def _parse_message_created_at(self, value: object) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            return parsed.astimezone()
        return parsed

    def _format_history_timestamp(self, created_at: datetime, life_context: dict | None) -> str:
        context = life_context if isinstance(life_context, dict) else {}
        if created_at.tzinfo is not None:
            created_at = created_at.astimezone()
        current_date = str(context.get("current_date") or "").strip()
        if current_date and created_at.strftime("%Y-%m-%d") == current_date:
            return created_at.strftime("%H:%M")
        return created_at.strftime("%Y-%m-%d %H:%M")

    def _build_history_timeline(self, messages: list[dict], life_context: dict | None) -> list[str]:
        lines: list[str] = []
        source_messages = messages if isinstance(messages, list) else []
        for item in source_messages[-6:]:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            if role not in {"user", "assistant"}:
                continue
            created_at = self._parse_message_created_at(item.get("created_at"))
            if created_at is None:
                continue
            text = str(item.get("content", "") or "").strip()
            if not text:
                continue
            if role == "assistant":
                text = self.response_polisher.clean_generation_context(text).strip()
                if not text:
                    continue
            label = "用户" if role == "user" else "Bot"
            snippet = text if len(text) <= 48 else text[:48].rstrip() + "..."
            lines.append(f"  - [{self._format_history_timestamp(created_at, life_context)}] {label}: {snippet}")
        return lines

    def _format_elapsed_delta_from_anchor(self, earlier: datetime, anchor_text: str) -> str:
        anchor = self._parse_anchor_datetime(anchor_text)
        if anchor is None:
            anchor = datetime.now()
        if earlier.tzinfo is not None:
            earlier = earlier.astimezone().replace(tzinfo=None)
        delta = anchor - earlier
        if delta.total_seconds() <= 0:
            return "不足1分钟"

        total_minutes = int(delta.total_seconds() // 60)
        days, rem_minutes = divmod(total_minutes, 24 * 60)
        hours, minutes = divmod(rem_minutes, 60)
        parts: list[str] = []
        if days:
            parts.append(f"{days}天")
        if hours:
            parts.append(f"{hours}小时")
        if minutes and not days:
            parts.append(f"{minutes}分钟")
        return "".join(parts) if parts else "不足1分钟"

    def _parse_anchor_datetime(self, value: str) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        normalized = re.sub(r"[（(].*?[）)]", "", text).strip()
        try:
            return datetime.strptime(normalized, "%Y-%m-%d %H:%M")
        except ValueError:
            return None

    def _is_assistant_initiated_memory(self, item: dict) -> bool:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        return bool(metadata.get("assistant_initiated") or metadata.get("proactive"))

    def _last_generation_context_message_index(self, messages: list[dict]) -> int | None:
        for idx in range(len(messages) - 1, -1, -1):
            item = messages[idx]
            if not isinstance(item, dict):
                continue
            if item.get("role") in {"user", "assistant"}:
                return idx
        return None

    def _prepare_document_context(
        self,
        user_input: str,
        memory_turn_context: dict | None,
    ) -> tuple[str, str, str]:
        context = memory_turn_context if isinstance(memory_turn_context, dict) else {}
        session_key = self._document_session_key(context)
        media_urls = context.get("media_urls") if isinstance(context.get("media_urls"), list) else []
        media_types = context.get("media_types") if isinstance(context.get("media_types"), list) else []
        instruction = str(user_input or "").strip()

        if self._has_document_media({"media_urls": media_urls, "media_types": media_types}):
            results = extract_documents_from_media(media_urls, media_types)
            combined, errors, truncated = combine_document_texts(results)
            if not combined:
                self._document_sessions.pop(session_key, None)
                if errors:
                    return "", f"我收到了文档，但这次没能读出正文（{'; '.join(errors[:2])}）。", ""
                return "", "我收到了文档，但这类文件现在还读不出正文。", ""

            chunks = split_text_chunks(combined, max_chars=DEFAULT_DOCUMENT_CHUNK_CHARS)
            if not chunks:
                self._document_sessions.pop(session_key, None)
                return "", "我收到了文档，但里面没有可读取的文字内容。", ""

            session = {
                "chunks": chunks,
                "full_text": combined,
                "names": [item.name for item in results if item.text],
                "errors": errors,
                "truncated": truncated,
            }
            self._document_sessions[session_key] = session
            if not instruction:
                return "", self._document_received_prompt(session), ""
            return self._document_context_for_instruction(session, instruction)

        pending = self._document_sessions.get(session_key)
        if pending and instruction:
            return self._document_context_for_instruction(pending, instruction)

        return "", "", ""

    def _document_received_prompt(self, session: dict) -> str:
        chunks = session.get("chunks") if isinstance(session.get("chunks"), list) else []
        names = session.get("names") if isinstance(session.get("names"), list) else []
        name_text = "、".join(str(item) for item in names[:3] if str(item).strip()) or "这份文档"
        note = f"我收到 {name_text} 了。"
        if chunks:
            note += f"内容比较长，我会等你说要怎么处理，再按你的要求去读。"
        else:
            note += "你想让我怎么处理？"
        return note + "你可以直接说：总结、出分析报告、帮你改稿、补充数据，或者指定从哪一章/哪一段开始看。"

    def _document_context_for_instruction(self, session: dict, instruction: str) -> tuple[str, str, str]:
        text = str(session.get("full_text") or "").strip()
        chunks = session.get("chunks") if isinstance(session.get("chunks"), list) else []
        names = session.get("names") if isinstance(session.get("names"), list) else []
        name_text = "、".join(str(item) for item in names[:3] if str(item).strip()) or "用户发送的文档"
        selected_text, selection_note, selection_found = self._select_document_text_for_instruction(text, instruction)
        excerpt = selected_text[:DEFAULT_DOCUMENT_TASK_CHARS].strip()
        truncated = len(selected_text) > len(excerpt) or bool(session.get("truncated"))
        lines = [
            "[用户已发送文档，以下内容供本轮任务使用]",
            f"文档: {name_text}",
            f"解析片段数: {len(chunks)}",
            f"用户本轮指令: {instruction}",
            f"文档定位: {selection_note}",
            "行为要求: 根据用户本轮指令决定阅读策略；不要默认从头朗读；只能引用下方摘录里实际出现的内容，不得编造文档情节。",
        ]
        if not selection_found:
            lines.append("重要: 未在文档中找到用户指定的章节/位置，必须先说明没找到，不要假装已经翻到该位置。")
        if truncated:
            lines.append("提示: 文档很长，本轮只注入前部摘录；需要更完整处理时应分批继续。")
        errors = session.get("errors") if isinstance(session.get("errors"), list) else []
        if errors:
            lines.append(f"未能读取的附件: {'; '.join(str(item) for item in errors[:2])}")
        lines.extend(["", excerpt])
        memory_text = self._document_memory_text(name_text, excerpt, index=0, total=max(1, len(chunks)), truncated=truncated)
        return "\n".join(lines).strip(), "", memory_text

    def _select_document_text_for_instruction(self, text: str, instruction: str) -> tuple[str, str, bool]:
        chapter = self._extract_requested_chapter_number(instruction)
        if chapter is None:
            return text, "未指定章节，使用文档开头作为任务摘录。", True

        start = self._find_chapter_start(text, chapter)
        chapter_label = self._chapter_label(chapter)
        if start is None:
            return text, f"未找到 {chapter_label}，暂时只能提供文档开头摘录。", False

        next_start = self._find_next_chapter_start(text, chapter, start)
        end = next_start if next_start is not None else len(text)
        selected = text[start:end].strip()
        if not selected:
            return text, f"找到 {chapter_label} 标题，但正文为空；暂时提供文档开头摘录。", False
        return selected, f"已定位到 {chapter_label}，本轮摘录从该章节标题开始。", True

    def _extract_requested_chapter_number(self, instruction: str) -> int | None:
        text = str(instruction or "")
        match = re.search(r"(?:第\s*)?(\d{1,3}|[一二三四五六七八九十百零〇两]{1,8})\s*章", text)
        if not match:
            return None
        raw = match.group(1)
        if raw.isdigit():
            return int(raw)
        return self._chinese_numeral_to_int(raw)

    def _find_chapter_start(self, text: str, chapter: int) -> int | None:
        for label in (str(chapter), self._int_to_chinese_numeral(chapter)):
            match = re.search(rf"(?m)^\s*第\s*{re.escape(label)}\s*章(?:\s|$)", text)
            if match:
                return match.start()
        return None

    def _find_next_chapter_start(self, text: str, chapter: int, start: int) -> int | None:
        tail = text[start + 1 :]
        for next_chapter in range(chapter + 1, chapter + 8):
            found = self._find_chapter_start(tail, next_chapter)
            if found is not None:
                return start + 1 + found
        match = re.search(r"(?m)^\s*第\s*(?:\d{1,3}|[一二三四五六七八九十百零〇两]{1,8})\s*章(?:\s|$)", tail)
        if match:
            return start + 1 + match.start()
        return None

    def _chapter_label(self, chapter: int) -> str:
        return f"第{chapter}章"

    def _chinese_numeral_to_int(self, value: str) -> int | None:
        digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
        text = str(value or "").strip()
        if not text:
            return None
        if "百" in text:
            left, _, right = text.partition("百")
            base = digits.get(left, 1 if not left else 0) * 100
            tail = self._chinese_numeral_to_int(right) if right else 0
            return base + int(tail or 0)
        if "十" in text:
            left, _, right = text.partition("十")
            tens = digits.get(left, 1 if not left else 0) * 10
            ones = digits.get(right, 0) if right else 0
            return tens + ones
        total = 0
        for ch in text:
            if ch not in digits:
                return None
            total = total * 10 + digits[ch]
        return total

    def _int_to_chinese_numeral(self, value: int) -> str:
        digits = "零一二三四五六七八九"
        if value <= 0:
            return str(value)
        if value < 10:
            return digits[value]
        if value < 20:
            return "十" + (digits[value % 10] if value % 10 else "")
        if value < 100:
            return digits[value // 10] + "十" + (digits[value % 10] if value % 10 else "")
        return str(value)

    def _document_context_for_session(self, session: dict, *, first: bool) -> tuple[str, str, str]:
        chunks = session.get("chunks") if isinstance(session.get("chunks"), list) else []
        if not chunks:
            return "", "", ""
        index = max(0, min(int(session.get("index", 0) or 0), len(chunks) - 1))
        total = len(chunks)
        names = session.get("names") if isinstance(session.get("names"), list) else []
        name_text = "、".join(str(item) for item in names[:3] if str(item).strip()) or "用户发送的文档"
        current = str(chunks[index] or "").strip()
        has_more = index < total - 1
        note_lines = [
            "[文档解析上下文]",
            f"文档: {name_text}",
            f"当前片段: {index + 1}/{total}",
        ]
        if session.get("truncated"):
            note_lines.append("提示: 文档较大，已按最大读取长度截取可解析正文。")
        errors = session.get("errors") if isinstance(session.get("errors"), list) else []
        if errors:
            note_lines.append(f"未能读取的附件: {'; '.join(str(item) for item in errors[:2])}")
        if has_more:
            note_lines.append("行为要求: 只基于当前片段回答或小结；结尾自然地询问用户要不要继续看下一部分。")
        else:
            note_lines.append("行为要求: 这是最后一部分；可以整合目前已看到的信息回答用户。")
        note_lines.append("")
        note_lines.append(current)
        context_suffix = "\n".join(note_lines).strip()

        if total == 1:
            user_hint = ""
        elif first:
            user_hint = f"我先读第 1/{total} 部分。"
        elif has_more:
            user_hint = f"我继续读第 {index + 1}/{total} 部分。"
        else:
            user_hint = f"这是第 {index + 1}/{total} 部分，也是最后一部分。"
        memory_text = self._document_memory_text(name_text, current, index=index, total=total, truncated=bool(session.get("truncated")))
        return context_suffix, user_hint, memory_text

    def _document_memory_text(
        self,
        name: str,
        text: str,
        *,
        index: int,
        total: int,
        truncated: bool,
    ) -> str:
        content = str(text or "").strip()
        if not content:
            return ""
        excerpt = content[:DEFAULT_DOCUMENT_MEMORY_CHARS].strip()
        if len(content) > len(excerpt):
            excerpt += "\n...[文档片段已截断]"
        if truncated:
            excerpt += "\n...[原始文档较大，解析阶段已截取可读正文]"
        return "\n".join(
            [
                f"[用户发送了一份文档: {name}]",
                f"[文档片段 {index + 1}/{total}]",
                excerpt,
            ]
        ).strip()

    def _document_memory_user_input(self, user_input: str, document_memory_text: str) -> str:
        user_text = str(user_input or "").strip()
        document_text = str(document_memory_text or "").strip()
        if not document_text:
            return user_text
        if user_text in {"", "[用户发送了一份文档]"}:
            return document_text
        return f"{user_text}\n\n[关联文档摘录]\n{document_text}"

    def _document_session_key(self, context: dict) -> str:
        return str(
            context.get("session_id")
            or context.get("chat_id")
            or getattr(getattr(self.memory, "working", None), "current_session", "")
            or "default"
        )

    def _has_document_media(self, runtime_input: dict) -> bool:
        media_urls = runtime_input.get("media_urls") if isinstance(runtime_input.get("media_urls"), list) else []
        media_types = runtime_input.get("media_types") if isinstance(runtime_input.get("media_types"), list) else []
        for idx, path in enumerate(media_urls):
            media_type = str(media_types[idx] if idx < len(media_types) else "" or "")
            if is_document_media(str(path), media_type):
                return True
        return False

    def _has_image_media(self, runtime_input: dict) -> bool:
        media_urls = runtime_input.get("media_urls") if isinstance(runtime_input.get("media_urls"), list) else []
        media_types = runtime_input.get("media_types") if isinstance(runtime_input.get("media_types"), list) else []
        if not media_urls:
            return False
        return any(str(item).startswith("image/") for item in media_types) if media_types else True

    def _is_document_continue_request(self, text: str) -> bool:
        compact = "".join(str(text or "").strip().lower().split())
        if not compact:
            return False
        if any(marker in compact for marker in {"不继续", "不用继续", "别继续", "先不", "stop", "停止"}):
            return False
        continue_markers = {
            "继续看",
            "下一部分",
            "下一段",
            "下一页",
            "接着看",
            "往下看",
            "看下去",
            "继续解析",
            "继续读",
        }
        if any(marker in compact for marker in continue_markers):
            return True
        return compact in {
            "继续",
            "goon",
            "continue",
            "next",
        }

    def _is_document_followup_request(self, text: str) -> bool:
        compact = "".join(str(text or "").strip().lower().split())
        if not compact:
            return False
        if self._is_document_continue_request(compact):
            return False
        followup_markers = {
            "这份文档",
            "这个文档",
            "这篇文档",
            "这份文件",
            "这个文件",
            "这篇文件",
            "读后感",
            "文档里",
            "文件里",
            "里面写",
            "里面说",
            "那几段",
            "那几个人",
            "名字",
            "感情关系",
        }
        return any(marker in compact for marker in followup_markers)

    def _prepare_generation_suffix(self, suffix: str | None) -> str | None:
        if not suffix:
            return suffix
        return self.response_polisher.clean_generation_context(str(suffix))

    def _is_realtime_status_query(self, text: str) -> bool:
        compact = "".join(str(text or "").lower().split())
        if not compact:
            return False

        english_tokens = (
            "whattime",
            "currenttime",
            "localtime",
            "whatdate",
            "today'sdate",
            "todaydate",
            "whatday",
        )
        if any(token in compact for token in english_tokens):
            return True

        current_markers = (
            "\u73b0\u5728",  # 现在
            "\u5f53\u524d",  # 当前
            "\u6b64\u523b",  # 此刻
            "\u8fd9\u4f1a\u513f",  # 这会儿
            "\u4eca\u5929",  # 今天
        )
        time_markers = (
            "\u51e0\u70b9",  # 几点
            "\u591a\u5c11\u70b9",  # 多少点
            "\u4ec0\u4e48\u65f6\u95f4",  # 什么时间
            "\u5f53\u524d\u65f6\u95f4",  # 当前时间
            "\u73b0\u5728\u65f6\u95f4",  # 现在时间
            "\u672c\u5730\u65f6\u95f4",  # 本地时间
        )
        date_markers = (
            "\u51e0\u53f7",  # 几号
            "\u65e5\u671f",  # 日期
            "\u661f\u671f\u51e0",  # 星期几
            "\u5468\u51e0",  # 周几
            "\u793c\u62dc\u51e0",  # 礼拜几
        )
        has_current_marker = any(marker in compact for marker in current_markers)
        if any(marker in compact for marker in date_markers) and has_current_marker:
            return True
        if any(marker in compact for marker in time_markers[2:]):
            return True
        if any(marker in compact for marker in time_markers[:2]) and has_current_marker:
            return True
        if compact in {"\u51e0\u70b9", "\u51e0\u70b9\u4e86", "\u51e0\u70b9\u5566", "\u51e0\u70b9\u5462"}:
            return True
        if "\u4f60\u90a3\u8fb9\u51e0\u70b9" in compact or "\u90a3\u8fb9\u51e0\u70b9" in compact:
            return True
        return False

    def _build_runtime_input(self, user_input: str, memory_turn_context: dict | None) -> dict:
        context = memory_turn_context if isinstance(memory_turn_context, dict) else {}
        media_urls = context.get("media_urls") if isinstance(context.get("media_urls"), list) else []
        media_types = context.get("media_types") if isinstance(context.get("media_types"), list) else []
        return {
            "text": user_input,
            "media_urls": [str(item) for item in media_urls if str(item).strip()],
            "media_types": [str(item) for item in media_types if str(item).strip()],
        }

    def _bind_memory_turn_context(self, memory_turn_context: dict | None) -> None:
        """Apply explicit per-turn memory routing before loading context."""
        if not self.memory or not isinstance(memory_turn_context, dict):
            return
        user_id = str(memory_turn_context.get("user_id") or "").strip()
        if user_id:
            self.memory.user_id = user_id
        session_id = str(memory_turn_context.get("session_id") or "").strip()
        if session_id:
            self.memory.start_session(session_id)

    def _build_skill_context(self) -> SkillContext:
        return SkillContext(
            bot_id=self.id,
            user_id=getattr(self.memory, "user_id", "default_user") if self.memory else "default_user",
            conversation_history=list(self.conversation_history),
            personality_tags=self.persona.profile.get("personality_tags", []) if self.persona else [],
        )

    def _merge_memory_suffix(self, original_suffix: str | None, extra_suffix: str) -> str:
        base = (original_suffix or "").strip()
        extra = (extra_suffix or "").strip()
        if not base:
            return extra
        if not extra:
            return base
        return f"{base}\n\n{extra}"

    async def _run_proactive_closeout_analysis(
        self,
        user_input: str,
        response: str,
        memory_turn_context: dict | None,
    ) -> None:
        if not self.proactive_config.continuity_enabled:
            return

        delivery = self._build_proactive_task_delivery(memory_turn_context)
        if delivery is None:
            logger.debug("[BotInstance] 无会话 ID，跳过主动 closeout 分析")
            return
        now = datetime.now()
        platform = delivery["platform"]
        session_id = delivery["session_id"]
        target = delivery["target"]
        user_id = delivery["user_id"]

        recent_turns = self.conversation_history[-6:] if self.conversation_history else []

        analyzer = CloseoutAnalyzer(self.model, self.proactive_config)
        result = await analyzer.analyze(user_input, response, recent_turns)

        if result.deferred_reply and self.proactive_config.deferred_reply_enabled:
            if not self.conversation_task_store.has_pending(self.id, session_id, ConversationTaskType.DEFERRED_REPLY.value):
                task = ConversationTask(
                    id=uuid.uuid4().hex,
                    bot_id=self.id,
                    type=ConversationTaskType.DEFERRED_REPLY,
                    status=ConversationTaskStatus.PENDING,
                    session_id=session_id,
                    user_id=user_id,
                    platform=platform,
                    target=target,
                    created_at=now,
                    due_at=now + timedelta(minutes=result.deferred_reply.delay_minutes),
                    expires_at=now + timedelta(hours=self.proactive_config.deferred_reply_expires_hours),
                    source_user_message=user_input,
                    source_bot_message=response,
                    topic_summary=result.deferred_reply.summary,
                    priority=100,
                )
                self.conversation_task_store.upsert(task)
                logger.info("[BotInstance] 已记录延迟回复任务: bot=%s session=%s", self.id, session_id)

        if result.unresolved_topic and self.proactive_config.topic_continuation_enabled:
            if not self.conversation_task_store.has_pending(self.id, session_id, ConversationTaskType.TOPIC_CONTINUATION.value):
                task = ConversationTask(
                    id=uuid.uuid4().hex,
                    bot_id=self.id,
                    type=ConversationTaskType.TOPIC_CONTINUATION,
                    status=ConversationTaskStatus.PENDING,
                    session_id=session_id,
                    user_id=user_id,
                    platform=platform,
                    target=target,
                    created_at=now,
                    due_at=now + timedelta(minutes=self.proactive_config.topic_continuation_idle_after_minutes),
                    expires_at=now + timedelta(hours=self.proactive_config.topic_continuation_expires_hours),
                    source_user_message=user_input,
                    source_bot_message=response,
                    topic_summary=result.unresolved_topic.summary,
                    priority=70,
                )
                self.conversation_task_store.upsert(task)
                logger.info("[BotInstance] 已记录话题续聊任务: bot=%s session=%s", self.id, session_id)

        if result.emotion_followup and self.proactive_config.emotion_followup_enabled:
            if not self.conversation_task_store.has_pending(self.id, session_id, ConversationTaskType.EMOTION_FOLLOWUP.value):
                task = ConversationTask(
                    id=uuid.uuid4().hex,
                    bot_id=self.id,
                    type=ConversationTaskType.EMOTION_FOLLOWUP,
                    status=ConversationTaskStatus.PENDING,
                    session_id=session_id,
                    user_id=user_id,
                    platform=platform,
                    target=target,
                    created_at=now,
                    due_at=now + timedelta(minutes=self.proactive_config.emotion_followup_delay_minutes),
                    expires_at=now + timedelta(hours=self.proactive_config.emotion_followup_expires_hours),
                    source_user_message=user_input,
                    source_bot_message=response,
                    topic_summary=f"情绪跟进：{result.emotion_followup.emotion} - {result.emotion_followup.summary}",
                    priority=85,
                )
                self.conversation_task_store.upsert(task)
                logger.info("[BotInstance] 已记录情绪跟进任务: bot=%s session=%s", self.id, session_id)

    def _build_proactive_task_delivery(self, memory_turn_context: dict | None) -> dict | None:
        context = memory_turn_context if isinstance(memory_turn_context, dict) else {}
        metadata = context.get("metadata") if isinstance(context.get("metadata"), dict) else {}
        session_id = str(
            context.get("session_id")
            or getattr(getattr(self.memory, "working", None), "current_session", "")
            or ""
        )
        if not session_id:
            return None
        platform = str(context.get("platform") or self.proactive_config.platform_type or "cli")
        return {
            "platform": platform,
            "session_id": session_id,
            "user_id": str(context.get("user_id") or "default_user"),
            "target": {
                "platform": platform,
                "chat_id": str(context.get("chat_id") or ""),
                "name": str(metadata.get("chat_name") or ""),
            },
        }

    def _record_deferred_reply_task_if_detected(
        self,
        user_input: str,
        response: str,
        memory_turn_context: dict | None,
    ) -> bool:
        if not (self.proactive_config.continuity_enabled and self.proactive_config.deferred_reply_enabled):
            return False
        delivery = self._build_proactive_task_delivery(memory_turn_context)
        if delivery is None:
            return False
        session_id = delivery["session_id"]
        if self.conversation_task_store.has_pending(self.id, session_id, ConversationTaskType.DEFERRED_REPLY.value):
            return False

        detector = DeferredReplyDetector(
            default_delay_minutes=self.proactive_config.deferred_reply_default_delay_minutes,
            min_delay_minutes=self.proactive_config.deferred_reply_min_delay_minutes,
            max_delay_minutes=self.proactive_config.deferred_reply_max_delay_minutes,
        )
        detected = detector.detect(user_input, response)
        if detected is None:
            return False

        now = datetime.now()
        task = ConversationTask(
            id=uuid.uuid4().hex,
            bot_id=self.id,
            type=ConversationTaskType.DEFERRED_REPLY,
            status=ConversationTaskStatus.PENDING,
            session_id=session_id,
            user_id=delivery["user_id"],
            platform=delivery["platform"],
            target=delivery["target"],
            created_at=now,
            due_at=now + timedelta(minutes=detected.delay_minutes),
            expires_at=now + timedelta(hours=self.proactive_config.deferred_reply_expires_hours),
            source_user_message=user_input,
            source_bot_message=response,
            topic_summary=detected.topic_summary,
            priority=100,
        )
        self.conversation_task_store.upsert(task)
        logger.info("[BotInstance] 已同步记录延迟回复任务: bot=%s session=%s", self.id, session_id)
        return True

    async def _handle_skill_command(self, user_input: str) -> str:
        context = self._build_skill_context()
        return await execute_skill_command(
            self.skill_dispatcher,
            user_input,
            context,
            capabilities=self.get_skill_capabilities(),
        )

    def _record_skill_command_history(self, user_input: str, response: str) -> None:
        history_input = redact_sensitive_tokens(user_input) if contains_sensitive_token(user_input) else user_input
        self.conversation_history.append({"role": "user", "content": history_input})
        self.conversation_history.append({"role": "assistant", "content": response})

    async def _record_refusal_turn(
        self,
        user_input: str,
        response: str,
        refusal_response,
        turn_context: dict | None,
    ) -> None:
        self.conversation_history.append({"role": "user", "content": user_input})
        self.conversation_history.append({"role": "assistant", "content": response})

        if not self.memory:
            return

        context = self._with_refusal_metadata(turn_context, refusal_response)
        recorded_context = await self.memory.record_turn(user_input, response, turn_context=context)
        self._track_background_task(
            self.memory.extract_turn_memory(user_input, response, turn_context=recorded_context),
            name="memory.extract_turn_memory.refusal",
        )

    def _with_refusal_metadata(self, turn_context: dict | None, refusal_response) -> dict:
        context = dict(turn_context or {})
        metadata = dict(context.get("metadata") or {})
        category = getattr(refusal_response, "category", None)
        metadata.update(
            {
                "refusal": True,
                "refusal_category": getattr(category, "value", str(category or "")),
                "refusal_reason": refusal_response.reason or "",
            }
        )
        context["metadata"] = metadata
        return context

    def _polish_response(self, response: str, memory_context: dict | None, relationship_state: dict | None) -> str:
        response = self.response_polisher.strip_reasoning_artifacts(response)
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
            response = await self.model.chat(messages, system_prompt)
            cleaned = self.response_polisher.strip_reasoning_artifacts(response)
            if cleaned and not self.response_polisher.looks_like_reasoning_artifact(cleaned):
                return cleaned

            logger.warning("[BotInstance] Suppressed likely reasoning artifact from model response; retrying once")
            retry_messages = list(messages) + [
                {
                    "role": "user",
                    "content": (
                        "请重新生成上一条回复。只输出会直接发给用户的自然回复，"
                        "不要输出分析、推理过程、角色分析、回复策略或标题。"
                    ),
                }
            ]
            response = await self.model.chat(retry_messages, system_prompt)
            cleaned = self.response_polisher.strip_reasoning_artifacts(response)
            if cleaned and not self.response_polisher.looks_like_reasoning_artifact(cleaned):
                return cleaned
            raise RuntimeError("model returned reasoning text instead of user-visible content")
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
            "conversation_tasks": {
                "pending": self.conversation_task_store.count_pending(self.id) if self.conversation_task_store else 0,
            },
            "scheduler_lock": {
                "proactive": {
                    "held": bool(self._proactive_scheduler_lock and self._proactive_scheduler_lock.acquired),
                    "owner": self._proactive_scheduler_lock_owner,
                },
                "dreaming": {
                    "held": bool(self._dreaming_scheduler_lock and self._dreaming_scheduler_lock.acquired),
                    "owner": self._dreaming_scheduler_lock_owner,
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
        for skill_name, status in self._capability_statuses.items():
            skill = self.skill_dispatcher.get(skill_name)
            if skill:
                status["registered"] = True
                status["available"] = bool(skill.is_available())
                if status["available"] and status.get("reason") in {"unavailable_runtime_check", "not_registered"}:
                    status["reason"] = ""
                elif not status["available"] and not status.get("reason"):
                    status["reason"] = "unavailable_runtime_check"
            else:
                status["registered"] = False
                status["available"] = False
                if status.get("enabled") and not status.get("reason"):
                    status["reason"] = "not_registered"

            capabilities["skills"][skill_name] = {
                **status,
                "description": getattr(skill, "description", "") if skill else "",
                "capabilities": getattr(skill, "capabilities", []) if skill else [],
                "is_available": bool(status.get("available", False)),
                "supported_models": getattr(skill, "supported_models", []) if skill else [],
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
        if self.memory and getattr(self.memory, "dreaming", None):
            await self.memory.dreaming.stop_scheduler()
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
