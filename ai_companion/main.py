import asyncio
import os
import sys
from pathlib import Path

from .config.loader import Config
from .model.minimax_adapter import MiniMaxAdapter
from .bot.manager import BotManager
from .bot.instance import BotInstance
from .cli.adapter import CLIAdapter


def get_data_dir() -> Path:
    """获取用户数据目录，跨平台兼容"""
    if sys.platform == "win32":
        return Path.home() / ".ai-companion"
    else:
        return Path.home() / "ai-companion"


async def main(bot_filter: str = None):
    """主启动函数"""
    # 加载配置（优先用户目录，其次项目目录）
    config = Config()

    # 检查 API Key
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        # 尝试从配置文件读取
        model_cfg = config.get_model_config()
        api_key = model_cfg.get("api_key", "")

    if not api_key or api_key.startswith("${"):
        print("❌ API Key 未配置")
        print("")
        print("请先配置 API Key：")
        print("  1. 设置环境变量: export MINIMAX_API_KEY='your_key'")
        print("  2. 或运行: python -m ai_companion setup")
        sys.exit(1)

    # 初始化模型
    model_cfg = config.get_model_config()
    try:
        model = MiniMaxAdapter(
            api_key=api_key,
            base_url=model_cfg["base_url"],
            model=model_cfg["model"],
        )
    except Exception as e:
        print(f"❌ 模型初始化失败: {e}")
        sys.exit(1)

    # 初始化 Bot 管理器
    bot_manager = BotManager()

    # 加载所有启用的 Bot
    data_dir = get_data_dir()
    for bot_config in config.get_enabled_bots():
        if bot_filter and bot_config["id"] != bot_filter:
            continue

        bot_config = {**bot_config, "data_dir": str(data_dir)}
        bot = BotInstance(bot_config)
        bot.set_model(model)
        bot_manager.register(bot)
        print(f"✓ 加载 Bot: {bot.name}")

    if not bot_manager.list_bots():
        print("❌ 没有可用的 Bot")
        print("请先创建 Bot 或运行: python -m ai_companion setup")
        sys.exit(1)

    # 启动 CLI
    print("")
    cli = CLIAdapter(bot_manager)
    await cli.start()


def show_status():
    """显示状态"""
    data_dir = get_data_dir()
    print(f"数据目录: {data_dir}")
    print(f"配置文件: {data_dir / 'config'}")

    config = Config()
    bots = config.get_enabled_bots()
    print(f"已配置 Bot: {len(bots)}")
    for b in bots:
        status = "✓" if b.get("enabled") else "✗"
        print(f"  [{status}] {b['name']} ({b['id']})")
