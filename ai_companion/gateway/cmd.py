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
from ai_companion.gateway.admin_services import (
    ConfigAdminService,
    admin_host,
    admin_port,
    allowed_cors_origins,
    list_sessions as admin_list_sessions,
    working_messages,
)
from ai_companion.gateway.path_resolver import (
    discover_bots as resolve_discover_bots,
    get_data_dir as resolve_data_dir,
    get_memory_db_path as resolve_memory_db_path,
)
from ai_companion.ui_server import (
    UIStartResult,
    ensure_ui_server,
    release_ui_server,
    should_start_ui,
)

logger = logging.getLogger(__name__)


# Frontend dev server ownership for this gateway process
_ui_server_result: UIStartResult | None = None


def _start_ui_server() -> bool:
    """Ensure the shared frontend dev server is running."""
    global _ui_server_result
    if _ui_server_result is not None and _ui_server_result.ok:
        return True

    _ui_server_result = ensure_ui_server(owner_name="gateway")
    if not _ui_server_result.ok:
        print(f"[WARN] UI 服务器未启动: {_ui_server_result.message}")
        return False

    if _ui_server_result.started:
        print(f"[OK] UI 服务器已启动 (PID: {_ui_server_result.pid})")
    elif _ui_server_result.reused:
        print("[OK] UI 服务器已在运行，复用现有实例")
    else:
        print("[OK] UI 服务器已可用")
    print(f"     访问地址: {_ui_server_result.url}")
    return True


def _stop_ui_server():
    """Release this process' ownership of the shared frontend dev server."""
    global _ui_server_result
    release_ui_server(_ui_server_result)
    _ui_server_result = None


# Admin API HTTP server
_admin_app = None
_admin_runner = None


def _admin_api_is_available(host: str, port: int) -> bool:
    """Return True when an existing admin API is already serving this port."""
    import urllib.error
    import urllib.request

    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{probe_host}:{port}/api/v1/admin/bots"
    try:
        with urllib.request.urlopen(url, timeout=0.5) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
        return response.status == 200 and isinstance(payload, dict) and "bots" in payload
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return False


def _get_data_dir() -> Path:
    """获取 Bot 数据根目录。"""
    return resolve_data_dir()


def _discover_bots() -> list[dict]:
    """扫描所有 data/bots/ 目录，自动发现所有 Bot（用户目录 + 项目目录）"""
    return resolve_discover_bots()


def _get_memory_db_path(bot_id: str, db_name: str) -> Path | None:
    """获取 Bot 内存数据库路径，同时检查用户目录和项目目录"""
    return resolve_memory_db_path(bot_id, db_name)


def _get_memory_file_path(bot_id: str, filename: str) -> Path | None:
    """获取 Bot 记忆文件路径。"""
    existing = resolve_memory_db_path(bot_id, filename)
    if existing:
        return existing
    return _get_data_dir() / bot_id / "memory" / filename


def _load_user_understanding(bot_id: str) -> tuple[dict, str | None]:
    path = _get_memory_file_path(bot_id, "user_understanding.json")
    if not path or not path.exists():
        return {}, str(path) if path else None
    try:
        return json.loads(path.read_text(encoding="utf-8")), str(path)
    except Exception:
        return {}, str(path)


