import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from ..memory.engine import MemoryEngine
from ..persona.loader import PersonaLoader
from ..persona.engine import PersonaEngine
from ..persona.refusal_engine import RefusalEngine
from ..persona.refusal_category import RefusalCategory

if TYPE_CHECKING:
    from ..model.minimax_adapter import MiniMaxAdapter

logger = logging.getLogger(__name__)


class BotInstance:
    """单个 Bot 的运行实例"""

    def __init__(self, config: dict, model: "MiniMaxAdapter" = None,
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
        self.model: "MiniMaxAdapter" = model
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

    def set_model(self, model: "MiniMaxAdapter"):
        self.model = model
        self.refusal_engine.set_model(model)

    async def init(self):
        """初始化记忆引擎（启动时调用一次）"""
        if self.memory:
            await self.memory.init()
            if self.model:
                self.memory.set_summarizer(self.model)
            self.memory.start_session()
        self._initialized = True

    async def handle_message(self, user_input: str) -> str:
        """处理用户消息，返回回复"""
        if self.model is None:
            return "[Error] 模型未初始化"
        if not self._initialized:
            logger.warning("[BotInstance] handle_message called before init(), initializing now...")
            await self.init()

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
            # 软边界调整不阻塞请求，但会在 system prompt 中加入态度提示
            adjustment_note = f"\n\n[态度提示: {refusal_response.adjustment}]"
        else:
            adjustment_note = ""

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
            # 加入拒绝态度调整提示
            if adjustment_note:
                system_prompt = system_prompt + adjustment_note

            # 4. 构建 messages（工作记忆摘要+原始消息 + 当前输入）
            messages = ctx.get("working_history", [])
            messages.append({"role": "user", "content": user_input})

            # 5. 对话
            response = await self.model.chat(messages, system_prompt)

            # 6. 异步写入记忆，异常不阻塞回复
            task = asyncio.create_task(self.memory.on_message(user_input, response))
            task.add_done_callback(
                lambda t: None if t.cancelled() or t.exception() is None
                else logger.error(f"[Memory] 写入异常: {t.exception()}")
            )
        else:
            # 无记忆引擎时，回退到简单逻辑
            system_prompt = self.persona_engine.build_system_prompt()
            if adjustment_note:
                system_prompt = system_prompt + adjustment_note
            messages = [{"role": "user", "content": user_input}]
            response = await self.model.chat(messages, system_prompt)

        # 记录历史（用于快速回复）
        self.conversation_history.append({"role": "user", "content": user_input})
        self.conversation_history.append({"role": "assistant", "content": response})

        return response

    def reset_history(self):
        """清空对话历史（同时重置工作记忆会话）"""
        self.conversation_history = []
        if self.memory:
            self.memory.start_session()  # 开始新会话

    async def close(self):
        """关闭时清理资源"""
        if self.memory:
            await self.memory.close()
