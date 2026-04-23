import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from ..persona.loader import PersonaLoader
from ..persona.engine import PersonaEngine

if TYPE_CHECKING:
    from ..model.minimax_adapter import MiniMaxAdapter


class BotInstance:
    """单个 Bot 的运行实例"""

    def __init__(self, config: dict, data_dir: Path = Path("data/bots")):
        self.id = config["id"]
        self.name = config["name"]
        self.description = config.get("description", "")
        self.data_dir = Path(data_dir) / self.id

        # 加载人格
        persona_dir = self.data_dir / "persona"
        self.persona_loader = PersonaLoader(persona_dir)
        self.persona = self.persona_loader.load()
        self.persona_engine = PersonaEngine(self.persona)

        # 模型（由 BotManager 注入）
        self.model: "MiniMaxAdapter" = None

        # 对话历史
        self.conversation_history: list[dict] = []

    def set_model(self, model: "MiniMaxAdapter"):
        self.model = model

    async def handle_message(self, user_input: str) -> str:
        """处理用户消息，返回回复"""
        if self.model is None:
            return "[Error] 模型未初始化"

        # 构建带人格的 system prompt
        system_prompt = self.persona_engine.build_system_prompt()

        # 添加对话历史（最近10轮）
        history = self.conversation_history[-10:]

        messages = [{"role": "user", "content": user_input}]
        response = await self.model.chat(messages, system_prompt)

        # 记录历史
        self.conversation_history.append({"role": "user", "content": user_input})
        self.conversation_history.append({"role": "assistant", "content": response})

        return response

    def reset_history(self):
        """清空对话历史"""
        self.conversation_history = []
