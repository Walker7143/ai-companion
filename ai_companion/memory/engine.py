"""
三层记忆引擎

记忆结构：
- working_memory:  SQLite会话表，当前对话上下文（摘要+原始消息）
- episodic_memory: SQLite事件表 + Chroma向量库，重要情景片段
- semantic_memory: SQLite事实表，用户画像和偏好

数据流：
  handle_message(user_input)
    → _check_and_compress()    检查并触发压缩
    → load_context()           加载三层记忆，构建 context dict
    → llm.chat(messages)       LLM 对话
    → on_message()             存储本轮 + 异步抽取新记忆
"""

import asyncio
import json
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

import aiosqlite

from .stores.episodic import EpisodicStore
from .stores.semantic import SemanticStore
from .stores.working import WorkingMemoryStore

# 上下文压缩器（可选）
try:
    from ..context import ContextCompressor
    CONTEXT_COMPRESSOR_AVAILABLE = True
except ImportError:
    CONTEXT_COMPRESSOR_AVAILABLE = False
    ContextCompressor = None


class MemoryEngine:
    """
    三层记忆引擎。

    路径约定：
    - memory_dir: Bot 数据根目录（应传入 data/bots 级别，不要包含 bot_id）
    - 实际存储路径为: memory_dir / bot_id / "memory"
      （即 data/bots/{bot_id}/memory/）

    示例：
        # 正确：传入根目录
        engine = MemoryEngine(bot_id="suqing", memory_dir=Path("data/bots"))
        # 实际路径: data/bots/suqing/memory/

        # 错误：传入包含 bot_id 的路径（会导致路径重复）
        engine = MemoryEngine(bot_id="suqing", memory_dir=Path("data/bots/suqing"))
        # 实际路径: data/bots/suqing/suqing/memory/  (错误!)
    """

    # 默认阈值（可被 config 覆盖）
    DEFAULT_HARD_LIMIT_CHARS = 5000
    DEFAULT_SOFT_LIMIT_CHARS = 3000
    DEFAULT_MAX_WORKING_TURNS = 20
    DEFAULT_MAX_SUMMARIES = 5  # 摘要最多保留条数，防止过多层累积

    # 压缩摘要 prompt（固定模板，不调 system prompt）
    COMPRESS_PROMPT = """以下是对话历史，请压缩成一段连贯的摘要，保留所有重要信息：
---
{old_messages_text}
---
摘要："""

    def __init__(self, bot_id: str, memory_dir: Path, config: Optional[dict] = None,
                 persona_backstory_path: str = None):
        self.bot_id = bot_id
        self.memory_dir = Path(memory_dir) / bot_id / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        self.config = config or {}

        # 从配置读取阈值（无则用默认值）
        self.hard_limit = self.config.get("hard_limit_chars", self.DEFAULT_HARD_LIMIT_CHARS)
        self.soft_limit = self.config.get("soft_limit_chars", self.DEFAULT_SOFT_LIMIT_CHARS)
        self.max_working_turns = self.config.get("max_working_turns", self.DEFAULT_MAX_WORKING_TURNS)
        self.max_summaries = self.config.get("max_summaries", self.DEFAULT_MAX_SUMMARIES)

        # embedding 配置
        emb_cfg = self.config
        embedding_mode = emb_cfg.get("embedding", "none")
        embedding_model = emb_cfg.get("embedding_model", "all-MiniLM-L6-v2")
        self.semantic_char_limit = emb_cfg.get("semantic_char_limit", 4400)

        self.working = WorkingMemoryStore(
            self.memory_dir / "working.db",
            soft_limit=self.soft_limit,
            hard_limit=self.hard_limit,
        )
        self.episodic = EpisodicStore(
            self.memory_dir / "episodic.db",
            self.memory_dir / "chroma",
            embedding_mode=embedding_mode,
            encoder_model=embedding_model,
        )
        self.semantic = SemanticStore(
            self.memory_dir / "semantic.db",
            max_chars=self.semantic_char_limit,
            persona_backstory_path=persona_backstory_path,
        )

        self._session_id: Optional[str] = None
        self._summarizer: Optional[object] = None
        self._compress_task: Optional[asyncio.Task] = None

        # 上下文压缩器（默认关闭，保持向后兼容）
        context_cfg = self.config.get("context", {}).get("compressor", {})
        if CONTEXT_COMPRESSOR_AVAILABLE and context_cfg.get("enabled", False):
            self._compressor = ContextCompressor(context_cfg)
            logger.info(f"[MemoryEngine] ContextCompressor 已启用")
        else:
            self._compressor = None

    def set_summarizer(self, summarizer):
        """注入 LLM 适配器（用于压缩摘要和语义抽取）"""
        self._summarizer = summarizer
        self.semantic.set_summarizer(summarizer)
        self.episodic.set_summarizer(summarizer)

    def start_session(self, session_id: str = None):
        self._session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.working.start_session(self._session_id)
        # 重置上下文压缩器
        if self._compressor:
            self._compressor.reset()

    # ── 公开接口 ─────────────────────────────────────────────

    async def init(self):
        """初始化所有 store"""
        await self.working.init()
        await self.episodic.init()
        await self.semantic.init()

    async def load_context(self, current_input: str) -> dict:
        """
        构建消息上下文，返回 dict：
        {
          "working_history": [...],   # 工作记忆消息列表（摘要正序+原始消息正序）
          "episodic_recall": [...],    # 情景记忆召回片段
          "semantic_facts": {...},     # 语义记忆（用户画像）
          "system_suffix": str,         # 拼入 system prompt 的记忆摘要
        }
        """
        sid = self._session_id or self.working.current_session
        logger.info(f"[Memory]  load_context called, sid={sid!r}, _session_id={self._session_id!r}, working.current={self.working.current_session!r}")

        # 工作记忆：摘要(正序) + 原始消息(正序)
        working = self.working.load_context(sid, max_working_turns=self.max_working_turns)

        # 情景记忆：基于当前输入召回（带 session_id 过滤，当前会话优先）
        episodic = self.episodic.recall(current_input, top_k=3, session_id=sid)

        # 语义记忆：跨会话聚合（用户画像，跨所有会话）
        facts = await self.semantic.get_all_facts()
        logger.info(f"[Memory]  load_context 召回语义记忆: {facts}")

        # 构建 system prompt 追加内容
        suffix_parts = []
        if facts:
            facts_str = "；".join([f"{k}={v}" for k, v in facts.items()])
            suffix_parts.append(f"你已了解用户的事实：{facts_str}")
        if episodic:
            moments_str = " | ".join([m["summary"][:100] for m in episodic])
            suffix_parts.append(f"相关记忆：{moments_str}")

        return {
            "working_history": working,
            "episodic_recall": episodic,
            "semantic_facts": facts,
            "system_suffix": "\n".join(suffix_parts),
        }

    async def on_message(self, user_input: str, llm_output: str):
        """
        每条消息调用一次：
        1. 存储本轮对话到工作记忆
        2. 异步抽取并更新情景记忆和语义记忆
        """
        sid = self._session_id or self.working.current_session or "default"
        await self.working.append(
            user_input=user_input,
            bot_output=llm_output,
            session_id=sid
        )

        # 2. 获取最近 3 轮对话上下文（用于判断整体语气：撒娇/吵架/调侃等）
        recent = self.working.get_recent(sid, turns=3)
        ctx_parts = []
        for msg in reversed(recent):
            label = "用户" if msg["role"] == "user" else "助手"
            ctx_parts.append(f"{label}：{msg['content']}")
        conversation_context = "\n".join(ctx_parts)

        # 3. 并发抽取并更新情景和语义记忆（带 session_id 隔离）
        task = asyncio.gather(
            self.episodic.extract_and_store(user_input, llm_output, session_id=sid),
            self.semantic.extract_and_store(
                user_input, llm_output, session_id=sid,
                conversation_context=conversation_context
            ),
        )
        def _on_task_done(t):
            if t.cancelled():
                logger.info("[Memory] 抽取被取消")
            elif t.exception():
                exc = t.exception()
                logger.info(f"[Memory]  抽取异常: {type(exc).__name__}: {exc}")
                import traceback
                for e in (exc.exceptions if hasattr(exc, 'exceptions') else [exc]):
                    traceback.print_exception(type(e), e, e.__traceback__)
            else:
                logger.info(f"[Memory]  抽取完成: {t.result()}")
                self._log_attitude_write(t.result()[1])

        task.add_done_callback(_on_task_done)
        await task

    def _log_attitude_write(self, semantic_result):
        """attitude_score 写入日志（semantic 返回单个 dict 或 None）"""
        if isinstance(semantic_result, dict) and semantic_result.get("key") == "attitude_score":
            logger.info(f"[Memory]    attitude写入: {semantic_result}")

    async def maybe_compress(self):
        """
        检查是否需要压缩，触发同步或异步压缩。
        - HARD_LIMIT(>hard_limit): 同步压缩，阻塞等待完成
        - SOFT_LIMIT(>soft_limit): 后台异步压缩
        """
        health = self.working.get_session_health()
        total_chars = health.get("total_chars", 0)
        compression_count = health.get("compression_count", 0)

        if total_chars > self.hard_limit:
            # 硬上限：同步压缩
            await self._do_compress()
        elif compression_count >= 1 and total_chars > self.soft_limit:
            # 已压缩过 + 超过软限：再次压缩
            await self._do_compress()
        elif total_chars > self.soft_limit and self._compress_task is None:
            # 软上限（首次）：后台异步压缩
            self._compress_task = asyncio.create_task(self._do_compress())

    async def get_memory_status(self) -> dict:
        """返回当前记忆状态（供 /memory 命令使用）"""
        sid = self._session_id or self.working.current_session
        health = self.working.get_session_health(sid)
        turn_count = self.working.get_turn_count(sid)
        summaries_count = len(self.working.get_summaries(sid))
        episodic_count = self._count_episodes()
        fact_count = await self.semantic.get_fact_count()

        return {
            "session_id": sid,
            "working_turns": turn_count,
            "compression_count": health.get("compression_count", 0),
            "summaries_count": summaries_count,
            "episodic_count": episodic_count,
            "fact_count": fact_count,
            "health": health,
        }

    async def forget_fact(self, key: str):
        """删除指定语义记忆（供 /forget 命令使用）"""
        await self.semantic.delete_fact(key)

    async def close(self):
        if self._compress_task and not self._compress_task.done():
            await self._compress_task
        await self.working.close()
        await self.episodic.close()
        await self.semantic.close()

    # ── 内部方法 ─────────────────────────────────────────────

    async def _do_compress(self):
        """执行压缩"""
        # 如果启用了 ContextCompressor，使用新压缩逻辑
        if self._compressor is not None and self._summarizer is not None:
            await self._do_compress_with_context()
            return

        # 使用原有压缩逻辑
        if self._summarizer is None:
            await self.working.compress(session_id=self._session_id, summarizer=None)
        else:
            summarizer = self._summarizer

            # 构建 summarizer 包装
            class _Summarizer:
                async def summarize_old_conversation(self, text: str) -> str:
                    prompt = MemoryEngine.COMPRESS_PROMPT.format(
                        old_messages_text=text
                    )
                    response = await summarizer.chat(
                        messages=[{"role": "user", "content": prompt}],
                        system_prompt=None,
                    )
                    # 统一处理：dict (有 content/reasoning_content) 或 str
                    raw = response.get("content") or response.get("reasoning_content") if isinstance(response, dict) else str(response)
                    return raw[:500] if raw else text[:200]

            await self.working.compress(
                session_id=self._session_id,
                summarizer=_Summarizer()
            )

    async def _do_compress_with_context(self):
        """使用 ContextCompressor 执行压缩"""
        # 获取所有消息
        messages = self.working.get_all_messages(self._session_id)
        if not messages:
            return

        # 构建 summarizer 包装
        summarizer = self._summarizer

        class _Summarizer:
            async def summarize_old_conversation(self, text: str) -> str:
                prompt = MemoryEngine.COMPRESS_PROMPT.format(
                    old_messages_text=text
                )
                response = await summarizer.chat(
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt=None,
                )
                raw = response.get("content") or response.get("reasoning_content") if isinstance(response, dict) else str(response)
                return raw[:500] if raw else text[:200]

        # 执行压缩
        success = await self._compressor.compress(messages, _Summarizer())
        if success:
            summary = self._compressor.get_last_summary()
            if summary:
                await self.working.apply_summary(summary, self._session_id)
                logger.info(f"[MemoryEngine] ContextCompressor 压缩成功，摘要长度: {len(summary)}")
        else:
            # 压缩未触发或失败，使用原有逻辑
            logger.info("[MemoryEngine] ContextCompressor 未触发压缩，回退到原有逻辑")
            await self.working.compress(session_id=self._session_id, summarizer=_Summarizer())

        self._compress_task = None

    def _count_episodes(self) -> int:
        """返回情景记忆条数"""
        try:
            conn = sqlite3.connect(self.episodic.db_path)
            cursor = conn.execute("SELECT COUNT(*) FROM episodic_memory")
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except Exception:
            return 0
