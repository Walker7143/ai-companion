"""
三层记忆引擎

记忆结构：
- working_memory:  SQLite会话表，当前对话上下文（摘要+原始消息）
- episodic_memory: SQLite事件表 + Chroma向量库，重要情景片段
- semantic_memory: SQLite事实表，用户画像和偏好
- user_understanding: JSON文件，用户可编辑的“对用户的理解”

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
from .stores.relationship import RelationshipStore
from .stores.semantic import SemanticStore
from .stores.user_understanding import UserUnderstandingStore
from .stores.working import WorkingMemoryStore
from .stores.daily import DailyMemoryStore, MemoryTurnContext
from .extractor import MemoryExtractor
from .governor import MemoryGovernor
from .maintenance import MemoryMaintenance
from .conscious import ConsciousContextBuilder
from .prompt_builder import MemoryPromptBuilder
from .retriever import MemoryRetriever
from ..context.tokenizer import TokenEstimator

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
        engine = MemoryEngine(bot_id="lin_wanqing", memory_dir=Path("data/bots"))
        # 实际路径: data/bots/lin_wanqing/memory/

        # 错误：传入包含 bot_id 的路径（会导致路径重复）
        engine = MemoryEngine(bot_id="lin_wanqing", memory_dir=Path("data/bots/lin_wanqing"))
        # 实际路径: data/bots/lin_wanqing/lin_wanqing/memory/  (错误!)
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
        self.user_id = (config or {}).get("user_id", "default_user")
        self.persona_backstory_path = persona_backstory_path
        self.memory_dir = Path(memory_dir) / bot_id / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        self.config = config or {}

        # 从配置读取阈值（无则用默认值）
        self.hard_limit = self.config.get("hard_limit_chars", self.DEFAULT_HARD_LIMIT_CHARS)
        self.soft_limit = self.config.get("soft_limit_chars", self.DEFAULT_SOFT_LIMIT_CHARS)
        self.max_working_turns = self.config.get("max_working_turns", self.DEFAULT_MAX_WORKING_TURNS)
        self.max_summaries = self.config.get("max_summaries", self.DEFAULT_MAX_SUMMARIES)
        daily_cfg = self.config.get("daily", {}) if isinstance(self.config.get("daily"), dict) else {}

        # embedding 配置
        emb_cfg = self.config
        embedding_mode = emb_cfg.get("embedding", "local")
        embedding_model = emb_cfg.get("embedding_model", "all-MiniLM-L6-v2")
        self.semantic_char_limit = emb_cfg.get("semantic_char_limit", 4400)
        self.prompt_char_limit = emb_cfg.get("prompt_char_limit", max(12000, self.semantic_char_limit))

        self.working = WorkingMemoryStore(
            self.memory_dir / "working.db",
            soft_limit=self.soft_limit,
            hard_limit=self.hard_limit,
        )
        self.daily = DailyMemoryStore(
            self.memory_dir / "daily.db",
            enabled=daily_cfg.get("enabled", True),
            retention_days=daily_cfg.get("retention_days", 10),
            recent_message_limit=daily_cfg.get("recent_message_limit", 16),
            summary_days=daily_cfg.get("summary_days", 10),
            max_prompt_chars=daily_cfg.get("max_prompt_chars", 1800),
            summarize_after_messages=daily_cfg.get("summarize_after_messages", 12),
            summarize_after_chars=daily_cfg.get("summarize_after_chars", 3000),
        )
        self.episodic = EpisodicStore(
            self.memory_dir / "episodic.db",
            self.memory_dir / "chroma",
            embedding_mode=embedding_mode,
            encoder_model=embedding_model,
        )
        self.user_understanding = UserUnderstandingStore(
            self.memory_dir / "user_understanding.json",
            max_value_chars=self.semantic_char_limit,
        )
        self.semantic = SemanticStore(
            self.memory_dir / "semantic.db",
            max_chars=self.semantic_char_limit,
            persona_backstory_path=persona_backstory_path,
            user_understanding=self.user_understanding,
        )
        self.relationship = RelationshipStore(
            self.memory_dir / "relationship.db",
            persona_backstory_path=persona_backstory_path,
        )
        self.extractor = MemoryExtractor()
        self.governor = MemoryGovernor(
            semantic_store=self.semantic,
            episodic_store=self.episodic,
            relationship_store=self.relationship,
            user_understanding=self.user_understanding,
        )
        self.retriever = MemoryRetriever(
            working_store=self.working,
            daily_store=self.daily,
            episodic_store=self.episodic,
            semantic_store=self.semantic,
            relationship_store=self.relationship,
            user_understanding=self.user_understanding,
            max_working_turns=self.max_working_turns,
            max_summaries=self.max_summaries,
        )
        self.prompt_builder = MemoryPromptBuilder(max_chars=self.prompt_char_limit)
        self.conscious_builder = ConsciousContextBuilder()
        self.maintenance = MemoryMaintenance(
            semantic_store=self.semantic,
            episodic_store=self.episodic,
            user_understanding=self.user_understanding,
            relationship_store=self.relationship,
            daily_store=self.daily,
        )

        self._session_id: Optional[str] = None
        self._summarizer: Optional[object] = None
        self._compress_task: Optional[asyncio.Task] = None
        self._maintenance_counter = 0

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
        self.extractor.set_summarizer(summarizer)

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
        await self.daily.init()
        await self.episodic.init()
        await self.user_understanding.init()
        self._seed_user_understanding_from_builtin()
        await self.semantic.init()
        await self.relationship.init()
        await self.maintenance.run_light(bot_id=self.bot_id, user_id=self.user_id, summarizer=self._summarizer)

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

        retrieved = await self.retriever.retrieve(
            current_input,
            bot_id=self.bot_id,
            user_id=self.user_id,
            session_id=sid,
        )
        logger.info(f"[Memory]  load_context 召回语义记忆: {retrieved.semantic_facts}")
        conscious = self.conscious_builder.build(retrieved, current_input)
        suffix, prompt_budget_diagnostics = self.prompt_builder.build_with_diagnostics(retrieved, conscious=conscious)
        diagnostics = self._build_prompt_diagnostics(
            retrieved=retrieved,
            system_suffix=suffix,
            conscious=conscious,
            prompt_budget_diagnostics=prompt_budget_diagnostics,
        )
        logger.info("[Memory] prompt diagnostics: %s", diagnostics)

        return {
            "working_history": retrieved.working_history,
            "episodic_recall": retrieved.episodic_recall,
            "semantic_facts": retrieved.semantic_facts,
            "relationship_state": retrieved.relationship_state,
            "daily_context": retrieved.daily_context,
            "memory_intent": retrieved.intent,
            "user_understanding": self.user_understanding.load(),
            "conscious_context": conscious.to_dict(),
            "memory_prompt_diagnostics": diagnostics,
            "system_suffix": suffix,
        }

    async def on_message(self, user_input: str, llm_output: str, turn_context: MemoryTurnContext | dict | None = None):
        """
        每条消息调用一次：
        1. 存储本轮对话到工作记忆
        2. 异步抽取并更新情景记忆和语义记忆
        """
        context = await self.record_turn(user_input, llm_output, turn_context=turn_context)
        await self.extract_turn_memory(user_input, llm_output, turn_context=context)

    async def record_turn(self, user_input: str, llm_output: str, turn_context: MemoryTurnContext | dict | None = None) -> MemoryTurnContext:
        """Persist the raw turn immediately so the next user message can see it."""
        current_sid = self._session_id or self.working.current_session or "default"
        context = self._normalize_turn_context(turn_context, session_id=current_sid)
        sid = context.session_id or current_sid
        user_id = context.user_id or self.user_id
        await self.working.append(
            user_input=user_input,
            bot_output=llm_output,
            session_id=sid,
            user_id=user_id,
            platform=context.platform,
        )
        await self.daily.append_turn(
            bot_id=self.bot_id,
            user_id=user_id,
            user_input=user_input,
            bot_output=llm_output,
            session_id=sid,
            context=context,
        )
        return context

    async def extract_turn_memory(self, user_input: str, llm_output: str, turn_context: MemoryTurnContext | dict | None = None):
        """Promote a recorded turn into long-term memory candidates."""
        current_sid = self._session_id or self.working.current_session or "default"
        context = self._normalize_turn_context(turn_context, session_id=current_sid)
        sid = context.session_id or current_sid
        user_id = context.user_id or self.user_id

        # 2. 获取最近 3 轮对话上下文（用于判断整体语气：撒娇/吵架/调侃等）
        recent = self.working.get_recent(sid, turns=3)
        ctx_parts = []
        for msg in reversed(recent):
            label = "用户" if msg["role"] == "user" else "助手"
            ctx_parts.append(f"{label}：{msg['content']}")
        conversation_context = "\n".join(ctx_parts)

        candidates = await self.extractor.extract(
            user_input,
            llm_output,
            session_id=sid,
            conversation_context=conversation_context,
        )
        task = asyncio.create_task(
            self.governor.apply(
                candidates,
                bot_id=self.bot_id,
                user_id=user_id,
                session_id=sid,
            )
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

        task.add_done_callback(_on_task_done)
        await task
        self._maintenance_counter += 1
        if self._maintenance_counter % 5 == 0:
            await self.maintenance.run_light(bot_id=self.bot_id, user_id=user_id, summarizer=self._summarizer)

    async def record_assistant_message(
        self,
        content: str,
        turn_context: MemoryTurnContext | dict | None = None,
    ):
        """Record an assistant-originated message that was not produced by a user turn."""
        content = str(content or "").strip()
        if not content:
            return
        current_sid = self._session_id or self.working.current_session or "default"
        context = self._normalize_turn_context(turn_context, session_id=current_sid)
        sid = context.session_id or current_sid
        user_id = context.user_id or self.user_id
        metadata_json = json.dumps(context.metadata or {}, ensure_ascii=False) if context.metadata else None

        await self.working.append_message(
            role="assistant",
            content=content,
            session_id=sid,
            user_id=user_id,
            platform=context.platform,
            metadata_json=metadata_json,
        )
        await self.daily.append_message(
            bot_id=self.bot_id,
            user_id=user_id,
            role="assistant",
            content=content,
            session_id=sid,
            context=context,
        )

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
        relationship = await self.relationship.get_state(bot_id=self.bot_id, user_id=self.user_id)
        daily_messages = self.daily.count_messages(bot_id=self.bot_id, user_id=self.user_id)
        daily_days = self.daily.count_recent_days(bot_id=self.bot_id, user_id=self.user_id)

        return {
            "session_id": sid,
            "working_turns": turn_count,
            "compression_count": health.get("compression_count", 0),
            "summaries_count": summaries_count,
            "episodic_count": episodic_count,
            "fact_count": fact_count,
            "relationship": relationship,
            "daily_messages": daily_messages,
            "daily_days": daily_days,
            "user_understanding_path": str(self.user_understanding.path),
            "user_understanding_auto_facts": self.user_understanding.auto_fact_count(),
            "health": health,
        }

    async def forget_fact(self, key: str):
        """删除指定语义记忆（供 /forget 命令使用）"""
        await self.semantic.delete_fact(key, bot_id=self.bot_id, user_id=self.user_id)
        await self.user_understanding.delete_auto_fact(key)

    async def close(self):
        if self._compress_task and not self._compress_task.done():
            await self._compress_task
        await self.working.close()
        await self.daily.close()
        await self.episodic.close()
        await self.semantic.close()
        await self.relationship.close()

    # ── 内部方法 ─────────────────────────────────────────────

    def _seed_user_understanding_from_builtin(self):
        project_root = Path(__file__).resolve().parents[2]
        seed_path = project_root / "ai_companion" / "data" / "bots" / self.bot_id / "memory" / "user_understanding.json"
        if not seed_path.exists():
            return
        if self.user_understanding.seed_manual_from(seed_path):
            logger.info("[Memory]  已从内置模板补充 user_understanding.manual: %s", seed_path)

    def _build_prompt_diagnostics(self, *, retrieved, system_suffix: str, conscious, prompt_budget_diagnostics: dict | None = None) -> dict:
        daily = retrieved.daily_context or {}
        daily_summaries = daily.get("summaries") if isinstance(daily.get("summaries"), list) else []
        daily_messages = daily.get("recent_messages") if isinstance(daily.get("recent_messages"), list) else []
        self_memory = daily.get("self_memory") if isinstance(daily.get("self_memory"), list) else []
        summary_chars = sum(
            len(str(item.get("content", "") or ""))
            for item in retrieved.working_history
            if isinstance(item, dict) and item.get("role") == "system"
        )
        recent_chars = sum(
            len(str(item.get("content", "") or ""))
            for item in retrieved.working_history
            if isinstance(item, dict) and item.get("role") != "system"
        )
        daily_chars = (
            len(json.dumps(daily_summaries, ensure_ascii=False))
            + len(json.dumps(daily_messages, ensure_ascii=False))
            + len(json.dumps(self_memory, ensure_ascii=False))
        )
        episodic_chars = sum(len(str(item.get("summary", "") or "")) for item in retrieved.episodic_recall)
        semantic_chars = sum(
            len(str(item.get("key", "") or "")) + len(str(item.get("value", "") or ""))
            for item in retrieved.semantic_items
        )
        conscious_text = conscious.render(max_chars=4000) if conscious is not None else ""
        working_summary_text = "\n".join(
            str(item.get("content", "") or "")
            for item in retrieved.working_history
            if isinstance(item, dict) and item.get("role") == "system"
        )
        working_recent_text = "\n".join(
            str(item.get("content", "") or "")
            for item in retrieved.working_history
            if isinstance(item, dict) and item.get("role") != "system"
        )
        daily_text = (
            json.dumps(daily_summaries, ensure_ascii=False)
            + json.dumps(daily_messages, ensure_ascii=False)
            + json.dumps(self_memory, ensure_ascii=False)
        )
        episodic_text = "\n".join(str(item.get("summary", "") or "") for item in retrieved.episodic_recall)
        semantic_text = "\n".join(
            f"{item.get('key', '')}: {item.get('value', '')}"
            for item in retrieved.semantic_items
        )
        diagnostics = {
            "intent": retrieved.intent,
            "system_suffix_chars": len(system_suffix or ""),
            "system_suffix_tokens_est": TokenEstimator.estimate(system_suffix or ""),
            "conscious_chars": len(conscious_text),
            "conscious_tokens_est": TokenEstimator.estimate(conscious_text),
            "working_summary_count": sum(1 for item in retrieved.working_history if isinstance(item, dict) and item.get("role") == "system"),
            "working_summary_chars": summary_chars,
            "working_summary_tokens_est": TokenEstimator.estimate(working_summary_text),
            "working_recent_message_count": sum(1 for item in retrieved.working_history if isinstance(item, dict) and item.get("role") != "system"),
            "working_recent_chars": recent_chars,
            "working_recent_tokens_est": TokenEstimator.estimate(working_recent_text),
            "daily_summary_count": len(daily_summaries),
            "daily_recent_message_count": len(daily_messages),
            "self_memory_count": len(self_memory),
            "daily_context_chars": daily_chars,
            "daily_context_tokens_est": TokenEstimator.estimate(daily_text),
            "episodic_count": len(retrieved.episodic_recall),
            "episodic_summary_chars": episodic_chars,
            "episodic_summary_tokens_est": TokenEstimator.estimate(episodic_text),
            "semantic_item_count": len(retrieved.semantic_items),
            "semantic_item_chars": semantic_chars,
            "semantic_item_tokens_est": TokenEstimator.estimate(semantic_text),
        }
        if prompt_budget_diagnostics:
            diagnostics["prompt_budget"] = prompt_budget_diagnostics
            diagnostics["prompt_block_count"] = len(prompt_budget_diagnostics.get("blocks", {}))
            diagnostics["prompt_truncated"] = bool(prompt_budget_diagnostics.get("truncated"))
        return diagnostics

    def _normalize_turn_context(self, value, *, session_id: str) -> MemoryTurnContext:
        if isinstance(value, MemoryTurnContext):
            if value.session_id is None:
                value.session_id = session_id
            if not value.user_id:
                value.user_id = self.user_id
            return value
        if isinstance(value, dict):
            metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
            return MemoryTurnContext(
                platform=str(value.get("platform") or "unknown"),
                session_id=value.get("session_id") or session_id,
                user_id=str(value.get("user_id") or self.user_id),
                channel_type=value.get("channel_type"),
                chat_id=value.get("chat_id"),
                message_id=value.get("message_id"),
                metadata=metadata,
            )
        return MemoryTurnContext(session_id=session_id, user_id=self.user_id)

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
