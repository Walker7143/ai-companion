import asyncio
import os
import sys
import shutil
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table

console = Console()


def get_data_dir() -> Path:
    """获取 AI Companion 数据目录"""
    if sys.platform == "win32":
        return Path.home() / ".ai-companion"
    else:
        return Path.home() / ".ai-companion"


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
    console.print("[bold]步骤 1/5:[/bold] 模型配置")
    console.print("-" * 40)

    console.print("可选模型:")
    console.print("  1. MiniMax       - MiniMax API（默认，适合国内用户）")
    console.print("  2. OpenAI        - GPT 系列模型")
    console.print("  3. Claude       - Anthropic Claude 模型")
    console.print("  4. Ollama        - 本地运行的大模型（如 qwen2.5）")
    console.print("  5. 自定义        - 接入其他 API")

    model_choice = Prompt.ask(
        "\n请选择模型来源",
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

    # Step 2: 创建 Bot(s)
    console.print("[bold]步骤 2/5:[/bold] 创建 Bot")
    console.print("-" * 40)

    templates = [
        ("suqing", "苏晴", "外冷内热的插画师少女，傲娇，嘴硬心软"),
        ("aiyue", "阿月", "活泼开朗的音乐学院学生，直接，有点粘人"),
    ]

    console.print("可选人格模板:")
    for i, (tid, tname, tdesc) in enumerate(templates, 1):
        console.print(f"  {i}. {tname} - {tdesc}")

    created_bots = []

    # 允许创建多个 bot
    while True:
        console.print("\n当前已创建: [cyan]" + ", ".join(b["name"] for b in created_bots) if created_bots else "[dim]无[/dim]")
        add_more = Confirm.ask("是否添加 Bot?", default=True)
        if not add_more:
            break

        bot_choice = Prompt.ask(
            "请选择人格模板",
            choices=["1", "2", "3"],
            default="3"
        )

        if bot_choice == "3":
            # 自定义 Bot
            bot_id = Prompt.ask("请输入 Bot ID (英文唯一标识)")
            bot_name = Prompt.ask("请输入 Bot 名称")
        else:
            bot_id, bot_name = templates[int(bot_choice) - 1][0], templates[int(bot_choice) - 1][1]

        # 检查是否已存在
        if any(b["id"] == bot_id for b in created_bots):
            console.print(f"[yellow]⚠ Bot {bot_id} 已存在，跳过[/yellow]")
            continue

        src_persona = project_dir / "data" / "bots" / bot_id / "persona"
        dst_persona = data_dir / "data" / "bots" / bot_id / "persona"

        if src_persona.exists():
            shutil.copytree(src_persona, dst_persona, dirs_exist_ok=True)
            console.print(f"✓ [green]{bot_name}[/green] 已添加")
        else:
            console.print(f"[yellow]⚠ 模板 {bot_id} 不存在，已创建空 Bot[/yellow]")
            (data_dir / "data" / "bots" / bot_id).mkdir(parents=True, exist_ok=True)

        created_bots.append({"id": bot_id, "name": bot_name})

    if not created_bots:
        console.print("[yellow]⚠ 未创建任何 Bot，将创建默认 Bot[/yellow]")
        bot_id, bot_name = "suqing", "苏晴"
        src_persona = project_dir / "data" / "bots" / bot_id / "persona"
        dst_persona = data_dir / "data" / "bots" / bot_id / "persona"
        if src_persona.exists():
            shutil.copytree(src_persona, dst_persona, dirs_exist_ok=True)
        created_bots.append({"id": bot_id, "name": bot_name})

    # 更新 bots.yaml
    import yaml
    bots_config = {"bots": []}
    for b in created_bots:
        bots_config["bots"].append({
            "id": b["id"],
            "name": b["name"],
            "description": "",
            "enabled": True
        })

    (config_dir / "bots.yaml").write_text(yaml.dump(bots_config, allow_unicode=True))
    console.print(f"✓ Bot 列表已更新 ({len(created_bots)} 个)\n")

    # Step 3: 飞书配置
    console.print("[bold]步骤 3/5:[/bold] 飞书配置")
    console.print("-" * 40)

    if Confirm.ask("是否配置飞书机器人?", default=False):
        app_id = Prompt.ask("请输入 App ID (cli_xxxxx)")
        app_secret = Prompt.ask("请输入 App Secret", password=True)

        console.print("\n连接模式:")
        console.print("  1. WebSocket - 长连接（推荐，生产环境使用）")
        console.print("  2. Webhook   - 需要公网回调地址")
        connection_mode = Prompt.ask(
            "\n请选择连接模式",
            choices=["1", "2"],
            default="1"
        )
        connection_mode = "websocket" if connection_mode == "1" else "webhook"

        if connection_mode == "webhook":
            webhook_host = Prompt.ask("Webhook 监听地址", default="0.0.0.0")
            webhook_port = Prompt.ask("Webhook 监听端口", default="8765")
        else:
            webhook_host, webhook_port = None, None

        # 群组策略
        console.print("\n群组策略:")
        console.print("  1. open - 完全开放")
        console.print("  2. allowlist - 仅白名单用户")
        console.print("  3. blacklist - 黑名单除外")
        console.print("  4. admin_only - 仅管理员")

        policy_choice = Prompt.ask("请选择策略", choices=["1", "2", "3", "4"], default="2")
        policy_map = {"1": "open", "2": "allowlist", "3": "blacklist", "4": "admin_only"}
        group_policy = policy_map[policy_choice]

        allowed_users = []
        if group_policy in ("allowlist", "blacklist", "admin_only"):
            console.print("\n请输入允许的用户 Open ID（留空结束）:")
            while True:
                user = Prompt.ask("用户 Open ID", default="")
                if not user:
                    break
                allowed_users.append(user)

        admins = []
        if group_policy == "admin_only":
            console.print("\n请输入管理员 Open ID（留空结束）:")
            while True:
                admin = Prompt.ask("管理员 Open ID", default="")
                if not admin:
                    break
                admins.append(admin)

        # 飞书配置写入 config_dir / config.yaml
        config_path = config_dir / "config.yaml"
        config_data = {}
        if config_path.exists():
            try:
                config_data = yaml.safe_load(config_path.read_text()) or {}
            except Exception:
                pass

        # 确保 platforms 结构存在
        if "platforms" not in config_data:
            config_data["platforms"] = {}
        if "feishu" not in config_data["platforms"]:
            config_data["platforms"]["feishu"] = {"enabled": True, "extra": {}}
        else:
            config_data["platforms"]["feishu"]["enabled"] = True

        # 更新飞书配置
        feishu_extra = {
            "app_id": app_id,
            "app_secret": app_secret,
            "domain": "feishu",
            "connection_mode": connection_mode,
            "group_policy": group_policy,
        }

        if webhook_host:
            feishu_extra["webhook_host"] = webhook_host
        if webhook_port:
            feishu_extra["webhook_port"] = int(webhook_port)

        if allowed_users:
            feishu_extra["allowed_users"] = allowed_users
        if admins:
            feishu_extra["admins"] = admins

        config_data["platforms"]["feishu"]["extra"] = feishu_extra

        # 路由配置
        console.print("\n路由模式:")
        console.print("  1. dedicated - 所有消息发给指定的一个 Bot")
        console.print("  2. chat_routed - 根据群聊 ID 匹配不同 Bot")

        routing_choice = Prompt.ask("请选择路由模式", choices=["1", "2"], default="1")
        routing_mode = "dedicated" if routing_choice == "1" else "chat_routed"

        routing_config = {"mode": routing_mode}

        if routing_mode == "dedicated":
            if created_bots:
                console.print(f"\n请选择 Bot（默认: {created_bots[0]['name']}）:")
                for i, b in enumerate(created_bots, 1):
                    console.print(f"  {i}. {b['name']} ({b['id']})")
                bot_choice = Prompt.ask("选择", choices=[str(i) for i in range(1, len(created_bots) + 1)], default="1")
                routing_config["bot_id"] = created_bots[int(bot_choice) - 1]["id"]
        else:  # chat_routed
            # 默认 bot
            if created_bots:
                console.print(f"\n请选择默认 Bot（未匹配群聊时使用，默认: {created_bots[0]['name']}）:")
                for i, b in enumerate(created_bots, 1):
                    console.print(f"  {i}. {b['name']} ({b['id']})")
                bot_choice = Prompt.ask("选择", choices=[str(i) for i in range(1, len(created_bots) + 1)], default="1")
                routing_config["default_bot"] = created_bots[int(bot_choice) - 1]["id"]

            # 群聊映射
            console.print("\n群聊 ID -> Bot 映射（留空结束）:")
            console.print("  格式: oc_xxxxx1,bot_id")
            console.print("  例如: oc_xxxxx1,aiyue")
            group_bot_map = {}
            while True:
                line = Prompt.ask("映射")
                if not line:
                    break
                parts = line.split(",")
                if len(parts) == 2:
                    chat_id, bot_id = parts[0].strip(), parts[1].strip()
                    if chat_id and bot_id:
                        group_bot_map[chat_id] = bot_id
            if group_bot_map:
                routing_config["group_bot_map"] = group_bot_map

        config_data["platforms"]["feishu"]["routing"] = routing_config

        # 写回 config.yaml
        config_path.write_text(yaml.dump(config_data, allow_unicode=True, sort_keys=False))
        console.print("✓ 飞书配置已保存到 config.yaml\n")
    else:
        console.print("✗ 跳过飞书配置\n")

    # Step 4: 环境变量配置（可选）
    console.print("[bold]步骤 4/5:[/bold] 环境变量配置")
    console.print("-" * 40)

    # 检查是否已有 .env
    env_path = data_dir / ".env"
    existing_env = {}
    if env_path.exists():
        console.print(f"[dim]发现现有 .env 文件: {env_path}[/dim]")
        for line in env_path.read_text().splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                existing_env[key.strip()] = value.strip()

    # 询问是否写入环境变量
    if Confirm.ask("是否将配置写入 .env 文件（推荐）?", default=True):
        # 写入必要的环境变量
        env_lines = [
            f'MINIMAX_API_KEY="{api_key}"',
        ]

        if created_bots:
            first_bot = created_bots[0]["id"]
            env_lines.append(f'DEFAULT_BOT_ID="{first_bot}"')

        # 飞书环境变量
        feishu_extra = config_data.get("platforms", {}).get("feishu", {}).get("extra", {})
        if feishu_extra.get("app_id"):
            env_lines.append(f'FEISHU_APP_ID="{feishu_extra["app_id"]}"')
        if feishu_extra.get("app_secret"):
            env_lines.append(f'FEISHU_APP_SECRET="{feishu_extra["app_secret"]}"')
        if feishu_extra.get("connection_mode"):
            env_lines.append(f'FEISHU_CONNECTION_MODE="{feishu_extra["connection_mode"]}"')
        if feishu_extra.get("group_policy"):
            env_lines.append(f'FEISHU_GROUP_POLICY="{feishu_extra["group_policy"]}"')

        env_path.write_text("\n".join(env_lines) + "\n")
        console.print(f"✓ 环境变量已保存到 {env_path}\n")
    else:
        console.print("✗ 跳过\n")

    # Step 5: 完成
    console.print("[bold]步骤 5/5:[/bold] 完成")
    console.print("-" * 40)

    console.print("\n[bold]创建的 Bots:[/bold]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("ID")
    table.add_column("名称")
    for b in created_bots:
        table.add_row(b["id"], b["name"])
    console.print(table)

    console.print("\n✓ 配置完成！\n")

    console.print("[bold]启动方式:[/bold]")
    console.print("  [cyan]python -m ai_companion start[/cyan]\n")
    console.print(f"[dim]配置文件: {config_dir}[/dim]")
    console.print(f"[dim]人格数据: {data_dir}/data/bots[/dim]\n")
