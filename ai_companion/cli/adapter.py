from rich.console import Console
from rich.prompt import Prompt

from ..bot.manager import BotManager


class CLIAdapter:
    """命令行交互适配器"""

    def __init__(self, bot_manager: BotManager):
        self.bot_manager = bot_manager
        self.console = Console()
        self.current_bot_id: str = None

    def _select_bot(self):
        bots = self.bot_manager.list_bots()
        if not bots:
            self.console.print("[red]没有可用的 Bot[/red]")
            return None
        self.console.print("[bold]可用 Bot：[/bold]")
        for i, bot in enumerate(bots, 1):
            self.console.print(f"  {i}. {bot['name']} ({bot['id']})")
        self.console.print("")
        choice = Prompt.ask(
            "[bold]选择 Bot 编号",
            default="1",
            choices=[str(i) for i in range(1, len(bots) + 1)],
        )
        return bots[int(choice) - 1]["id"]

    async def start(self):
        self.console.print("\n[bold green]═══ AI Companion CLI ═══[/bold green]\n")

        bot_id = self._select_bot()
        if not bot_id:
            return
        self.current_bot_id = bot_id
        bot = self.bot_manager.get_bot(bot_id)

        self.console.print(f"[bold]当前 Bot:[/bold] {bot.name} ({bot.id})")
        self.console.print(f"[dim]{bot.description}[/dim]\n")
        self.console.print("[dim]输入 quit 退出，输入 switch 切换 Bot[/dim]\n")

        while True:
            user_input = Prompt.ask("[bold blue]你[/bold blue]").strip()
            if not user_input:
                continue

            if user_input.lower() in ["quit", "exit", "退出"]:
                self.console.print("[dim]再见！[/dim]")
                break

            if user_input.lower() in ["switch", "切换"]:
                bot_id = self._select_bot()
                if bot_id:
                    self.current_bot_id = bot_id
                    bot = self.bot_manager.get_bot(bot_id)
                    self.console.print(f"\n[bold]切换到:[/bold] {bot.name}\n")
                continue

            if user_input.lower() in ["reset", "重置"]:
                bot.reset_history()
                self.console.print("[dim]对话历史已清空[/dim]\n")
                continue

            bot = self.bot_manager.get_bot(self.current_bot_id)
            try:
                response = await bot.handle_message(user_input)
                self.console.print(f"[bold pink]{bot.name}[/bold pink]: {response}\n")
            except Exception as e:
                self.console.print(f"[red]Error:[/red] {e}\n")
