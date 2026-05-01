import asyncio
import os
import sys
from pathlib import Path

from .config.loader import Config
from .logging_utils import setup_logging
from .model.factory import ModelFactory

from .bot.manager import BotManager
from .bot.instance import BotInstance
from .cli.adapter import CLIAdapter
from .ui_server import ensure_ui_server, release_ui_server, should_start_ui


def get_data_dir() -> Path:
    """获取 Bot 数据根目录，优先用户目录 ~/.ai-companion/"""
    user_dir = Path.home() / ".ai-companion" / "data" / "bots"
    if user_dir.exists():
        return user_dir
    return Path(__file__).parent.parent.parent / "data" / "bots"


def build_memory_config_for_provider(config: Config, provider: str) -> dict:
    """Merge provider context metadata into memory compressor config."""
    memory_config = dict(config.models.get("memory", {}) or {})
    provider_config = config.get_provider_config(provider)
    max_context_tokens = provider_config.get("max_context_tokens") or provider_config.get("max_context_chars")
    if max_context_tokens:
        context_cfg = dict(memory_config.get("context", {}) or {})
        compressor_cfg = dict(context_cfg.get("compressor", {}) or {})
        compressor_cfg.setdefault("model_context", int(max_context_tokens))
        context_cfg["compressor"] = compressor_cfg
        memory_config["context"] = context_cfg
    return memory_config


async def main(bot_filter: str = None):
    """主启动函数"""
    # 先加载配置，便于按 bot 名称分日志文件
    config = Config()
    bot_name_for_log = None
    if bot_filter:
        selected = next((b for b in config.get_enabled_bots() if b.get("id") == bot_filter), None)
        bot_name_for_log = selected.get("name") if selected else bot_filter
    setup_logging(bot_name=bot_name_for_log)

    # 获取数据目录
    user_dir = Path.home() / ".ai-companion" / "data" / "bots"
    if user_dir.exists():
        data_dir = user_dir
    else:
        project_data = Path(__file__).parent.parent.parent / "data" / "bots"
        data_dir = project_data

    # 已在上方加载配置

    model_cfg = config.get_model_config()
    provider = model_cfg.get("provider", config.default_provider)
    env_key_map = {
        "minimax": "MINIMAX_API_KEY",
        "openai": "OPENAI_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
        "mimo": "MIMO_API_KEY",
    }
    env_key = env_key_map.get(provider)
    api_key = os.environ.get(env_key, "") if env_key else ""
    if not api_key:
        api_key = model_cfg.get("api_key", "")

    if provider in env_key_map and (not api_key or api_key.startswith("${")):
        print("[ERROR] API Key 未配置")
        print("")
        print(f"请先配置 {provider} 的 API Key：")
        print(f"  1. 设置环境变量: export {env_key}='your_key'")
        print("  2. 或运行: ai-companion setup")
        sys.exit(1)

    # 初始化模型（按 provider 动态创建）
    try:
        model = ModelFactory.create_from_runtime_config(
            model_config=model_cfg,
            provider=provider,
            api_key=api_key if provider in env_key_map else None,
        )
        print(f"[OK] 模型初始化成功: provider={provider}, model={model_cfg.get('model', '')}")
    except Exception as e:
        print(f"[ERROR] 模型初始化失败: {e}")
        sys.exit(1)

    # 初始化 Bot 管理器
    bot_manager = BotManager()

    # 加载 memory 配置
    memory_config = build_memory_config_for_provider(config, provider)

    # 加载所有启用的 Bot
    data_dir = get_data_dir()
    for bot_config in config.get_enabled_bots():
        if bot_filter and bot_config["id"] != bot_filter:
            continue

        bot_config = {**bot_config, "data_dir": str(data_dir)}
        bot = BotInstance(bot_config, model=model, memory_config=memory_config)
        # CLI 模式下延迟启动后台调度器：
        # 仅在用户真正与该 Bot 开始对话后再启动人生轨迹/主动唤醒。
        await bot.init(start_schedulers=False)
        bot_manager.register(bot)
        print(f"[OK] 加载 Bot: {bot.name}")

    if not bot_manager.list_bots():
        print("[ERROR] 没有可用的 Bot")
        print("请先创建 Bot 或运行: ai-companion setup")
        sys.exit(1)

    start_ui_enabled = should_start_ui(default=True)
    admin_api_owned = False
    if start_ui_enabled:
        try:
            from .gateway.cmd import _start_admin_api
            admin_api_owned = bool(await _start_admin_api(bot_manager, config))
        except Exception as e:
            print(f"[WARN] 管理 API 未启动: {e}")

    ui_result = None
    if start_ui_enabled:
        ui_result = ensure_ui_server(owner_name="cli")
        if ui_result.ok:
            if ui_result.started:
                print(f"[OK] UI 服务器已启动 (PID: {ui_result.pid})")
            elif ui_result.reused:
                print("[OK] UI 服务器已在运行，复用现有实例")
            print(f"     管理后台: {ui_result.url}")
        else:
            print(f"[WARN] UI 服务器未启动: {ui_result.message}")

    # 启动 CLI
    print("")
    try:
        cli = CLIAdapter(bot_manager)
        await cli.start()
    finally:
        release_ui_server(ui_result)
        if admin_api_owned:
            from .gateway.cmd import _stop_admin_api
            await _stop_admin_api()
        for bot in bot_manager.bots.values():
            await bot.close()
        await model.close()


def show_status():
    """显示状态"""
    setup_logging()
    data_dir = get_data_dir()
    print(f"数据目录: {data_dir}")
    print(f"配置文件: {data_dir / 'config'}")

    config = Config()
    bots = config.get_enabled_bots()
    print(f"已配置 Bot: {len(bots)}")
    for b in bots:
        status = "[OK]" if b.get("enabled") else "[ERROR]"
        print(f"  [{status}] {b['name']} ({b['id']})")
