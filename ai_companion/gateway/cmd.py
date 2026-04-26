"""
Gateway 命令入口 - 启动网关服务连接飞书
"""

# Import aiohttp early to avoid platform module shadowing issue
import aiohttp

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import time
import uuid
import yaml
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 path
_project_root = Path(__file__).parent.parent.parent
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


# Frontend dev server process
_ui_process = None


def _start_ui_server() -> bool:
    """Start the frontend dev server as a subprocess."""
    global _ui_process
    if _ui_process is not None:
        return True

    # Find UI directory - look relative to this file's location
    ui_dir = Path(__file__).parent.parent.parent / "ai-companion-ui"
    if not ui_dir.exists():
        ui_dir = Path.cwd() / "ai-companion-ui"
    if not ui_dir.exists():
        print("[WARN] ai-companion-ui 目录未找到，跳过启动 UI")
        return False

    # Check if npm is available
    try:
        subprocess.run(["npm", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[WARN] npm 未安装，无法启动 UI 服务器")
        return False

    print("[OK] 正在启动 UI 服务器...")
    try:
        _ui_process = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=str(ui_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        print(f"[OK] UI 服务器已启动 (PID: {_ui_process.pid})")
        print(f"     访问地址: http://localhost:1421")
        return True
    except Exception as e:
        print(f"[ERROR] 启动 UI 服务器失败: {e}")
        _ui_process = None
        return False


def _stop_ui_server():
    """Stop the frontend dev server."""
    global _ui_process
    if _ui_process is None:
        return
    try:
        _ui_process.terminate()
        _ui_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _ui_process.kill()
    except Exception:
        pass
    _ui_process = None
    print("[OK] UI 服务器已停止")


# Admin API HTTP server
_admin_app = None
_admin_runner = None


async def _start_admin_api(bot_manager: BotManager, config: Config):
    """Start the admin API HTTP server on port 8642."""
    global _admin_app, _admin_runner

    # Import aiohttp early, before sys.path is modified
    try:
        import aiohttp
        from aiohttp import web
    except ImportError:
        print("[WARN] aiohttp 未安装，无法启动管理 API")
        return

    async def handle_bots(request):
        """GET /api/v1/admin/bots"""
        bots = bot_manager.list_bots()
        return web.json_response({"bots": bots})

    async def handle_metrics_system(request):
        """GET /api/v1/admin/metrics/system"""
        try:
            import psutil
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            return web.json_response({
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_used_mb": memory.used // (1024 * 1024),
                "disk_percent": disk.percent,
                "uptime_seconds": int(time.time() - psutil.Process().create_time()),
            })
        except ImportError:
            # psutil not installed, return placeholder data
            return web.json_response({
                "cpu_percent": 0,
                "memory_percent": 0,
                "memory_used_mb": 0,
                "disk_percent": 0,
                "uptime_seconds": 0,
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_metrics_bot(request):
        """GET /api/v1/admin/metrics/bot/:bot_id"""
        bot_id = request.match_info["bot_id"]
        bot = bot_manager.get_bot(bot_id)
        if not bot:
            return web.json_response({"error": "Bot not found"}, status=404)
        try:
            memory_status = await bot.memory.get_memory_status()
            return web.json_response({
                "bot_id": bot_id,
                "status": "running",
                "uptime_seconds": 0,
                "conversations_today": 0,
                "proactive_messages_today": 0,
                "input_tokens_today": 0,
                "output_tokens_today": 0,
                "memory_stats": {
                    "working_count": memory_status.get("working_turns", 0),
                    "working_size_kb": 0,
                    "episodic_count": memory_status.get("episodic_count", 0),
                    "episodic_size_kb": 0,
                    "semantic_count": memory_status.get("fact_count", 0),
                    "semantic_size_kb": 0,
                    "embedding_enabled": False,
                },
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_sessions(request):
        """GET /api/v1/admin/sessions"""
        return web.json_response({"sessions": []})

    async def handle_session_detail(request):
        """GET /api/v1/admin/sessions/:session_key"""
        return web.json_response({"error": "Not implemented"}, status=501)

    async def handle_session_reset(request):
        """POST /api/v1/admin/sessions/:session_key/reset"""
        return web.json_response({"error": "Not implemented"}, status=501)

    async def handle_logs(request):
        """GET /api/v1/admin/logs"""
        hermes_home = Path.home() / ".ai-companion"
        log_dir = hermes_home / "logs"
        logs = []
        if log_dir.exists():
            import re
            for log_file in sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
                try:
                    content = log_file.read_text(encoding="utf-8")
                    for line in content.splitlines()[-100:]:
                        match = re.match(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\w+)\s+\[(.*?)\]\s+(.*)", line)
                        if match:
                            timestamp, level, logger_name, msg = match.groups()
                            logs.append({
                                "id": str(uuid.uuid4())[:8],
                                "timestamp": timestamp,
                                "level": level.lower(),
                                "log_type": "system",
                                "platform": "cli",
                                "message": msg,
                            })
                except Exception:
                    pass
        logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return web.json_response({
            "logs": logs[:20],
            "total": len(logs),
            "page": 1,
            "page_size": 20,
            "total_pages": 1,
        })

    async def handle_memory_stats(request):
        """GET /api/v1/admin/memory/:bot_id/stats"""
        bot_id = request.match_info["bot_id"]
        bot = bot_manager.get_bot(bot_id)
        if not bot:
            return web.json_response({"error": "Bot not found"}, status=404)
        try:
            status = await bot.memory.get_memory_status()
            return web.json_response({
                "working_count": status.get("working_turns", 0),
                "working_size_kb": 0,
                "episodic_count": status.get("episodic_count", 0),
                "episodic_size_kb": 0,
                "semantic_count": status.get("fact_count", 0),
                "semantic_size_kb": 0,
                "embedding_enabled": False,
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_memory_working(request):
        """GET /api/v1/admin/memory/:bot_id/working"""
        bot_id = request.match_info["bot_id"]
        bot = bot_manager.get_bot(bot_id)
        if not bot:
            return web.json_response({"error": "Bot not found"}, status=404)
        try:
            working = bot.memory.working
            messages = working.get_messages(working.current_session) if hasattr(working, "get_messages") else []
            result = []
            for msg in messages[-20:]:
                result.append({
                    "id": str(uuid.uuid4())[:8],
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                    "created_at": msg.get("created_at", ""),
                })
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_memory_episodic(request):
        """GET /api/v1/admin/memory/:bot_id/episodic"""
        bot_id = request.match_info["bot_id"]
        bot = bot_manager.get_bot(bot_id)
        if not bot:
            return web.json_response({"error": "Bot not found"}, status=404)
        try:
            episodic = bot.memory.episodic
            items = episodic.get_recent_items(20) if hasattr(episodic, "get_recent_items") else []
            result = []
            for item in items:
                result.append({
                    "id": item.get("id", str(uuid.uuid4())[:8]),
                    "summary": item.get("summary", ""),
                    "content": item.get("content", ""),
                    "importance": item.get("importance", 0.5),
                    "created_at": item.get("created_at", ""),
                })
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_memory_semantic(request):
        """GET /api/v1/admin/memory/:bot_id/semantic"""
        bot_id = request.match_info["bot_id"]
        bot = bot_manager.get_bot(bot_id)
        if not bot:
            return web.json_response({"error": "Bot not found"}, status=404)
        try:
            semantic = bot.memory.semantic
            facts = semantic.get_facts() if hasattr(semantic, "get_facts") else []
            result = []
            for fact in facts:
                result.append({
                    "key": fact.get("key", ""),
                    "value": fact.get("value", ""),
                    "updated_at": fact.get("updated_at", ""),
                })
            return web.json_response({
                "facts": result,
                "attitude_score": 0.0,
                "relationship_level": "陌生",
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_config(request):
        """GET /api/v1/admin/config/:bot_id"""
        bot_id = request.match_info["bot_id"]
        bot = bot_manager.get_bot(bot_id)
        if not bot:
            return web.json_response({"error": "Bot not found"}, status=404)
        model_cfg = config.get_model_config()
        memory_cfg = config.models.get("memory", {}) if hasattr(config, "models") else {}
        return web.json_response({
            "bot_id": bot_id,
            "name": bot.name,
            "model": {
                "provider": model_cfg.get("provider", "minimax"),
                "api_key": model_cfg.get("api_key", ""),
                "base_url": model_cfg.get("base_url", "https://api.minimax.chat/v1"),
                "model": model_cfg.get("model", "MiniMax-M2.7"),
                "temperature": model_cfg.get("temperature", 0.7),
                "max_tokens": model_cfg.get("max_tokens", 2000),
            },
            "memory": {
                "hard_limit_chars": memory_cfg.get("hard_limit_chars", 100000),
                "soft_limit_chars": memory_cfg.get("soft_limit_chars", 80000),
                "max_working_turns": memory_cfg.get("max_working_turns", 20),
                "embedding": memory_cfg.get("embedding", "none"),
                "embedding_model": memory_cfg.get("embedding_model", ""),
            },
            "proactive": {
                "enabled": False,
                "idle_threshold_hours": 24,
                "min_interval_hours": 3,
                "max_daily": 5,
                "emotion_keywords": [],
            },
            "platforms": [
                {"name": "cli", "enabled": True, "config": {}},
                {"name": "feishu", "enabled": True, "config": {}},
                {"name": "webhook", "enabled": False, "config": {}},
            ],
            "session_reset": {
                "mode": "daily",
                "at_hour": 0,
                "idle_minutes": 30,
                "notify": True,
            },
        })

    async def handle_config_update(request):
        """PUT /api/v1/admin/config/:bot_id"""
        return web.json_response({"ok": True})

    async def handle_config_test(request):
        """POST /api/v1/admin/config/:bot_id/test"""
        return web.json_response({"ok": True})

    # Create aiohttp app
    _admin_app = web.Application()
    _admin_app.router.add_get("/api/v1/admin/bots", handle_bots)
    _admin_app.router.add_get("/api/v1/admin/metrics/system", handle_metrics_system)
    _admin_app.router.add_get("/api/v1/admin/metrics/bot/{bot_id}", handle_metrics_bot)
    _admin_app.router.add_get("/api/v1/admin/sessions", handle_sessions)
    _admin_app.router.add_get("/api/v1/admin/sessions/{session_key}", handle_session_detail)
    _admin_app.router.add_post("/api/v1/admin/sessions/{session_key}/reset", handle_session_reset)
    _admin_app.router.add_post("/api/v1/admin/sessions/{session_key}/suspend", handle_session_reset)
    _admin_app.router.add_get("/api/v1/admin/logs", handle_logs)
    _admin_app.router.add_get("/api/v1/admin/memory/{bot_id}/stats", handle_memory_stats)
    _admin_app.router.add_get("/api/v1/admin/memory/{bot_id}/working", handle_memory_working)
    _admin_app.router.add_get("/api/v1/admin/memory/{bot_id}/episodic", handle_memory_episodic)
    _admin_app.router.add_get("/api/v1/admin/memory/{bot_id}/semantic", handle_memory_semantic)
    _admin_app.router.add_get("/api/v1/admin/config/{bot_id}", handle_config)
    _admin_app.router.add_put("/api/v1/admin/config/{bot_id}", handle_config_update)
    _admin_app.router.add_post("/api/v1/admin/config/{bot_id}/test", handle_config_test)

    # Add CORS headers
    @web.middleware
    async def cors_middleware(request, handler):
        if request.method == "OPTIONS":
            return web.Response(status=200, headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            })
        response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response
    _admin_app.middlewares.append(cors_middleware)

    _admin_runner = web.AppRunner(_admin_app)
    await _admin_runner.setup()
    site = web.TCPSite(_admin_runner, "0.0.0.0", 8642)
    await site.start()
    print("[OK] 管理 API 已启动 (http://0.0.0.0:8642)")
    print()


async def _stop_admin_api():
    """Stop the admin API server."""
    global _admin_runner
    if _admin_runner:
        await _admin_runner.cleanup()
        _admin_runner = None
        print("[OK] 管理 API 已停止")


def get_data_dir() -> Path:
    """获取 Bot 数据根目录"""
    user_dir = Path.home() / ".ai-companion" / "data" / "bots"
    if user_dir.exists():
        return user_dir
    return Path(__file__).parent.parent.parent / "data" / "bots"


def load_feishu_config() -> dict:
    """从 ~/.ai-companion/config/config.yaml 加载飞书配置"""
    config_path = Path.home() / ".ai-companion" / "config" / "config.yaml"
    if not config_path.exists():
        return None

    try:
        with open(config_path, encoding="utf-8") as f:
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
        _stop_ui_server()
        # Admin API is stopped via KeyboardInterrupt handler below

    # 注册清理函数
    signal.signal(signal.SIGTERM, lambda s, f: cleanup())
    signal.signal(signal.SIGINT, lambda s, f: cleanup())

    print("=" * 50)
    print("AI Companion Gateway")
    print("=" * 50)
    print()

    # 检查是否启动 UI
    start_ui = os.environ.get("START_UI", "true").lower() in ("true", "1", "yes")
    if start_ui:
        _start_ui_server()
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
        print("[ERROR] API Key 未配置")
        print("")
        print("请先配置 API Key：")
        print("  1. 设置环境变量: export MINIMAX_API_KEY='your_key'")
        print("  2. 或运行: ai-companion setup")
        sys.exit(1)

    # 初始化模型
    model_cfg = config.get_model_config()
    try:
        model = MiniMaxAdapter(
            api_key=api_key,
            base_url=model_cfg["base_url"],
            model=model_cfg["model"],
        )
        print(f"[OK] 模型初始化成功: {model_cfg['model']}")
    except Exception as e:
        print(f"[ERROR] 模型初始化失败: {e}")
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
        print(f"[OK] 加载 Bot: {bot.name}")

    if not bot_manager.list_bots():
        print("[ERROR] 没有可用的 Bot")
        sys.exit(1)

    # 启动管理 API
    await _start_admin_api(bot_manager, config)

    # 加载飞书配置
    if not feishu_config:
        print("[ERROR] 飞书未配置")
        print("请运行: ai-companion setup")
        sys.exit(1)

    print("[OK] 飞书配置已加载")

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
    print(f"[OK] 路由模式: {router.mode}")

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
        print("[ERROR] 飞书连接失败")
        print(f"   错误: {adapter.fatal_error_message or '未知错误'}")
        sys.exit(1)

    print(f"[OK] 飞书连接成功 [{feishu_config.get('connection_mode', 'websocket')}]")
    print()
    print("=" * 50)
    if _ui_process:
        print("网关 + UI 已启动")
        print(f"  管理后台: http://localhost:1421")
        print("  按 Ctrl+C 退出")
    else:
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
        await _stop_admin_api()
        cleanup()
        print("[OK] 网关已停止")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    asyncio.run(run_gateway())
