from rich.console import Console
from rich.prompt import Prompt
import asyncio
import random
import sys

# 初始化 readline，确保方向键工作
def _init_readline():
    try:
        import readline
        # 强制加载默认绑定
        readline.parse_and_bind(r'"\e[D": backward-char')
        readline.parse_and_bind(r'"\e[C": forward-char')
        readline.parse_and_bind(r'"\e[A": previous-history')
        readline.parse_and_bind(r'"\e[B": next-history')
    except Exception:
        pass

_init_readline()

from ..bot.manager import BotManager
from ..gateway.sentence_splitter import SentenceSplitter


class CLIAdapter:
    """命令行交互适配器"""

    def __init__(self, bot_manager: BotManager):
        self.bot_manager = bot_manager
        self.console = Console()
        self.current_bot_id: str = None

    async def _read_input(self) -> str:
        """读取用户输入"""
        try:
            line = await asyncio.to_thread(input, "\u001b[1m\u001b[36m你\u001b[0m ")
            return line.strip()
        except (EOFError, KeyboardInterrupt):
            raise

    async def _select_bot(self):
        bots = self.bot_manager.list_bots()
        if not bots:
            self.console.print("[red]没有可用的 Bot[/red]")
            return None
        self.console.print("[bold]可用 Bot：[/bold]")
        for i, bot in enumerate(bots, 1):
            self.console.print(f"  {i}. {bot['name']} ({bot['id']})")
        self.console.print("")

        while True:
            try:
                choice = await asyncio.to_thread(
                    Prompt.ask,
                    "[bold]选择 Bot 编号",
                    default="1",
                    choices=[str(i) for i in range(1, len(bots) + 1)],
                )
                return bots[int(choice) - 1]["id"]
            except (ValueError, KeyError):
                self.console.print("[red]请输入有效的编号[/red]")

    async def start(self):
        self.console.print("\n[bold green]═══ AI Companion CLI ═══[/bold green]\n")

        bot_id = await self._select_bot()
        if not bot_id:
            return
        self.current_bot_id = bot_id
        bot = self.bot_manager.get_bot(bot_id)
        if bot:
            from ..logging_utils import configure_bot_log_files
            configure_bot_log_files(bot.name)
            await bot.ensure_schedulers_started()

        self.console.print(f"[bold]当前 Bot:[/bold] {bot.name} ({bot.id})")
        self.console.print(f"[dim]{bot.description}[/dim]\n")
        self.console.print("[dim]输入 quit 退出，输入 switch 切换 Bot[/dim]\n")

        while True:
            user_input = await self._read_input()
            if not user_input:
                continue

            if user_input.lower() in ["quit", "exit", "退出"]:
                self.console.print("[dim]再见！[/dim]")
                break

            if user_input.lower() in ["switch", "切换"]:
                bot_id = await self._select_bot()
                if bot_id:
                    self.current_bot_id = bot_id
                    bot = self.bot_manager.get_bot(bot_id)
                    if bot:
                        from ..logging_utils import configure_bot_log_files
                        configure_bot_log_files(bot.name)
                        await bot.ensure_schedulers_started()
                    self.console.print(f"\n[bold]切换到:[/bold] {bot.name}\n")
                continue

            if user_input.lower() in ["reset", "重置"]:
                bot.reset_history()
                self.console.print("[dim]对话历史已清空[/dim]\n")
                continue

            # /new — 新会话
            if user_input.strip() == "/new":
                bot.reset_history()
                self.console.print("[dim]已开启新会话[/dim]\n")
                continue

            # /memory — 查看记忆状态
            if user_input.strip() == "/memory":
                if bot.memory:
                    status = await bot.memory.get_memory_status()
                    self.console.print("[bold]━━━ 记忆状态 ━━━[/bold]")
                    self.console.print(f"  会话ID: {status['session_id']}")
                    self.console.print(f"  工作记忆轮数: {status['working_turns']}")
                    self.console.print(f"  已压缩次数: {status['compression_count']}")
                    self.console.print(f"  情景记忆条数: {status['episodic_count']}")
                    self.console.print(f"  语义记忆事实数: {status['fact_count']}")
                    if status.get("user_understanding_path"):
                        self.console.print(f"  用户理解文件: {status['user_understanding_path']}")
                        self.console.print(f"  自动补充事实数: {status.get('user_understanding_auto_facts', 0)}")
                    health = status.get('health', {})
                    if health.get('reason'):
                        self.console.print(f"  状态: {health['reason']}")
                else:
                    self.console.print("[dim]记忆引擎未启用[/dim]")
                self.console.print("")
                continue

            # /forget <key> — 删除语义记忆
            if user_input.strip().startswith("/forget "):
                key = user_input.strip()[8:].strip()
                if not key:
                    self.console.print("[red]/forget 需要指定 key，例如: /forget occupation[/red]\n")
                elif bot.memory:
                    await bot.memory.forget_fact(key)
                    self.console.print(f"[dim]已删除语义记忆: {key}[/dim]\n")
                else:
                    self.console.print("[dim]记忆引擎未启用[/dim]\n")
                continue

            bot = self.bot_manager.get_bot(self.current_bot_id)
            try:
                response = await bot.handle_message(user_input)
                sentences = SentenceSplitter.split(response)
                if sentences:
                    # Print bot name prefix only before the first sentence
                    self.console.print(f"[bold pink]{bot.name}[/bold pink]: {sentences[0]}")
                    for i in range(1, len(sentences)):
                        # Random delay between sentences (1-2 seconds)
                        await asyncio.sleep(random.uniform(1.0, 2.0))
                        self.console.print(sentences[i])
                    self.console.print()  # Blank line after response
                else:
                    self.console.print(f"[bold pink]{bot.name}[/bold pink]:\n")
            except Exception as e:
                self.console.print(f"[red]Error:[/red] {e}\n")
