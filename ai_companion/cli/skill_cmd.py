"""
Skill CLI Commands - 技能命令行接口

提供 skill list/install/uninstall/enable/disable 等命令
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

from ..bot.instance import BotInstance
from ..config.loader import Config
from ..skill.config_merge import merge_skill_config
from ..skill.registry import SkillRegistry
from ..skill.installer import SkillInstaller
from ..skill.base import SkillContext
from ..skill.dispatcher import SkillDispatcher
from ..skill.command import format_skill_result, parse_cli_params, format_runtime_skill_capabilities


console = Console()


def create_skill_parser(subparsers: argparse.Action = None) -> Optional[argparse.ArgumentParser]:
    """创建 skill 命令解析器"""
    if subparsers is not None:
        parser = subparsers.add_parser("skill", help="技能管理")
    else:
        parser = argparse.ArgumentParser(
            prog="skill",
            description="技能管理命令",
            add_help=False
        )

    sub = parser.add_subparsers(dest="skill_action", help="技能操作")

    # skill list
    list_parser = sub.add_parser("list", help="列出已安装的技能")
    list_parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    list_parser.add_argument("--runtime", action="store_true", help="显示运行时能力状态")

    # skill info
    info_parser = sub.add_parser("info", help="显示技能详细信息")
    info_parser.add_argument("name", help="技能名称")

    # skill install
    install_parser = sub.add_parser("install", help="安装技能")
    install_parser.add_argument("source", help="技能来源（路径或 URL）")
    install_parser.add_argument("--name", "-n", help="强制指定名称")
    install_parser.add_argument("--force", "-f", action="store_true", help="强制覆盖")

    # skill uninstall
    uninstall_parser = sub.add_parser("uninstall", help="卸载技能")
    uninstall_parser.add_argument("name", help="技能名称")
    uninstall_parser.add_argument("--force", "-f", action="store_true", help="跳过确认")

    # skill enable
    enable_parser = sub.add_parser("enable", help="启用技能")
    enable_parser.add_argument("name", help="技能名称")

    # skill disable
    disable_parser = sub.add_parser("disable", help="禁用技能")
    disable_parser.add_argument("name", help="技能名称")

    # skill create
    create_parser = sub.add_parser("create", help="创建技能脚手架")
    create_parser.add_argument("name", help="技能名称")
    create_parser.add_argument("--description", "-d", default="", help="技能描述")
    create_parser.add_argument("--author", "-a", default="", help="作者")

    # skill registry
    registry_parser = sub.add_parser("registry", help="显示技能注册表路径")

    # skill run
    run_parser = sub.add_parser("run", help="执行技能")
    run_parser.add_argument("name", help="技能名称")
    run_parser.add_argument("params", nargs=argparse.REMAINDER, help="JSON 对象或 key=value/text 参数")

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
    """列出已安装的技能"""
    registry = SkillRegistry()
    skills = registry.list_installed()

    if runtime:
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
        return

    if json_output:
        print(json.dumps(skills, indent=2, ensure_ascii=False))
        return

    if not skills:
        console.print("[dim]没有已安装的技能[/dim]")
        return

    table = Table(title="已安装的技能")
    table.add_column("名称", style="cyan")
    table.add_column("版本", style="green")
    table.add_column("描述")
    table.add_column("状态", style="yellow")
    table.add_column("作者")

    for s in skills:
        status = "✓ 启用" if s.get("enabled") else "✗ 禁用"
        table.add_row(
            s.get("name", ""),
            s.get("version", "1.0.0"),
            s.get("description", ""),
            status,
            s.get("author", "")
        )

    console.print(table)


def cmd_skill_info(name: str):
    """显示技能详细信息"""
    registry = SkillRegistry()
    info = registry.get_info(name)

    if not info:
        console.print(f"[red]技能不存在: {name}[/red]")
        return

    console.print(f"\n[bold cyan]技能: {info.get('name')}[/bold cyan]")
    console.print(f"  版本: {info.get('version', '1.0.0')}")
    console.print(f"  描述: {info.get('description', '无')}")
    console.print(f"  作者: {info.get('author', '未知')}")
    console.print(f"  状态: {'启用' if info.get('enabled') else '禁用'}")
    console.print(f"  路径: {info.get('path', '')}")
    console.print(f"  入口: {info.get('entry', '')}")

    requirements = info.get("requirements", [])
    if requirements:
        console.print(f"  依赖: {', '.join(requirements)}")

    # 尝试加载技能获取能力信息
    skill = registry.load_skill(name)
    if skill:
        console.print(f"  能力: {', '.join(skill.capabilities)}")

    console.print()


def cmd_skill_install(source: str, name: str = None, force: bool = False):
    """安装技能"""
    installer = SkillInstaller()

    # 判断来源类型
    if source.startswith(("http://", "https://")):
        console.print(f"[cyan]从 URL 安装: {source}[/cyan]")
        result = installer.install_from_url(source, name, force=force)
    elif source.endswith((".zip", ".tar.gz", ".tgz")):
        console.print(f"[cyan]从压缩包安装: {source}[/cyan]")
        result = installer.install_from_path(Path(source), name, force=force)
    elif Path(source).is_dir():
        console.print(f"[cyan]从目录安装: {source}[/cyan]")
        result = installer.install_from_path(Path(source), name, force=force)
    else:
        console.print(f"[red]不支持的来源类型: {source}[/red]")
        return

    if result:
        console.print(f"[green]✓ 安装成功: {result.get('name')}[/green]")
    else:
        console.print(f"[red]✗ 安装失败[/red]")
        sys.exit(1)


def cmd_skill_uninstall(name: str, force: bool = False):
    """卸载技能"""
    registry = SkillRegistry()

    if not force:
        console.print(f"[yellow]确认卸载技能: {name}?[/yellow] [y/N]")
        confirm = input().strip().lower()
        if confirm not in ("y", "yes"):
            console.print("[dim]取消卸载[/dim]")
            return

    if registry.uninstall(name):
        console.print(f"[green]✓ 已卸载: {name}[/green]")
    else:
        console.print(f"[red]✗ 卸载失败: {name}[/red]")
        sys.exit(1)


def cmd_skill_enable(name: str):
    """启用技能"""
    registry = SkillRegistry()

    if registry.enable(name):
        console.print(f"[green]✓ 已启用: {name}[/green]")
    else:
        console.print(f"[red]✗ 启用失败: {name}[/red]")
        sys.exit(1)


def cmd_skill_disable(name: str):
    """禁用技能"""
    registry = SkillRegistry()

    if registry.disable(name):
        console.print(f"[green]✓ 已禁用: {name}[/green]")
    else:
        console.print(f"[red]✗ 禁用失败: {name}[/red]")
        sys.exit(1)


def cmd_skill_create(name: str, description: str = "", author: str = ""):
    """创建技能脚手架"""
    installer = SkillInstaller()
    path = installer.create_scaffold(name, description, author)

    if path:
        console.print(f"[green]✓ 已创建技能脚手架: {path}[/green]")
        console.print(f"[dim]编辑 {path / name}_skill.py 开始开发[/dim]")
    else:
        console.print(f"[red]✗ 创建失败[/red]")
        sys.exit(1)


def cmd_skill_registry():
    """显示技能注册表路径"""
    registry = SkillRegistry()
    console.print(f"[cyan]技能目录: {registry.skills_dir}[/cyan]")

    if registry.skills_dir.exists():
        count = len(registry.list_installed())
        console.print(f"[dim]已安装技能: {count}[/dim]")
    else:
        console.print("[dim]目录不存在[/dim]")


async def cmd_skill_run(name: str, raw_params: list[str]):
    """执行技能"""
    registry = SkillRegistry()
    dispatcher = SkillDispatcher()

    for info in registry.list_installed():
        if not info.get("enabled", True):
            continue
        skill = registry.load_skill(info["name"])
        if skill:
            dispatcher.register(skill)

    skill = dispatcher.get(name)
    if not skill:
        console.print(f"[red]技能不存在或未启用: {name}[/red]")
        sys.exit(1)

    try:
        params = parse_cli_params(raw_params)
    except Exception as exc:
        console.print(f"[red]参数解析失败: {exc}[/red]")
        sys.exit(1)

    context = SkillContext(
        bot_id="cli",
        user_id="cli",
        conversation_history=[],
        personality_tags=[],
    )
    result = await dispatcher.execute(name, params, context)
    output = format_skill_result(result)
    if result.success:
        console.print(output)
    else:
        console.print(f"[red]{output}[/red]")
        sys.exit(1)


def run_skill_command(args: list = None):
    """运行技能命令"""
    if args is None:
        args = sys.argv[2:] if len(sys.argv) > 2 else []

    parser = create_skill_parser()
    parsed, unknown = parser.parse_known_args(args)

    if not parsed.skill_action:
        parser.print_help()
        return

    try:
        {
            "list": lambda: cmd_skill_list(parsed.json, parsed.runtime),
            "info": lambda: cmd_skill_info(parsed.name),
            "install": lambda: cmd_skill_install(parsed.source, parsed.name, parsed.force),
            "uninstall": lambda: cmd_skill_uninstall(parsed.name, parsed.force),
            "enable": lambda: cmd_skill_enable(parsed.name),
            "disable": lambda: cmd_skill_disable(parsed.name),
            "create": lambda: cmd_skill_create(parsed.name, parsed.description, parsed.author),
            "registry": lambda: cmd_skill_registry(),
            "run": lambda: asyncio.run(cmd_skill_run(parsed.name, parsed.params)),
        }[parsed.skill_action]()
    except KeyboardInterrupt:
        console.print("\n[dim]已取消[/dim]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        sys.exit(1)
