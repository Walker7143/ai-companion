"""CLI helpers for built-in companion capabilities."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console

from ..bot.instance import BotInstance
from ..config.loader import Config
from ..skill.base import SkillContext
from ..skill.builtin_manager import BuiltinSkillManager
from ..skill.command import format_runtime_skill_capabilities, format_skill_result, parse_cli_params
from ..skill.config_merge import merge_skill_config
from ..skill.dispatcher import SkillDispatcher

console = Console()


def create_skill_parser(subparsers: argparse.Action = None) -> Optional[argparse.ArgumentParser]:
    if subparsers is not None:
        parser = subparsers.add_parser("skill", help="内置能力")
    else:
        parser = argparse.ArgumentParser(prog="skill", description="内置能力命令")

    sub = parser.add_subparsers(dest="skill_action", help="能力操作")

    list_parser = sub.add_parser("list", help="列出运行时能力")
    list_parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    list_parser.add_argument("--runtime", action="store_true", help="兼容旧参数，始终显示运行时能力")

    run_parser = sub.add_parser("run", help="执行内置能力")
    run_parser.add_argument("name", help="能力名称，例如 image_generation、image_understanding、tts")
    run_parser.add_argument("params", nargs=argparse.REMAINDER, help="JSON 对象或文本参数")

    return parser


def _get_data_dir() -> Path:
    user_dir = Path.home() / ".ai-companion" / "data" / "bots"
    if user_dir.exists():
        return user_dir
    return Path(__file__).parent.parent.parent / "data" / "bots"


async def _collect_runtime_skill_views() -> list[dict]:
    config = Config()
    data_dir = _get_data_dir()
    views: list[dict] = []

    for bot_config in config.get_enabled_bots():
        merged_skills = merge_skill_config(config.models.get("skills", {}), bot_config.get("skills", {}))
        instance_config = {**bot_config, "data_dir": str(data_dir), "skills": merged_skills}
        bot = BotInstance(instance_config, model=None, memory_config=None)
        try:
            views.append(
                {
                    "bot_id": bot.id,
                    "bot_name": bot.name,
                    "skills": bot.get_skill_capabilities().get("skills", {}),
                }
            )
        finally:
            await bot.close()

    return views


def cmd_skill_list(json_output: bool = False, runtime: bool = False):
    runtime_views = asyncio.run(_collect_runtime_skill_views())
    if json_output:
        print(json.dumps(runtime_views, ensure_ascii=False, indent=2))
        return

    if not runtime_views:
        console.print("[dim]没有可用的运行时能力[/dim]")
        return

    for index, view in enumerate(runtime_views):
        if index > 0:
            console.print("")
        console.print(f"[bold cyan]{view['bot_name']} ({view['bot_id']})[/bold cyan]")
        console.print(format_runtime_skill_capabilities({"skills": view["skills"]}))


async def cmd_skill_run(name: str, raw_params: list[str]):
    config = Config()
    dispatcher = SkillDispatcher()
    BuiltinSkillManager(dispatcher).register(config.models.get("skills", {}), {})

    skill = dispatcher.get(name)
    if not skill:
        console.print(f"[red]内置能力不存在: {name}[/red]")
        sys.exit(1)

    try:
        params = parse_cli_params(raw_params)
    except Exception as exc:
        console.print(f"[red]参数解析失败: {exc}[/red]")
        sys.exit(1)

    context = SkillContext(bot_id="cli", user_id="cli", conversation_history=[], personality_tags=[])
    result = await dispatcher.execute(name, params, context)
    output = format_skill_result(result)
    if result.success:
        console.print(output)
    else:
        console.print(f"[red]{output}[/red]")
        sys.exit(1)


def run_skill_command(args: list = None):
    if args is None:
        args = sys.argv[2:] if len(sys.argv) > 2 else []

    parser = create_skill_parser()
    parsed = parser.parse_args(args)

    if not parsed.skill_action:
        parser.print_help()
        return

    try:
        if parsed.skill_action == "list":
            cmd_skill_list(parsed.json, parsed.runtime)
        elif parsed.skill_action == "run":
            asyncio.run(cmd_skill_run(parsed.name, parsed.params))
    except KeyboardInterrupt:
        console.print("\n[dim]已取消[/dim]")
        sys.exit(0)
    except Exception as exc:
        console.print(f"[red]错误: {exc}[/red]")
        sys.exit(1)
