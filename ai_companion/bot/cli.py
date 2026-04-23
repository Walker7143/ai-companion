"""Bot 管理命令处理"""

from rich.console import Console
from rich.table import Table

console = Console()


def handle_bot_command(command, args):
    if command == "list":
        list_bots()
    elif command == "add":
        add_bot(args)
    elif command == "remove":
        remove_bot(args)


def list_bots():
    from ai_companion.config.loader import Config

    config = Config()
    bots = config.get_enabled_bots()

    table = Table(title="Bot 列表")
    table.add_column("ID", style="cyan")
    table.add_column("名称", style="green")
    table.add_column("状态", style="yellow")
    table.add_column("描述")

    for bot in bots:
        status = "启用" if bot.get("enabled") else "禁用"
        table.add_row(
            bot["id"],
            bot["name"],
            status,
            bot.get("description", ""),
        )

    console.print(table)
