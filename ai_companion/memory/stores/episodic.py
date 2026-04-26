"""
情景记忆：SQLite + jieba 中文分词 + Chroma 向量库
存储重要情景片段，可跨会话语义召回

召回优先级：
1. SQLite jieba tokens LIKE 搜索（中文友好，高精度）
2. Chroma 向量语义召回（可选，语义相近但非精确）
3. summary/content 直接 LIKE（兜底）
"""

import aiosqlite
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
                    session_id TEXT,
                    summary TEXT,
                    content TEXT,
                    tokens TEXT,
                    importance REAL DEFAULT 0.6,
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
            await db.execute("CREATE INDEX IF NOT EXISTS idx_episodic_session ON episodic_memory(session_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_episodic_importance ON episodic_memory(importance DESC)")
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
        """每次都抽取，recall 负责过滤相关性"""
        return True

    async def extract_and_store(self, user_input: str, bot_output: str,
                                 session_id: Optional[str] = None):
        """抽取情景摘要（LLM提炼或简单截断），写入SQLite和Chroma"""
        sid = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")

        # LLM 提炼摘要（有 summarizer 时）
        if self._summarizer:
            summary = await self._llm_extract(user_input, bot_output)
        else:
            summary = self._simple_extract(user_input, bot_output)

        content = f"用户：{user_input}\n助手：{bot_output}"
        tokens = self._tokenize(summary) + " " + self._tokenize(content)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO episodic_memory (session_id, summary, content, tokens, importance)
                VALUES (?, ?, ?, ?, ?)
            """, (sid, summary, content, tokens, 0.6))
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
                    metadatas=[{"summary": summary, "session_id": sid}]
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
               session_id: Optional[str] = None) -> list[dict]:
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
        results = self._tokens_recall(query, top_k, session_id)
        if results:
            return results

        # 3. summary/content 直接 LIKE 降级兜底
        return self._fallback_recall(query, top_k, session_id)

    def _tokens_recall(self, query: str, top_k: int,
                       session_id: Optional[str] = None) -> list[dict]:
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

            if session_id:
                sql = f"""
                    SELECT summary, content, session_id,
                           ({' + '.join(['(CASE WHEN tokens LIKE ? THEN 1 ELSE 0 END)' for _ in q_tokens])}) AS match_count
                    FROM episodic_memory
                    WHERE ({like_clauses}) AND session_id = ?
                    ORDER BY match_count DESC, created_at DESC
                    LIMIT ?
                """
                cursor = conn.execute(sql, params * 2 + [session_id, top_k])
            else:
                sql = f"""
                    SELECT summary, content, session_id,
                           ({' + '.join(['(CASE WHEN tokens LIKE ? THEN 1 ELSE 0 END)' for _ in q_tokens])}) AS match_count
                    FROM episodic_memory
                    WHERE {like_clauses}
                    ORDER BY match_count DESC, created_at DESC
                    LIMIT ?
                """
                cursor = conn.execute(sql, params * 2 + [top_k])

            rows = cursor.fetchall()
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
                         session_id: Optional[str] = None) -> list[dict]:
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

        if session_id:
            cursor = conn.execute(f"""
                SELECT summary, content, session_id
                FROM episodic_memory
                WHERE ({like_clauses}) AND session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, params + [session_id, top_k])
        else:
            cursor = conn.execute(f"""
                SELECT summary, content, session_id
                FROM episodic_memory
                WHERE {like_clauses}
                ORDER BY created_at DESC
                LIMIT ?
            """, params + [top_k])

        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows] if rows else []

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
