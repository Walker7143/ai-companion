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
from ..skill import SkillDispatcher, SkillRegistry, ImageGenerationSkill, TTSSkill, MultimodalSender, create_channel

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

        # 人格文件目录：优先用户目录，不存在则用项目目录
        if data_dir:
            persona_dir = data_dir / self.id / "persona"
        elif "data_dir" in config:
            persona_dir = Path(config["data_dir"]) / self.id / "persona"
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
                memory_dir=data_dir or (Path(__file__).parent.parent.parent / "data" / "bots"),
                config=memory_config,
                persona_backstory_path=persona_backstory_path,
            )

        # 对话历史（用于快速回复，暂时保留）
        self.conversation_history: list[dict] = []

        # ── 主动唤醒系统 ─────────────────────────────────────
        self.proactive_config = ProactiveConfig(persona_dir)
        self.proactive_state = ProactiveState(self.id, data_dir or Path(__file__).parent.parent.parent / "data" / "bots")
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

        # ── 人生轨迹系统 ─────────────────────────────────────
        self.life_config = LifeConfig(_persona_dir=persona_dir)
        self.life_config.load()
        self.life_state = LifeState(self.id, data_dir or Path(__file__).parent.parent.parent / "data" / "bots")
        self.life_engine = LifeEngine(
            bot_id=self.id,
            config=self.life_config,
            state=self.life_state,
            model=model,
            memory=self.memory,
            persona_dir=persona_dir,
        )
        self.life_scheduler: Optional[LifeScheduler] = None

        # 初始化日期和年龄（从 profile.json 读取）
        self._init_life_from_profile()

        # ── 技能系统 ─────────────────────────────────────
        self.skill_dispatcher = SkillDispatcher()
        self._register_skills()

        self.multimodal_sender: Optional[MultimodalSender] = None
        self._channel = None

    def _register_skills(self):
        """注册可用技能（内置 + 已安装的）"""
        # 图片生成技能
        self.skill_dispatcher.register(ImageGenerationSkill())
        # TTS 技能
        self.skill_dispatcher.register(TTSSkill())

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
        tags = "".join(self.persona.profile.get("personality_tags", []))
        if "傲娇" in tags or "外冷内热" in tags:
            return "傲娇"
        elif "活泼" in tags or "开朗" in tags:
            return "活泼"
        elif "高冷" in tags:
            return "高冷"
        elif "温柔" in tags:
            return "温柔"
        return "默认"

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

        logger.info(f"[BotInstance] 初始化人生轨迹: initial_age={initial_age}, birth_date={self.life_state.birth_date}")

    def set_model(self, model: "ModelAdapter"):
        self.model = model
        self.refusal_engine.set_model(model)
        self.proactive_engine.set_model(model)

    def set_proactive_platform(self, platform_type: str = None, feishu_adapter=None, **kwargs):
        """设置主动消息发送平台"""
        if feishu_adapter:
            # 直接使用传入的飞书适配器
            self._proactive_platform = feishu_adapter
            self.proactive_engine._platform_sender = lambda msg: self._wrap_feishu_send(msg, feishu_adapter)
            return

        ptype = platform_type or self.proactive_config.platform_type
        self._proactive_platform = create_platform(ptype, **kwargs)
        # 设置回调
        self.proactive_engine._platform_sender = lambda msg: self._proactive_platform.send(self.id, msg)

    async def _wrap_feishu_send(self, message: str, adapter) -> bool:
        """包装飞书发送（适配 proactive 引擎的接口）"""
        try:
            # 优先使用用户最近发消息的 chat_id（动态获取）
            chat_id = getattr(self, "_feishu_chat_id", None)
            if not chat_id:
                # 尝试从 proactive 配置获取
                chat_id = self.proactive_config.get("home_channel")
            if not chat_id:
                # 尝试从 platform 配置获取
                feishu_cfg = self.proactive_config.get("platform", {})
                chat_id = feishu_cfg.get("home_channel")
            if not chat_id:
                logger.warning(f"[BotInstance] 未配置 home_channel，无法发送主动消息")
                return False
            result = await adapter.send(chat_id=chat_id, content=message)
            return result.success if hasattr(result, 'success') else result
        except Exception as e:
            logger.error(f"[BotInstance] 飞书发送失败: {e}")
            return False

    def set_channel(self, channel_type: str = "cli", **kwargs):
        """设置消息通道（用于多模态发送）"""
        self._channel = create_channel(channel_type, **kwargs)
        self.multimodal_sender = MultimodalSender(
            bot_id=self.id,
            channel=self._channel,
            skill_dispatcher=self.skill_dispatcher
        )

    async def init(self):
        """初始化记忆引擎（启动时调用一次）"""
        if self.memory:
            await self.memory.init()
            if self.model:
                self.memory.set_summarizer(self.model)
            self.proactive_engine.set_memory(self.memory)
            self.memory.start_session()
        self._initialized = True

        # 启动主动唤醒调度器（发送消息，受黄金时段限制）
        if self.proactive_config.is_active:
            self.proactive_scheduler = ProactiveScheduler(self.proactive_engine)
            self.proactive_scheduler.set_dependencies(self.model, self.memory)
            await self.proactive_scheduler.start()
            logger.info(f"[BotInstance] 主动唤醒配置: idle_threshold={self.proactive_config.idle_threshold_hours}h, max_daily={self.proactive_config.max_daily}, 黄金时段={self.proactive_config.preferred_contact_times}")

            # 启动人生轨迹调度器（独立周期，不受黄金时段限制）
            self.life_scheduler = LifeScheduler(
                life_engine=self.life_engine,
                life_config=self.life_config,
                life_state=self.life_state,
            )
            self.life_engine.set_model(self.model)
            if self.memory:
                self.life_engine.set_memory(self.memory)
            if hasattr(self, '_persona_loader'):
                self.life_engine.set_persona_loader(self._persona_loader)
            await self.life_scheduler.start()
            print(f"[OK] {self.name} 人生轨迹已启动")
            print(f"     日常事件间隔: {self.life_config.daily_interval}s, 人生大事间隔: {self.life_config.major_interval}s")
        else:
            logger.info(f"[BotInstance] {self.name} 处于静默模式，跳过调度器")

    async def handle_message(self, user_input: str) -> str:
        """处理用户消息，返回回复"""
        if self.model is None:
            return "[Error] 模型未初始化"
        if not self._initialized:
            logger.warning("[BotInstance] handle_message called before init(), initializing now...")
            await self.init()

        # 0. 用户发消息了，通知主动唤醒系统
        self.proactive_engine.on_user_message_received()

        # 1. 拒绝检查（如果启用）
        relationship_state = None
        if self.memory:
            semantic_facts = await self.memory.semantic.get_all_facts()
            relationship_state = {"attitude_score": int(semantic_facts.get("attitude_score", 0))}

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
            system_prompt = self.persona_engine.build_system_prompt()
            if ctx.get("system_suffix"):
                system_prompt = system_prompt + "\n\n" + ctx["system_suffix"]
            if adjustment_note:
                system_prompt = system_prompt + adjustment_note

            # 4. 构建 messages
            messages = ctx.get("working_history", [])
            messages.append({"role": "user", "content": user_input})

            # 5. 对话
            response = await self._chat_with_fallback(messages, system_prompt)
            if response is None:
                return f"抱歉，网络不稳定，请稍后再试。"

            # 6. 异步写入记忆
            task = asyncio.create_task(self.memory.on_message(user_input, response))
            task.add_done_callback(
                lambda t: None if t.cancelled() or t.exception() is None
                else logger.error(f"[Memory] 写入异常: {t.exception()}")
            )
        else:
            system_prompt = self.persona_engine.build_system_prompt()
            if adjustment_note:
                system_prompt = system_prompt + adjustment_note
            messages = [{"role": "user", "content": user_input}]
            response = await self._chat_with_fallback(messages, system_prompt)
            if response is None:
                return f"抱歉，网络不稳定，请稍后再试。"

        # 记录历史
        self.conversation_history.append({"role": "user", "content": user_input})
        self.conversation_history.append({"role": "assistant", "content": response})

        return response

    async def _chat_with_fallback(self, messages: list[dict], system_prompt: str = "") -> Optional[str]:
        """调用模型聊天，失败时返回 None（由调用者处理友好提示）"""
        try:
            return await self.model.chat(messages, system_prompt)
        except RuntimeError as e:
            logger.error(f"[BotInstance] 对话失败: {e}")
            return None

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

    async def close(self):
        """关闭时清理资源"""
        if self.proactive_scheduler:
            await self.proactive_scheduler.stop()
        if self.life_scheduler:
            await self.life_scheduler.stop()
        if self.memory:
            await self.memory.close()
        # 关闭 MiniMax adapter 的 session
        if self.model and hasattr(self.model, 'close'):
            await self.model.close()