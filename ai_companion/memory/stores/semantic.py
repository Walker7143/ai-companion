"""
语义记忆：SQLite，存储用户事实画像
CRUD + LLM 抽取新事实，支持字数限制和会话隔离
"""

import aiosqlite
import asyncio
import json
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .user_understanding import UserUnderstandingStore
from .vector import VectorMemoryDocument, VectorMemoryStore

logger = logging.getLogger(__name__)


class SemanticStore:
    """
    语义记忆存储

    表结构：
    - user_facts: 用户事实 (key, value, updated_at, session_id)

    抽取策略：
    每次回复后异步调用 LLM，判断是否有新事实透露。
    有则写入/更新，无则跳过。

    会话隔离：
    - session_id 不为空时写入该会话的记忆
    - 跨会话召回时读全部会话的事实
    - 私密信息可按 session_id 删除
    """

    # 抽取用户事实的 prompt
    EXTRACT_PROMPT = """对话：
用户：{user_input}
助手：{bot_output}

请只根据用户亲口透露的内容，判断这段对话是否出现了新的用户画像信息。
可记录的类型包括：姓名/称呼、城市、职业/学习、作息、爱好、长期偏好、讨厌的事、重要关系、当前压力源、希望被怎样回应、聊天边界。

有一条就输出一行 JSON，可输出多行：
{{"key": "事实key", "value": "事实value"}}
{{"key": "事实key2", "value": "事实value2"}}
无则输出：NO_FACT
不要从助手回复里反推事实；不要记录短暂情绪，除非用户明确说这是近期持续状态。
只输出 JSON 行或 NO_FACT，不要解释。"""

    # 抽取关系变化的 prompt（识别对话中用户与bot关系是否有进展）
    # 抽取关系的 prompt（结合最近 3 轮上下文判断整体氛围）
    EXTRACT_RELATION_PROMPT = """【最近几轮对话上下文】
{conversation_context}

【当前这轮对话】
用户：{user_input}
助手：{bot_output}

请结合上下文，判断这段对话是否让当前 bot 对用户的感情/关系发生了变化。
判断依据：
- 需要结合上下文：如果用户连续几轮都在调侃/撩 bot，可能关系已升级
- 如果本轮是吵架后和解，或用户连续几轮关心 → 关系可能升级
- 如果本轮是单方面的，用户一直在吐槽/冷漠 → 关系可能降级
- 如果前后语气反差大（如用户先撩后冷）→ 需要综合判断

可能的情感变化：
- "朋友" → "暧昧中" → "恋人"（逐步升级）
- "恋人" → "朋友"（分手/吵架导致）
- "暧昧中" → "朋友"（关系倒退）

有变化则输出 JSON：{{"key": "relationship_to_user", "value": "新关系"}}
无变化或无判断把握则输出：NO_CHANGE
只输出 JSON 或 NO_CHANGE，不要解释。"""

    # 抽取态度变化的 prompt（结合最近 3 轮上下文判断整体语气）
    # attitude_score 范围 -10（极度厌恶）到 +10（非常喜欢），初始约 0
    # LLM 输出本轮变化量（-5 到 +5），而非绝对值
    EXTRACT_ATTITUDE_PROMPT = """对话上下文：
{conversation_context}

当前这轮：
用户：{user_input}
助手：{bot_output}

请输出一个数字（-5 到 +5），表示本轮对话后 bot 对用户好感度的变化：
-5 大幅下降（恶语相向、严重伤害）
-3 有所下降（冷淡、敷衍）
-1 略微下降（略显不耐烦）
0 持平（普通闲聊）
+1 略微上升（有一点小感动）
+3 有所上升（被关心、被安慰）
+5 大幅上升（被告白、重大感动）

只输出数字，不要任何解释。"""

    # 抽取是否值得写入 key_moments 的 prompt（结合最近 3 轮上下文）
    EXTRACT_KEY_MOMENT_PROMPT = """【最近几轮对话上下文】
{conversation_context}

【当前这轮对话】
用户：{user_input}
助手：{bot_output}

这是一段对话情景。请判断这是否是一个值得永久记住的关键时刻：
- 两人吵架/和解
- bot 向用户敞开心扉
- 用户做了让 bot 特别感动的事
- 两人关系发生质变（确认恋爱、分手等）
- 第一次一起做某事（旅行、送礼等）

注意：需要结合上下文判断整体氛围：
- 用户连续几轮都在损 bot，突然本轮语气稍好 → 可能只是缓和，不是关键进展
- 用户表白后 bot 接受了，即使本轮只是简单回应 → 本身是关键进展
- 吵架后用户道歉+bot原谅 → 整体是关键进展（和好）

是关键时刻则输出 JSON：{{"key": "key_moment", "value": "关键时刻描述（30-60字）"}}
不是特别重要则输出：NO_MOMENT
只输出 JSON 或 NO_MOMENT，不要解释。"""

    def __init__(self, db_path: str, max_chars: int = 4400,
                 persona_backstory_path: str = None,
                 user_understanding: Optional[UserUnderstandingStore] = None,
                 vector_store: Optional[VectorMemoryStore] = None):
        self.db_path = db_path
        self.max_chars = max_chars  # 单条事实的最大字符数（可配置）
        self._summarizer: Optional[object] = None
        self._persona_backstory_path = persona_backstory_path
        self._user_understanding = user_understanding
        self._vector_store = vector_store

    def set_summarizer(self, summarizer):
        """注入 LLM 适配器（用于事实抽取）"""
        self._summarizer = summarizer

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id TEXT NOT NULL DEFAULT '',
                    user_id TEXT NOT NULL DEFAULT 'default_user',
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'general',
                    confidence REAL NOT NULL DEFAULT 0.7,
                    source TEXT NOT NULL DEFAULT 'auto',
                    evidence_json TEXT,
                    session_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_seen_at TEXT,
                    last_confirmed_at TEXT,
                    expires_at TEXT,
                    manual_override INTEGER DEFAULT 0,
                    archived INTEGER DEFAULT 0,
                    UNIQUE(bot_id, user_id, key)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS fact_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id TEXT NOT NULL DEFAULT '',
                    user_id TEXT NOT NULL DEFAULT 'default_user',
                    key TEXT NOT NULL,
                    old_value TEXT,
                    old_category TEXT,
                    old_confidence REAL,
                    old_source TEXT,
                    old_evidence_json TEXT,
                    old_session_id TEXT,
                    old_created_at TEXT,
                    old_updated_at TEXT,
                    superseded_by_value TEXT,
                    reason TEXT,
                    superseded_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_lifecycle_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id TEXT NOT NULL DEFAULT '',
                    user_id TEXT NOT NULL DEFAULT 'default_user',
                    memory_type TEXT NOT NULL,
                    memory_key TEXT,
                    action TEXT NOT NULL,
                    reason TEXT,
                    before_json TEXT,
                    after_json TEXT,
                    evidence_json TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            cursor = await db.execute("PRAGMA table_info(user_facts)")
            columns = [row[1] async for row in cursor]
            if "id" not in columns or "bot_id" not in columns:
                await self._migrate_user_facts_table(db, columns)
                cursor = await db.execute("PRAGMA table_info(user_facts)")
                columns = [row[1] async for row in cursor]
            for name, ddl in [
                ("bot_id", "ALTER TABLE user_facts ADD COLUMN bot_id TEXT NOT NULL DEFAULT ''"),
                ("user_id", "ALTER TABLE user_facts ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default_user'"),
                ("category", "ALTER TABLE user_facts ADD COLUMN category TEXT NOT NULL DEFAULT 'general'"),
                ("confidence", "ALTER TABLE user_facts ADD COLUMN confidence REAL NOT NULL DEFAULT 0.7"),
                ("source", "ALTER TABLE user_facts ADD COLUMN source TEXT NOT NULL DEFAULT 'auto'"),
                ("evidence_json", "ALTER TABLE user_facts ADD COLUMN evidence_json TEXT"),
                ("created_at", "ALTER TABLE user_facts ADD COLUMN created_at TEXT"),
                ("last_seen_at", "ALTER TABLE user_facts ADD COLUMN last_seen_at TEXT"),
                ("last_confirmed_at", "ALTER TABLE user_facts ADD COLUMN last_confirmed_at TEXT"),
                ("expires_at", "ALTER TABLE user_facts ADD COLUMN expires_at TEXT"),
                ("manual_override", "ALTER TABLE user_facts ADD COLUMN manual_override INTEGER DEFAULT 0"),
                ("archived", "ALTER TABLE user_facts ADD COLUMN archived INTEGER DEFAULT 0"),
            ]:
                if name not in columns:
                    await db.execute(ddl)
            await db.execute("UPDATE user_facts SET created_at = COALESCE(created_at, updated_at, ?)", (datetime.now().isoformat(),))
            await db.execute("CREATE INDEX IF NOT EXISTS idx_facts_session ON user_facts(session_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_facts_user_category ON user_facts(bot_id, user_id, category, archived)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_fact_history_key ON fact_history(bot_id, user_id, key, superseded_at)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_lifecycle_events_key ON memory_lifecycle_events(bot_id, user_id, memory_type, memory_key, created_at)")
            await db.commit()

    async def _migrate_user_facts_table(self, db, columns: list[str]):
        old_table = "user_facts_legacy"
        await db.execute(f"ALTER TABLE user_facts RENAME TO {old_table}")
        await db.execute(
            """
            CREATE TABLE user_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id TEXT NOT NULL DEFAULT '',
                user_id TEXT NOT NULL DEFAULT 'default_user',
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                confidence REAL NOT NULL DEFAULT 0.7,
                source TEXT NOT NULL DEFAULT 'auto',
                evidence_json TEXT,
                session_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_seen_at TEXT,
                last_confirmed_at TEXT,
                expires_at TEXT,
                manual_override INTEGER DEFAULT 0,
                archived INTEGER DEFAULT 0,
                UNIQUE(bot_id, user_id, key)
            )
            """
        )
        select_cols = ", ".join([c for c in ["key", "value", "session_id", "updated_at"] if c in columns])
        if select_cols:
            cursor = await db.execute(f"SELECT {select_cols} FROM {old_table} ORDER BY updated_at ASC")
            rows = await cursor.fetchall()
            col_index = {name: idx for idx, name in enumerate(select_cols.split(", "))}
            for row in rows:
                key = row[col_index.get("key")]
                value = row[col_index.get("value")]
                session_id = row[col_index["session_id"]] if "session_id" in col_index else None
                updated_at = row[col_index["updated_at"]] if "updated_at" in col_index else datetime.now().isoformat()
                if not key or value is None:
                    continue
                await db.execute(
                    """
                    INSERT OR REPLACE INTO user_facts (
                        bot_id, user_id, key, value, category, confidence, source,
                        session_id, created_at, updated_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "",
                        "default_user",
                        str(key),
                        str(value),
                        self._infer_category(str(key), str(value)),
                        0.7,
                        "legacy",
                        session_id,
                        updated_at,
                        updated_at,
                        updated_at,
                    ),
                )
        await db.execute(f"DROP TABLE {old_table}")

    def _trim_value(self, value: str) -> str:
        """超长 value 截断，超出 max_chars 直接丢弃（占位）"""
        if len(value) > self.max_chars:
            # 保留前缀 + 省略号
            return value[:self.max_chars - 3] + "..."
        return value

    async def set_fact(
        self,
        key: str,
        value: str,
        session_id: Optional[str] = None,
        *,
        bot_id: str = "",
        user_id: str = "default_user",
        category: str = "general",
        confidence: float = 0.7,
        source: str = "auto",
        evidence: Optional[list[str]] = None,
        expires_at: Optional[str] = None,
        manual_override: bool = False,
    ):
        """
        写入/更新单个事实（自动截断超长 value）。

        注意：SQLite 中 NULL 不等于 NULL，因此 session_id=None 的多条记录会共存。
        对于 attitude_score 等跨会话共享的事实，写入时应确保先删除旧记录。
        """
        value = self._trim_value(value)
        now = datetime.now().isoformat()
        category = category or self._infer_category(key, value)
        evidence_list = [str(item).strip() for item in (evidence or []) if str(item).strip()]
        async with aiosqlite.connect(self.db_path) as db:
            existing = await db.execute(
                """
                SELECT manual_override FROM user_facts
                WHERE bot_id = ? AND user_id = ? AND key = ?
                """,
                (bot_id, user_id, key),
            )
            row = await existing.fetchone()
            if row and row[0] and not manual_override:
                return
            await db.execute("""
                INSERT INTO user_facts (
                    bot_id, user_id, key, value, category, confidence, source,
                    evidence_json, session_id, created_at, updated_at, last_seen_at,
                    expires_at, manual_override, archived
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(bot_id, user_id, key) DO UPDATE SET
                    value = excluded.value,
                    category = excluded.category,
                    confidence = excluded.confidence,
                    source = excluded.source,
                    evidence_json = excluded.evidence_json,
                    session_id = excluded.session_id,
                    updated_at = excluded.updated_at,
                    last_seen_at = excluded.last_seen_at,
                    expires_at = excluded.expires_at,
                    manual_override = CASE
                        WHEN user_facts.manual_override = 1 THEN 1
                        ELSE excluded.manual_override
                    END,
                    archived = 0
            """, (
                bot_id,
                user_id,
                    key,
                    value,
                    category,
                    float(confidence),
                    source,
                    json.dumps(evidence_list, ensure_ascii=False),
                    session_id,
                    now,
                    now,
                    now,
                expires_at,
                1 if manual_override else 0,
            ))
            await db.commit()
        # Semantic storage is the source of facts only. User-understanding
        # projection is refreshed by MemoryGovernor/MemoryMaintenance so the
        # write path has a single policy gate.
        if self._vector_store:
            await self._vector_store.upsert(
                VectorMemoryDocument(
                    source_type="semantic_fact",
                    source_id=key,
                    text=f"[{category}] {key}: {value}",
                    bot_id=bot_id,
                    user_id=user_id,
                    category=category,
                    importance=max(0.3, min(1.0, float(confidence or 0.7))),
                    sensitivity=_fact_sensitivity(category, key, value),
                    created_at=now,
                    updated_at=now,
                    metadata={
                        "confidence": float(confidence),
                        "source": source,
                        "manual_override": bool(manual_override),
                    },
                )
            )

    async def get_fact(
        self,
        key: str,
        session_id: Optional[str] = None,
        *,
        bot_id: str = "",
        user_id: str = "default_user",
    ) -> Optional[str]:
        """读取单个事实"""
        async with aiosqlite.connect(self.db_path) as db:
            if session_id:
                cursor = await db.execute(
                    """
                    SELECT value FROM user_facts
                    WHERE key = ? AND session_id = ? AND (bot_id = ? OR bot_id = '' OR bot_id IS NULL) AND user_id = ?
                      AND COALESCE(archived, 0) = 0
                    """,
                    (key, session_id, bot_id, user_id)
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT value FROM user_facts
                    WHERE key = ? AND (bot_id = ? OR bot_id = '' OR bot_id IS NULL) AND user_id = ?
                      AND COALESCE(archived, 0) = 0
                    """,
                    (key, bot_id, user_id)
                )
            row = await cursor.fetchone()
            return row[0] if row else None

    async def get_fact_record(
        self,
        key: str,
        *,
        bot_id: str = "",
        user_id: str = "default_user",
        include_archived: bool = False,
    ) -> Optional[dict]:
        clauses = ["key = ?", "(bot_id = ? OR bot_id = '' OR bot_id IS NULL)", "user_id = ?"]
        params: list[object] = [key, bot_id, user_id]
        if not include_archived:
            clauses.append("COALESCE(archived, 0) = 0")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f"""
                SELECT id, key, value, category, confidence, source, evidence_json,
                       session_id, created_at, updated_at, last_seen_at, last_confirmed_at,
                       expires_at, manual_override, archived
                FROM user_facts
                WHERE {' AND '.join(clauses)}
                ORDER BY manual_override DESC, confidence DESC, updated_at DESC
                LIMIT 1
                """,
                params,
            )
            row = await cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "key": row[1],
            "value": row[2],
            "category": row[3],
            "confidence": row[4],
            "source": row[5],
            "evidence": _json_list(row[6]),
            "session_id": row[7],
            "created_at": row[8],
            "updated_at": row[9],
            "last_seen_at": row[10],
            "last_confirmed_at": row[11],
            "expires_at": row[12],
            "manual_override": bool(row[13]),
            "archived": bool(row[14]),
        }

    async def record_fact_supersession(
        self,
        *,
        old_fact: dict,
        new_value: str,
        reason: str,
        bot_id: str = "",
        user_id: str = "default_user",
    ):
        if not old_fact:
            return
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO fact_history (
                    bot_id, user_id, key, old_value, old_category, old_confidence,
                    old_source, old_evidence_json, old_session_id, old_created_at,
                    old_updated_at, superseded_by_value, reason, superseded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bot_id,
                    user_id,
                    str(old_fact.get("key") or ""),
                    str(old_fact.get("value") or ""),
                    str(old_fact.get("category") or ""),
                    float(old_fact.get("confidence") or 0),
                    str(old_fact.get("source") or ""),
                    json.dumps(old_fact.get("evidence") or [], ensure_ascii=False),
                    old_fact.get("session_id"),
                    old_fact.get("created_at"),
                    old_fact.get("updated_at"),
                    str(new_value or ""),
                    str(reason or ""),
                    now,
                ),
            )
            await db.commit()

    async def confirm_fact(
        self,
        key: str,
        *,
        bot_id: str = "",
        user_id: str = "default_user",
        confidence: float = 0.95,
        source: str = "user_confirmed",
        evidence: Optional[list[str]] = None,
    ):
        now = datetime.now().isoformat()
        evidence_list = [str(item).strip() for item in (evidence or []) if str(item).strip()]
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE user_facts
                SET confidence = MAX(confidence, ?),
                    source = ?,
                    last_confirmed_at = ?,
                    last_seen_at = ?,
                    evidence_json = CASE
                        WHEN ? IS NULL THEN evidence_json
                        ELSE ?
                    END
                WHERE key = ? AND (bot_id = ? OR bot_id = '' OR bot_id IS NULL) AND user_id = ?
                  AND COALESCE(archived, 0) = 0
                """,
                (
                    float(confidence),
                    source,
                    now,
                    now,
                    json.dumps(evidence_list, ensure_ascii=False) if evidence_list else None,
                    json.dumps(evidence_list, ensure_ascii=False) if evidence_list else None,
                    key,
                    bot_id,
                    user_id,
                ),
            )
            await db.commit()

    async def record_lifecycle_event(
        self,
        *,
        memory_type: str,
        memory_key: str,
        action: str,
        reason: str = "",
        before: Optional[dict] = None,
        after: Optional[dict] = None,
        evidence: Optional[list[str]] = None,
        bot_id: str = "",
        user_id: str = "default_user",
    ):
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO memory_lifecycle_events (
                    bot_id, user_id, memory_type, memory_key, action, reason,
                    before_json, after_json, evidence_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bot_id,
                    user_id,
                    memory_type,
                    memory_key,
                    action,
                    reason,
                    json.dumps(before or {}, ensure_ascii=False),
                    json.dumps(after or {}, ensure_ascii=False),
                    json.dumps(evidence or [], ensure_ascii=False),
                    now,
                ),
            )
            await db.commit()

    async def list_fact_history(
        self,
        *,
        bot_id: str = "",
        user_id: str = "default_user",
        limit: int = 10,
    ) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT key, old_value, old_category, old_confidence, old_source,
                       superseded_by_value, reason, superseded_at
                FROM fact_history
                WHERE (bot_id = ? OR bot_id = '' OR bot_id IS NULL) AND user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (bot_id, user_id, max(0, int(limit))),
            )
            rows = await cursor.fetchall()
        return [
            {
                "key": row[0],
                "old_value": row[1],
                "old_category": row[2],
                "old_confidence": row[3],
                "old_source": row[4],
                "new_value": row[5],
                "reason": row[6],
                "superseded_at": row[7],
            }
            for row in rows
        ]

    async def list_lifecycle_events(
        self,
        *,
        bot_id: str = "",
        user_id: str = "default_user",
        memory_type: Optional[str] = None,
        actions: Optional[set[str]] = None,
        limit: int = 20,
    ) -> list[dict]:
        clauses = ["(bot_id = ? OR bot_id = '' OR bot_id IS NULL)", "user_id = ?"]
        params: list[object] = [bot_id, user_id]
        if memory_type:
            clauses.append("memory_type = ?")
            params.append(memory_type)
        if actions:
            placeholders = ", ".join("?" for _ in actions)
            clauses.append(f"action IN ({placeholders})")
            params.extend(sorted(actions))
        params.append(max(0, int(limit)))
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f"""
                SELECT memory_type, memory_key, action, reason, before_json,
                       after_json, evidence_json, created_at
                FROM memory_lifecycle_events
                WHERE {' AND '.join(clauses)}
                ORDER BY id DESC
                LIMIT ?
                """,
                params,
            )
            rows = await cursor.fetchall()
        return [
            {
                "memory_type": row[0],
                "memory_key": row[1],
                "action": row[2],
                "reason": row[3],
                "before": _json_dict(row[4]),
                "after": _json_dict(row[5]),
                "evidence": _json_list(row[6]),
                "created_at": row[7],
            }
            for row in rows
        ]

    async def get_all_facts(
        self,
        session_id: Optional[str] = None,
        *,
        bot_id: str = "",
        user_id: str = "default_user",
    ) -> dict[str, str]:
        """
        读取全部或指定会话的事实。
        不传 session_id 时读全部（跨会话聚合）。
        """
        async with aiosqlite.connect(self.db_path) as db:
            if session_id:
                cursor = await db.execute(
                    """
                    SELECT key, value FROM user_facts
                    WHERE session_id = ? AND (bot_id = ? OR bot_id = '' OR bot_id IS NULL) AND user_id = ?
                      AND COALESCE(archived, 0) = 0
                    ORDER BY updated_at DESC
                    """,
                    (session_id, bot_id, user_id)
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT key, value FROM user_facts
                    WHERE (bot_id = ? OR bot_id = '' OR bot_id IS NULL) AND user_id = ? AND COALESCE(archived, 0) = 0
                    ORDER BY updated_at DESC
                    """,
                    (bot_id, user_id)
                )
            rows = await cursor.fetchall()
            result = {}
            for key, value in rows:
                # Rows are newest first; keep the freshest value for duplicate keys
                # across sessions instead of letting older rows overwrite it.
                if key not in result:
                    result[key] = value
            logger.info(f"[Semantic]  get_all_facts(session_id={session_id!r}): {result}")
            return result

    async def list_facts(
        self,
        *,
        bot_id: str = "",
        user_id: str = "default_user",
        categories: Optional[set[str]] = None,
        min_confidence: float = 0.0,
        include_archived: bool = False,
        limit: Optional[int] = None,
    ) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            clauses = ["(bot_id = ? OR bot_id = '' OR bot_id IS NULL)", "user_id = ?", "confidence >= ?"]
            params: list[object] = [bot_id, user_id, min_confidence]
            if categories:
                placeholders = ", ".join("?" for _ in categories)
                clauses.append(f"category IN ({placeholders})")
                params.extend(sorted(categories))
            if not include_archived:
                clauses.append("COALESCE(archived, 0) = 0")
            clauses.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(datetime.now().isoformat())
            sql = f"""
                SELECT id, key, value, category, confidence, source, evidence_json,
                       session_id, created_at, updated_at, last_seen_at, expires_at,
                       manual_override, archived
                FROM user_facts
                WHERE {' AND '.join(clauses)}
                ORDER BY manual_override DESC, confidence DESC, updated_at DESC
            """
            if limit is not None:
                sql += " LIMIT ?"
                params.append(limit)
            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()
        result = []
        for row in rows:
            result.append({
                "id": row[0],
                "key": row[1],
                "value": row[2],
                "category": row[3],
                "confidence": row[4],
                "source": row[5],
                "evidence": _json_list(row[6]),
                "session_id": row[7],
                "created_at": row[8],
                "updated_at": row[9],
                "last_seen_at": row[10],
                "expires_at": row[11],
                "manual_override": bool(row[12]),
                "archived": bool(row[13]),
                "evidence": _json_list(row[6]),
            })
        return result

    async def search_facts(
        self,
        query: str,
        *,
        bot_id: str = "",
        user_id: str = "default_user",
        categories: Optional[set[str]] = None,
        min_confidence: float = 0.0,
        include_archived: bool = False,
        limit: Optional[int] = 24,
    ) -> list[dict]:
        """Search all active facts, then rank by relevance instead of SQL recency.

        ``categories`` is an intent hint, not a hard filter. This keeps facts like
        pet names available in casual chat even when they live under life_context
        or important_people.
        """
        facts = await self.list_facts(
            bot_id=bot_id,
            user_id=user_id,
            categories=None,
            min_confidence=min_confidence,
            include_archived=include_archived,
            limit=None,
        )
        ranked = self._rank_facts(query, facts, categories=categories)
        if limit is None:
            return ranked
        return ranked[: max(0, int(limit))]

    def _rank_facts(
        self,
        query: str,
        facts: list[dict],
        *,
        categories: Optional[set[str]] = None,
    ) -> list[dict]:
        query = str(query or "")
        query_cues = _fact_cues(query)
        category_hints = set(categories or set())
        ranked: list[dict] = []
        for fact in facts:
            key = str(fact.get("key") or "")
            value = str(fact.get("value") or "")
            category = str(fact.get("category") or "general")
            haystack = f"{key} {value} {category}".lower()

            overlap = sum(1 for cue in query_cues if cue and cue in haystack)
            salient_overlap = sum(1 for cue in _SALIENT_FACT_CUES if cue in query and cue.lower() in haystack)
            score = 0.0
            if fact.get("manual_override"):
                score += 3.0
            score += min(1.0, _float(fact.get("confidence"), 0.0)) * 0.8
            if category in category_hints:
                score += 0.45
            if overlap:
                score += min(2.4, overlap * 0.35)
            if salient_overlap:
                score += min(1.5, salient_overlap * 0.75)
            if str(fact.get("source") or "") in {"manual", "manual_repair", "user_explicit"}:
                score += 0.25

            # Category is only a boost after the query matches the fact. Let the
            # user_understanding layer carry broad background; semantic search
            # should stay query-related.
            category_fallback = (
                category in category_hints
                and _float(fact.get("confidence"), 0.0) >= 0.9
                and category in {"communication_style", "boundaries", "important_people", "life_context", "open_threads"}
            )
            if not overlap and not salient_overlap and not category_fallback:
                continue
            if score <= 0:
                continue
            item = dict(fact)
            item["retrieval_score"] = round(score, 3)
            item["retrieval_reasons"] = {
                "query_cue_overlap": overlap,
                "salient_overlap": salient_overlap,
                "category_hint": category in category_hints,
                "category_fallback": category_fallback,
                "manual_override": bool(fact.get("manual_override")),
            }
            ranked.append(item)

        ranked.sort(
            key=lambda item: (
                item.get("retrieval_score", 0),
                1 if item.get("manual_override") else 0,
                _float(item.get("confidence"), 0.0),
                str(item.get("updated_at") or ""),
            ),
            reverse=True,
        )
        return ranked

    async def delete_fact(
        self,
        key: str,
        session_id: Optional[str] = None,
        *,
        bot_id: str = "",
        user_id: str = "default_user",
    ):
        """删除指定事实（不传 session_id 时删除所有匹配 key 的事实）"""
        async with aiosqlite.connect(self.db_path) as db:
            if session_id:
                await db.execute(
                    "DELETE FROM user_facts WHERE key = ? AND session_id = ? AND (bot_id = ? OR bot_id = '' OR bot_id IS NULL) AND user_id = ?",
                    (key, session_id, bot_id, user_id)
                )
            else:
                await db.execute(
                    "DELETE FROM user_facts WHERE key = ? AND (bot_id = ? OR bot_id = '' OR bot_id IS NULL) AND user_id = ?",
                    (key, bot_id, user_id)
                )
            await db.commit()
        if self._user_understanding:
            await self._user_understanding.delete_auto_fact(key)
        if self._vector_store:
            await self._vector_store.delete(
                source_type="semantic_fact",
                source_id=key,
                bot_id=bot_id,
                user_id=user_id,
            )

    async def archive_fact(
        self,
        key: str,
        *,
        bot_id: str = "",
        user_id: str = "default_user",
        reason: str = "",
    ) -> bool:
        before = await self.get_fact_record(key, bot_id=bot_id, user_id=user_id, include_archived=False)
        if not before:
            return False
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE user_facts
                SET archived = 1, updated_at = ?
                WHERE key = ? AND (bot_id = ? OR bot_id = '' OR bot_id IS NULL) AND user_id = ?
                  AND COALESCE(archived, 0) = 0
                """,
                (datetime.now().isoformat(), key, bot_id, user_id),
            )
            await db.commit()
        if self._user_understanding:
            await self._user_understanding.delete_auto_fact(key)
        if self._vector_store:
            await self._vector_store.delete(
                source_type="semantic_fact",
                source_id=key,
                bot_id=bot_id,
                user_id=user_id,
            )
        await self.record_lifecycle_event(
            memory_type="semantic_fact",
            memory_key=key,
            action="archive",
            reason=reason,
            before=before,
            bot_id=bot_id,
            user_id=user_id,
        )
        return True

    async def archive_facts_matching(
        self,
        *,
        bot_id: str = "",
        user_id: str = "default_user",
        categories: Optional[set[str]] = None,
        predicate,
        reason: str = "",
    ) -> list[dict]:
        facts = await self.list_facts(
            bot_id=bot_id,
            user_id=user_id,
            categories=categories,
            include_archived=False,
            limit=None,
        )
        archived: list[dict] = []
        for fact in facts:
            try:
                should_archive = bool(predicate(fact))
            except Exception:
                should_archive = False
            if not should_archive:
                continue
            if await self.archive_fact(str(fact.get("key") or ""), bot_id=bot_id, user_id=user_id, reason=reason):
                archived.append(fact)
        return archived

    async def archive_expired(self, *, now: str, bot_id: str = "", user_id: str = "default_user"):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE user_facts
                SET archived = 1
                WHERE (bot_id = ? OR bot_id = '' OR bot_id IS NULL) AND user_id = ?
                  AND expires_at IS NOT NULL
                  AND expires_at <= ?
                  AND COALESCE(manual_override, 0) = 0
                """,
                (bot_id, user_id, now),
            )
            await db.commit()

    async def extract_and_store(self, user_input: str, bot_output: str,
                               session_id: Optional[str] = None,
                               model: Optional[object] = None,
                               conversation_context: str = "") -> Optional[dict]:
        """
        异步抽取本轮对话中的新事实，有则写入 SQLite。
        conversation_context: 最近 3 轮对话的原始文本，用于辅助判断语气/氛围。
        返回写入的事实 {"key": ..., "value": ...} 或 None。
        """
        logger.info(f"[Semantic]  extract_and_store 开始 | ctx_len={len(conversation_context)} | user={user_input[:30]!r}")
        summarizer = model or self._summarizer
        if not summarizer:
            logger.info(f"[Semantic]  无 summarizer，跳过")
            return None

        # attitude 单独抽取（prompt 要求输出纯数字，不再走 JSON 解析）
        async def try_extract_attitude(prompt: str) -> Optional[dict]:
            try:
                response = await summarizer.chat(
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt=None
                )
                if isinstance(response, dict):
                    content = response.get("content") or response.get("reasoning_content") or ""
                elif isinstance(response, str):
                    content = response
                else:
                    content = str(response)
                content = content.strip()
                logger.info(f"[Semantic] [attitude] LLM原始回复: {content!r}")
                # MiniMax-M2.7 的 content 包含完整推理过程，取最后一个数字才是结论
                all_nums = re.findall(r'-?\d+', content)
                if all_nums:
                    delta = int(all_nums[-1])  # 最后一个匹配是推理后的最终结论
                    delta = max(-5, min(5, delta))  # 限制在 ±5
                    logger.info(f"[Semantic] [attitude] 解析结果: delta={delta} (from {all_nums})")
                    return {"key": "attitude_score", "value": str(delta)}
                logger.info(f"[Semantic] [attitude] 解析结果: 无数字")
                return None
            except Exception as e:
                logger.info(f"[Semantic] [attitude] 抽取异常: {e}")
                return None

        # fact/relation/key_moment 用 JSON 解析
        async def try_extract_json(prompt: str, label: str) -> list[dict]:
            try:
                response = await summarizer.chat(
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt=None
                )
                if isinstance(response, dict):
                    content = response.get("content") or response.get("reasoning_content") or ""
                elif isinstance(response, str):
                    content = response
                else:
                    content = str(response)
                content = content.strip()
                logger.info(f"[Semantic] [{label}] LLM原始回复: {content[:200]!r}")
                facts = self._parse_facts(content)
                logger.info(f"[Semantic] [{label}] 解析结果: {facts}")
                return facts
            except Exception as e:
                logger.info(f"[Semantic] [{label}] 抽取异常: {e}")
                return []

        # 并行执行所有抽取
        fact_task = try_extract_json(self.EXTRACT_PROMPT.format(
            user_input=user_input, bot_output=bot_output), "fact")
        # Relationship state is owned by RelationshipStore now. Keep the old
        # relation prompt disabled here so a single LLM output cannot overwrite
        # runtime_profile["relationship_to_user"] and make the stage wobble
        # between "朋友/好朋友/暧昧中".
        rel_task = asyncio.sleep(0, result=[])
        att_task = try_extract_attitude(self.EXTRACT_ATTITUDE_PROMPT.format(
            conversation_context=conversation_context,
            user_input=user_input, bot_output=bot_output))
        moment_task = try_extract_json(self.EXTRACT_KEY_MOMENT_PROMPT.format(
            conversation_context=conversation_context,
            user_input=user_input, bot_output=bot_output), "key_moment")

        results = await asyncio.gather(fact_task, rel_task, att_task, moment_task)

        written = []
        for result in results:
            if isinstance(result, list):
                items = result
            else:
                items = [result]

            for res in items:
                if not res or not res.get("key") or not res.get("value"):
                    continue

                key = res["key"]
                value = res["value"]

                # attitude_score 用增量叠加，而不是覆盖
                if key == "attitude_score":
                    delta = self._parse_attitude_delta(value)
                    if delta != 0:
                        # attitude_score 跨会话共享，不传 session_id
                        await self._apply_attitude_delta(delta, session_id=None)
                        written.append({"key": key, "value": str(delta)})
                        logger.info(f"[Semantic]  attitude_score {delta:+d}")
                    # 跳过 set_fact，由 _apply_attitude_delta 处理
                    continue

                if key in {"relationship_to_user", "relationship_level", "relationship_label"}:
                    logger.info(f"[Semantic]  跳过旧关系标签写入，由 RelationshipStore 接管: {res}")
                    continue

                # 其余类型直接写入
                value_text = str(value)
                await self.set_fact(
                    key,
                    value_text,
                    session_id=session_id,
                    category=self._infer_category(key, value_text),
                    confidence=0.78,
                    source="legacy_extract",
                )
                written.append(res)
                logger.info(f"[Semantic]  写入记忆: {res}")

                # key_moment 追加到人格文件（去重后才写）
                if key == "key_moment":
                    await self._append_key_moment(value)

        return written[0] if written else None

    def _parse_facts(self, text: str) -> list[dict]:
        """
        从 LLM 输出中解析 JSON 事实。

        支持两种格式：
        1. {"key": "事实key", "value": "事实value"}         — 单条标准格式
        2. {"姓名": "小明", "职业": "建筑师", ...}          — 平面 KV 格式

        返回所有解析到的事实列表（自动处理多行 JSON）。
        """
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*", "", text)
        text = text.strip()

        if text == "NO_FACT" or not text:
            return []

        facts = []
        seen_keys = set()  # 用于去重，同一 key 只保留第一个值

        # 按行处理，支持多行 JSON（每行一个 JSON 对象）
        for line in text.split('\n'):
            line = line.strip()
            if not line or line == "NO_FACT":
                continue

            try:
                data = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue

            # 格式 1：标准 {"key": ..., "value": ...}
            if isinstance(data, dict) and "key" in data and "value" in data:
                key = data["key"].strip()
                value = str(data["value"]).strip()
                if key and value and len(key) < 50 and len(value) < 500 and key not in seen_keys:
                    facts.append({"key": key, "value": value})
                    seen_keys.add(key)
                continue

            # 格式 2：平面 KV {"姓名": "小明", "职业": "建筑师", ...}
            if isinstance(data, dict):
                for k, v in data.items():
                    k = k.strip()
                    v = str(v).strip()
                    if k and v and len(k) < 50 and len(v) < 500 and k not in seen_keys:
                        facts.append({"key": k, "value": v})
                        seen_keys.add(k)

        return facts

    async def get_fact_count(self, session_id: Optional[str] = None) -> int:
        """返回当前事实数量"""
        async with aiosqlite.connect(self.db_path) as db:
            if session_id:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM user_facts WHERE session_id = ? AND COALESCE(archived, 0) = 0", (session_id,)
                )
            else:
                cursor = await db.execute("SELECT COUNT(*) FROM user_facts WHERE COALESCE(archived, 0) = 0")
            row = await cursor.fetchone()
            return row[0] if row else 0

    def _infer_category(self, key: str, value: str) -> str:
        text = f"{key} {value}"
        if any(word in text for word in ["不要", "别", "边界", "雷区", "不想聊"]):
            return "boundaries"
        if any(word in text for word in ["先共情", "少讲道理", "说教", "怎么回应"]):
            return "communication_style"
        if any(word in text for word in ["压力", "失眠", "焦虑", "最近", "面试", "考试", "作品集"]):
            return "life_context"
        if any(word in text for word in ["计划", "目标", "继续", "明天"]):
            return "goals"
        if any(word in text for word in ["名字", "称呼", "城市", "职业", "我叫", "叫我"]):
            return "identity"
        if any(word in text for word in ["喜欢", "偏好", "爱吃", "爱听"]):
            return "preferences"
        if any(word in text for word in ["讨厌", "不喜欢"]):
            return "dislikes"
        return "general"

    # ── 态度分增量处理 ─────────────────────────────────────────

    def _parse_attitude_delta(self, value) -> int:
        """从 LLM 输出的 attitude_score 解析出本轮变化量"""
        try:
            num = int(str(value).strip())
            return max(-5, min(5, num))  # 限制单轮最大变化 ±5
        except (ValueError, TypeError):
            return 0

    async def _apply_attitude_delta(self, delta: int, session_id: Optional[str] = None):
        """
        将变化量叠加到现有 attitude_score。

        注意：attitude_score 跨会话共享，不使用 session_id 隔离。
        这样保证用户在开启新会话后，attitude_score 仍然基于历史累计值。
        """
        # attitude_score 跨会话共享，读取时不传 session_id
        current = await self.get_fact("attitude_score", session_id=None)
        try:
            current_score = int(float(current)) if current else 0
        except (ValueError, TypeError):
            current_score = 0
        new_score = max(-10, min(10, current_score + delta))
        # 写入时也不传 session_id，确保跨会话共享
        await self.set_fact("attitude_score", str(new_score), session_id=None)
        await self._update_attitude_profile(new_score)
        logger.info(f"[Semantic]  attitude_score: {current_score} {delta:+d} -> {new_score}")

    # ── 运行态人格状态 ───────────────────────────────────────

    def _runtime_profile_path(self) -> Optional[Path]:
        if not self._persona_backstory_path:
            return None
        return Path(self._persona_backstory_path).parent / "runtime_profile.json"

    def _load_runtime_profile(self) -> dict:
        path = self._runtime_profile_path()
        if not path or not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_runtime_profile(self, data: dict):
        path = self._runtime_profile_path()
        if not path:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".json.tmp")
        payload = dict(data or {})
        payload["updated_at"] = datetime.now().isoformat()
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp_path.replace(path)

    # ── 人格运行态写回 ───────────────────────────────────────

    async def _append_key_moment(self, moment: str):
        """将关键时刻追加到 runtime_profile.json，避免污染模板 backstory。"""
        if not self._persona_backstory_path:
            return
        try:
            data = self._load_runtime_profile()
            moments = data.get("key_moments", [])
            if moment not in moments:
                moments.append(moment)
                data["key_moments"] = moments
                self._write_runtime_profile(data)
                logger.info(f"[Semantic]  key_moment 已写入 runtime_profile: {moment[:30]}...")
        except Exception as e:
            logger.info(f"[Semantic]  写回 key_moment 失败: {e}")

    async def _update_relationship(self, relationship: str):
        """将关系变化更新到 runtime_profile.json。"""
        if not self._persona_backstory_path:
            return
        try:
            data = self._load_runtime_profile()
            old_rel = data.get("relationship_to_user", "")
            if old_rel != relationship:
                data["relationship_to_user"] = relationship
                self._write_runtime_profile(data)
                logger.info(f"[Semantic]  relationship 已更新到 runtime_profile: {old_rel} -> {relationship}")
        except Exception as e:
            logger.info(f"[Semantic]  写回 relationship 失败: {e}")

    async def _update_attitude_profile(self, new_score: int):
        """将 attitude_score 变化更新到 runtime_profile.json。"""
        if not self._persona_backstory_path:
            return
        try:
            data = self._load_runtime_profile()
            data["attitude_score"] = new_score
            self._write_runtime_profile(data)
            logger.info(f"[Semantic]  attitude_score 已写入 runtime_profile: {new_score}")
        except Exception as e:
            logger.info(f"[Semantic]  写回 attitude_score 失败: {e}")

    async def close(self):
        pass


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        data = json.loads(value)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data if str(item).strip()]


