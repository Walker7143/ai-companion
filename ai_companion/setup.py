import asyncio
import json
import os
import sys
import shutil
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table
import yaml

console = Console()


REALTIME_DAILY_INTERVAL_SECONDS = 86400
REALTIME_MAJOR_INTERVAL_SECONDS = 604800

LIFE_TIME_PRESETS = {
    "1": {
        "name": "现实同步 1:1",
        "time_ratio": 1,
        "description": "现实 1 天 = Bot 1 天；日常约 24 小时检查一次，人生大事约 7 天检查一次",
    },
    "2": {
        "name": "轻度加速 24x",
        "time_ratio": 24,
        "description": "现实 1 小时 = Bot 1 天；适合日常体验中稍快推进",
    },
    "3": {
        "name": "观察测试 1440x",
        "time_ratio": 1440,
        "description": "现实 1 分钟 = Bot 1 天；适合短时间观察人生轨迹",
    },
    "4": {
        "name": "极速压测 86400x",
        "time_ratio": 86400,
        "description": "现实 1 秒 = Bot 1 天；仅建议测试使用",
    },
}


def _load_yaml_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _write_yaml_file(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _load_structured_file(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            return yaml.safe_load(text) or {}
        except Exception:
            return {}


def _write_json_file(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _persona_template_roots(project_dir: Path, data_dir: Path | None = None) -> list[Path]:
    roots = [
        project_dir / "ai_companion" / "data" / "bots",
        project_dir / "data" / "bots",
    ]
    if data_dir is not None:
        roots.append(data_dir / "data" / "bots")
    return roots


def _discover_builtin_bot_templates(project_dir: Path) -> list[dict]:
    bots = []
    seen_ids = set()
    for root in _persona_template_roots(project_dir):
        if not root.exists():
            continue
        for bot_dir in sorted(root.iterdir(), key=lambda p: p.name):
            bot_id = bot_dir.name
            persona_dir = bot_dir / "persona"
            profile_path = persona_dir / "profile.json"
            if bot_id.startswith("_") or bot_id in seen_ids or not profile_path.exists():
                continue
            profile = _load_structured_file(profile_path)
            if not isinstance(profile, dict):
                profile = {}
            seen_ids.add(bot_id)
            bots.append({
                "id": bot_id,
                "name": profile.get("name") or bot_id,
                "description": profile.get("occupation") or profile.get("summary") or "",
            })
    return bots


def _deep_merge(base: dict, updates: dict) -> dict:
    result = dict(base or {})
    for key, value in (updates or {}).items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _bot_label(bot: dict) -> str:
    return bot.get("name") or bot.get("id") or "unknown"


def _merge_bot_entries(
    existing_bots: list[dict],
    selected_bots: list[dict],
    overwritten_bot_ids: set[str] | None = None,
) -> dict[str, dict]:
    overwritten_bot_ids = overwritten_bot_ids or set()
    bots_by_id = {b["id"]: dict(b) for b in existing_bots}

    for bot in selected_bots:
        bot_id = bot["id"]
        existing = bots_by_id.get(bot_id)
        if existing and bot_id not in overwritten_bot_ids:
            # Re-running setup should not mutate an existing Bot unless the user
            # explicitly chose to overwrite/update it.
            bots_by_id[bot_id] = existing
            continue

        entry = dict(existing or {})
        entry["id"] = bot_id
        entry["name"] = bot.get("name") or entry.get("name") or bot_id
        entry.setdefault("description", "")
        entry.setdefault("enabled", True)
        bots_by_id[bot_id] = entry

    return bots_by_id


def _copy_persona_template(
    project_dir: Path,
    data_dir: Path,
    bot_id: str,
    bot_name: str = "",
    overwrite: bool = False,
) -> bool:
    src_candidates = []
    for root in _persona_template_roots(project_dir, data_dir):
        src_candidates.append(root / bot_id / "persona")
    for root in _persona_template_roots(project_dir, data_dir):
        src_candidates.append(root / "_template" / "persona")
    src_persona = next((path for path in src_candidates if path.exists()), None)
    dst_persona = data_dir / "data" / "bots" / bot_id / "persona"
    copied_template = False
    if src_persona and src_persona.resolve() != dst_persona.resolve():
        if overwrite or not dst_persona.exists():
            shutil.copytree(src_persona, dst_persona, dirs_exist_ok=True)
        else:
            dst_persona.mkdir(parents=True, exist_ok=True)
        copied_template = True
    else:
        dst_persona.mkdir(parents=True, exist_ok=True)

    profile_path = dst_persona / "profile.json"
    profile = _load_structured_file(profile_path)
    if not isinstance(profile, dict):
        profile = {}
    if not profile:
        profile = {"id": bot_id, "name": bot_name or bot_id}
        _write_json_file(profile_path, profile)
    else:
        updated = False
        if profile.get("id") != bot_id:
            profile["id"] = bot_id
            updated = True
        if bot_name and profile.get("name") in {"", "你的名字", "template"}:
            profile["name"] = bot_name
            updated = True
        if updated:
            _write_json_file(profile_path, profile)

    return copied_template


def _life_profile_default_choice(existing_life: dict) -> str:
    if not existing_life:
        return "1"
    ratio = int(existing_life.get("time_ratio", 1) or 1)
    daily = int(existing_life.get("daily_interval_seconds", REALTIME_DAILY_INTERVAL_SECONDS) or REALTIME_DAILY_INTERVAL_SECONDS)
    major = int(existing_life.get("major_interval_seconds", REALTIME_MAJOR_INTERVAL_SECONDS) or REALTIME_MAJOR_INTERVAL_SECONDS)
    if daily != REALTIME_DAILY_INTERVAL_SECONDS or major != REALTIME_MAJOR_INTERVAL_SECONDS:
        return "5"
    for key, preset in LIFE_TIME_PRESETS.items():
        if preset["time_ratio"] == ratio:
            return key
    return "5"


def _build_life_time_config(existing_life: dict | None = None) -> dict:
    existing_life = existing_life or {}
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("选项")
    table.add_column("名称")
    table.add_column("效果")
    for key, preset in LIFE_TIME_PRESETS.items():
        table.add_row(key, preset["name"], preset["description"])
    table.add_row("5", "自定义", "手动输入基础检查间隔和 time_ratio")
    console.print(table)

    choice = Prompt.ask(
        "请选择 Bot 时间流速",
        choices=["1", "2", "3", "4", "5"],
        default=_life_profile_default_choice(existing_life),
    )
    if choice == "5":
        daily_interval = int(Prompt.ask(
            "日常事件基础检查间隔（秒；86400 表示现实 1 天）",
            default=str(existing_life.get("daily_interval_seconds", REALTIME_DAILY_INTERVAL_SECONDS)),
        ))
        major_interval = int(Prompt.ask(
            "人生大事基础检查间隔（秒；604800 表示现实 7 天）",
            default=str(existing_life.get("major_interval_seconds", REALTIME_MAJOR_INTERVAL_SECONDS)),
        ))
        time_ratio = int(Prompt.ask(
            "时间流速倍率（1=现实同步，24=现实1小时过1个Bot日，1440=现实1分钟过1个Bot日）",
            default=str(existing_life.get("time_ratio", 1)),
        ))
    else:
        preset = LIFE_TIME_PRESETS[choice]
        daily_interval = REALTIME_DAILY_INTERVAL_SECONDS
        major_interval = REALTIME_MAJOR_INTERVAL_SECONDS
        time_ratio = preset["time_ratio"]

    return {
        "daily_interval_seconds": daily_interval,
        "major_interval_seconds": major_interval,
        "time_ratio": max(1, time_ratio),
        "time_ratio_warning_threshold": int(existing_life.get("time_ratio_warning_threshold", 500) or 500),
        "max_events": 100,
        "max_context_bits": int(existing_life.get("max_context_bits", 2000) or 2000),
    }


def _bot_persona_file(data_dir: Path, bot_id: str, filename: str) -> Path:
    return data_dir / "data" / "bots" / bot_id / "persona" / filename


def _prompt_proactive_config(existing_proactive: dict | None = None, bot_label: str = "") -> dict:
    existing_proactive = existing_proactive or {}
    if bot_label:
        console.print(f"\n[cyan]配置 {bot_label} 的主动唤醒[/cyan]")

    scheduler = existing_proactive.get("scheduler", {}) if isinstance(existing_proactive.get("scheduler"), dict) else {}
    triggers = existing_proactive.get("triggers", {}) if isinstance(existing_proactive.get("triggers"), dict) else {}
    emotion = triggers.get("emotion_trigger", {}) if isinstance(triggers.get("emotion_trigger"), dict) else {}

    default_idle = Prompt.ask(
        "空闲触发阈值（小时）",
        default=str(scheduler.get("idle_threshold_hours", existing_proactive.get("idle_threshold_hours", 24))),
    )
    default_max_daily = Prompt.ask(
        "每日最大主动消息数",
        default=str(scheduler.get("max_daily", existing_proactive.get("max_daily", 5))),
    )
    default_min_interval = Prompt.ask(
        "最小发送间隔（小时）",
        default=str(scheduler.get("min_interval_hours", existing_proactive.get("min_interval_hours", 4))),
    )

    console.print("\n发送平台:")
    console.print("  1. CLI       - 终端输出（默认）")
    console.print("  2. 飞书     - 通过飞书机器人发送")
    console.print("  3. Webhook   - 通过 Webhook 发送")

    platform = existing_proactive.get("platform", {}) if isinstance(existing_proactive.get("platform"), dict) else {}
    existing_platform_type = platform.get("type", existing_proactive.get("platform_type", "cli"))
    platform_default = {"cli": "1", "feishu": "2", "webhook": "3"}.get(existing_platform_type, "1")
    platform_choice = Prompt.ask("选择发送平台", choices=["1", "2", "3"], default=platform_default)
    platform_type = {"1": "cli", "2": "feishu", "3": "webhook"}[platform_choice]
    console.print(f"选择: [green]{platform_type}[/green]")

    console.print("\n主动唤醒模式:")
    console.print("  1. 启用 - Bot 会主动联系你")
    console.print("  2. 禁用 - Bot 不会主动发送消息")

    existing_mode = existing_proactive.get("mode", "active")
    mode_choice = Prompt.ask("选择模式", choices=["1", "2"], default="1" if existing_mode == "active" else "2")
    proactive_mode = {"1": "active", "2": "silent"}[mode_choice]

    proactive_config = {
        "enabled": True,
        "mode": proactive_mode,
        "scheduler": {
            "check_interval_seconds": int(scheduler.get("check_interval_seconds", existing_proactive.get("check_interval", 600))),
            "idle_threshold_hours": int(default_idle),
            "min_interval_hours": float(default_min_interval),
            "max_daily": int(default_max_daily),
            "max_idle_days": int(scheduler.get("max_idle_days", existing_proactive.get("max_idle_days", 7))),
        },
        "triggers": {
            "idle_reminder": {
                "enabled": True,
                "idle_hours": int(default_idle),
            },
            "emotion_trigger": {
                "enabled": True,
                "keywords": emotion.get("keywords", existing_proactive.get("emotion_keywords", ["难过", "伤心", "生气", "委屈", "累"])),
                "response_delay_minutes": int(emotion.get("response_delay_minutes", existing_proactive.get("emotion_response_delay_minutes", 30))),
            },
        },
        "platform": {
            "type": platform_type,
        },
    }
    if platform_type == "webhook":
        existing_webhook = platform.get("webhook_url", existing_proactive.get("webhook_url", ""))
        proactive_config["platform"]["webhook_url"] = Prompt.ask("Webhook URL", default=existing_webhook)

    return proactive_config


def _extract_existing_feishu_binding(existing_feishu: dict, bot_id: str) -> dict:
    bindings = existing_feishu.get("bot_bindings")
    if bindings is None:
        bindings = existing_feishu.get("bots")
    if isinstance(bindings, dict) and isinstance(bindings.get(bot_id), dict):
        return bindings[bot_id]

    routing = existing_feishu.get("routing", {}) if isinstance(existing_feishu.get("routing"), dict) else {}
    if routing.get("bot_id") == bot_id:
        return {"extra": existing_feishu.get("extra", {}) or {}}
    return {}


def _prompt_feishu_extra(existing_extra: dict | None = None, bot_label: str = "") -> dict:
    existing_extra = existing_extra or {}
    if bot_label:
        console.print(f"\n[cyan]配置 {bot_label} 的飞书 App[/cyan]")

    app_id = Prompt.ask("请输入 App ID (cli_xxxxx)", default=existing_extra.get("app_id", ""))
    while not app_id.strip():
        console.print("[red]飞书 App ID 不能为空。绑定飞书必须同时绑定 App 和 Bot。[/red]")
        app_id = Prompt.ask("请输入 App ID (cli_xxxxx)", default=existing_extra.get("app_id", ""))

    app_secret = Prompt.ask("请输入 App Secret", password=True, default="")
    while not app_secret.strip() and not str(existing_extra.get("app_secret", "")).strip():
        console.print("[red]飞书 App Secret 不能为空。[/red]")
        app_secret = Prompt.ask("请输入 App Secret", password=True, default="")

    console.print("\n连接模式:")
    console.print("  1. WebSocket - 长连接（推荐，生产环境使用）")
    console.print("  2. Webhook   - 需要公网回调地址")
    connection_mode = Prompt.ask(
        "\n请选择连接模式",
        choices=["1", "2"],
        default="1" if existing_extra.get("connection_mode") != "webhook" else "2",
    )
    connection_mode = "websocket" if connection_mode == "1" else "webhook"

    webhook_host = None
    webhook_port = None
    if connection_mode == "webhook":
        webhook_host = Prompt.ask("Webhook 监听地址", default=existing_extra.get("webhook_host", "0.0.0.0"))
        webhook_port = Prompt.ask("Webhook 监听端口", default=str(existing_extra.get("webhook_port", 8765)))

    console.print("\n群组策略:")
    console.print("  1. open - 完全开放")
    console.print("  2. allowlist - 仅白名单用户")
    console.print("  3. blacklist - 黑名单除外")
    console.print("  4. admin_only - 仅管理员")

    existing_policy = existing_extra.get("group_policy", "allowlist")
    policy_num = {"open": "1", "allowlist": "2", "blacklist": "3", "admin_only": "4"}.get(existing_policy, "2")
    policy_choice = Prompt.ask("请选择策略", choices=["1", "2", "3", "4"], default=policy_num)
    group_policy = {"1": "open", "2": "allowlist", "3": "blacklist", "4": "admin_only"}[policy_choice]

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

    feishu_extra = dict(existing_extra)
    feishu_extra["app_id"] = app_id.strip()
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
    return feishu_extra


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

    config_dir = data_dir / "config"
    config_dir.mkdir(exist_ok=True)
    models_config_path = config_dir / "models.yaml"
    bots_config_path = config_dir / "bots.yaml"
    existing_config = _load_yaml_file(models_config_path)
    existing_provider = existing_config.get("model", {}).get("provider", "minimax") if isinstance(existing_config.get("model"), dict) else "minimax"

    # Step 1: API Key 配置
    console.print("[bold]步骤 1/7:[/bold] 模型配置")
    console.print("-" * 40)

    console.print("可选模型:")
    console.print("  1. MiniMax       - MiniMax API（默认，适合国内用户）")
    console.print("  2. OpenAI        - GPT 系列模型")
    console.print("  3. Claude       - Anthropic Claude 模型")
    console.print("  4. Ollama        - 本地运行的大模型（如 qwen2.5）")
    console.print("  5. 自定义        - 接入其他 API")

    provider_choice_map = {
        "minimax": "1",
        "openai": "2",
        "claude": "3",
        "ollama": "4",
        "custom": "5",
    }
    if existing_config:
        console.print("[dim]发现现有模型配置；本步骤只会合并更新所选 provider，其他 provider/memory 配置会保留[/dim]")

    model_choice = Prompt.ask(
        "\n请选择模型来源",
        choices=["1", "2", "3", "4", "5"],
        default=provider_choice_map.get(existing_provider, "1")
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

    existing_api_key = existing_config.get(provider_key, {}).get("api_key", "") if isinstance(existing_config.get(provider_key), dict) else existing_config.get("api_key", "")
    existing_base_url = existing_config.get(provider_key, {}).get("base_url", "") if isinstance(existing_config.get(provider_key), dict) else ""
    existing_model = existing_config.get(provider_key, {}).get("model", "") if isinstance(existing_config.get(provider_key), dict) else ""

    api_key = existing_api_key or ""
    if provider_key != "ollama":
        api_key_prompt = Prompt.ask(
            "[dim]请输入 API Key[/dim]" if not existing_api_key else "[dim]请输入 API Key（直接回车保留现有配置）[/dim]",
            password=True,
            default="",
        )

        # 只有用户输入了内容才更新
        if api_key_prompt.strip():
            api_key = api_key_prompt
        elif existing_api_key:
            console.print("[dim]保留现有 API Key[/dim]")
    else:
        console.print("[dim]Ollama 默认不需要 API Key[/dim]")

    if model_choice == "5":
        custom_url = Prompt.ask("请输入 API URL", default=existing_base_url or "https://api.example.com/v1")
        custom_model = Prompt.ask("请输入模型名称", default=existing_model or "custom-model")
    else:
        custom_url = existing_base_url or default_url
        custom_model = Prompt.ask("模型名称", default=existing_model or default_model)

    models_config = dict(existing_config)
    model_defaults = dict(models_config.get("model", {}) if isinstance(models_config.get("model"), dict) else {})
    model_defaults["provider"] = provider_key
    models_config["model"] = model_defaults

    provider_config = dict(models_config.get(provider_key, {}) if isinstance(models_config.get(provider_key), dict) else {})
    if api_key.strip() or existing_api_key:
        provider_config["api_key"] = api_key
    provider_config["base_url"] = custom_url
    provider_config["model"] = custom_model
    models_config[provider_key] = provider_config

    _write_yaml_file(models_config_path, models_config)
    console.print("✓ 模型配置已保存（已保留其他模型和 memory 配置）\n")

    # Step 2: 创建 Bot(s)
    console.print("[bold]步骤 2/7:[/bold] 创建 Bot")
    console.print("-" * 40)

    builtin_bots = _discover_builtin_bot_templates(project_dir)
    if builtin_bots:
        console.print("可用内置 Bot 模板：")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("ID", style="cyan")
        table.add_column("名称", style="green")
        table.add_column("简介")
        for bot in builtin_bots:
            table.add_row(bot["id"], bot["name"], bot.get("description", ""))
        console.print(table)
        console.print("[dim]输入上方 ID 会复制对应人格模板；也可以输入新的 ID 创建自定义 Bot。[/dim]")
    else:
        console.print("[dim]未发现内置 Bot 模板，可以创建自定义 Bot。[/dim]")

    bots_config = _load_yaml_file(bots_config_path)
    existing_bots = [b for b in bots_config.get("bots", []) if isinstance(b, dict) and b.get("id")]
    if existing_bots:
        console.print("\n[dim]发现现有 Bot 配置，默认保留不覆盖：[/dim]")
        for bot in existing_bots:
            console.print(f"  - {_bot_label(bot)} ({bot.get('id')})")

    created_bots = []
    overwritten_bot_ids = set()
    configure_bots = Confirm.ask("是否添加或更新 Bot?", default=not bool(existing_bots))

    if configure_bots:
        # 允许创建多个 bot
        while True:
            current_names = ", ".join(_bot_label(b) for b in created_bots) if created_bots else "无"
            console.print(f"\n本次已选择: [cyan]{current_names}[/cyan]")
            add_more = Confirm.ask("是否添加 Bot?", default=not bool(created_bots))
            if not add_more:
                break

            bot_id = Prompt.ask("请输入 Bot ID (内置模板 ID 或英文唯一标识)").strip()
            if not bot_id:
                console.print("[yellow]⚠ Bot ID 不能为空，已跳过[/yellow]")
                continue
            bot_name = Prompt.ask("请输入 Bot 名称", default=bot_id).strip() or bot_id

            if any(b["id"] == bot_id for b in created_bots):
                console.print(f"[yellow]⚠ Bot {bot_id} 已在本次选择中，跳过[/yellow]")
                continue

            bot_exists = any(b.get("id") == bot_id for b in existing_bots)
            overwrite_persona = False
            if bot_exists:
                overwrite_persona = Confirm.ask(
                    f"Bot {bot_id} 已存在，是否覆盖它的人格文件?",
                    default=False,
                )
                if overwrite_persona:
                    overwritten_bot_ids.add(bot_id)

            template_found = _copy_persona_template(
                project_dir,
                data_dir,
                bot_id,
                bot_name=bot_name,
                overwrite=overwrite_persona,
            )
            if template_found:
                if bot_exists and not overwrite_persona:
                    console.print(f"✓ [green]{bot_name}[/green] 已保留现有人格文件")
                else:
                    console.print(f"✓ [green]{bot_name}[/green] 已添加/更新")
            else:
                console.print(f"[yellow]⚠ 模板 {bot_id} 不存在，已创建空 Bot[/yellow]")

            created_bots.append({"id": bot_id, "name": bot_name})

    if not existing_bots and not created_bots:
        console.print("[red]✗ 至少需要创建一个 Bot，setup 已中止。[/red]")
        return

    bots_by_id = _merge_bot_entries(existing_bots, created_bots, overwritten_bot_ids)
    bots_config["bots"] = list(bots_by_id.values())
    _write_yaml_file(bots_config_path, bots_config)
    raw_target_bots = created_bots if created_bots else list(bots_by_id.values())
    target_bots = [{"id": b["id"], "name": _bot_label(bots_by_id.get(b["id"], b))} for b in raw_target_bots if b.get("id")]
    console.print(f"✓ Bot 列表已保存（总计 {len(bots_config['bots'])} 个；旧 Bot 配置已保留）\n")

    # Step 3: 主动唤醒配置
    console.print("[bold]步骤 3/7:[/bold] 主动唤醒配置")
    console.print("-" * 40)

    sample_proactive = {}
    if target_bots:
        sample_path = data_dir / "data" / "bots" / target_bots[0]["id"] / "persona" / "proactive.json"
        sample_proactive = _load_structured_file(sample_path)
    proactive_default = bool(created_bots) or not bool(existing_bots)

    if Confirm.ask("是否配置 Bot 主动唤醒功能?", default=proactive_default):
        per_bot_proactive = len(target_bots) > 1 and Confirm.ask(
            "是否为每个 Bot 单独配置主动唤醒活跃程度?",
            default=True,
        )
        if per_bot_proactive:
            for b in target_bots:
                proactive_path = _bot_persona_file(data_dir, b["id"], "proactive.json")
                existing = _load_structured_file(proactive_path)
                proactive_config = _prompt_proactive_config(existing, b["name"])
                _write_json_file(proactive_path, _deep_merge(existing, proactive_config))
                console.print(f"✓ [green]{b['name']}[/green] 主动唤醒已配置")
        else:
            proactive_config = _prompt_proactive_config(sample_proactive)
            for b in target_bots:
                proactive_path = _bot_persona_file(data_dir, b["id"], "proactive.json")
                existing = _load_structured_file(proactive_path)
                _write_json_file(proactive_path, _deep_merge(existing, proactive_config))
                console.print(f"✓ [green]{b['name']}[/green] 主动唤醒已配置")
        console.print("[dim]可在 data/bots/{bot_id}/persona/proactive.json 中进一步调整[/dim]\n")
    else:
        console.print("[dim]跳过主动唤醒配置[/dim]\n")

    # Step 4: Bot 人生轨迹配置
    console.print("[bold]步骤 4/7:[/bold] Bot 人生轨迹配置")
    console.print("-" * 40)

    sample_life = {}
    if target_bots:
        sample_path = data_dir / "data" / "bots" / target_bots[0]["id"] / "persona" / "life.json"
        sample_life = _load_structured_file(sample_path)
    life_default = bool(created_bots) or not bool(existing_bots)

    if Confirm.ask("是否配置 Bot 人生轨迹（LifeEngine）?", default=life_default):
        console.print("[dim]默认推荐“现实同步 1:1”：现实 1 天推进 1 个 Bot 日。需要观察测试时再选择加速档。[/dim]")
        per_bot_life = len(target_bots) > 1 and Confirm.ask(
            "是否为每个 Bot 单独配置人生轨迹参数?",
            default=True,
        )
        if per_bot_life:
            for b in target_bots:
                console.print(f"\n[cyan]配置 {b['name']} 的人生轨迹[/cyan]")
                life_path = _bot_persona_file(data_dir, b["id"], "life.json")
                existing = _load_structured_file(life_path)
                life_config = _build_life_time_config(existing)
                _write_json_file(life_path, _deep_merge(existing, life_config))
                console.print(f"✓ [green]{b['name']}[/green] 人生轨迹已配置")
        else:
            life_config = _build_life_time_config(sample_life)
            for b in target_bots:
                life_path = _bot_persona_file(data_dir, b["id"], "life.json")
                existing = _load_structured_file(life_path)
                _write_json_file(life_path, _deep_merge(existing, life_config))
                console.print(f"✓ [green]{b['name']}[/green] 人生轨迹已配置")
        console.print("[dim]可在 data/bots/{bot_id}/persona/life.json 中进一步调整[/dim]\n")
    else:
        console.print("[dim]跳过人生轨迹配置[/dim]\n")

    # Step 5: 飞书配置
    console.print("[bold]步骤 5/7:[/bold] 飞书配置")
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
        feishu_binding_bots = [
            {"id": b["id"], "name": _bot_label(b)}
            for b in bots_config.get("bots", [])
            if isinstance(b, dict) and b.get("id")
        ]
        if not feishu_binding_bots:
            console.print("[red]✗ 绑定飞书前必须先创建 Bot，请重新运行 setup 并添加 Bot。[/red]\n")
            return

        # 路由配置：飞书强制一个 App 只绑定一个 Bot。
        console.print("\n飞书路由:")
        console.print("  绑定飞书 App 时必须同时绑定 Bot；多个 Bot 请分别配置不同飞书 App。")

        per_bot_feishu = len(feishu_binding_bots) > 1 and Confirm.ask(
            "是否为多个 Bot 分别配置飞书 App?",
            default=True,
        )

        # 确保 platforms 结构存在
        if "platforms" not in config_data:
            config_data["platforms"] = {}
        if "feishu" not in config_data["platforms"]:
            config_data["platforms"]["feishu"] = {"enabled": True, "extra": {}}
        else:
            config_data["platforms"]["feishu"]["enabled"] = True

        feishu_config = config_data["platforms"]["feishu"]
        if per_bot_feishu:
            feishu_config.pop("extra", None)
            feishu_config.pop("routing", None)
            existing_bindings = existing_feishu.get("bot_bindings")
            if existing_bindings is None:
                existing_bindings = existing_feishu.get("bots")
            bot_bindings = dict(existing_bindings or {}) if isinstance(existing_bindings, dict) else {}
            configured_count = 0
            for b in feishu_binding_bots:
                binding = _extract_existing_feishu_binding(existing_feishu, b["id"])
                existing_extra = binding.get("extra", {}) if isinstance(binding.get("extra"), dict) else {}
                bind_default = bool(existing_extra.get("app_id"))
                if Confirm.ask(f"是否为 {b['name']} ({b['id']}) 绑定飞书 App?", default=bind_default):
                    bot_bindings[b["id"]] = {
                        **{k: v for k, v in binding.items() if k not in {"extra", "routing"}},
                        "extra": _prompt_feishu_extra(existing_extra, b["name"]),
                    }
                    configured_count += 1
                elif b["id"] in bot_bindings and Confirm.ask(f"是否移除 {b['name']} 现有飞书绑定?", default=False):
                    bot_bindings.pop(b["id"], None)

            if configured_count == 0 and not bot_bindings:
                console.print("[yellow]未配置任何 Bot 的飞书绑定，跳过飞书配置写入。[/yellow]\n")
                feishu_config["enabled"] = False
            else:
                feishu_config["enabled"] = True
                feishu_config["bot_bindings"] = bot_bindings
        else:
            existing_extra = existing_feishu.get("extra", {}) or {}
            existing_routing = existing_feishu.get("routing", {}) or {}
            routing_config = {"mode": "dedicated"}
            existing_bot_id = existing_routing.get("bot_id", "")
            default_index = 1
            for i, b in enumerate(feishu_binding_bots, 1):
                if b["id"] == existing_bot_id:
                    default_index = i
                    break
            console.print(f"\n请选择这个飞书 App 绑定的 Bot（默认: {feishu_binding_bots[default_index - 1]['name']}）:")
            for i, b in enumerate(feishu_binding_bots, 1):
                console.print(f"  {i}. {b['name']} ({b['id']})")
            bot_choice = Prompt.ask(
                "选择",
                choices=[str(i) for i in range(1, len(feishu_binding_bots) + 1)],
                default=str(default_index),
            )
            routing_config["bot_id"] = feishu_binding_bots[int(bot_choice) - 1]["id"]
            feishu_config["enabled"] = True
            feishu_config["extra"] = _prompt_feishu_extra(existing_extra)
            feishu_config["routing"] = routing_config
            feishu_config.pop("bot_bindings", None)

        # 写回 config.yaml
        config_path.write_text(yaml.dump(config_data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        console.print("✓ 飞书配置已保存到 config.yaml\n")
    else:
        console.print("✗ 跳过飞书配置\n")

    # Step 6: 环境变量配置（可选）
    console.print("[bold]步骤 6/7:[/bold] 环境变量配置")
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

        # API Key - 只更新当前 provider 对应的环境变量，其他变量保留
        provider_env_key = {
            "minimax": "MINIMAX_API_KEY",
            "openai": "OPENAI_API_KEY",
            "claude": "ANTHROPIC_API_KEY",
        }.get(provider_key)
        if provider_env_key:
            if api_key.strip():
                env_lines.append(f'{provider_env_key}="{api_key}"')
            elif existing_env.get(provider_env_key):
                console.print(f"[dim]保留现有 {provider_env_key}[/dim]")
            else:
                env_lines.append(f'{provider_env_key}=""')

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

    # Step 7: 完成
    console.print("[bold]步骤 7/7:[/bold] 完成")
    console.print("-" * 40)

    console.print("\n[bold]当前可用 Bots:[/bold]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("ID")
    table.add_column("名称")
    for b in target_bots:
        table.add_row(b["id"], b["name"])
    console.print(table)

    console.print("\n✓ 配置完成！\n")

    console.print("[bold]启动方式:[/bold]")
    console.print("  [cyan]ai-companion start[/cyan]\n")
    console.print(f"[dim]配置文件: {config_dir}[/dim]")
    console.print(f"[dim]人格数据: {data_dir}/data/bots[/dim]\n")
