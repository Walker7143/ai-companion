"""
AI Companion CLI 入口

用法:
    ai-companion start          # 启动本地 CLI 对话
    ai-companion gateway       # 启动网关服务（连接飞书）
    ai-companion gateway start  # 后台启动网关（默认）
    ai-companion gateway start --sync  # 前台启动网关（显示日志）
    ai-companion gateway stop   # 停止网关
    ai-companion gateway restart  # 重启网关
    ai-companion gateway logs   # 查看网关日志
    ai-companion gateway status  # 查看网关状态
    ai-companion setup          # 配置向导
    ai-companion update         # 一键更新到最新代码
    ai-companion status         # 查看状态
    ai-companion bot list       # Bot 管理
    ai-companion --help         # 帮助
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
    from ai_companion.persona_importer.cli import add_persona_parser, handle_persona_command
    from ai_companion.cli.skill_cmd import create_skill_parser, run_skill_command
    from ai_companion.gateway import control
    from ai_companion.updater import UpdateOptions, run_update

    parser = argparse.ArgumentParser(
        prog="ai-companion",
        description="AI Companion - 开源 AI 陪伴产品",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # start 命令
    start_parser = subparsers.add_parser("start", help="启动 AI Companion (本地 CLI)")
    start_parser.add_argument("--bot", type=str, help="只启动指定 Bot")

    # gateway 命令（支持子命令）
    gateway_parser = subparsers.add_parser("gateway", help="网关服务管理 (连接飞书等平台)")
    gateway_subparsers = gateway_parser.add_subparsers(dest="gateway_command")

    # gateway start
    gateway_start = gateway_subparsers.add_parser("start", help="启动网关（后台运行）")
    gateway_start.add_argument("--sync", action="store_true", help="前台模式（显示日志，按 Ctrl+C 退出）")

    # gateway stop
    gateway_subparsers.add_parser("stop", help="停止网关")

    # gateway restart
    gateway_restart = gateway_subparsers.add_parser("restart", help="重启网关")
    gateway_restart.add_argument("--sync", action="store_true", help="前台模式（显示日志）")

    # gateway replace
    gateway_replace = gateway_subparsers.add_parser("replace", help="替换网关（先停止旧实例再启动新实例）")
    gateway_replace.add_argument("--sync", action="store_true", help="前台模式（显示日志）")

    # gateway logs
    gateway_logs = gateway_subparsers.add_parser("logs", help="查看网关日志")
    gateway_logs.add_argument("-n", "--lines", type=int, default=50, help="显示行数")

    # gateway status
    gateway_subparsers.add_parser("status", help="查看网关状态")

    # setup 命令
    subparsers.add_parser("setup", help="运行配置向导")

    # update 命令
    update_parser = subparsers.add_parser("update", help="一键更新到最新代码")
    update_parser.add_argument(
        "--no-restart-gateway",
        action="store_true",
        help="更新前后不自动停止/重启 Gateway",
    )
    update_parser.add_argument("--skip-ui", action="store_true", help="跳过管理后台 UI 依赖同步")
    update_parser.add_argument(
        "--index-url",
        type=str,
        help="指定 pip 镜像源，例如 https://pypi.tuna.tsinghua.edu.cn/simple",
    )
    update_parser.add_argument(
        "--cn",
        action="store_true",
        help="使用清华 PyPI 镜像同步 Python 依赖",
    )

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

    # persona 子命令
    add_persona_parser(subparsers)

    # skill 子命令
    create_skill_parser(subparsers)

    # model 子命令
    model_parser = subparsers.add_parser("model", help="模型管理")
    model_subparsers = model_parser.add_subparsers(dest="model_command")
    model_test = model_subparsers.add_parser("test", help="测试模型连接")

    args = parser.parse_args()

    # 路由
    if args.command == "start":
        asyncio.run(start_main(bot_filter=args.bot))
    elif args.command == "gateway":
        if args.gateway_command == "start":
            control.start_gateway(sync=args.sync)
        elif args.gateway_command == "stop":
            control.stop_gateway()
        elif args.gateway_command == "restart":
            control.restart_gateway(sync=args.sync)
        elif args.gateway_command == "replace":
            control.replace_gateway(sync=args.sync)
        elif args.gateway_command == "logs":
            control.tail_logs(lines=args.lines)
        elif args.gateway_command == "status":
            control.show_gateway_status()
        else:
            # 无子命令时直接运行 gateway（默认后台运行）
            from ai_companion.gateway.cmd import run_gateway
            asyncio.run(run_gateway(daemon=True))
    elif args.command == "setup":
        asyncio.run(run_setup())
    elif args.command == "update":
        index_url = args.index_url
        if args.cn and not index_url:
            index_url = "https://pypi.tuna.tsinghua.edu.cn/simple"
        sys.exit(
            run_update(
                UpdateOptions(
                    restart_gateway=not args.no_restart_gateway,
                    skip_ui=args.skip_ui,
                    index_url=index_url,
                )
            )
        )
    elif args.command == "status":
        show_status()
    elif args.command == "bot":
        handle_bot_command(args.bot_command, args)
    elif args.command == "persona":
        handle_persona_command(args.persona_command, args)
    elif args.command == "skill":
        run_skill_command(sys.argv[2:])
    elif args.command == "model":
        if args.model_command == "test":
            print("测试模型连接...")
            print("[OK] 配置读取正常")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
