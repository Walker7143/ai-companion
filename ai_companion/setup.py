import asyncio
import os
import sys
import shutil
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt, Confirm

console = Console()


def get_data_dir() -> Path:
    if sys.platform == "win32":
        return Path.home() / ".ai-companion"
    else:
        return Path.home() / "ai-companion"


def get_project_dir() -> Path:
    return Path(__file__).parent.parent


async def run_setup():
    """运行配置向导"""
    console.print("\n[bold cyan]╔══════════════════════════════════════════════╗[/bold cyan]")
    console.print("[bold cyan]║        AI Companion 配置向导                ║[/bold cyan]")
    console.print("[bold cyan]╚══════════════════════════════════════════════╝[/bold cyan]\n")

    data_dir = get_data_dir()
    project_dir = get_project_dir()

    # 确保目录存在
    (data_dir / "config").mkdir(parents=True, exist_ok=True)
    (data_dir / "data" / "bots").mkdir(parents=True, exist_ok=True)

    console.print(f"[dim]数据目录: {data_dir}[/dim]\n")

    # Step 1: API Key 配置
    console.print("[bold]步骤 1/4:[/bold] 模型配置")
    console.print("-" * 40)

    model_choice = Prompt.ask(
        "请选择模型来源",
        choices=["1", "2", "3", "4", "5"],
        default="1"
    )

    model_map = {
        "1": ("MiniMax", "abab6.5s-chat", "https://api.minimax.chat/v1"),
        "2": ("OpenAI", "gpt-4o", "https://api.openai.com/v1"),
        "3": ("Claude", "claude-3-opus-20240229", "https://api.anthropic.com/v1"),
        "4": ("Ollama (本地)", "qwen2.5-14b", "http://localhost:11434/v1"),
        "5": ("自定义", "", ""),
    }

    provider, default_model, default_url = model_map[model_choice]
    console.print(f"选择: [green]{provider}[/green]")

    api_key = Prompt.ask("请输入 API Key", password=True)

    if model_choice == "5":
        custom_url = Prompt.ask("请输入 API URL", default="https://api.example.com/v1")
        custom_model = Prompt.ask("请输入模型名称")
    else:
        custom_url = default_url
        custom_model = Prompt.ask("模型名称", default=default_model)

    # 保存到用户数据目录
    config_dir = data_dir / "config"
    config_dir.mkdir(exist_ok=True)

    models_config = f"""minimax:
  api_key: "{api_key}"
  base_url: "{custom_url}"
  model: "{custom_model}"
"""
    (config_dir / "models.yaml").write_text(models_config)
    console.print("✓ 模型配置已保存\n")

    # Step 2: 创建 Bot
    console.print("[bold]步骤 2/4:[/bold] 创建 Bot")
    console.print("-" * 40)

    templates = [
        ("suqing", "苏晴", "外冷内热的插画师少女，傲娇，嘴硬心软"),
        ("aiyue", "阿月", "活泼开朗的音乐学院学生，直接，有点粘人"),
    ]

    console.print("可选人格模板:")
    for i, (tid, tname, tdesc) in enumerate(templates, 1):
        console.print(f"  {i}. {tname} - {tdesc}")
    console.print("  3. 稍后创建")

    bot_choice = Prompt.ask("请选择", choices=["1", "2", "3"], default="3")
    created_bots = []

    if bot_choice in ["1", "2"]:
        bot_id, bot_name = templates[int(bot_choice) - 1][0], templates[int(bot_choice) - 1][1]

        src_persona = project_dir / "data" / "bots" / bot_id / "persona"
        dst_persona = data_dir / "data" / "bots" / bot_id / "persona"

        if src_persona.exists():
            shutil.copytree(src_persona, dst_persona, dirs_exist_ok=True)
            created_bots.append({"id": bot_id, "name": bot_name})
            console.print(f"✓ {bot_name} 已创建")

    # 更新 bots.yaml
    bots_config = {"bots": []}
    for b in created_bots:
        bots_config["bots"].append({
            "id": b["id"],
            "name": b["name"],
            "description": "",
            "enabled": True
        })

    import yaml
    (config_dir / "bots.yaml").write_text(yaml.dump(bots_config, allow_unicode=True))
    console.print("✓ Bot 列表已更新\n")

    # Step 3: 飞书配置（可选）
    console.print("[bold]步骤 3/4:[/bold] 飞书配置（可选）")
    console.print("-" * 40)

    if Confirm.ask("是否配置飞书机器人?", default=False):
        app_id = Prompt.ask("请输入 App ID (cli_xxxxx)")
        app_secret = Prompt.ask("请输入 App Secret", password=True)

        feishu_config = f"""feishu:
  app_id: "{app_id}"
  app_secret: "{app_secret}"
  bot_name: "{created_bots[0]['name'] if created_bots else 'AI Companion'}"
"""
        (config_dir / "feishu.yaml").write_text(feishu_config)
        console.print("✓ 飞书配置已保存\n")
    else:
        console.print("✗ 跳过\n")

    # Step 4: 完成
    console.print("[bold]步骤 4/4:[/bold] 完成")
    console.print("-" * 40)
    console.print("✓ 配置完成！\n")

    console.print("[bold]启动方式:[/bold]")
    console.print("  [cyan]python -m ai_companion start[/cyan]\n")
    console.print(f"[dim]配置文件位置: {config_dir}[/dim]")
    console.print(f"[dim]人格数据位置: {data_dir}/data/bots[/dim]\n")
