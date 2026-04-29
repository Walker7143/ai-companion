"""
情景记忆：SQLite + jieba 中文分词 + Chroma 向量库
存储重要情景片段，可跨会话语义召回

召回优先级：
1. SQLite jieba tokens LIKE 搜索（中文友好，高精度）
2. Chroma 向量语义召回（可选，语义相近但非精确）
3. summary/content 直接 LIKE（兜底）
"""

import aiosqlite
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import jieba
import logging
jieba.setLogLevel(logging.WARNING)  # 屏蔽 jieba 加载信息


class EpisodicStore:
    """重要情景片段，jieba 分词全文搜索 + Chroma 向量召回"""

    # sentence-transformers 模型名
    DEFAULT_ENCODER_MODEL = "all-MiniLM-L6-v2"

    # LLM 抽取情景摘要的 prompt
    EXTRACT_EPISODE_PROMPT = """对话：
用户：{user_input}
助手：{bot_output}

请为这段对话生成一段简洁的情景摘要（30-60字），概括发生了什么重要的事或有什么值得记住的情节。
只输出摘要文字，不要解释。"""

    def __init__(self, db_path: str, chroma_dir: str,
                 embedding_mode: str = "none",
                 encoder_model: str = "all-MiniLM-L6-v2"):
        self.db_path = db_path
        self.chroma_dir = Path(chroma_dir)
        self.embedding_mode = embedding_mode  # "local" | "none"
        self.encoder_model = encoder_model
        self._encoder = None
        self._chroma = None
        self._collection = None
        self._summarizer: Optional[object] = None

    def set_summarizer(self, summarizer):
        """注入 LLM 适配器（用于情景摘要生成）"""
        self._summarizer = summarizer

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS episodic_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id TEXT DEFAULT '',
                    user_id TEXT DEFAULT 'default_user',
                    session_id TEXT,
                    title TEXT,
                    summary TEXT,
                    content TEXT,
                    tokens TEXT,
                    importance REAL DEFAULT 0.6,
                    confidence REAL DEFAULT 0.7,
                    participants_json TEXT,
                    topics_json TEXT,
                    emotion_tags_json TEXT,
                    source_message_ids_json TEXT,
                    last_recalled_at TEXT,
                    recall_count INTEGER DEFAULT 0,
                    decay_score REAL DEFAULT 1.0,
                    archived INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 迁移旧数据库
            cur = await db.execute("PRAGMA table_info(episodic_memory)")
            cols = [row[1] async for row in cur]
            if "session_id" not in cols:
                await db.execute("ALTER TABLE episodic_memory ADD COLUMN session_id TEXT")
            if "tokens" not in cols:
                await db.execute("ALTER TABLE episodic_memory ADD COLUMN tokens TEXT")
            for name, ddl in [
                ("bot_id", "ALTER TABLE episodic_memory ADD COLUMN bot_id TEXT DEFAULT ''"),
                ("user_id", "ALTER TABLE episodic_memory ADD COLUMN user_id TEXT DEFAULT 'default_user'"),
                ("title", "ALTER TABLE episodic_memory ADD COLUMN title TEXT"),
                ("confidence", "ALTER TABLE episodic_memory ADD COLUMN confidence REAL DEFAULT 0.7"),
                ("participants_json", "ALTER TABLE episodic_memory ADD COLUMN participants_json TEXT"),
                ("topics_json", "ALTER TABLE episodic_memory ADD COLUMN topics_json TEXT"),
                ("emotion_tags_json", "ALTER TABLE episodic_memory ADD COLUMN emotion_tags_json TEXT"),
                ("source_message_ids_json", "ALTER TABLE episodic_memory ADD COLUMN source_message_ids_json TEXT"),
                ("last_recalled_at", "ALTER TABLE episodic_memory ADD COLUMN last_recalled_at TEXT"),
                ("recall_count", "ALTER TABLE episodic_memory ADD COLUMN recall_count INTEGER DEFAULT 0"),
                ("decay_score", "ALTER TABLE episodic_memory ADD COLUMN decay_score REAL DEFAULT 1.0"),
                ("archived", "ALTER TABLE episodic_memory ADD COLUMN archived INTEGER DEFAULT 0"),
            ]:
                if name not in cols:
                    await db.execute(ddl)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_episodic_session ON episodic_memory(session_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_episodic_importance ON episodic_memory(importance DESC)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_episodic_user ON episodic_memory(bot_id, user_id, archived)")
            await db.commit()

        self._chroma = None
        self._collection = None

    def _get_chroma(self):
        """延迟加载 Chroma"""
        if self._chroma is None:
            import chromadb
            from chromadb.config import Settings
            self._chroma = chromadb.PersistentClient(
                path=str(self.chroma_dir),
                settings=Settings(anonymized_telemetry=False)
            )
            self._collection = self._chroma.get_or_create_collection("episodes")
        return self._collection

    def _get_encoder(self):
        """延迟加载 sentence-transformers"""
        if self.embedding_mode != "local":
            return None
        if self._encoder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._encoder = SentenceTransformer(self.encoder_model)
            except Exception:
                self.embedding_mode = "none"
                return None
        return self._encoder

    def _tokenize(self, text: str) -> str:
        """用 jieba 分词，返回空格分隔的词序列"""
        return " ".join(jieba.cut(text))

    def _should_extract(self, user_input: str, bot_output: str) -> bool:
        """Only keep exchanges that look like durable shared experiences."""
        text = f"{user_input}\n{bot_output}"
        if len(user_input.strip()) < 8:
            return False
        keywords = [
            "吵架", "和好", "道歉", "承诺", "约定", "表白", "分手", "第一次",
            "搬家", "考试", "面试", "失眠", "崩溃", "重要", "难过", "焦虑",
        ]
        return any(keyword in text for keyword in keywords)

    async def extract_and_store(self, user_input: str, bot_output: str,
                                 session_id: Optional[str] = None):
        """抽取情景摘要（LLM提炼或简单截断），写入SQLite和Chroma"""
        if not self._should_extract(user_input, bot_output):
            return None
        sid = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")

        # LLM 提炼摘要（有 summarizer 时）
        if self._summarizer:
            summary = await self._llm_extract(user_input, bot_output)
        else:
            summary = self._simple_extract(user_input, bot_output)

        content = f"用户：{user_input}\n助手：{bot_output}"
        tokens = self._tokenize(summary) + " " + self._tokenize(content)

        await self.store_episode(
            summary=summary,
            content=content,
            session_id=sid,
            importance=self._importance_for(user_input, bot_output),
            confidence=0.65,
        )
        return summary

    async def store_episode(
        self,
        *,
        summary: str,
        content: str,
        session_id: Optional[str] = None,
        bot_id: str = "",
        user_id: str = "default_user",
        title: str = "",
        importance: float = 0.6,
        confidence: float = 0.7,
        topics: Optional[list[str]] = None,
        emotion_tags: Optional[list[str]] = None,
        source_message_ids: Optional[list[str]] = None,
    ):
        """Store an approved episodic memory."""
        sid = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        content = content or summary
        tokens = self._tokenize(summary) + " " + self._tokenize(content)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO episodic_memory (
                    bot_id, user_id, session_id, title, summary, content, tokens,
                    importance, confidence, topics_json, emotion_tags_json,
                    source_message_ids_json, decay_score, archived, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                bot_id,
                user_id,
                sid,
                title,
                summary,
                content,
                tokens,
                float(importance),
                float(confidence),
                json.dumps(topics or [], ensure_ascii=False),
                json.dumps(emotion_tags or [], ensure_ascii=False),
                json.dumps(source_message_ids or [], ensure_ascii=False),
                1.0,
                0,
                datetime.now().isoformat(),
            ))
            await db.commit()

        # Chroma 写入（仅在 embedding_mode="local" 时）
        if self.embedding_mode == "local":
            try:
                collection = self._get_chroma()
                embedding = self._get_embedding(summary)
                collection.add(
                    ids=[str(datetime.now().timestamp())],
                    embeddings=[embedding],
                    documents=[f"{summary}\n\n原始：{content}"],
                    metadatas=[{"summary": summary, "session_id": sid, "bot_id": bot_id, "user_id": user_id}]
                )
            except Exception:
                pass

    async def _llm_extract(self, user_input: str, bot_output: str) -> str:
        """用 LLM 生成情景摘要"""
        try:
            prompt = self.EXTRACT_EPISODE_PROMPT.format(
                user_input=user_input,
                bot_output=bot_output
            )
            response = await self._summarizer.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=None
            )
            # 处理 MiniMax-M2.7: 优先 content，降级用 reasoning_content
            if isinstance(response, dict):
                text = response.get("content") or response.get("reasoning_content") or ""
            elif isinstance(response, str):
                text = response
            else:
                text = str(response)
            text = text.strip()
            if text:
                return text[:200]  # 限制长度
        except Exception:
            pass
        return self._simple_extract(user_input, bot_output)

    def _simple_extract(self, user_input: str, bot_output: str) -> str:
        """无外部依赖的简单抽取策略"""
        return user_input[:40].strip()

    def _importance_for(self, user_input: str, bot_output: str) -> float:
        text = f"{user_input}\n{bot_output}"
        high = ["表白", "分手", "和好", "吵架", "承诺", "第一次"]
        medium = ["考试", "面试", "搬家", "失眠", "崩溃", "焦虑", "难过"]
        if any(k in text for k in high):
            return 0.85
        if any(k in text for k in medium):
            return 0.72
        return 0.6

    def _get_embedding(self, text: str) -> list[float]:
        encoder = self._get_encoder()
        if encoder is not None:
            return encoder.encode(text).tolist()
        # 降级：基于 hash 的确定性向量（维度 384）
        import hashlib, struct
        h = hashlib.sha256(text.encode()).digest()
        vals = list(struct.unpack(f"{len(h) // 4}f", h))
        while len(vals) < 384:
            vals.append(0.0)
        return vals[:384]

    def recall(self, query: str, top_k: int = 3,
               session_id: Optional[str] = None,
               bot_id: Optional[str] = None,
               user_id: str = "default_user",
               include_archived: bool = False) -> list[dict]:
        """
        语义召回：Chroma → jieba tokens → summary/content LIKE 降级。
        session_id 不为空时只召回该会话的记忆。
        embedding_mode="local" 时启用 Chroma 向量召回（语义优先）。
        """
        # 1. Chroma 向量召回（语义优先，embedding_mode="local" 时）
        if self.embedding_mode == "local":
            results = self._chroma_recall(query, top_k, session_id)
            if results:
                return results

        # 2. jieba tokens LIKE 搜索（中文关键词）
        results = self._tokens_recall(query, top_k, session_id, bot_id, user_id, include_archived)
        if results:
            return results

        # 3. summary/content 直接 LIKE 降级兜底
        return self._fallback_recall(query, top_k, session_id, bot_id, user_id, include_archived)

    def _tokens_recall(self, query: str, top_k: int,
                       session_id: Optional[str] = None,
                       bot_id: Optional[str] = None,
                       user_id: str = "default_user",
                       include_archived: bool = False) -> list[dict]:
        """
        jieba 分词 tokens 列 LIKE 搜索：
        1. query 用 jieba 分词
        2. 每个 token 都做 OR LIKE 匹配 tokens 列
        3. 匹配 token 数越多越相关（ORDER BY 匹配数 DESC）
        """
        try:
            # query 分词
            q_tokens = self._tokenize(query).split()
            if not q_tokens:
                return []

            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row

            # 每个 token 都做 OR 匹配 tokens 列
            like_clauses = " OR ".join(["tokens LIKE ?" for _ in q_tokens])
            params = [f"%{t}%" for t in q_tokens]

            filters = []
            filter_params: list[object] = []
            if session_id:
                filters.append("session_id = ?")
                filter_params.append(session_id)
            if bot_id is not None:
                filters.append("(bot_id = ? OR bot_id IS NULL OR bot_id = '')")
                filter_params.append(bot_id)
                filters.append("(user_id = ? OR user_id IS NULL)")
                filter_params.append(user_id)
            if not include_archived:
                filters.append("(archived IS NULL OR archived = 0)")
            filter_sql = " AND ".join(filters)
            where_suffix = f" AND {filter_sql}" if filter_sql else ""

            if session_id or bot_id is not None or not include_archived:
                sql = f"""
                    SELECT id, summary, content, session_id, importance, confidence,
                           ({' + '.join(['(CASE WHEN tokens LIKE ? THEN 1 ELSE 0 END)' for _ in q_tokens])}) AS match_count
                    FROM episodic_memory
                    WHERE ({like_clauses}){where_suffix}
                    ORDER BY match_count DESC, importance DESC, confidence DESC, decay_score DESC, created_at DESC
                    LIMIT ?
                """
                cursor = conn.execute(sql, params * 2 + filter_params + [top_k])
            else:
                sql = f"""
                    SELECT id, summary, content, session_id, importance, confidence,
                           ({' + '.join(['(CASE WHEN tokens LIKE ? THEN 1 ELSE 0 END)' for _ in q_tokens])}) AS match_count
                    FROM episodic_memory
                    WHERE {like_clauses}
                    ORDER BY match_count DESC, importance DESC, confidence DESC, decay_score DESC, created_at DESC
                    LIMIT ?
                """
                cursor = conn.execute(sql, params * 2 + [top_k])

            rows = cursor.fetchall()
            self._mark_recalled(conn, [r["id"] for r in rows])
            conn.close()
            return [dict(r) for r in rows] if rows else []
        except Exception:
            return []

    def _chroma_recall(self, query: str, top_k: int,
                       session_id: Optional[str] = None) -> list[dict]:
        """Chroma 向量召回"""
        try:
            collection = self._get_chroma()
            query_embedding = self._get_embedding(query)
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where={"session_id": session_id} if session_id else None
            )
            episodes = []
            if results and results.get("documents"):
                for i, doc in enumerate(results["documents"][0]):
                    meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                    episodes.append({
                        "summary": meta.get("summary", ""),
                        "content": doc,
                        "session_id": meta.get("session_id", ""),
                    })
            return episodes
        except Exception:
            return []

    def _fallback_recall(self, query: str, top_k: int,
                         session_id: Optional[str] = None,
                         bot_id: Optional[str] = None,
                         user_id: str = "default_user",
                         include_archived: bool = False) -> list[dict]:
        """summary/content 直接 LIKE 兜底"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        words = re.findall(r'[\u4e00-\u9fa5]{2,4}', query)
        if not words:
            words = [query.strip()[:4]] if query.strip() else []

        like_clauses = " OR ".join(
            ["(summary LIKE ? OR content LIKE ?)" for _ in words]
        )
        params = [f"%{w}%" for w in words for _ in range(2)]

        filters = []
        filter_params: list[object] = []
        if session_id:
            filters.append("session_id = ?")
            filter_params.append(session_id)
        if bot_id is not None:
            filters.append("(bot_id = ? OR bot_id IS NULL OR bot_id = '')")
            filter_params.append(bot_id)
            filters.append("(user_id = ? OR user_id IS NULL)")
            filter_params.append(user_id)
        if not include_archived:
            filters.append("(archived IS NULL OR archived = 0)")
        filter_sql = " AND ".join(filters)
        where_suffix = f" AND {filter_sql}" if filter_sql else ""

        if filters:
            cursor = conn.execute(f"""
                SELECT id, summary, content, session_id, importance, confidence
                FROM episodic_memory
                WHERE ({like_clauses}){where_suffix}
                ORDER BY importance DESC, confidence DESC, decay_score DESC, created_at DESC
                LIMIT ?
            """, params + filter_params + [top_k])
        else:
            cursor = conn.execute(f"""
                SELECT id, summary, content, session_id, importance, confidence
                FROM episodic_memory
                WHERE {like_clauses}
                ORDER BY importance DESC, confidence DESC, decay_score DESC, created_at DESC
                LIMIT ?
            """, params + [top_k])

        rows = cursor.fetchall()
        self._mark_recalled(conn, [r["id"] for r in rows])
        conn.close()
        return [dict(r) for r in rows] if rows else []

    def _mark_recalled(self, conn: sqlite3.Connection, ids: list[int]):
        if not ids:
            return
        now = datetime.now().isoformat()
        conn.executemany(
            "UPDATE episodic_memory SET recall_count = COALESCE(recall_count, 0) + 1, last_recalled_at = ? WHERE id = ?",
            [(now, memory_id) for memory_id in ids],
        )
        conn.commit()

    async def archive_low_value(self, *, bot_id: str, user_id: str = "default_user"):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE episodic_memory
                SET archived = 1
                WHERE (bot_id = ? OR bot_id IS NULL OR bot_id = '')
                  AND (user_id = ? OR user_id IS NULL)
                  AND COALESCE(importance, 0) < 0.35
                  AND COALESCE(recall_count, 0) = 0
                """,
                (bot_id, user_id),
            )
            await db.commit()

    def list_recent(self, limit: int = 20) -> list[dict]:
        """返回最近的情景记忆片段"""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("""
            SELECT id, session_id, summary, content, importance, created_at
            FROM episodic_memory
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()
        conn.close()
        return [{"id": str(r[0]), "session_id": r[1], "summary": r[2],
                 "content": r[3], "importance": r[4], "created_at": r[5]} for r in rows]

    async def close(self):
        pass
