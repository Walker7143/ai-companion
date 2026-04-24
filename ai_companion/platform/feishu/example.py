"""
飞书接入示例

演示如何使用 FeishuServer 接入飞书平台
"""

import os
import logging
import asyncio

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """示例：启动飞书服务"""
    from ai_companion.platform.feishu import FeishuServer, FeishuHandler
    from ai_companion.platform.feishu.models import FeishuBot
    from ai_companion.bot.instance import BotInstance
    from ai_companion.model.minimax_adapter import MiniMaxAdapter
    from ai_companion.config.loader import Config

    # 加载配置
    config = Config()
    feishu_config = config.models.get("feishu", {})

    if not feishu_config.get("enabled"):
        print("飞书接入未启用，请在 config/models.yaml 中配置")
        return

    # 获取 API Key
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        model_cfg = config.get_model_config()
        api_key = model_cfg.get("api_key", "")

    if not api_key:
        print("MINIMAX_API_KEY 未配置")
        return

    # 初始化模型
    model_cfg = config.get_model_config()
    model = MiniMaxAdapter(
        api_key=api_key,
        base_url=model_cfg["base_url"],
        model=model_cfg["model"],
    )

    # 初始化 Bot
    bot_config = {"id": "suqing", "name": "苏青", "description": "飞书测试 Bot"}
    bot = BotInstance(bot_config, model=model)
    await bot.init()

    # 创建消息处理器
    handler = FeishuHandler()
    handler.register_bot(FeishuBot(
        bot_id="suqing",
        app_id=feishu_config["app_id"],
        app_secret=feishu_config["app_secret"],
        bot_name="苏青"
    ))
    handler.register_handler("suqing", handler.create_reply_handler(
        lambda bot_id: bot
    ))

    # 创建并启动飞书服务
    server = FeishuServer(
        app_id=feishu_config["app_id"],
        app_secret=feishu_config["app_secret"],
    )

    logger.info("飞书服务启动中...")
    server.start()

    try:
        # 保持运行
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("正在停止...")
        server.stop()


if __name__ == "__main__":
    asyncio.run(main())