def _write_user_understanding(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _delete_user_understanding_auto_fact(bot_id: str, key: str):
    path = _get_memory_file_path(bot_id, "user_understanding.json")
    if not path or not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        auto = data.get("auto") if isinstance(data.get("auto"), dict) else {}
        auto_facts = auto.get("facts") if isinstance(auto.get("facts"), dict) else {}
        if key in auto_facts:
            del auto_facts[key]
            changed = True
        legacy_auto_facts = data.get("auto_facts")
        if isinstance(legacy_auto_facts, dict) and key in legacy_auto_facts:
            del legacy_auto_facts[key]
            changed = True
        if changed:
            auto["last_refresh_at"] = datetime.now().isoformat()
            data["auto"] = auto
            data["updated_at"] = datetime.now().isoformat()
            _write_user_understanding(path, data)
    except Exception:
        pass


def _understanding_auto_count(data: dict) -> int:
    if not isinstance(data, dict):
        return 0
    auto = data.get("auto") if isinstance(data.get("auto"), dict) else {}
    facts = auto.get("facts") if isinstance(auto.get("facts"), dict) else {}
    if facts:
        return len(facts)
    legacy = data.get("auto_facts")
    return len(legacy) if isinstance(legacy, dict) else 0


def _clear_user_understanding_auto(data: dict) -> tuple[dict, int]:
    if not isinstance(data, dict):
        return data, 0
    count = _understanding_auto_count(data)
    if isinstance(data.get("auto"), dict):
        auto = data["auto"]
        auto["facts"] = {}
        for key in ("preferences", "communication_style", "boundaries", "important_people", "current_context", "open_threads"):
            auto[key] = []
        auto["summary"] = ""
        auto["last_refresh_at"] = datetime.now().isoformat()
    data["auto_facts"] = {}
    data["updated_at"] = datetime.now().isoformat()
    return data, count


async def _start_admin_api(bot_manager: BotManager, config: Config):
    """Start the admin API HTTP server on port 8642."""
    global _admin_app, _admin_runner

    # Import aiohttp early, before sys.path is modified
    try:
        import aiohttp
        from aiohttp import web
    except ImportError:
        print("[WARN] aiohttp 未安装，无法启动管理 API")
        return False

    host = admin_host(config.config)
    port = admin_port(config.config)
    if _admin_runner is not None:
        print(f"[OK] 管理 API 已在运行，复用现有实例 (http://{host}:{port})")
        print()
        return False
    if _admin_api_is_available(host, port):
        print(f"[OK] 管理 API 已在运行，复用现有实例 (http://{host}:{port})")
        print()
        return False

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
        understanding, understanding_path = _load_user_understanding(bot_id)

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
                "user_understanding_path": understanding_path,
                "user_understanding_auto_facts": _understanding_auto_count(understanding),
                "embedding_enabled": False,
            },
        })

    async def handle_sessions(request):
        """GET /api/v1/admin/sessions"""
        bot_id = request.query.get("bot_id")
        return web.json_response({"sessions": admin_list_sessions(bot_id=bot_id)})

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
        understanding, understanding_path = _load_user_understanding(bot_id)

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
            "user_understanding_path": understanding_path,
            "user_understanding_auto_facts": _understanding_auto_count(understanding),
            "embedding_enabled": False,
        })

    async def handle_memory_working(request):
        """GET /api/v1/admin/memory/:bot_id/working"""
        bot_id = request.match_info["bot_id"]
        query_session = request.query.get("session_id")
        return web.json_response(working_messages(bot_id, query_session))

    async def handle_memory_episodic(request):
        """GET /api/v1/admin/memory/:bot_id/episodic"""
        bot_id = request.match_info["bot_id"]
        db_path = _get_memory_db_path(bot_id, "episodic.db")
        if not db_path:
            return web.json_response([])
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            cols = [r[1] for r in conn.execute("PRAGMA table_info(episodic_memory)").fetchall()]
            where_clause = "WHERE COALESCE(archived, 0) = 0" if "archived" in cols else ""
            select_cols = [
                "id",
                "session_id",
                "summary",
                "content",
                "importance",
                "created_at",
                "confidence" if "confidence" in cols else "0.7 AS confidence",
            ]
            rows = conn.execute("""
                SELECT {cols}
                FROM episodic_memory
                {where_clause}
                ORDER BY id DESC
                LIMIT 50
            """.format(cols=", ".join(select_cols), where_clause=where_clause)).fetchall()
            conn.close()
            result = [{"id": str(r[0]), "session_id": r[1], "summary": r[2],
                       "content": r[3], "importance": r[4], "created_at": r[5],
                       "confidence": r[6], "related_session": r[1]} for r in rows]
            return web.json_response(result)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_memory_semantic(request):
        """GET /api/v1/admin/memory/:bot_id/semantic"""
        bot_id = request.match_info["bot_id"]
        db_path = _get_memory_db_path(bot_id, "semantic.db")
        relationship_path = _get_memory_db_path(bot_id, "relationship.db")
        user_understanding, user_understanding_path = _load_user_understanding(bot_id)
        if not db_path:
            return web.json_response({
                "facts": [],
                "attitude_score": 0.0,
                "relationship_level": "陌生",
                "user_understanding": user_understanding,
                "user_understanding_path": user_understanding_path,
            })
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            cols = [r[1] for r in conn.execute("PRAGMA table_info(user_facts)").fetchall()]
            select_cols = [
                "key",
                "value",
                "updated_at",
                "category" if "category" in cols else "'general' AS category",
                "confidence" if "confidence" in cols else "0.7 AS confidence",
                "source" if "source" in cols else "'legacy' AS source",
            ]
            where_clause = "WHERE COALESCE(archived, 0) = 0" if "archived" in cols else ""
            rows = conn.execute("""
                SELECT {cols} FROM user_facts
                {where_clause}
                ORDER BY updated_at DESC
            """.format(cols=", ".join(select_cols), where_clause=where_clause)).fetchall()
            conn.close()
            facts = [
                {
                    "key": r[0],
                    "value": r[1],
                    "updated_at": r[2],
                    "category": r[3],
                    "confidence": r[4],
                    "source": r[5],
                }
                for r in rows
            ]
            attitude_score = 0.0
            relationship_level = "陌生"
            if relationship_path and relationship_path.exists():
                try:
                    rel_conn = sqlite3.connect(str(relationship_path))
                    rel_row = rel_conn.execute(
                        """
                        SELECT relationship_label, attitude_score
                        FROM relationship_state
                        WHERE bot_id = ? OR bot_id = ''
                        ORDER BY updated_at DESC
                        LIMIT 1
                        """,
                        (bot_id,),
                    ).fetchone()
                    rel_conn.close()
                    if rel_row:
                        relationship_level = rel_row[0] or relationship_level
                        attitude_score = float(rel_row[1] or 0)
                except Exception:
                    pass
            else:
                for f in facts:
                    if f["key"] == "attitude_score":
                        try:
                            attitude_score = float(f["value"])
                        except Exception:
                            pass
                    elif f["key"] in {"relationship_level", "relationship_to_user"}:
                        relationship_level = f["value"]
            return web.json_response({
                "facts": facts,
                "attitude_score": attitude_score,
                "relationship_level": relationship_level,
                "user_understanding": user_understanding,
                "user_understanding_path": user_understanding_path,
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
            if memory_type == "semantic":
                _delete_user_understanding_auto_fact(bot_id, memory_id)
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
            "relationship": 0,
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
        relationship_db = _get_memory_db_path(bot_id, "relationship.db")
        understanding_path = _get_memory_file_path(bot_id, "user_understanding.json")

        _delete_rows(working_db, "DELETE FROM messages", "working_messages")
        _delete_rows(working_db, "DELETE FROM summaries", "working_summaries")
        _delete_rows(episodic_db, "DELETE FROM episodic_memory", "episodic")
        _delete_rows(semantic_db, "DELETE FROM user_facts", "semantic")
        _delete_rows(relationship_db, "DELETE FROM relationship_state", "relationship")
        if understanding_path and understanding_path.exists():
            try:
                data = json.loads(understanding_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data, count = _clear_user_understanding_auto(data)
                    deleted["user_understanding_auto_facts"] = count
                    _write_user_understanding(understanding_path, data)
            except Exception:
                pass

        return web.json_response({"ok": True, "deleted": deleted})

    async def handle_config(request):
        """GET /api/v1/admin/config/:bot_id"""
        bot_id = request.match_info["bot_id"]
        service = ConfigAdminService(config, bot_manager)
        result = service.get_bot_config(bot_id)
        if not result:
            return web.json_response({"error": "Bot not found"}, status=404)
        return web.json_response(result)

    async def handle_config_update(request):
        """PUT /api/v1/admin/config/:bot_id"""
        bot_id = request.match_info["bot_id"]
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        try:
            service = ConfigAdminService(config, bot_manager)
            result = service.update_bot_config(bot_id, body)
            bot = bot_manager.get_bot(bot_id)
            if bot and "proactive" in body and bot.proactive_scheduler:
                await bot.proactive_scheduler.stop()
                bot.proactive_scheduler = None
                from ai_companion.proactive.scheduler import ProactiveScheduler
                bot.proactive_scheduler = ProactiveScheduler(bot.proactive_engine)
                bot.proactive_scheduler.set_dependencies(bot.model, bot.memory)
                await bot.proactive_scheduler.start()
            return web.json_response(result)
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        except Exception as e:
            return web.json_response({"error": f"Failed to save config: {e}"}, status=500)

    async def handle_config_test(request):
        """POST /api/v1/admin/config/:bot_id/test"""
        try:
            body = await request.json()
        except Exception:
            body = {}
        model_data = body.get("model", body) if isinstance(body, dict) else {}
        provider = model_data.get("provider") or config.default_provider
        base_url = model_data.get("base_url", "")
        api_key = model_data.get("api_key", "")
        provider_requires_key = provider in {"minimax", "openai", "claude"}
        if provider_requires_key and (not api_key or is_masked_secret(api_key)):
            existing = config.get_model_config(provider)
            api_key = existing.get("api_key", "")
        if provider_requires_key and not api_key:
            return web.json_response({"ok": False, "error": "API Key 未配置"}, status=400)
        if provider in {"ollama", "custom"} and not base_url:
            return web.json_response({"ok": False, "error": "base_url 未配置"}, status=400)
        try:
            ModelFactory.create_from_runtime_config(
                model_config={**model_data, "api_key": api_key, "base_url": base_url},
                provider=provider,
                api_key=api_key if provider_requires_key else None,
            )
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)
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
    cors_origins = allowed_cors_origins(config.config)

    @web.middleware
    async def cors_middleware(request, handler):
        origin = request.headers.get("Origin", "")
        cors_headers = {}
        if origin in cors_origins:
            cors_headers = {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Vary": "Origin",
            }
        if request.method == "OPTIONS":
            return web.Response(status=204, headers=cors_headers)
        response = await handler(request)
        for key, value in cors_headers.items():
            response.headers[key] = value
        return response
    _admin_app.middlewares.append(cors_middleware)

    _admin_runner = web.AppRunner(_admin_app)
    await _admin_runner.setup()
    site = web.TCPSite(_admin_runner, host, port)
    try:
        await site.start()
    except OSError:
        await _admin_runner.cleanup()
        _admin_runner = None
        if _admin_api_is_available(host, port):
            print(f"[OK] 管理 API 已在运行，复用现有实例 (http://{host}:{port})")
            print()
            return False
        raise
    print(f"[OK] 管理 API 已启动 (http://{host}:{port})")
    print()
    return True


async def _stop_admin_api():
    """Stop the admin API server."""
    global _admin_runner
    if _admin_runner:
        await _admin_runner.cleanup()
        _admin_runner = None
        print("[OK] 管理 API 已停止")


def get_data_dir() -> Path:
    """获取 Bot 数据根目录"""
    return resolve_data_dir()


_FEISHU_EXTRA_KEYS = {
    "app_id",
    "app_secret",
    "domain",
    "connection_mode",
    "group_policy",
    "allowed_users",
    "admins",
    "webhook_host",
    "webhook_port",
    "webhook_path",
    "encrypt_key",
    "verification_token",
}


def load_feishu_platform_config() -> dict | None:
    """从 ~/.ai-companion/config/config.yaml 加载飞书平台完整配置。"""
    config_path = Path.home() / ".ai-companion" / "config" / "config.yaml"
    if not config_path.exists():
        return None

    try:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        platforms = config.get("platforms", {})
        feishu = platforms.get("feishu", {})
        if feishu.get("enabled"):
            return feishu
    except Exception as e:
        logger.error(f"加载飞书配置失败: {e}")

    return None


def _normalize_feishu_extra(base: dict | None, override: dict | None = None) -> dict:
    """合并飞书 app 凭据配置，兼容 bot binding 里的扁平字段。"""
    extra = dict(base or {})
    override = override or {}
    base_app_id = extra.get("app_id")

    nested_extra = override.get("extra")
    if isinstance(nested_extra, dict):
        extra.update(nested_extra)

    for key in _FEISHU_EXTRA_KEYS:
        if key in override and override.get(key) is not None:
            extra[key] = override[key]

    # Bot 级配置如果切到另一个 app_id，不能沿用全局 app_secret。
    if extra.get("app_id") and extra.get("app_id") != base_app_id:
        override_has_secret = (
            "app_secret" in override
            or (isinstance(nested_extra, dict) and "app_secret" in nested_extra)
        )
        if not override_has_secret:
            extra.pop("app_secret", None)

    return extra


def load_feishu_config() -> dict:
    """兼容旧调用：返回默认飞书 app 的 extra 配置。"""
    feishu = load_feishu_platform_config()
    if not feishu:
        return None
    extra = _normalize_feishu_extra(feishu.get("extra", {}))
    return extra if extra.get("app_id") else None


def _get_feishu_bot_bindings(feishu_platform_config: dict | None) -> dict:
    if not feishu_platform_config:
        return {}
    bindings = feishu_platform_config.get("bot_bindings")
    if bindings is None:
        # 兼容一个更口语化的配置名，但文档推荐 bot_bindings。
        bindings = feishu_platform_config.get("bots")
    return bindings if isinstance(bindings, dict) else {}


def _extract_home_channel_id(config: dict | None) -> str:
    if not isinstance(config, dict):
        return ""

    home = config.get("home_channel")
    if isinstance(home, dict):
        chat_id = home.get("chat_id") or home.get("group_id")
        if chat_id:
            return str(chat_id)
    elif home:
        return str(home)

    for key in ("chat_id", "group_id"):
        value = config.get(key)
        if value:
            return str(value)
    return ""


def _get_feishu_binding_for_bot(feishu_platform_config: dict | None, bot_id: str) -> dict:
    bindings = _get_feishu_bot_bindings(feishu_platform_config)
    binding = bindings.get(bot_id, {})
    return binding if isinstance(binding, dict) else {}


def _extract_feishu_dedicated_bot_id(routing: dict | None) -> str:
    """飞书网关强制一个 app 只绑定一个 Bot。"""
    routing = routing or {}
    mode = routing.get("mode", "dedicated")
    if mode != "dedicated":
        raise ValueError(
            "飞书配置不再支持一个 App 路由多个 Bot：请不要使用 routing.mode=chat_routed，"
            "需要多 Bot 时请为每个 Bot 配置独立的飞书 App。"
        )
    if routing.get("group_bot_map"):
        raise ValueError(
            "飞书配置不再支持 group_bot_map：一个飞书 App 只能绑定一个 Bot，"
            "需要多 Bot 时请为每个 Bot 配置独立的飞书 App。"
        )
    return str(routing.get("bot_id") or "")


def _build_feishu_adapter_profiles(feishu_platform_config: dict | None) -> list[dict]:
    """生成需要连接的飞书 app 列表。

    支持：
    - 旧结构：platforms.feishu.extra + routing（单 app 单 Bot）
    - 新结构：platforms.feishu.bot_bindings.<bot_id>.extra（多 app，每个 app 单 Bot）
    """
    if not feishu_platform_config:
        return []

    profiles_by_app_id: dict[str, dict] = {}
    default_extra = _normalize_feishu_extra(feishu_platform_config.get("extra", {}))
    default_app_id = default_extra.get("app_id")
    default_bot_id = _extract_feishu_dedicated_bot_id(feishu_platform_config.get("routing", {}) or {})
    if default_app_id:
        profiles_by_app_id[default_app_id] = {
            "name": "default",
            "app_id": default_app_id,
            "extra": default_extra,
            "routing": {"mode": "dedicated", "bot_id": default_bot_id},
            "bot_id": default_bot_id,
        }

    for bot_id, binding in _get_feishu_bot_bindings(feishu_platform_config).items():
        if not isinstance(binding, dict):
            continue

        extra = _normalize_feishu_extra(default_extra, binding)
        app_id = extra.get("app_id")
        if not app_id:
            continue

        binding_routing = binding.get("routing")
        if isinstance(binding_routing, dict):
            binding_routing_bot_id = _extract_feishu_dedicated_bot_id(binding_routing)
            if binding_routing_bot_id and binding_routing_bot_id != bot_id:
                raise ValueError(
                    f"飞书 Bot 绑定不一致：bot_bindings.{bot_id}.routing.bot_id="
                    f"{binding_routing_bot_id}，应与绑定键一致。"
                )

        if app_id not in profiles_by_app_id:
            profiles_by_app_id[app_id] = {
                "name": f"bot:{bot_id}",
                "app_id": app_id,
                "extra": extra,
                "routing": {"mode": "dedicated", "bot_id": bot_id},
                "bot_id": bot_id,
            }
        else:
            existing_bot_id = profiles_by_app_id[app_id].get("bot_id") or ""
            if existing_bot_id and existing_bot_id != bot_id:
                raise ValueError(
                    f"飞书 App {app_id} 同时绑定了多个 Bot：{existing_bot_id}, {bot_id}。"
                    "一个飞书 App 只能绑定一个 Bot；请为不同 Bot 配置不同 app_id/app_secret。"
                )
            profiles_by_app_id[app_id]["bot_id"] = bot_id
            profiles_by_app_id[app_id]["routing"] = {"mode": "dedicated", "bot_id": bot_id}

    for profile in profiles_by_app_id.values():
        if not profile.get("bot_id"):
            raise ValueError(
                f"飞书 App {profile['app_id']} 未绑定 Bot：请配置 platforms.feishu.routing.bot_id "
                "或 platforms.feishu.bot_bindings.<bot_id>。"
            )

    app_id_by_bot_id: dict[str, str] = {}
    for profile in profiles_by_app_id.values():
        bot_id = str(profile.get("bot_id") or "")
        app_id = str(profile.get("app_id") or "")
        existing_app_id = app_id_by_bot_id.get(bot_id)
        if existing_app_id and existing_app_id != app_id:
            raise ValueError(
                f"飞书 Bot {bot_id} 同时绑定了多个 App：{existing_app_id}, {app_id}。"
                "飞书 App 与 Bot 必须一对一绑定；请移除重复绑定。"
            )
        app_id_by_bot_id[bot_id] = app_id

    return list(profiles_by_app_id.values())


def _get_feishu_app_id_for_bot(feishu_platform_config: dict | None, bot_id: str) -> str:
    if not feishu_platform_config:
        return ""
    default_extra = _normalize_feishu_extra(feishu_platform_config.get("extra", {}))
    binding = _get_feishu_binding_for_bot(feishu_platform_config, bot_id)
    if binding:
        extra = _normalize_feishu_extra(default_extra, binding)
        return str(extra.get("app_id") or "")

    try:
        default_bot_id = _extract_feishu_dedicated_bot_id(feishu_platform_config.get("routing", {}) or {})
    except ValueError:
        return ""
    if default_bot_id == bot_id:
        return str(default_extra.get("app_id") or "")
    return ""


def _get_feishu_home_channel_for_bot(feishu_platform_config: dict | None, bot_id: str) -> str:
    binding = _get_feishu_binding_for_bot(feishu_platform_config, bot_id)
    return _extract_home_channel_id(binding)


def _extract_feishu_target_id_from_bot(bot) -> str:
    """从 Bot proactive 配置提取可用于主动发送的飞书目标（群聊/会话 ID）。"""
    runtime_chat_id = getattr(bot, "_feishu_chat_id", None)
    if runtime_chat_id:
        return str(runtime_chat_id)

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

    # 需要有飞书机器人配置；如果没有固定目标，会在收到入站消息后按动态 chat_id 启动。
    has_feishu_robot = bool(feishu_config and feishu_config.get("app_id"))
    target_id = _extract_feishu_target_id_from_bot(bot)
    has_target = bool(target_id)
    if not has_feishu_robot:
        return False, "feishu_app_missing"
    if not has_target:
        return False, "feishu_target_missing_waiting_for_inbound"

    return True, f"platform=feishu has_robot={has_feishu_robot} has_target={has_target}"


async def run_gateway(daemon: bool = True):
    """启动网关服务"""
    # 保存 PID
    save_gateway_pid(os.getpid())
    adapter = None
    ui_available = False
    stop_requested = False

    def cleanup():
        remove_gateway_pid()
        _stop_ui_server()
        # Admin API is stopped via KeyboardInterrupt handler below

    def request_shutdown(signum, frame):
        nonlocal stop_requested
        stop_requested = True

    # 注册清理函数
    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)

    print("=" * 50)
    print("AI Companion Gateway")
    print("=" * 50)
    print()

    if daemon:
        print("[OK] 守护进程模式，关闭终端后网关将继续运行")
        print()

    # 加载配置
    config = Config()
    feishu_platform_config = load_feishu_platform_config()
    try:
        feishu_profiles = _build_feishu_adapter_profiles(feishu_platform_config)
    except ValueError as e:
        print(f"[ERROR] 飞书配置无效: {e}")
        sys.exit(1)

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
    feishu_adapters_by_app_id: dict[str, FeishuAdapter] = {}
    for profile in feishu_profiles:
        platform_config = PlatformConfig(
            enabled=True,
            extra=profile["extra"]
        )
        feishu_adapters_by_app_id[profile["app_id"]] = FeishuAdapter(platform_config)

    for bot_config in config.get_enabled_bots():
        bot_config = {**bot_config, "data_dir": str(data_dir)}
        bot = BotInstance(bot_config, model=model, memory_config=memory_config)

        # 设置主动消息发送平台（需要飞书适配器在 init 之前设置）。
        # 必须复用后续 connect() 的同一个 adapter，否则主动发送会命中未连接实例。
        bot_feishu_app_id = _get_feishu_app_id_for_bot(feishu_platform_config, bot.id)
        bot_feishu_adapter = feishu_adapters_by_app_id.get(bot_feishu_app_id)
        if bot_feishu_adapter:
            bot.set_proactive_platform(feishu_adapter=bot_feishu_adapter)

        # Bot 级持久化目标会话，来自 config.yaml 的 platforms.feishu.bot_bindings。
        bot_home_channel = _get_feishu_home_channel_for_bot(feishu_platform_config, bot.id)
        if bot_home_channel:
            bot._feishu_chat_id = bot_home_channel

        # 网关默认先初始化，不全量拉起轮询；按规则选择性启动
        await bot.init(start_schedulers=False)
        bot_feishu_config = None
        if bot_feishu_app_id:
            for profile in feishu_profiles:
                if profile["app_id"] == bot_feishu_app_id:
                    bot_feishu_config = profile["extra"]
                    break
        should_start, reason = _should_start_gateway_schedulers_for_bot(bot, bot_feishu_config)
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
    connected_feishu_adapters = []
    if feishu_profiles:
        print(f"[OK] 飞书配置已加载 ({len(feishu_profiles)} 个应用)")

        def _make_feishu_message_handler(router: PlatformRouter):
            async def feishu_message_handler(event):
                """process feishu message, route to BotInstance"""
                bot_id = router.route(event)
                bot = bot_manager.get_bot(bot_id) if bot_id else None

                if not bot:
                    # Fallback: 使用第一个可用的 bot
                    bot = bot_manager.first_bot

                if not bot:
                    return "没有可用的 Bot"

                # 记录用户所在的 chat_id，作为本轮运行时主动消息发送目标。
                # 持久化目标建议写入 config.yaml 的 platforms.feishu.bot_bindings。
                if event.source and hasattr(event.source, 'chat_id'):
                    bot._feishu_chat_id = event.source.chat_id

                try:
                    response = await bot.handle_message(event.text)
                    return response
                except Exception as e:
                    logger.error(f"处理消息失败: {e}")
                    return f"处理失败: {e}"

            return feishu_message_handler

        print()
        print("正在连接飞书...")

        for profile in feishu_profiles:
            adapter = feishu_adapters_by_app_id[profile["app_id"]]
            router = PlatformRouter(profile.get("routing", {}) or {})
            adapter.set_message_handler(_make_feishu_message_handler(router))
            print(f"[OK] 路由模式({profile['name']}): {router.mode}")

            success = await adapter.connect()
            if not success:
                print("[ERROR] 飞书连接失败")
                print(f"   错误: {adapter.fatal_error_message or '未知错误'}")
                sys.exit(1)

            connected_feishu_adapters.append(adapter)
            print(f"[OK] 飞书连接成功 [{profile['extra'].get('connection_mode', 'websocket')}]")
    else:
        print("[WARN] 飞书未配置，跳过网关连接")
        print("       管理 API 已启动，可访问 http://localhost:8642")

    # 默认随网关启动 UI；可用 START_UI=false 或 AI_COMPANION_START_UI=false 关闭。
    if should_start_ui(default=True):
        ui_available = _start_ui_server()
        print()

    print()
    print("=" * 50)
    if ui_available:
        print("网关 + UI 已启动")
        print(f"  管理后台: http://localhost:1421")
        print("  按 Ctrl+C 退出")
    else:
        print("网关已启动，等待飞书消息...")
        print("按 Ctrl+C 退出")
    print("=" * 50)

    try:
        # 保持运行
        while not stop_requested:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print()
        print("正在停止网关...")
    finally:
        _stop_ui_server()
        for feishu_adapter in connected_feishu_adapters:
            await feishu_adapter.disconnect()
        await _stop_admin_api()
        for bot in bot_manager.bots.values():
            try:
                await bot.close()
            except Exception as e:
                logger.debug(f"关闭 Bot 失败（忽略）: {e}")
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
