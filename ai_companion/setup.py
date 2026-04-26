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
    console.print("[bold]步骤 1/6:[/bold] 模型配置")
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
        "1": ("minimax", "MiniMax", "abab6.5s-chat", "https://api.minimax.chat/v1"),
        "2": ("openai", "OpenAI", "gpt-4o", "https://api.openai.com/v1"),
        "3": ("claude", "Claude", "claude-3-opus-20240229", "https://api.anthropic.com/v1"),
        "4": ("ollama", "Ollama (本地)", "qwen2.5-14b", "http://localhost:11434/v1"),
        "5": ("custom", "自定义", "", ""),
    }

    provider_key, provider_name, default_model, default_url = model_map[model_choice]
    console.print(f"选择: [green]{provider_name}[/green]")

    # 检查现有配置
    config_dir = data_dir / "config"
    config_dir.mkdir(exist_ok=True)
    models_config_path = config_dir / "models.yaml"

    existing_config = {}
    if models_config_path.exists():
        try:
            import yaml
            existing_config = yaml.safe_load(models_config_path.read_text(encoding="utf-8")) or {}
            console.print("[dim]发现现有模型配置，将以此为默认值[/dim]")
        except Exception:
            pass

    existing_api_key = existing_config.get(provider_key, {}).get("api_key", "") if isinstance(existing_config.get(provider_key), dict) else existing_config.get("api_key", "")
    existing_base_url = existing_config.get(provider_key, {}).get("base_url", "") if isinstance(existing_config.get(provider_key), dict) else ""
    existing_model = existing_config.get(provider_key, {}).get("model", "") if isinstance(existing_config.get(provider_key), dict) else ""

    # 读取现有 API Key（如果有的话，用作默认）
    existing_minimax_key = ""
    if models_config_path.exists():
        try:
            import yaml
            existing_models = yaml.safe_load(models_config_path.read_text(encoding="utf-8")) or {}
            existing_minimax_key = existing_models.get("minimax", {}).get("api_key", "") if isinstance(existing_models.get("minimax"), dict) else ""
        except Exception:
            pass

    api_key_prompt = Prompt.ask(
        "[dim]请输入 API Key（直接回车保留现有配置）[/dim]",
        password=True,
        default=""
    )

    # 只有用户输入了内容才更新
    if api_key_prompt.strip():
        api_key = api_key_prompt
    else:
        api_key = existing_minimax_key
        console.print("[dim]保留现有 API Key[/dim]")

    if model_choice == "5":
        custom_url = Prompt.ask("请输入 API URL", default=existing_base_url or "https://api.example.com/v1")
        custom_model = Prompt.ask("请输入模型名称", default=existing_model or "custom-model")
    else:
        custom_url = default_url
        custom_model = Prompt.ask("模型名称", default=existing_model or default_model)

    # 如果有提供新配置，则更新
    if api_key.strip() or custom_model.strip():
        models_config = f"""{provider_key}:
  api_key: "{api_key}"
  base_url: "{custom_url}"
  model: "{custom_model}"
"""
        (config_dir / "models.yaml").write_text(models_config, encoding="utf-8")
        console.print("✓ 模型配置已保存\n")
    else:
        console.print("[dim]跳过模型配置保存[/dim]\n")

    # Step 2: 创建 Bot(s)
    console.print("[bold]步骤 2/6:[/bold] 创建 Bot")
    console.print("-" * 40)

    templates = [
        ("suqing", "苏晴", "外冷内热的插画师少女，傲娇，嘴硬心软"),
        ("aiyue", "阿月", "活泼开朗的音乐学院学生，直接，有点粘人"),
        ("chenxing", "陈行", "沉稳内敛的程序员，话少但可靠，高冷但温柔"),
        ("yutian", "雨天", "阳光开朗的健身教练，热情直接，有点占有欲"),
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
            choices=["1", "2", "3", "4", "5"],
            default="5"
        )

        if bot_choice == "5":
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
            (data_dir / "data" / "bots" / bot_id / "persona").mkdir(parents=True, exist_ok=True)

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

    (config_dir / "bots.yaml").write_text(yaml.dump(bots_config, allow_unicode=True), encoding="utf-8")
    console.print(f"✓ Bot 列表已更新 ({len(created_bots)} 个)\n")

    # Step 3: 主动唤醒配置
    console.print("[bold]步骤 3/6:[/bold] 主动唤醒配置")
    console.print("-" * 40)

    if Confirm.ask("是否启用 Bot 主动唤醒功能?", default=True):
        default_idle = Prompt.ask("空闲触发阈值（小时）", default="24")
        default_max_daily = Prompt.ask("每日最大主动消息数", default="5")
        default_min_interval = Prompt.ask("最小发送间隔（小时）", default="3")

        console.print("\n发送平台:")
        console.print("  1. CLI       - 终端输出（默认）")
        console.print("  2. 飞书     - 通过飞书机器人发送")
        console.print("  3. Webhook   - 通过 Webhook 发送")

        platform_choice = Prompt.ask("选择发送平台", choices=["1", "2", "3"], default="1")
        platform_map = {"1": "cli", "2": "feishu", "3": "webhook"}
        platform_type = platform_map[platform_choice]
        console.print(f"选择: [green]{platform_choice}[/green]")

        console.print("\n主动唤醒模式:")
        console.print("  1. idle     - 空闲触发（用户沉默后主动联系）")
        console.print("  2. active   - 活跃模式（更积极主动）")
        console.print("  3. silent   - 静默模式（不主动发送）")

        mode_choice = Prompt.ask("选择模式", choices=["1", "2", "3"], default="1")
        mode_map = {"1": "idle", "2": "active", "3": "silent"}
        proactive_mode = mode_map[mode_choice]

        proactive_config = {
            "enabled": True,
            "mode": proactive_mode,
            "check_interval": 60,
            "idle_threshold_hours": int(default_idle),
            "min_interval_hours": int(default_min_interval),
            "max_daily": int(default_max_daily),
            "emotion_trigger_enabled": True,
            "emotion_keywords": ["难过", "伤心", "生气", "委屈", "累"],
            "emotion_response_delay_minutes": 30,
            "platform_type": platform_type,
        }

        # 为每个创建的 Bot 更新 proactive.json
        for b in created_bots:
            proactive_path = data_dir / "data" / "bots" / b["id"] / "persona" / "proactive.json"
            if proactive_path.exists():
                existing = yaml.safe_load(proactive_path.read_text(encoding="utf-8")) or {}
                existing.update(proactive_config)
                proactive_path.write_text(yaml.dump(existing, allow_unicode=True, sort_keys=False), encoding="utf-8")
            console.print(f"✓ [green]{b['name']}[/green] 主动唤醒已配置")
        console.print("[dim]可在 data/bots/{bot_id}/persona/proactive.json 中进一步调整[/dim]\n")
    else:
        console.print("[dim]跳过主动唤醒配置[/dim]\n")

    # Step 4: Bot 人生轨迹配置
    console.print("[bold]步骤 4/6:[/bold] Bot 人生轨迹配置")
    console.print("-" * 40)

    if Confirm.ask("是否启用 Bot 人生轨迹（LifeEngine）?", default=True):
        daily_interval = Prompt.ask("日常事件检查间隔（秒）", default="3600")
        major_interval = Prompt.ask("人生大事检查间隔（秒）", default="21600")
        time_ratio = Prompt.ask("时间加速比率（1=现实时间）", default="1")

        life_config = {
            "daily_interval_seconds": int(daily_interval),
            "major_interval_seconds": int(major_interval),
            "time_ratio": int(time_ratio),
            "max_events": 20,
            "max_context_bits": 2000
        }

        for b in created_bots:
            life_path = data_dir / "data" / "bots" / b["id"] / "persona" / "life.json"
            if life_path.exists():
                existing = yaml.safe_load(life_path.read_text(encoding="utf-8")) or {}
                existing.update(life_config)
                life_path.write_text(yaml.dump(existing, allow_unicode=True, sort_keys=False), encoding="utf-8")
            console.print(f"✓ [green]{b['name']}[/green] 人生轨迹已配置")
        console.print("[dim]可在 data/bots/{bot_id}/persona/life.json 中进一步调整[/dim]\n")
    else:
        console.print("[dim]跳过人生轨迹配置[/dim]\n")

    # Step 5: 飞书配置
    console.print("[bold]步骤 5/6:[/bold] 飞书配置")
    console.print("-" * 40)

    # 加载现有飞书配置（用于默认值）
    config_path = config_dir / "config.yaml"
    config_data = {}
    existing_feishu = {}
    if config_path.exists():
        try:
            config_data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            existing_feishu = config_data.get("platforms", {}).get("feishu", {}) or {}
        except Exception:
            pass

    if Confirm.ask("是否配置飞书机器人?", default=bool(existing_feishu)):
        # 获取现有值作为默认值
        existing_extra = existing_feishu.get("extra", {}) or {}
        existing_routing = existing_feishu.get("routing", {}) or {}

        app_id = Prompt.ask("请输入 App ID (cli_xxxxx)", default=existing_extra.get("app_id", ""))
        app_secret = Prompt.ask("请输入 App Secret", password=True, default="")

        console.print("\n连接模式:")
        console.print("  1. WebSocket - 长连接（推荐，生产环境使用）")
        console.print("  2. Webhook   - 需要公网回调地址")
        connection_mode = Prompt.ask(
            "\n请选择连接模式",
            choices=["1", "2"],
            default="1" if existing_extra.get("connection_mode") != "webhook" else "2"
        )
        connection_mode = "websocket" if connection_mode == "1" else "webhook"

        if connection_mode == "webhook":
            webhook_host = Prompt.ask("Webhook 监听地址", default=existing_extra.get("webhook_host", "0.0.0.0"))
            webhook_port = Prompt.ask("Webhook 监听端口", default=str(existing_extra.get("webhook_port", 8765)))
        else:
            webhook_host = None
            webhook_port = None

        # 群组策略
        console.print("\n群组策略:")
        console.print("  1. open - 完全开放")
        console.print("  2. allowlist - 仅白名单用户")
        console.print("  3. blacklist - 黑名单除外")
        console.print("  4. admin_only - 仅管理员")

        existing_policy = existing_extra.get("group_policy", "allowlist")
        policy_num = {"open": "1", "allowlist": "2", "blacklist": "3", "admin_only": "4"}.get(existing_policy, "2")
        policy_choice = Prompt.ask("请选择策略", choices=["1", "2", "3", "4"], default=policy_num)
        policy_map = {"1": "open", "2": "allowlist", "3": "blacklist", "4": "admin_only"}
        group_policy = policy_map[policy_choice]

        allowed_users = list(existing_extra.get("allowed_users", []))
        if group_policy in ("allowlist", "blacklist", "admin_only"):
            console.print("\n允许的用户 Open ID（留空结束，输入 . 保留现有）:")
            while True:
                user = Prompt.ask("用户 Open ID", default="")
                if not user:
                    break
                if user == ".":
                    break
                allowed_users.append(user)

        admins = list(existing_extra.get("admins", []))
        if group_policy == "admin_only":
            console.print("\n管理员 Open ID（留空结束，输入 . 保留现有）:")
            while True:
                admin = Prompt.ask("管理员 Open ID", default="")
                if not admin:
                    break
                if admin == ".":
                    break
                admins.append(admin)

        # 确保 platforms 结构存在
        if "platforms" not in config_data:
            config_data["platforms"] = {}
        if "feishu" not in config_data["platforms"]:
            config_data["platforms"]["feishu"] = {"enabled": True, "extra": {}}
        else:
            config_data["platforms"]["feishu"]["enabled"] = True

        # 更新飞书配置（合并新旧值）
        feishu_extra = dict(existing_extra)
        if app_id:
            feishu_extra["app_id"] = app_id
        if app_secret:
            feishu_extra["app_secret"] = app_secret
        feishu_extra["domain"] = "feishu"
        feishu_extra["connection_mode"] = connection_mode
        feishu_extra["group_policy"] = group_policy

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

        existing_mode = existing_routing.get("mode", "dedicated")
        routing_choice = Prompt.ask("请选择路由模式", choices=["1", "2"], default="1" if existing_mode == "dedicated" else "2")
        routing_mode = "dedicated" if routing_choice == "1" else "chat_routed"

        routing_config = dict(existing_routing)
        routing_config["mode"] = routing_mode

        if routing_mode == "dedicated":
            existing_bot_id = existing_routing.get("bot_id", "")
            if created_bots:
                console.print(f"\n请选择 Bot（默认: {existing_bot_id or created_bots[0]['name']}）:")
                for i, b in enumerate(created_bots, 1):
                    console.print(f"  {i}. {b['name']} ({b['id']})")
                bot_choice = Prompt.ask("选择", choices=[str(i) for i in range(1, len(created_bots) + 1)], default="1")
                routing_config["bot_id"] = created_bots[int(bot_choice) - 1]["id"]
        else:  # chat_routed
            if created_bots:
                existing_default_bot = existing_routing.get("default_bot", "")
                console.print(f"\n请选择默认 Bot（默认: {existing_default_bot or created_bots[0]['name']}）:")
                for i, b in enumerate(created_bots, 1):
                    console.print(f"  {i}. {b['name']} ({b['id']})")
                bot_choice = Prompt.ask("选择", choices=[str(i) for i in range(1, len(created_bots) + 1)], default="1")
                routing_config["default_bot"] = created_bots[int(bot_choice) - 1]["id"]

            existing_group_map = existing_routing.get("group_bot_map", {})
            console.print("\n群聊 ID -> Bot 映射（留空结束，输入 . 保留现有）:")
            console.print("  格式: oc_xxxxx1,bot_id")
            group_bot_map = {}
            for chat_id, bot_id in existing_group_map.items():
                console.print(f"  现有: {chat_id} -> {bot_id}")
            while True:
                line = Prompt.ask("映射")
                if not line:
                    break
                if line == ".":
                    group_bot_map = dict(existing_group_map)
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
        config_path.write_text(yaml.dump(config_data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        console.print("✓ 飞书配置已保存到 config.yaml\n")
    else:
        console.print("✗ 跳过飞书配置\n")

    # Step 6: 环境变量配置（可选）
    console.print("[bold]步骤 6/6:[/bold] 环境变量配置")
    console.print("-" * 40)

    # 检查是否已有 .env
    env_path = data_dir / ".env"
    existing_env = {}
    if env_path.exists():
        console.print(f"[dim]发现现有 .env 文件: {env_path}[/dim]")
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                existing_env[key.strip()] = value.strip()

    # 询问是否写入环境变量
    if Confirm.ask("是否将配置写入 .env 文件（推荐）?", default=True):
        # 写入必要的环境变量（不覆盖已有值）
        env_lines = []

        # API Key - 只在用户输入了新值时才写入
        if api_key.strip():
            env_lines.append(f'MINIMAX_API_KEY="{api_key}"')
        elif existing_env.get("MINIMAX_API_KEY"):
            console.print("[dim]保留现有 MINIMAX_API_KEY[/dim]")
        else:
            env_lines.append(f'MINIMAX_API_KEY=""')

        # 默认 Bot
        if created_bots:
            first_bot = created_bots[0]["id"]
            if first_bot:
                env_lines.append(f'DEFAULT_BOT_ID="{first_bot}"')
        elif existing_env.get("DEFAULT_BOT_ID"):
            console.print("[dim]保留现有 DEFAULT_BOT_ID[/dim]")

        # 飞书环境变量 - 只在新配置存在时才写入
        feishu_extra = config_data.get("platforms", {}).get("feishu", {}).get("extra", {})
        if feishu_extra.get("app_id"):
            env_lines.append(f'FEISHU_APP_ID="{feishu_extra["app_id"]}"')
        elif existing_env.get("FEISHU_APP_ID"):
            console.print("[dim]保留现有 FEISHU_APP_ID[/dim]")

        if feishu_extra.get("app_secret"):
            env_lines.append(f'FEISHU_APP_SECRET="{feishu_extra["app_secret"]}"')
        elif existing_env.get("FEISHU_APP_SECRET"):
            console.print("[dim]保留现有 FEISHU_APP_SECRET[/dim]")

        if feishu_extra.get("connection_mode"):
            env_lines.append(f'FEISHU_CONNECTION_MODE="{feishu_extra["connection_mode"]}"')
        elif existing_env.get("FEISHU_CONNECTION_MODE"):
            console.print("[dim]保留现有 FEISHU_CONNECTION_MODE[/dim]")

        if feishu_extra.get("group_policy"):
            env_lines.append(f'FEISHU_GROUP_POLICY="{feishu_extra["group_policy"]}"')
        elif existing_env.get("FEISHU_GROUP_POLICY"):
            console.print("[dim]保留现有 FEISHU_GROUP_POLICY[/dim]")

        # 保留原有但不在本次更新的变量
        for key, value in existing_env.items():
            if key not in [line.split("=")[0] for line in env_lines if "=" in line]:
                env_lines.append(f'{key}={value}')

        env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
        console.print(f"✓ 环境变量已保存到 {env_path}\n")
    else:
        console.print("✗ 跳过\n")

    # Step 5: 完成
    console.print("[bold]步骤 7/7:[/bold] 完成")
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
