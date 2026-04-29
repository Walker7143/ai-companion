"""Small admin API helpers kept outside the gateway command entrypoint."""

from __future__ import annotations

import hmac
import os
from pathlib import Path

from .path_resolver import discover_bots, get_memory_db_path


MASKED_SECRET = "********"


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    value = str(value)
    if len(value) <= 8:
        return MASKED_SECRET
    return f"{value[:4]}...{value[-4:]}"


def is_masked_secret(value: str | None) -> bool:
    if not value:
        return False
    value = str(value)
    return value == MASKED_SECRET or ("..." in value and len(value) <= 16)


def public_model_config(model_cfg: dict) -> dict:
    return {
        "provider": model_cfg.get("provider", "minimax"),
        "api_key": mask_secret(model_cfg.get("api_key", "")),
        "base_url": model_cfg.get("base_url", "https://api.minimax.chat/v1"),
        "model": model_cfg.get("model", "MiniMax-M2.7"),
        "temperature": model_cfg.get("temperature", 0.7),
        "max_tokens": model_cfg.get("max_tokens", 2000),
    }


def admin_host(config: dict) -> str:
    admin_cfg = config.get("admin", {}) if isinstance(config, dict) else {}
    return os.environ.get("AI_COMPANION_ADMIN_HOST") or admin_cfg.get("host") or "127.0.0.1"


def admin_port(config: dict) -> int:
    admin_cfg = config.get("admin", {}) if isinstance(config, dict) else {}
    raw = os.environ.get("AI_COMPANION_ADMIN_PORT") or admin_cfg.get("port") or 8642
    return int(raw)


def allowed_cors_origins(config: dict) -> set[str]:
    admin_cfg = config.get("admin", {}) if isinstance(config, dict) else {}
    raw = os.environ.get("AI_COMPANION_ADMIN_CORS_ORIGINS") or admin_cfg.get("cors_origins")
    if isinstance(raw, str) and raw.strip():
        return {item.strip() for item in raw.split(",") if item.strip()}
    if isinstance(raw, list):
        return {str(item).strip() for item in raw if str(item).strip()}
    return {"http://localhost:1421", "http://127.0.0.1:1421"}


def list_sessions(bot_id: str | None = None) -> list[dict]:
    import sqlite3

    sessions: list[dict] = []
    bots = [b for b in discover_bots() if not bot_id or b["id"] == bot_id]
    for bot in bots:
        current_bot_id = bot["id"]
        db_path = get_memory_db_path(current_bot_id, "working.db")
        if not db_path:
            continue
        try:
            conn = sqlite3.connect(str(db_path))
            rows = conn.execute(
                """
                SELECT session_id,
                       COUNT(*) as msg_count,
                       MAX(id) as last_msg_id,
                       MIN(created_at) as first_at,
                       MAX(created_at) as last_at,
                       COALESCE(SUM(LENGTH(content)), 0) as total_chars
                FROM messages
                GROUP BY session_id
                ORDER BY last_msg_id DESC
                LIMIT 100
                """
            ).fetchall()
            conn.close()
        except Exception:
            continue

        for row in rows:
            sessions.append(
                {
                    "session_key": f"{current_bot_id}:{row[0]}",
                    "session_id": row[0],
                    "bot_id": current_bot_id,
                    "platform": "cli",
                    "user": "用户",
                    "created_at": row[3],
                    "updated_at": row[4],
                    "last_at": row[4],
                    "status": "active",
                    "reset_reason": None,
                    "total_tokens": row[5] // 2,
                }
            )
    sessions.sort(key=lambda item: item.get("last_at") or "", reverse=True)
    return sessions


def working_messages(bot_id: str, session_id: str | None = None) -> list[dict]:
    import sqlite3

    db_path = get_memory_db_path(bot_id, "working.db")
    if not db_path:
        return []
    conn = sqlite3.connect(str(db_path))
    if session_id:
        rows = conn.execute(
            """
            SELECT id, role, content, created_at
            FROM messages
            WHERE session_id = ? AND compressed = 0
            ORDER BY id DESC
            LIMIT 50
            """,
            (session_id,),
        ).fetchall()
        conn.close()
        rows = list(reversed(rows))
    else:
        row = conn.execute(
            """
            SELECT session_id FROM messages
            WHERE compressed = 0
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        if not row:
            conn.close()
            return []
        rows = conn.execute(
            """
            SELECT id, role, content, created_at
            FROM messages
            WHERE session_id = ? AND compressed = 0
            ORDER BY id ASC
            """,
            (row[0],),
        ).fetchall()
        conn.close()

    return [{"id": str(r[0]), "role": r[1], "content": r[2], "created_at": r[3]} for r in rows]


def append_audit_record(path: Path, record: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(record.rstrip() + "\n")


def constant_time_token_match(actual: str | None, provided: str | None) -> bool:
    if not actual:
        return True
    return hmac.compare_digest(str(actual), str(provided or ""))
