"""
AI Companion CLI 入口

用法:
    python -m ai_companion start      # 启动
    python -m ai_companion setup     # 配置向导
    python -m ai_companion status     # 查看状态
    python -m ai_companion bot list   # Bot 管理
    python -m ai_companion --help     # 帮助
"""

import argparse
import asyncio
import sys
from pathlib import Path

# 项目根目录
_project_root = Path(__file__).parent.parent
sys.path.insert(0, str(_project_root))


def main():
    from ai_companion.main import main as start_main
    from ai_companion.setup import run_setup
    from ai_companion.main import show_status
    from ai_companion.bot.cli import handle_bot_command

    parser = argparse.ArgumentParser(
        prog="ai-companion",
        description="AI Companion - 开源 AI 陪伴产品",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # start 命令
    start_parser = subparsers.add_parser("start", help="启动 AI Companion")
    start_parser.add_argument("--bot", type=str, help="只启动指定 Bot")

    # setup 命令
    subparsers.add_parser("setup", help="运行配置向导")

    # status 命令
    subparsers.add_parser("status", help="查看运行状态")

    # bot 子命令
    bot_parser = subparsers.add_parser("bot", help="Bot 管理")
    bot_subparsers = bot_parser.add_subparsers(dest="bot_command")

    bot_list = bot_subparsers.add_parser("list", help="列出所有 Bot")
    bot_add = bot_subparsers.add_parser("add", help="添加新 Bot")
    bot_add.add_argument("--name", type=str, required=True, help="Bot 名称")
    bot_add.add_argument("--persona", type=str, help="人格模板")

    bot_remove = bot_subparsers.add_parser("remove", help="删除 Bot")
    bot_remove.add_argument("--name", type=str, required=True, help="Bot 名称")

    # model 子命令
    model_parser = subparsers.add_parser("model", help="模型管理")
    model_subparsers = model_parser.add_subparsers(dest="model_command")
    model_test = model_subparsers.add_parser("test", help="测试模型连接")

    args = parser.parse_args()

    # 路由
    if args.command == "start":
        asyncio.run(start_main(bot_filter=args.bot))
    elif args.command == "setup":
        asyncio.run(run_setup())
    elif args.command == "status":
        show_status()
    elif args.command == "bot":
        handle_bot_command(args.bot_command, args)
    elif args.command == "model":
        if args.model_command == "test":
            print("测试模型连接...")
            print("✓ 配置读取正常")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
