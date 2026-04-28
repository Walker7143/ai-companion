"""
Gateway 命令入口 - 启动网关服务连接飞书
"""

# Import aiohttp early to avoid platform module shadowing issue
import aiohttp

import asyncio
import json
import logging
import logging.handlers
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
from ai_companion.model.factory import ModelFactory
from ai_companion.bot.manager import BotManager
from ai_companion.bot.instance import BotInstance
from ai_companion.gateway.config import Platform, PlatformConfig
from ai_companion.gateway.platforms.feishu import FeishuAdapter
from ai_companion.gateway.router import PlatformRouter
from ai_companion.gateway.control import GATEWAY_PID_FILE, GATEWAY_LOG_FILE, save_gateway_pid, remove_gateway_pid

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

    # Check if npm is available (use shutil.which for reliable cross-platform detection)
    import shutil
    npm_path = shutil.which("npm")
    if not npm_path:
        print("[WARN] npm 未安装，无法启动 UI 服务器")
        return False

    # Check if node_modules exists, try to install if not
    node_modules = ui_dir / "node_modules"
    if not node_modules.exists():
        print("[INFO] 正在安装前端依赖（首次运行需等待）...")
        try:
            result = subprocess.run(
                [npm_path, "install"],
                cwd=str(ui_dir),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                print(f"[ERROR] npm install 失败，请手动执行: cd {ui_dir} && npm install")
                print(f"       错误: {result.stderr[:200]}")
                return False
            print("[OK] 前端依赖安装完成")
        except subprocess.TimeoutExpired:
            print("[ERROR] npm install 超时，请手动执行: cd %s && npm install" % ui_dir)
            return False
        except Exception as e:
            print(f"[ERROR] npm install 失败: {e}")
            print(f"       请手动执行: cd {ui_dir} && npm install")
            return False

    print("[OK] 正在启动 UI 服务器...")
    try:
        # Open gateway log file for UI server output
        GATEWAY_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(GATEWAY_LOG_FILE, "a", encoding="utf-8")
        _ui_process = subprocess.Popen(
            [npm_path, "run", "dev"],
            cwd=str(ui_dir),
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        # Give it a moment to fail immediately (e.g. port in use)
        import time
        time.sleep(3)
        if _ui_process.poll() is not None:
            # Process already exited - capture output from log file tail
            log_file.close()
            try:
                with open(GATEWAY_LOG_FILE, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                # Find recent UI-related log entries
                ui_lines = [l for l in lines[-50:] if "vite" in l.lower() or "ui" in l.lower() or "1421" in l]
                output = "".join(ui_lines[-10:]) if ui_lines else ""
            except Exception:
                output = ""
            print(f"[ERROR] UI 服务器启动后立即退出")
            print(f"       请手动启动排查: cd {ui_dir} && npm run dev")
            if output:
                print(f"       最近日志: {output[:300]}")
            _ui_process = None
            return False
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


def _get_data_dir() -> Path:
    """获取 Bot 数据根目录。

    优先返回有实际数据的目录：
    1. ~/.ai-companion/data/bots（如果该目录下有 bot 目录）
    2. 项目 data/bots 目录（兼容旧数据）
    """
    user_dir = Path.home() / ".ai-companion" / "data" / "bots"
    project_dir = Path(__file__).parent.parent.parent / "data" / "bots"
    # 如果用户目录存在且有内容，使用用户目录
    if user_dir.exists() and any(user_dir.iterdir()):
        return user_dir
    # 否则用项目目录
    return project_dir


def _discover_bots() -> list[dict]:
    """扫描所有 data/bots/ 目录，自动发现所有 Bot（用户目录 + 项目目录）"""
    user_dir = Path.home() / ".ai-companion" / "data" / "bots"
    project_dir = Path(__file__).parent.parent.parent / "data" / "bots"
    seen = set()
    bots = []
    for base_dir in (user_dir, project_dir):
        if not base_dir.exists():
            continue
        for bot_dir in base_dir.iterdir():
            if not bot_dir.is_dir() or bot_dir.name in seen:
                continue
            persona_file = bot_dir / "persona" / "profile.json"
            name = bot_dir.name
            description = ""
            if persona_file.exists():
                try:
                    import json as _json
                    profile = _json.loads(persona_file.read_text(encoding="utf-8"))
                    name = profile.get("name", name)
                    description = profile.get("description", description)
                except Exception:
                    pass
            seen.add(bot_dir.name)
            bots.append({"id": bot_dir.name, "name": name, "description": description})
    return bots


def _get_memory_db_path(bot_id: str, db_name: str) -> Path | None:
    """获取 Bot 内存数据库路径，同时检查用户目录和项目目录"""
    user_dir = Path.home() / ".ai-companion" / "data" / "bots"
    # gateway/cmd.py -> parent=ai_companion/gateway -> parent.parent=ai_companion -> parent.parent.parent=project_root
    project_dir = Path(__file__).parent.parent.parent / "data" / "bots"
    # 优先返回有实际数据的目录（检查 db 文件是否存在）
    for base in (project_dir, user_dir):
        db_path = base / bot_id / "memory" / db_name
        if db_path.exists():
            return db_path
    return None


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
        bots = _discover_bots()
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
            # psutil not installed, try os module for basic info
            try:
                import os
                loadavg = os.getloadavg()
                # loadavg is (1min, 5min, 15min) - convert to percent (approximate)
                # multiply by 100/n CPUs for percentage
                cpu_load = min(loadavg[0] * 30, 100)  # rough approximation
                # Try to get memory info from sysconf
                import resource
                rusage = resource.getrusage(resource.RUSAGE_SELF)
                # This doesn't give total memory, so return estimated
                return web.json_response({
                    "cpu_percent": cpu_load,
                    "memory_percent": 0,  # can't determine without psutil
                    "memory_used_mb": rusage.ru_maxrss // 1024,  # macOS maxrss is in bytes
                    "disk_percent": 0,
                    "uptime_seconds": 0,
                })
            except Exception:
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
        db_path = _get_memory_db_path(bot_id, "working.db")
        episodic_path = _get_memory_db_path(bot_id, "episodic.db")
        semantic_path = _get_memory_db_path(bot_id, "semantic.db")

        def _table_count(path, table):
            if not path:
                return 0
            try:
                import sqlite3
                conn = sqlite3.connect(str(path))
                c = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                conn.close()
                return c
            except Exception:
                return 0

        def _sessions_today(path):
            """Count distinct sessions created today"""
            if not path:
                return 0
            try:
                import sqlite3
                from datetime import datetime
                today = datetime.now().strftime("%Y%m%d")
                conn = sqlite3.connect(str(path))
                # session_id format is like "20260426_211009"
                c = conn.execute(
                    "SELECT COUNT(DISTINCT session_id) FROM messages WHERE session_id LIKE ?",
                    (f"{today}%",)
                ).fetchone()[0]
                conn.close()
                return c
            except Exception:
                return 0

        def _token_estimate(path):
            """Calculate tokens from actual character count (~2 chars ≈ 1 token)"""
            if not path:
                return 0, 0
            try:
                import sqlite3
                conn = sqlite3.connect(str(path))
                user_chars = conn.execute("SELECT COALESCE(SUM(LENGTH(content)), 0) FROM messages WHERE role = 'user'").fetchone()[0]
                assistant_chars = conn.execute("SELECT COALESCE(SUM(LENGTH(content)), 0) FROM messages WHERE role = 'assistant'").fetchone()[0]
                conn.close()
                return user_chars // 2, assistant_chars // 2
            except Exception:
                return 0, 0

        # 实时状态：BotManager 中存在则 running
        bot = bot_manager.get_bot(bot_id)
        status = "running" if bot else "stopped"
        input_tokens, output_tokens = _token_estimate(db_path)

        return web.json_response({
            "bot_id": bot_id,
            "status": status,
            "uptime_seconds": 0,
            "conversations_today": _sessions_today(db_path),
            "proactive_messages_today": 0,
            "input_tokens_today": input_tokens,
            "output_tokens_today": output_tokens,
            "memory_stats": {
                "working_count": _table_count(db_path, "messages"),
                "working_size_kb": 0,
                "episodic_count": _table_count(episodic_path, "episodic_memory"),
                "episodic_size_kb": 0,
                "semantic_count": _table_count(semantic_path, "user_facts"),
                "semantic_size_kb": 0,
                "embedding_enabled": False,
            },
        })

    async def handle_sessions(request):
        """GET /api/v1/admin/sessions"""
        import sqlite3
        # 扫描所有 Bot 的 working.db，获取会话列表
        all_sessions = []
        bots = _discover_bots()
        for bot in bots:
            bot_id = bot["id"]
            db_path = _get_memory_db_path(bot_id, "working.db")
            if not db_path:
                continue
            try:
                conn = sqlite3.connect(str(db_path))
                rows = conn.execute("""
                    SELECT session_id,
                           COUNT(*) as msg_count,
                           MAX(id) as last_msg_id,
                           MAX(created_at) as last_at,
                           COALESCE(SUM(LENGTH(content)), 0) as total_chars
                    FROM messages
                    GROUP BY session_id
                    ORDER BY last_msg_id DESC
                    LIMIT 100
                """).fetchall()
                conn.close()
                for r in rows:
                    all_sessions.append({
                        "session_key": f"{bot_id}:{r[0]}",
                        "session_id": r[0],
                        "platform": "cli",
                        "user": "用户",
                        "created_at": r[3],
                        "updated_at": r[3],
                        "status": "active",
                        "reset_reason": None,
                        "total_tokens": r[4] // 2,  # ~2 chars ≈ 1 token
                    })
            except Exception:
                pass
        # 按最后消息时间倒序
        all_sessions.sort(key=lambda x: x.get("last_at", ""), reverse=True)
        return web.json_response({"sessions": all_sessions})

    async def handle_session_detail(request):
        """GET /api/v1/admin/sessions/:session_key"""
        import sqlite3
        session_key = request.match_info["session_key"]
        # session_key format: "bot_id:session_id"
        if ":" in session_key:
            bot_id, session_id = session_key.split(":", 1)
        else:
            return web.json_response({"error": "Invalid session key"}, status=400)

        db_path = _get_memory_db_path(bot_id, "working.db")
        if not db_path:
            return web.json_response({"error": "Session not found"}, status=404)

        try:
            conn = sqlite3.connect(str(db_path))
            rows = conn.execute("""
                SELECT role, content, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY id ASC
            """, (session_id,)).fetchall()
            # Calculate token counts from character lengths
            user_chars = sum(len(r[1]) for r in rows if r[0] == "user")
            assistant_chars = sum(len(r[1]) for r in rows if r[0] == "assistant")
            input_tokens = user_chars // 2
            output_tokens = assistant_chars // 2
            total_chars = user_chars + assistant_chars
            conn.close()
            messages = [{"role": r[0], "content": r[1], "created_at": r[2]} for r in rows]
            return web.json_response({
                "info": {
                    "session_key": session_key,
                    "session_id": session_id,
                    "platform": "cli",
                    "user": "用户",
                    "created_at": rows[0][2] if rows else "",
                    "updated_at": rows[-1][2] if rows else "",
                    "status": "active",
                    "reset_reason": None,
                    "total_tokens": total_chars // 2,
                },
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_write_tokens": 0,
                "cache_read_tokens": 0,
                "estimated_cost_usd": 0.0,
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_session_reset(request):
        """POST /api/v1/admin/sessions/:session_key/reset"""
        # 清空该会话的工作记忆消息
        import sqlite3
        session_key = request.match_info["session_key"]
        if ":" in session_key:
            bot_id, session_id = session_key.split(":", 1)
        else:
            return web.json_response({"error": "Invalid session key"}, status=400)

        db_path = _get_memory_db_path(bot_id, "working.db")
        if not db_path:
            return web.json_response({"error": "Session not found"}, status=404)

        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM summaries WHERE session_id = ?", (session_id,))
            conn.commit()
            conn.close()
            return web.json_response({"ok": True})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_logs(request):
        """GET /api/v1/admin/logs"""
        hermes_home = Path.home() / ".ai-companion"
        log_dir = hermes_home / "logs"
        logs = []
        if log_dir.exists():
            import re
            # Pattern: 2026-04-26 22:14:32,764 [INFO] ai_companion.proactive: [ProactiveScheduler] message
            # or: 2026-04-26 22:14:32,764 [INFO] aiohttp.access: message
            for log_file in sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
                try:
                    content = log_file.read_text(encoding="utf-8")
                    for line in content.splitlines()[-200:]:
                        # Match timestamp and rest: 2026-04-26 22:14:32,764 [LEVEL] [logger] message
                        # or: 2026-04-26 22:14:32,764 [LEVEL] logger: message
                        m = re.match(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+\[(\w+)\]\s+(?:\[(.*?)\]\s+)?(.+)", line)
                        if m:
                            timestamp, level, logger_name, msg = m.groups()
                            logs.append({
                                "id": str(uuid.uuid4())[:8],
                                "timestamp": timestamp.split(",")[0],  # remove milliseconds
                                "level": level.lower(),
                                "log_type": "system",
                                "platform": log_file.stem,
                                "message": f"[{logger_name}] {msg}" if logger_name else msg,
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

    async def handle_logs_stream(request):
        """GET /api/v1/admin/logs/stream - WebSocket log streaming"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        hermes_home = Path.home() / ".ai-companion"
        log_file = hermes_home / "logs" / "gateway.log"
        last_size = 0
        if log_file.exists():
            last_size = log_file.stat().st_size

        import re
        async def send_log_lines():
            if log_file.exists():
                content = log_file.read_text(encoding="utf-8")
                for line in content.splitlines()[-50:]:
                    m = re.match(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+\[(\w+)\]\s+(?:\[(.*?)\]\s+)?(.+)", line)
                    if m:
                        timestamp, level, logger_name, msg = m.groups()
                        await ws.send_json({
                            "id": str(uuid.uuid4())[:8],
                            "timestamp": timestamp.split(",")[0],
                            "level": level.lower(),
                            "log_type": "system",
                            "platform": "gateway",
                            "message": f"[{logger_name}] {msg}" if logger_name else msg,
                        })

        # Send initial batch
        await send_log_lines()

        # Stream new lines
        try:
            while True:
                await asyncio.sleep(1)
                if log_file.exists():
                    current_size = log_file.stat().st_size
                    if current_size > last_size:
                        content = log_file.read_text(encoding="utf-8")
                        new_content = content[last_size:]
                        for line in new_content.splitlines():
                            if line.strip():
                                m = re.match(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+\[(\w+)\]\s+(?:\[(.*?)\]\s+)?(.+)", line)
                                if m:
                                    timestamp, level, logger_name, msg = m.groups()
                                    await ws.send_json({
                                        "id": str(uuid.uuid4())[:8],
                                        "timestamp": timestamp.split(",")[0],
                                        "level": level.lower(),
                                        "log_type": "system",
                                        "platform": "gateway",
                                        "message": f"[{logger_name}] {msg}" if logger_name else msg,
                                    })
                        last_size = current_size
        except Exception:
            pass
        finally:
            await ws.close()

    async def handle_memory_stats(request):
        """GET /api/v1/admin/memory/:bot_id/stats"""
        bot_id = request.match_info["bot_id"]
        db_path = _get_memory_db_path(bot_id, "working.db")
        episodic_path = _get_memory_db_path(bot_id, "episodic.db")
        semantic_path = _get_memory_db_path(bot_id, "semantic.db")

        def _table_count(path, table):
            if not path:
                return 0
            try:
                import sqlite3
                conn = sqlite3.connect(str(path))
                c = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                conn.close()
                return c
            except Exception:
                return 0

        return web.json_response({
            "working_count": _table_count(db_path, "messages"),
            "working_size_kb": 0,
            "episodic_count": _table_count(episodic_path, "episodic_memory"),
            "episodic_size_kb": 0,
            "semantic_count": _table_count(semantic_path, "user_facts"),
            "semantic_size_kb": 0,
            "embedding_enabled": False,
        })

    async def handle_memory_working(request):
        """GET /api/v1/admin/memory/:bot_id/working"""
        bot_id = request.match_info["bot_id"]
        query_session = request.query.get("session_id")
        db_path = _get_memory_db_path(bot_id, "working.db")
        if not db_path:
            return web.json_response([])

        import sqlite3
        conn = sqlite3.connect(str(db_path))

        if query_session:
            rows = conn.execute("""
                SELECT role, content, created_at
                FROM messages
                WHERE session_id = ? AND compressed = 0
                ORDER BY id DESC
                LIMIT 50
            """, (query_session,)).fetchall()
            conn.close()
            messages = [{"role": r[0], "content": r[1], "created_at": r[2]} for r in reversed(rows)]
            return web.json_response(messages)

        # 无 session_id 时返回最近一次会话的消息
        row = conn.execute("""
            SELECT session_id FROM messages
            WHERE compressed = 0
            ORDER BY id DESC LIMIT 1
        """).fetchone()
        if not row:
            conn.close()
            return web.json_response([])
        session_id = row[0]
        rows = conn.execute("""
            SELECT role, content, created_at
            FROM messages
            WHERE session_id = ? AND compressed = 0
            ORDER BY id ASC
        """, (session_id,)).fetchall()
        conn.close()
        messages = [{"role": r[0], "content": r[1], "created_at": r[2]} for r in rows]
        return web.json_response(messages)

    async def handle_memory_episodic(request):
        """GET /api/v1/admin/memory/:bot_id/episodic"""
        bot_id = request.match_info["bot_id"]
        db_path = _get_memory_db_path(bot_id, "episodic.db")
        if not db_path:
            return web.json_response([])
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            rows = conn.execute("""
                SELECT id, session_id, summary, content, importance, created_at
                FROM episodic_memory
                ORDER BY id DESC
                LIMIT 50
            """).fetchall()
            conn.close()
            result = [{"id": str(r[0]), "session_id": r[1], "summary": r[2],
                       "content": r[3], "importance": r[4], "created_at": r[5]} for r in rows]
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_memory_semantic(request):
        """GET /api/v1/admin/memory/:bot_id/semantic"""
        bot_id = request.match_info["bot_id"]
        db_path = _get_memory_db_path(bot_id, "semantic.db")
        if not db_path:
            return web.json_response({"facts": [], "attitude_score": 0.0, "relationship_level": "陌生"})
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            rows = conn.execute("""
                SELECT key, value, updated_at FROM user_facts ORDER BY updated_at DESC
            """).fetchall()
            conn.close()
            facts = [{"key": r[0], "value": r[1], "updated_at": r[2]} for r in rows]
            # 尝试获取 attitude_score
            attitude_score = 0.0
            relationship_level = "陌生"
            for f in facts:
                if f["key"] == "attitude_score":
                    try:
                        attitude_score = float(f["value"])
                    except Exception:
                        pass
                elif f["key"] == "relationship_level":
                    relationship_level = f["value"]
            return web.json_response({
                "facts": facts,
                "attitude_score": attitude_score,
                "relationship_level": relationship_level,
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_memory_delete(request):
        """DELETE /api/v1/admin/memory/:bot_id/:memory_type/:memory_id"""
        bot_id = request.match_info["bot_id"]
        memory_type = request.match_info["memory_type"]
        memory_id = request.match_info["memory_id"]

        type_to_db = {
            "working": "working.db",
            "episodic": "episodic.db",
            "semantic": "semantic.db",
        }
        db_name = type_to_db.get(memory_type)
        if not db_name:
            return web.json_response({"error": f"Unknown memory type: {memory_type}"}, status=400)

        db_path = _get_memory_db_path(bot_id, db_name)
        if not db_path:
            return web.json_response({"error": "Memory db not found"}, status=404)

        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            if memory_type == "working":
                cur = conn.execute("DELETE FROM messages WHERE id = ?", (memory_id,))
            elif memory_type == "episodic":
                cur = conn.execute("DELETE FROM episodic_memory WHERE id = ?", (memory_id,))
            else:  # semantic
                cur = conn.execute("DELETE FROM user_facts WHERE key = ?", (memory_id,))
            conn.commit()
            deleted = cur.rowcount
            conn.close()
            return web.json_response({"ok": True, "deleted": deleted})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_memory_clear_all(request):
        """DELETE /api/v1/admin/memory/:bot_id/all"""
        bot_id = request.match_info["bot_id"]
        deleted = {
            "working_messages": 0,
            "working_summaries": 0,
            "episodic": 0,
            "semantic": 0,
        }

        def _delete_rows(path: Path | None, sql: str, key: str):
            if not path:
                return
            try:
                import sqlite3
                conn = sqlite3.connect(str(path))
                cur = conn.execute(sql)
                conn.commit()
                deleted[key] += max(cur.rowcount, 0)
                conn.close()
            except Exception:
                pass

        working_db = _get_memory_db_path(bot_id, "working.db")
        episodic_db = _get_memory_db_path(bot_id, "episodic.db")
        semantic_db = _get_memory_db_path(bot_id, "semantic.db")

        _delete_rows(working_db, "DELETE FROM messages", "working_messages")
        _delete_rows(working_db, "DELETE FROM summaries", "working_summaries")
        _delete_rows(episodic_db, "DELETE FROM episodic_memory", "episodic")
        _delete_rows(semantic_db, "DELETE FROM user_facts", "semantic")

        return web.json_response({"ok": True, "deleted": deleted})

    async def handle_config(request):
        """GET /api/v1/admin/config/:bot_id"""
        bot_id = request.match_info["bot_id"]
        # 优先从 BotManager 获取
        bot = bot_manager.get_bot(bot_id)
        # 如果 BotManager 中没有，尝试从目录发现
        if not bot:
            discovered = _discover_bots()
            found = next((b for b in discovered if b["id"] == bot_id), None)
            if not found:
                return web.json_response({"error": "Bot not found"}, status=404)
            bot_name = found["name"]
        else:
            bot_name = bot.name
        model_cfg = config.get_model_config()
        memory_cfg = config.models.get("memory", {}) if hasattr(config, "models") else {}

        # 从运行中的 bot 获取 proactive 配置
        proactive_cfg = {
            "enabled": False,
            "idle_threshold_hours": 24,
            "min_interval_hours": 3,
            "max_daily": 5,
            "emotion_keywords": [],
        }
        if bot and hasattr(bot, "proactive_config"):
            pc = bot.proactive_config
            proactive_cfg = {
                "enabled": pc.enabled,
                "idle_threshold_hours": pc.idle_threshold_hours,
                "min_interval_hours": pc.min_interval_hours,
                "max_daily": pc.max_daily,
                "emotion_keywords": pc.emotion_keywords,
            }

        return web.json_response({
            "bot_id": bot_id,
            "name": bot_name,
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
            "proactive": proactive_cfg,
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
        bot_id = request.match_info["bot_id"]
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        bot = bot_manager.get_bot(bot_id)

        # 1. 保存模型配置到 models.yaml（合并更新，保留未修改的字段）
        if "model" in body:
            model_data = body["model"]
            models_cfg_path = Path.home() / ".ai-companion" / "config" / "models.yaml"
            try:
                models_data = {}
                if models_cfg_path.exists():
                    with open(models_cfg_path, encoding="utf-8") as f:
                        models_data = yaml.safe_load(f) or {}
                provider = model_data.get("provider", "minimax")
                # 合并 provider 配置（保留未修改的字段）
                if provider not in models_data:
                    models_data[provider] = {}
                existing_provider = models_data.get(provider, {})
                models_data[provider] = {
                    "api_key": model_data.get("api_key", existing_provider.get("api_key", "")),
                    "base_url": model_data.get("base_url", existing_provider.get("base_url", "")),
                    "model": model_data.get("model", existing_provider.get("model", "")),
                }
                # 全局默认参数
                if "model" not in models_data:
                    models_data["model"] = {}
                existing_global = models_data.get("model", {})
                models_data["model"] = {
                    "provider": provider,
                    "temperature": model_data.get("temperature", existing_global.get("temperature", 0.7)),
                    "max_tokens": model_data.get("max_tokens", existing_global.get("max_tokens", 2000)),
                }
                models_cfg_path.parent.mkdir(parents=True, exist_ok=True)
                with open(models_cfg_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(models_data, f, allow_unicode=True, default_flow_style=False)
            except Exception as e:
                return web.json_response({"error": f"Failed to save model config: {e}"}, status=500)

        # 2. 保存 proactive 配置并热更新
        if "proactive" in body and bot and hasattr(bot, "proactive_config"):
            proactive_data = body["proactive"]
            pc = bot.proactive_config
            try:
                if "enabled" in proactive_data:
                    pc._config["enabled"] = proactive_data["enabled"]
                if "idle_threshold_hours" in proactive_data:
                    pc._config.setdefault("scheduler", {})["idle_threshold_hours"] = proactive_data["idle_threshold_hours"]
                if "min_interval_hours" in proactive_data:
                    pc._config.setdefault("scheduler", {})["min_interval_hours"] = proactive_data["min_interval_hours"]
                if "max_daily" in proactive_data:
                    pc._config.setdefault("scheduler", {})["max_daily"] = proactive_data["max_daily"]
                if "emotion_keywords" in proactive_data:
                    pc._config.setdefault("triggers", {}).setdefault("emotion_trigger", {})["keywords"] = proactive_data["emotion_keywords"]
                pc.save()

                # 重启调度器以应用新配置
                if bot.proactive_scheduler:
                    await bot.proactive_scheduler.stop()
                    bot.proactive_scheduler = None
                    from ai_companion.proactive.scheduler import ProactiveScheduler
                    bot.proactive_scheduler = ProactiveScheduler(bot.proactive_engine)
                    bot.proactive_scheduler.set_dependencies(bot.model, bot.memory)
                    await bot.proactive_scheduler.start()
            except Exception as e:
                return web.json_response({"error": f"Failed to save proactive config: {e}"}, status=500)

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
    _admin_app.router.add_get("/api/v1/admin/logs/stream", handle_logs_stream)
    _admin_app.router.add_get("/api/v1/admin/memory/{bot_id}/stats", handle_memory_stats)
    _admin_app.router.add_get("/api/v1/admin/memory/{bot_id}/working", handle_memory_working)
    _admin_app.router.add_get("/api/v1/admin/memory/{bot_id}/episodic", handle_memory_episodic)
    _admin_app.router.add_get("/api/v1/admin/memory/{bot_id}/semantic", handle_memory_semantic)
    _admin_app.router.add_delete("/api/v1/admin/memory/{bot_id}/all", handle_memory_clear_all)
    _admin_app.router.add_delete("/api/v1/admin/memory/{bot_id}/{memory_type}/{memory_id}", handle_memory_delete)
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


def _extract_feishu_target_id_from_bot(bot) -> str:
    """从 Bot proactive 配置提取可用于主动发送的飞书目标（群聊/会话 ID）。"""
    try:
        cfg = bot.proactive_config.to_dict() if hasattr(bot.proactive_config, "to_dict") else {}
    except Exception:
        cfg = {}

    # 兼容几种可能结构
    home = cfg.get("home_channel")
    if isinstance(home, dict):
        chat_id = home.get("chat_id") or home.get("group_id")
        if chat_id:
            return str(chat_id)
    elif home:
        return str(home)

    platform_cfg = cfg.get("platform", {}) if isinstance(cfg, dict) else {}
    if isinstance(platform_cfg, dict):
        for key in ("home_channel", "chat_id", "group_id"):
            v = platform_cfg.get(key)
            if v:
                return str(v)
    return ""


def _should_start_gateway_schedulers_for_bot(bot, feishu_config: dict) -> tuple[bool, str]:
    """网关启动时判断是否应立即启动某 Bot 的 proactive/life 轮询。"""
    pc = getattr(bot, "proactive_config", None)
    if not pc:
        return False, "missing_proactive_config"

    # 仅 active + 非 silent 才考虑
    if not pc.is_active:
        return False, f"inactive(mode={pc.mode},enabled={pc.enabled})"

    # 发送通道必须是 feishu，cli/webhook 跳过
    platform_type = (pc.platform_type or "cli").lower()
    if platform_type != "feishu":
        return False, f"platform={platform_type}"

    # 需要至少有飞书机器人配置（app_id）或 Bot 级别目标群聊/chat_id
    has_feishu_robot = bool(feishu_config and feishu_config.get("app_id"))
    target_id = _extract_feishu_target_id_from_bot(bot)
    has_target = bool(target_id)
    if not (has_feishu_robot or has_target):
        return False, "feishu_target_missing"

    return True, f"platform=feishu has_robot={has_feishu_robot} has_target={has_target}"


async def run_gateway(daemon: bool = True):
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

    if daemon:
        print("[OK] 守护进程模式，关闭终端后网关将继续运行")
        print()

    # 检查是否启动 UI
    start_ui = os.environ.get("START_UI", "true").lower() in ("true", "1", "yes")
    if start_ui:
        _start_ui_server()
        print()

    # 加载配置
    config = Config()
    feishu_config = load_feishu_config()

    model_cfg = config.get_model_config()
    provider = model_cfg.get("provider", config.default_provider)
    env_key_map = {
        "minimax": "MINIMAX_API_KEY",
        "openai": "OPENAI_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
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

    # 加载 Bot
    bot_manager = BotManager()
    memory_config = config.models.get("memory", {})
    data_dir = get_data_dir()

    for bot_config in config.get_enabled_bots():
        bot_config = {**bot_config, "data_dir": str(data_dir)}
        bot = BotInstance(bot_config, model=model, memory_config=memory_config)

        # 设置主动消息发送平台（需要飞书适配器在 init 之前设置）
        if feishu_config:
            # 先创建飞书适配器（用于主动消息发送）
            platform_config = PlatformConfig(
                enabled=True,
                extra=feishu_config
            )
            feishu_adapter = FeishuAdapter(platform_config)
            bot.set_proactive_platform(feishu_adapter=feishu_adapter)

        # 网关默认先初始化，不全量拉起轮询；按规则选择性启动
        await bot.init(start_schedulers=False)
        should_start, reason = _should_start_gateway_schedulers_for_bot(bot, feishu_config)
        if should_start:
            await bot.ensure_schedulers_started()
            print(f"[OK] 启动轮询: {bot.name} ({bot.id}) [{reason}]")
        else:
            print(f"[SKIP] 跳过轮询: {bot.name} ({bot.id}) [{reason}]")
        bot_manager.register(bot)
        print(f"[OK] 加载 Bot: {bot.name}")

    if not bot_manager.list_bots():
        print("[ERROR] 没有可用的 Bot")
        sys.exit(1)

    # 启动管理 API
    await _start_admin_api(bot_manager, config)

    # 飞书未配置时，只启动管理 API
    if feishu_config:
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
            """process feishu message, route to BotInstance"""
            # 根据路由模式获取 bot_id
            bot_id = router.route(event)
            bot = bot_manager.get_bot(bot_id)

            if not bot:
                # Fallback: 使用第一个可用的 bot
                bot = next(iter(bot_manager._bots.values()), None)

            if not bot:
                return "没有可用的 Bot"

            # 记录用户所在的 chat_id，作为主动消息的发送目标
            if event.source and hasattr(event.source, 'chat_id'):
                bot._feishu_chat_id = event.source.chat_id

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
    else:
        print("[WARN] 飞书未配置，跳过网关连接")
        print("       管理 API 已启动，可访问 http://localhost:8642")
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
        _stop_ui_server()
        await adapter.disconnect()
        await _stop_admin_api()
        cleanup()
        print("[OK] 网关已停止")


class AiohttpAccessFilter(logging.Filter):
    """过滤 aiohttp.access 的 INFO 日志，只打印 warn 和 error"""

    def filter(self, record):
        if record.name == "aiohttp.access" and record.levelno == logging.INFO:
            return False
        return True


if __name__ == "__main__":
    def setup_logging():
        """配置日志，同时输出到 stdout 和文件"""
        import pathlib
        log_dir = pathlib.Path.home() / ".ai-companion" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "gateway.log"

        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.addFilter(AiohttpAccessFilter())

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)

        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[console_handler, file_handler],
        )

    setup_logging()
    asyncio.run(run_gateway())