def _json_dict(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        data = json.loads(str(value))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fact_sensitivity(category: str, key: str, value: str) -> str:
    text = f"{category} {key} {value}".lower()
    sensitive_cues = {
        "health", "medical", "body", "trauma", "boundary", "boundaries",
        "鍋ュ悍", "韬綋", "鐤剧梾", "鍖荤枟", "杈圭晫", "闅愮", "鍒嗘墜", "鍚垫灦",
    }
    if str(category or "") in {"boundaries", "sensitive", "health"}:
        return "sensitive"
    if any(cue in text for cue in sensitive_cues):
        return "sensitive"
    return "normal"


_SALIENT_FACT_CUES = {
    "猫",
    "宠物",
    "布丁",
    "奥利奥",
    "布偶",
    "孟买",
    "狗",
    "车",
    "小米",
    "SU7",
    "妹妹",
    "爷爷",
    "奶奶",
    "北京",
    "大理",
    "游戏",
    "永劫",
    "咖啡",
    "约定",
    "喝酒",
    "酒",
    "抽烟",
    "吸烟",
    "腿脚",
    "腿",
    "脚",
    "膝盖",
    "腰",
    "身体",
    "健康",
    "跑步",
    "跑",
}


def _fact_cues(text: str) -> list[str]:
    compact = "".join(str(text or "").split())
    cues: list[str] = []
    for cue in _SALIENT_FACT_CUES:
        if cue.lower() in compact.lower():
            cues.append(cue.lower())
    for size in (4, 3, 2):
        for idx in range(0, max(0, len(compact) - size + 1)):
            chunk = compact[idx : idx + size]
            if _is_fact_cue(chunk):
                cues.append(chunk.lower())
    ascii_word = []
    for char in compact:
        if char.isascii() and char.isalnum():
            ascii_word.append(char.lower())
        else:
            if len(ascii_word) >= 3:
                cues.append("".join(ascii_word))
            ascii_word = []
    if len(ascii_word) >= 3:
        cues.append("".join(ascii_word))
    return _dedupe(cues)[:32]


def _is_fact_cue(value: str) -> bool:
    if not value:
        return False
    stop = {
        "我的", "你的", "我们", "你们", "这个", "那个", "什么", "怎么", "是不是",
        "还记", "记得", "之前", "上次", "应该", "知道", "说过",
    }
    return value not in stop and any("\u4e00" <= char <= "\u9fff" or char.isalnum() for char in value)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result
