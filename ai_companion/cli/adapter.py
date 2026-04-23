from rich.console import Console
from rich.prompt import Prompt
import re
import sys

from ..bot.manager import BotManager


class CLIAdapter:
    """命令行交互适配器"""

    def __init__(self, bot_manager: BotManager):
        self.bot_manager = bot_manager
        self.console = Console()
        self.current_bot_id: str = None

    def _read_input(self) -> str:
        """读取用户输入，过滤终端控制字符后解码"""
        sys.stdout.write("\u001b[1m\u001b[36m你\u001b[0m")
        sys.stdout.flush()
        raw_bytes = sys.stdin.buffer.readline()
        # 1. 先过滤掉所有控制字符（方向键转义序列 \x1b[D \x1b[C 等）
        filtered = bytearray()
        i = 0
        while i < len(raw_bytes):
            b = raw_bytes[i]
            if b == 0x1b:  # ESC
                # 跳过完整的 ANSI escape sequence（如 [D, [C, [A, [B 等方向键）
                if i + 1 < len(raw_bytes) and raw_bytes[i + 1] == 0x5b:  # '['
                    j = i + 2
                    while j < len(raw_bytes) and raw_bytes[j] in (0x30-0x3f):  # 0-9, ;, <, =, >, ?
                        j += 1
                    if j < len(raw_bytes) and 0x40 <= raw_bytes[j] <= 0x7e:  # @-~
                        i = j + 1
                        continue
                # 单独的 ESC 或无法解析的序列，跳过
                i += 1
                continue
            elif b < 0x20 and b not in (0x09, 0x0a, 0x0d):  # 排除 Tab/CR/LF
                i += 1
                continue
            filtered.append(b)
            i += 1
        # 2. 尝试多种编码解码
        for enc in ("utf-8", "gbk", "latin-1"):
            try:
                return filtered.decode(enc).strip()
            except UnicodeDecodeError:
                continue
        return filtered.decode("utf-8", errors="replace").strip()

    def _select_bot(self):
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
                choice = Prompt.ask(
                    "[bold]选择 Bot 编号",
                    default="1",
                    choices=[str(i) for i in range(1, len(bots) + 1)],
                )
                return bots[int(choice) - 1]["id"]
            except (ValueError, KeyError):
                self.console.print("[red]请输入有效的编号[/red]")

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
            user_input = self._read_input()
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
                self.console.print(f"[bold pink]{bot.name}[/bold pink]: {response}\n")
            except Exception as e:
                self.console.print(f"[red]Error:[/red] {e}\n")
