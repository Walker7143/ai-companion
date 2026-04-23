import asyncio
import os
import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.loader import Config
from src.model.minimax_adapter import MiniMaxAdapter
from src.bot.manager import BotManager
from src.bot.instance import BotInstance
from src.cli.adapter import CLIAdapter


async def main():
    # 加载配置
    config = Config()

    # 检查 API Key
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        print("Error: MINIMAX_API_KEY environment variable not set")
        print("Please run: export MINIMAX_API_KEY='your_key_here'")
        sys.exit(1)

    # 初始化模型
    model_cfg = config.get_model_config()
    model = MiniMaxAdapter(
        api_key=api_key,
        base_url=model_cfg["base_url"],
        model=model_cfg["model"],
    )

    # 初始化 Bot 管理器
    bot_manager = BotManager()

    # 加载所有启用的 Bot
    for bot_config in config.get_enabled_bots():
        bot = BotInstance(bot_config)
        bot.set_model(model)
        bot_manager.register(bot)
        print(f"Loaded bot: {bot.name} ({bot.id})")

    if not bot_manager.list_bots():
        print("Error: No bots enabled")
        sys.exit(1)

    # 启动 CLI
    cli = CLIAdapter(bot_manager)
    await cli.start()


if __name__ == "__main__":
    asyncio.run(main())
