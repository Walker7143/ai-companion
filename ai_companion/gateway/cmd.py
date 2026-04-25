"""
Gateway 命令入口 - 启动网关服务连接飞书
"""

import asyncio
import logging
import os
import signal
import sys
import yaml
from pathlib import Path

# 添加项目根目录到 path
_project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_project_root))

from ai_companion.config.loader import Config
from ai_companion.model.minimax_adapter import MiniMaxAdapter
from ai_companion.bot.manager import BotManager
from ai_companion.bot.instance import BotInstance
from ai_companion.gateway.config import Platform, PlatformConfig
from ai_companion.gateway.platforms.feishu import FeishuAdapter
from ai_companion.gateway.router import PlatformRouter
from ai_companion.gateway.control import GATEWAY_PID_FILE, save_gateway_pid, remove_gateway_pid

logger = logging.getLogger(__name__)


def get_data_dir() -> Path:
    """获取 Bot 数据根目录"""
    user_dir = Path.home() / ".ai-companion" / "data" / "bots"
    if user_dir.exists():
        return user_dir
    return Path(__file__).parent.parent.parent.parent / "data" / "bots"


def load_feishu_config() -> dict:
    """从 ~/.ai-companion/config/config.yaml 加载飞书配置"""
    config_path = Path.home() / ".ai-companion" / "config" / "config.yaml"
    if not config_path.exists():
        return None

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        platforms = config.get("platforms", {})
        feishu = platforms.get("feishu", {})
        if feishu.get("enabled") and feishu.get("extra", {}).get("app_id"):
            return feishu["extra"]
    except Exception as e:
        logger.error(f"加载飞书配置失败: {e}")

    return None


async def run_gateway():
    """启动网关服务"""
    # 保存 PID
    save_gateway_pid(os.getpid())

    def cleanup():
        remove_gateway_pid()

    # 注册清理函数
    signal.signal(signal.SIGTERM, lambda s, f: cleanup())
    signal.signal(signal.SIGINT, lambda s, f: cleanup())

    print("=" * 50)
    print("AI Companion Gateway")
    print("=" * 50)
    print()

    # 加载配置
    config = Config()
    feishu_config = load_feishu_config()

    # 检查 API Key
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
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
        print(f"✓ 模型初始化成功: {model_cfg['model']}")
    except Exception as e:
        print(f"❌ 模型初始化失败: {e}")
        sys.exit(1)

    # 加载 Bot
    bot_manager = BotManager()
    memory_config = config.models.get("memory", {})
    data_dir = get_data_dir()

    for bot_config in config.get_enabled_bots():
        bot_config = {**bot_config, "data_dir": str(data_dir)}
        bot = BotInstance(bot_config, model=model, memory_config=memory_config)
        await bot.init()
        bot_manager.register(bot)
        print(f"✓ 加载 Bot: {bot.name}")

    if not bot_manager.list_bots():
        print("❌ 没有可用的 Bot")
        sys.exit(1)

    print()

    # 加载飞书配置
    if not feishu_config:
        print("❌ 飞书未配置")
        print("请运行: python -m ai_companion setup")
        sys.exit(1)

    print("✓ 飞书配置已加载")

    # 创建飞书适配器
    platform_config = PlatformConfig(
        enabled=True,
        extra=feishu_config
    )

    adapter = FeishuAdapter(platform_config)

    # 加载路由配置
    feishu_full_config = config.get_platform_config("feishu")
    routing_config = feishu_full_config.get("routing", {})
    router = PlatformRouter(routing_config)
    print(f"✓ 路由模式: {router.mode}")

    # 设置消息处理器 - 将消息路由到 Bot
    async def feishu_message_handler(event):
        """处理飞书消息，路由到 BotInstance"""
        # 根据路由模式获取 bot_id
        bot_id = router.route(event)
        bot = bot_manager.get_bot(bot_id)

        if not bot:
            # Fallback: 使用第一个可用的 bot
            bot = next(iter(bot_manager._bots.values()), None)

        if not bot:
            return "没有可用的 Bot"

        try:
            response = await bot.handle_message(event.text)
            return response
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
            return f"处理失败: {e}"

    adapter.set_message_handler(feishu_message_handler)

    # 连接飞书
    print()
    print("正在连接飞书...")

    success = await adapter.connect()
    if not success:
        print("❌ 飞书连接失败")
        print(f"   错误: {adapter.fatal_error_message or '未知错误'}")
        sys.exit(1)

    print(f"✓ 飞书连接成功 [{feishu_config.get('connection_mode', 'websocket')}]")
    print()
    print("=" * 50)
    print("网关已启动，等待飞书消息...")
    print("按 Ctrl+C 退出")
    print("=" * 50)

    # 保持运行
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print()
        print("正在停止网关...")
        await adapter.disconnect()
        cleanup()
        print("✓ 网关已停止")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    asyncio.run(run_gateway())
