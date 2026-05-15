"""
工作记忆：SQLite，存储当前会话的原始对话
支持多会话隔离、自动上下文压缩、会话健康度评估
"""

import json
import aiosqlite
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


class WorkingMemoryStore:
    """
    工作记忆存储

    表结构：
    - messages: 原始对话消息
    - summaries: 压缩后的历史摘要（每次压缩生成一条）

    上下文超限时：
    1. 将早期消息压缩成一段摘要
    2. 保留最近 N 轮原始消息
    3. 累加 compression_count

    会话健康度：
    - compression_count 过多（>2）→ 建议新起会话
    - 原始消息 token 估计超限（>4000字）→ 触发压缩
    """

    # 约等于 token 数（中文约 2 字符 ≈ 1 token）
    MAX_CHARS_BEFORE_COMPRESS = 4000
    # 压缩后保留的最近轮数
    KEEP_RECENT_TURNS = 6
    # 触发压缩的字符上限
    SOFT_LIMIT_CHARS = 3000
    # 硬上限（超过此值强制压缩）
    HARD_LIMIT_CHARS = 5000

    def __init__(self, db_path: str, soft_limit: int = 3000, hard_limit: int = 5000):
        self.db_path = db_path
        self.soft_limit = soft_limit
        self.hard_limit = hard_limit
        self.current_session: Optional[str] = None
        # 每会话压缩计数，超过2次建议新起会话
        self._compression_counts: dict[str, int] = {}

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    user_id TEXT DEFAULT 'default_user',
                    platform TEXT,
                    role TEXT,
                    content TEXT,
                    compressed INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata_json TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    summary TEXT,
                    message_count INTEGER,
                    compressed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 迁移旧数据库
            msg_cursor = await db.execute("PRAGMA table_info(messages)")
            msg_cols = [row[1] async for row in msg_cursor]
            if "session_id" not in msg_cols:
                await db.execute("ALTER TABLE messages ADD COLUMN session_id TEXT")
            if "user_id" not in msg_cols:
                await db.execute("ALTER TABLE messages ADD COLUMN user_id TEXT DEFAULT 'default_user'")
            if "platform" not in msg_cols:
                await db.execute("ALTER TABLE messages ADD COLUMN platform TEXT")
            if "metadata_json" not in msg_cols:
                await db.execute("ALTER TABLE messages ADD COLUMN metadata_json TEXT")
            sum_cursor = await db.execute("PRAGMA table_info(summaries)")
            sum_cols = [row[1] async for row in sum_cursor]
            if "session_id" not in sum_cols:
                await db.execute("ALTER TABLE summaries ADD COLUMN session_id TEXT")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_session ON messages(session_id, id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_session_compressed ON messages(session_id, compressed)")
            await db.commit()

    def start_session(self, session_id: str):
        self.current_session = session_id
        if session_id not in self._compression_counts:
            self._compression_counts[session_id] = 0

    def get_or_create_session(self) -> str:
        if self.current_session is None:
            self.current_session = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._compression_counts[self.current_session] = 0
        return self.current_session

    async def append(
        self,
        user_input: str,
        bot_output: str,
        session_id: Optional[str] = None,
        user_id: str = "default_user",
        platform: Optional[str] = None,
        metadata_json: Optional[str] = None,
    ):
        sid = session_id or self.get_or_create_session()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO messages (session_id, user_id, platform, role, content, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
                (sid, user_id, platform, "user", user_input, metadata_json)
            )
            await db.execute(
                "INSERT INTO messages (session_id, user_id, platform, role, content, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
                (sid, user_id, platform, "assistant", bot_output, metadata_json)
            )
            await db.commit()

    async def append_message(
        self,
        *,
        role: str,
        content: str,
        session_id: Optional[str] = None,
        user_id: str = "default_user",
        platform: Optional[str] = None,
        metadata_json: Optional[str] = None,
    ):
        content = str(content or "").strip()
        if not content:
            return
        role = str(role or "").strip()
        if role not in {"user", "assistant", "system"}:
            raise ValueError(f"unsupported memory role: {role}")
        sid = session_id or self.get_or_create_session()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO messages (session_id, user_id, platform, role, content, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
                (sid, user_id, platform, role, content, metadata_json)
            )
            await db.commit()

    def get_all(self, session_id: Optional[str] = None) -> list[dict]:
        """获取会话所有未压缩的原始消息（按时间正序）"""
        sid = session_id or self.current_session
        if not sid:
            return []
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT role, content, metadata_json, created_at FROM messages
            WHERE session_id = ? AND compressed = 0
            ORDER BY id ASC
        """, (sid,))
        rows = cursor.fetchall()
        conn.close()
        return [_message_row(r[0], r[1], r[2], created_at=r[3]) for r in rows]

    def get_recent(self, session_id: Optional[str] = None, turns: int = 20) -> list[dict]:
        """获取最近 N 轮原始消息"""
        sid = session_id or self.current_session
        if not sid:
            return []
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT role, content, metadata_json, created_at FROM messages
            WHERE session_id = ? AND compressed = 0
            ORDER BY id DESC
            LIMIT ?
        """, (sid, turns * 2))
        rows = cursor.fetchall()
        conn.close()
        return [_message_row(r[0], r[1], r[2], created_at=r[3]) for r in rows]

    def load_context(self, session_id: Optional[str] = None,
                     max_working_turns: int = 20,
                     max_summaries: Optional[int] = None) -> list[dict]:
        """
        返回完整消息列表：
        1. 最近若干条压缩摘要（正序，最早→最近）
        2. 未压缩的原始消息（正序，最早→最近）

        保证 LLM 看到压缩后的连续性和最近对话，同时避免摘要无限累积。
        """
        sid = session_id or self.current_session
        if not sid:
            return []

        summaries = self.get_summaries(sid, limit=max_summaries)  # ["早期摘要1", "早期摘要2"]
        recent = self.get_recent(sid, turns=max_working_turns)  # [{role, content}, ...]

        messages = []
        # 先加摘要（每条摘要作为一个 "system" 角色消息）
        for s in summaries:
            messages.append({"role": "system", "content": f"[早期对话摘要] {s}"})
        # 再加原始消息
        # recent = get_recent 返回逆序(新→老)，逆转回正序(老→新)保证 LLM 看到正确时间线
        recent = list(reversed(recent))
        messages.extend(recent)
        return messages

    def get_summaries(self, session_id: Optional[str] = None, limit: Optional[int] = None) -> list[str]:
        """获取会话的所有压缩摘要"""
        sid = session_id or self.current_session
        if not sid:
            return []
        conn = sqlite3.connect(self.db_path)
        try:
            normalized_limit = int(limit) if limit is not None else None
        except (TypeError, ValueError):
            normalized_limit = None
        if normalized_limit is not None and normalized_limit > 0:
            cursor = conn.execute("""
                SELECT summary FROM (
                    SELECT id, summary FROM summaries
                    WHERE session_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
                ORDER BY id ASC
            """, (sid, normalized_limit))
        else:
            cursor = conn.execute("""
                SELECT summary FROM summaries
                WHERE session_id = ?
                ORDER BY id ASC
            """, (sid,))
        rows = cursor.fetchall()
        conn.close()
        return [r[0] for r in rows]

    def _total_chars(self, session_id: Optional[str] = None) -> int:
        """估算当前未压缩消息的总字符数"""
        sid = session_id or self.current_session
        if not sid:
            return 0
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT SUM(LENGTH(content)) FROM messages
            WHERE session_id = ? AND compressed = 0
        """, (sid,))
        result = cursor.fetchone()[0]
        conn.close()
        return result or 0

    def get_session_health(self, session_id: Optional[str] = None) -> dict:
        """
        返回会话健康度状态，供上层决策是否提示用户新起会话
        """
        sid = session_id or self.current_session
        if not sid:
            return {"ok": True, "reason": None}

        total_chars = self._total_chars(sid)
        compression_count = self._compression_counts.get(sid, 0)

        if compression_count >= 3:
            return {
                "ok": False,
                "reason": "会话已压缩3次以上，继续聊下去上下文可能混乱，建议 /new 开始新会话",
                "total_chars": total_chars,
                "compression_count": compression_count,
            }
        if total_chars > self.hard_limit:
            return {
                "ok": False,
                "reason": "会话内容过长，可能丢失早期上下文，建议 /new 开始新会话",
                "total_chars": total_chars,
                "compression_count": compression_count,
            }
        if compression_count >= 1 or total_chars > self.soft_limit:
            return {
                "ok": True,
                "reason": "会话较长，继续聊可能触发压缩，建议适时 /new 开新会话",
                "total_chars": total_chars,
                "compression_count": compression_count,
            }
        return {
            "ok": True,
            "reason": None,
            "total_chars": total_chars,
            "compression_count": compression_count,
        }

    async def compress(self, session_id: Optional[str] = None,
                       summarizer=None) -> Optional[str]:
        """
        压缩早期对话：把较旧的消息汇总成一段摘要
        返回压缩摘要文字，供 LLM 理解历史
        """
        sid = session_id or self.current_session
        if not sid:
            return None

        conn = sqlite3.connect(self.db_path)
        keep_count = self.KEEP_RECENT_TURNS * 2
        keep_boundary = conn.execute("""
            SELECT id FROM messages
            WHERE session_id = ? AND compressed = 0
            ORDER BY id DESC
            LIMIT 1 OFFSET ?
        """, (sid, keep_count - 1)).fetchone()
        if not keep_boundary:
            conn.close()
            return None

        keep_id = keep_boundary[0]
        cursor = conn.execute("""
            SELECT role, content FROM messages
            WHERE session_id = ? AND compressed = 0 AND id < ?
            ORDER BY id ASC
        """, (sid, keep_id))
        old_rows = cursor.fetchall()

        if len(old_rows) < 4:
            # 消息太少不需要压缩
            conn.close()
            return None

        # 构建待压缩文本
        old_messages_text = "\n".join([f"{r[0]}: {r[1]}" for r in old_rows])

        # 交给 summarizer LLM 来总结（如果提供了）
        if summarizer:
            summary = await summarizer.summarize_old_conversation(old_messages_text)
        else:
            # 无 summarizer 时用简单策略
            summary = self._simple_summarize(old_messages_text)

        # 只标记已进入摘要的旧消息，保留最近 K 轮原文。
        conn.execute("UPDATE messages SET compressed = 1 WHERE session_id = ? AND id < ?", (sid, keep_id))

        # 写入摘要记录
        conn.execute(
            "INSERT INTO summaries (session_id, summary, message_count) VALUES (?, ?, ?)",
            (sid, summary, len(old_rows))
        )
        conn.commit()
        conn.close()

        # 累加压缩计数
        self._compression_counts[sid] = self._compression_counts.get(sid, 0) + 1

        return summary

    def _simple_summarize(self, text: str) -> str:
        """无LLM时的简单摘要：取前100字+后50字"""
        if len(text) <= 150:
            return text
        return text[:100].strip() + "..."

    def get_turn_count(self, session_id: Optional[str] = None) -> int:
        sid = session_id or self.current_session
        if not sid:
            return 0
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user'",
            (sid,)
        )
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def get_all_messages(self, session_id: Optional[str] = None) -> list[dict]:
        """获取会话所有消息（包括压缩和未压缩的）

        Args:
            session_id: 会话 ID

        Returns:
            消息列表，每条包含 role 和 content
        """
        sid = session_id or self.current_session
        if not sid:
            return []
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT role, content, compressed, metadata_json, created_at FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
        """, (sid,))
        rows = cursor.fetchall()
        conn.close()
        return [_message_row(r[0], r[1], r[3], compressed=r[2], created_at=r[4]) for r in rows]

    async def apply_summary(self, summary: str, session_id: Optional[str] = None) -> bool:
        """应用结构化摘要到工作记忆

        Args:
            summary: 结构化摘要文本
            session_id: 会话 ID

        Returns:
            是否成功
        """
        sid = session_id or self.current_session
        if not sid:
            return False

        # 标记所有未压缩消息为已压缩
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE messages SET compressed = 1 WHERE session_id = ? AND compressed = 0", (sid,))

        # 写入新摘要
        conn.execute(
            "INSERT INTO summaries (session_id, summary, message_count) VALUES (?, ?, ?)",
            (sid, summary, -1)  # -1 表示这是结构化摘要
        )
        conn.commit()
        conn.close()

        # 累加压缩计数
        self._compression_counts[sid] = self._compression_counts.get(sid, 0) + 1
        return True

    def list_sessions(self, limit: int = 50) -> list[dict]:
        """返回所有会话列表，按最后消息时间倒序"""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("""
            SELECT session_id,
                   COUNT(*) as msg_count,
                   MAX(id) as last_msg_id,
                   MAX(created_at) as last_at
            FROM messages
            GROUP BY session_id
            ORDER BY last_msg_id DESC
            LIMIT ?
        """, (limit,)).fetchall()
        conn.close()
        return [{"session_id": r[0], "msg_count": r[1], "last_at": r[3]} for r in rows]

    async def close(self):
        pass


def _message_row(
    role: str,
    content: str,
    metadata_json: Optional[str] = None,
    *,
    compressed: int | None = None,
    created_at: Optional[str] = None,
) -> dict:
    item = {"role": role, "content": content}
    if compressed is not None:
        item["compressed"] = compressed
    if created_at:
        item["created_at"] = created_at
    metadata = _decode_metadata(metadata_json)
    if metadata:
        item["metadata"] = metadata
    return item


def _decode_metadata(metadata_json: Optional[str]) -> dict:
    if not metadata_json:
        return {}
    try:
        value = json.loads(metadata_json)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}
