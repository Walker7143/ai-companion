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
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

import aiosqlite

from .stores.episodic import EpisodicStore
from .stores.relationship import RelationshipStore
from .stores.memory_rollup import MemoryRollupStore
from .stores.semantic import SemanticStore
from .stores.user_understanding import UserUnderstandingStore
from .stores.vector import VectorMemoryDocument, VectorMemoryStore
from .stores.working import WorkingMemoryStore
from .stores.daily import DailyMemoryStore, MemoryTurnContext
from .extractor import MemoryExtractor
from .governor import MemoryGovernor
from .maintenance import MemoryMaintenance
from .activation import MemoryActivationPlanner
from .conscious import ConsciousContextBuilder
from .prompt_builder import MemoryPromptBuilder
from .retriever import MemoryRetriever
from .continuity import ContinuityContractBuilder, RelationshipProjectionService
from .dreaming import DreamingOrchestrator
from .scene_authority import build_scene_authority_diff, detect_user_scene_match
from .session_state import (
    RelationshipConsistencyChecker,
    ResponseStateConsistencyChecker,
    SessionStateDiff,
    SessionStateExtractor,
    SessionStateResolver,
    SessionStateStore,
    get_scene_snapshot,
    extract_scene_summary,
)
from ..context.tokenizer import TokenEstimator
from ..persona.evolution import PersonaEvolutionEngine

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
        self.persona_dir = Path(persona_backstory_path).parent if persona_backstory_path else None
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
            persona_backstory_path=persona_backstory_path,
        )
        self.vector = VectorMemoryStore(
            self.memory_dir / "vector",
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
            vector_store=self.vector,
        )
        self.relationship = RelationshipStore(
            self.memory_dir / "relationship.db",
            persona_backstory_path=persona_backstory_path,
        )
        self.rollups = MemoryRollupStore(self.memory_dir / "rollups.db", enabled=self.config.get("rollups", {}).get("enabled", True) if isinstance(self.config.get("rollups"), dict) else True)
        self.session_state = SessionStateStore(self.memory_dir / "session_state.db")
        self.extractor = MemoryExtractor()
        self.session_state_extractor = SessionStateExtractor()
        self.session_state_resolver = SessionStateResolver()
        self.response_state_checker = ResponseStateConsistencyChecker()
        self.relationship_state_checker = RelationshipConsistencyChecker()
        self.continuity_contract_builder = ContinuityContractBuilder()
        self.relationship_projection = RelationshipProjectionService()
        self.governor = MemoryGovernor(
            semantic_store=self.semantic,
            episodic_store=self.episodic,
            relationship_store=self.relationship,
            user_understanding=self.user_understanding,
        )
        scene_filter_enabled = bool(self.config.get("scene_filter_memory_enabled", True))
        self.retriever = MemoryRetriever(
            working_store=self.working,
            daily_store=self.daily,
            vector_store=self.vector,
            episodic_store=self.episodic,
            semantic_store=self.semantic,
            relationship_store=self.relationship,
            rollup_store=self.rollups,
            user_understanding=self.user_understanding,
            session_state_store=self.session_state,
            max_working_turns=self.max_working_turns,
            max_summaries=self.max_summaries,
            scene_filter_enabled=scene_filter_enabled,
        )
        self.prompt_builder = MemoryPromptBuilder(
            max_chars=self.prompt_char_limit,
            scene_filter_enabled=scene_filter_enabled,
        )
        self.activation_planner = MemoryActivationPlanner(
            self.config.get("activation", {}) if isinstance(self.config.get("activation"), dict) else {}
        )
        self.conscious_builder = ConsciousContextBuilder()
        self.maintenance = MemoryMaintenance(
            semantic_store=self.semantic,
            episodic_store=self.episodic,
            user_understanding=self.user_understanding,
            relationship_store=self.relationship,
            daily_store=self.daily,
            rollup_store=self.rollups,
        )
        self.dreaming = DreamingOrchestrator(self, self.config.get("dreaming", {}))
        self.evolution = PersonaEvolutionEngine(
            bot_id=self.bot_id,
            persona_dir=self.persona_dir,
            config=self.config.get("evolution", {}) if isinstance(self.config.get("evolution"), dict) else {},
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
        self.session_state_extractor.set_summarizer(summarizer)
        self.response_state_checker.set_summarizer(summarizer)
        self.relationship_state_checker.set_summarizer(summarizer)
        self.evolution.set_summarizer(summarizer)

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
        await self.vector.init()
        await self.user_understanding.init()
        self._seed_user_understanding_from_builtin()
        await self.semantic.init()
        await self.relationship.init()
        await self.rollups.init()
        await self.session_state.init()
        await self.dreaming.init()
        await self.maintenance.run_light(bot_id=self.bot_id, user_id=self.user_id, summarizer=self._summarizer)
        await self.rebuild_vector_index()

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
        awareness = await self.build_awareness(current_input, retrieved=retrieved)
        retrieved = awareness["retrieved"]
        conscious = awareness["conscious"]
        suffix, prompt_budget_diagnostics = self.prompt_builder.build_with_diagnostics(retrieved, conscious=conscious)
        scene_capsule = self._build_scene_capsule(retrieved.session_state)
        memory_authority = self._build_memory_authority(retrieved, scene_capsule=scene_capsule)
        memory_decision_trace = self._build_memory_decision_trace(
            retrieved,
            conscious=conscious,
            prompt_budget_diagnostics=prompt_budget_diagnostics,
            scene_capsule=scene_capsule,
        )
        diagnostics = self._build_prompt_diagnostics(
            retrieved=retrieved,
            system_suffix=suffix,
            conscious=conscious,
            prompt_budget_diagnostics=prompt_budget_diagnostics,
            scene_capsule=scene_capsule,
            memory_decision_trace=memory_decision_trace,
        )
        logger.info("[Memory] prompt diagnostics: %s", diagnostics)

        return {
            "working_history": retrieved.working_history,
            "episodic_recall": retrieved.episodic_recall,
            "vector_recall": retrieved.vector_recall,
            "semantic_facts": retrieved.semantic_facts,
            "turn_constraints": retrieved.turn_constraints,
            "relationship_state": retrieved.relationship_state,
            "daily_context": retrieved.daily_context,
            "session_state": retrieved.session_state,
            "scene_capsule": scene_capsule,
            "memory_intent": retrieved.intent,
            "user_understanding": self.user_understanding.load(),
            "memory_authority": memory_authority,
            "memory_decision_trace": memory_decision_trace,
            "memory_activation_plan": retrieved.activation_plan.to_dict() if retrieved.activation_plan else {},
            "continuity_contract": retrieved.continuity_contract.to_dict() if retrieved.continuity_contract else {},
            "conscious_context": conscious.to_dict(),
            "memory_awareness": awareness["awareness"],
            "memory_prompt_diagnostics": diagnostics,
            "evolution_diagnostics": self.evolution.get_diagnostics(),
            "evolution_refs": self.evolution.get_link_refs(limit=4),
            "system_suffix": suffix,
            "memory_continuity": {
                "session_state_count": len(retrieved.session_state or []),
                "daily_open_threads": retrieved.daily_context.get("open_threads", []) if isinstance(retrieved.daily_context, dict) else [],
                "daily_commitments": retrieved.daily_context.get("commitments", []) if isinstance(retrieved.daily_context, dict) else [],
                "relationship_label": retrieved.relationship_state.get("relationship_label") if isinstance(retrieved.relationship_state, dict) else None,
                "relationship_status": retrieved.relationship_state.get("relationship_status") if isinstance(retrieved.relationship_state, dict) else None,
                "scene_capsule": scene_capsule,
            },
        }

    async def build_awareness(
        self,
        current_input: str,
        *,
        intent: str | None = None,
        retrieved=None,
    ) -> dict[str, Any]:
        """Build the few memory lines that should feel active this turn."""
        if retrieved is None:
            sid = self._session_id or self.working.current_session
            retrieved = await self.retriever.retrieve(
                current_input,
                bot_id=self.bot_id,
                user_id=self.user_id,
                session_id=sid,
                intent=intent,
            )
        retrieved.activation_plan = self.activation_planner.build(retrieved, current_input)
        conscious = self.conscious_builder.build(retrieved, current_input)
        awareness = {
            "intent": retrieved.intent,
            "current_focus": conscious.current_focus,
            "emotional_read": conscious.emotional_read,
            "relationship_posture": conscious.relationship_posture,
            "active_memories": conscious.active_memory_details or conscious.active_memories,
            "avoid": conscious.avoid,
            "recall_style": conscious.recall_style,
            "activation_strategy": retrieved.activation_plan.strategy if retrieved.activation_plan else "",
        }
        return {
            "retrieved": retrieved,
            "conscious": conscious,
            "awareness": awareness,
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
        self.working.start_session(sid)
        self._session_id = sid
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
        relationship_state = await self.relationship.get_state(
            bot_id=self.bot_id,
            user_id=user_id,
        )
        bot_current_date = self._get_bot_current_date()
        await self.evolution.capture_turn(
            user_input=user_input,
            bot_output=llm_output,
            relationship_state=relationship_state,
            turn_context={
                "session_id": sid,
                "user_id": user_id,
                "platform": context.platform,
                "bot_current_date": bot_current_date,
            },
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
        turn_id = f"{sid}:{len(recent)}:{datetime.now().timestamp()}"
        active_states = await self.session_state.list_active_states(sid)
        state_diff = await self.session_state_extractor.extract(
            user_input=user_input,
            bot_output=llm_output,
            conversation_context=conversation_context,
            active_states=active_states,
        )
        state_diff = self._filter_scene_state_diff(
            state_diff,
            user_input=user_input,
            conversation_context=conversation_context,
        )
        deterministic_scene_diff = self._build_scene_authority_diff(
            user_input=user_input,
            bot_output=llm_output,
            conversation_context=conversation_context,
            active_states=active_states,
        )
        if deterministic_scene_diff.upserts or deterministic_scene_diff.invalidations:
            state_diff.upserts = [*deterministic_scene_diff.upserts, *state_diff.upserts]
            state_diff.invalidations = [*deterministic_scene_diff.invalidations, *state_diff.invalidations]
            state_diff.confidence_explanations = [
                *state_diff.confidence_explanations,
                *deterministic_scene_diff.confidence_explanations,
            ]
            state_diff.no_change = False
        session_state_result = await self.session_state_resolver.apply_diff(
            store=self.session_state,
            session_id=sid,
            diff=state_diff,
            evidence_turn_id=turn_id,
        )
        self._maintenance_counter += 1
        if self._maintenance_counter % 5 == 0:
            await self.maintenance.run_light(bot_id=self.bot_id, user_id=user_id, summarizer=self._summarizer)
            await self.rebuild_vector_index()
        latest_relationship_state = await self.relationship.get_state(
            bot_id=self.bot_id,
            user_id=user_id,
        )
        bot_current_date = self._get_bot_current_date()
        await self.evolution.capture_relationship_state(
            latest_relationship_state,
            turn_context={
                "session_id": sid,
                "user_id": user_id,
                "bot_current_date": bot_current_date,
            },
        )
        return session_state_result

    def evolution_summary(self) -> dict[str, Any]:
        return self.evolution.get_snapshot()

    def evolution_timeline(
        self,
        *,
        cursor: str | None = None,
        limit: int = 50,
        dimension: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        return self.evolution.get_timeline(
            cursor=cursor,
            limit=limit,
            dimension=dimension,
            status=status,
        )

    def evolution_event_detail(self, event_id: str) -> dict[str, Any] | None:
        return self.evolution.get_event_detail(event_id)

    def evolution_state_view(self) -> dict[str, Any]:
        return self.evolution.get_state_view()

    def evolution_config_view(self) -> dict[str, Any]:
        return self.evolution.get_config()

    async def evolution_reflect(self) -> dict[str, Any]:
        return await self.evolution.reflect(reason="manual_admin")

    async def evolution_rebuild(self) -> dict[str, Any]:
        relationship_state = await self.relationship.get_state(
            bot_id=self.bot_id,
            user_id=self.user_id,
        )
        life_events: list[dict[str, Any]] = []
        try:
            life_state_path = self.memory_dir.parent / "life_state.json"
            if life_state_path.exists():
                raw = json.loads(life_state_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    life_events = list(raw.get("major_life_events", []) or []) + list(raw.get("life_events", []) or [])
        except Exception:
            life_events = []
        return await self.evolution.rebuild(
            relationship_state=relationship_state,
            life_events=life_events,
        )

    async def evolution_apply_promotion(self, candidate_id: str) -> dict[str, Any]:
        return await self.evolution.apply_core_patch(candidate_id, approval_reason="manual_admin")

    async def evolution_reject_promotion(self, candidate_id: str, reason: str) -> dict[str, Any]:
        return await self.evolution.reject_promotion(candidate_id, reason)

    def _build_scene_authority_diff(
        self,
        *,
        user_input: str,
        bot_output: str,
        conversation_context: str,
        active_states: list | None = None,
    ) -> SessionStateDiff:
        snapshot = get_scene_snapshot(active_states or [], user_input=user_input)
        diff = build_scene_authority_diff(
            user_input=user_input,
            bot_output=bot_output,
            conversation_context=conversation_context,
            active_scene_context={
                "subject": snapshot.subject,
                "categories": sorted(snapshot.categories),
                "scene_names": sorted(snapshot.scene_names),
            },
        )
        return SessionStateDiff(
            upserts=diff.upserts,
            invalidations=diff.invalidations,
            no_change=diff.no_change,
            confidence_explanations=diff.confidence_explanations,
        )

    def _filter_scene_state_diff(
        self,
        diff: SessionStateDiff,
        *,
        user_input: str,
        conversation_context: str,
    ) -> SessionStateDiff:
        if not diff.upserts:
            return diff
        user_scene_match = detect_user_scene_match(
            user_input=user_input,
            conversation_context=conversation_context,
        )
        if user_scene_match is not None or _has_user_explicit_scene_diff(diff):
            return diff

        filtered_upserts = []
        filtered_any = False
        for item in diff.upserts:
            if not isinstance(item, dict):
                filtered_upserts.append(item)
                continue
            scope = str(item.get("scope") or "").strip()
            predicate = str(item.get("predicate") or "").strip()
            if scope == "current_scene" or scope.startswith("current_scene/"):
                filtered_any = True
                continue
            filtered_upserts.append(item)
        if not filtered_any:
            return diff
        return SessionStateDiff(
            upserts=filtered_upserts,
            confirmations=diff.confirmations,
            invalidations=diff.invalidations,
            no_change=diff.no_change and not filtered_upserts,
            confidence_explanations=[
                *list(diff.confidence_explanations),
                "filtered_scene_upserts_without_user_scene_evidence",
            ],
        )

    async def ensure_response_state_consistency(
        self,
        response: str,
        session_id: str,
        relationship_state: dict[str, Any] | None = None,
        *,
        user_input: str = "",
    ) -> tuple[str, dict[str, Any]]:
        active_states = await self.session_state.list_active_states(session_id) if session_id else []
        check = await self.response_state_checker.check(response, active_states, user_input=user_input)
        if not check.get("consistent", True):
            response = await self.response_state_checker.rewrite(response, active_states, check.get("conflicts") or [])

        relationship_check = await self.relationship_state_checker.check(response, relationship_state)
        if not relationship_check.get("consistent", True):
            response = await self.relationship_state_checker.rewrite(response, relationship_state, relationship_check.get("conflicts") or [])

        merged = {
            "consistent": bool(check.get("consistent", True) and relationship_check.get("consistent", True)),
            "severity": relationship_check.get("severity") if not relationship_check.get("consistent", True) else check.get("severity", "none"),
            "conflicts": [*(check.get("conflicts") or []), *(relationship_check.get("conflicts") or [])],
            "rewrite_guidance": relationship_check.get("rewrite_guidance") or check.get("rewrite_guidance") or "",
            "relationship_consistency": relationship_check,
            "session_state_consistency": check,
        }
        return response, merged

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
        vector_count = self.vector.count(bot_id=self.bot_id, user_id=self.user_id)
        relationship = await self.relationship.get_state(bot_id=self.bot_id, user_id=self.user_id)
        rollup_count = len(await self.rollups.get_latest_by_scope(bot_id=self.bot_id, user_id=self.user_id, scope="global", limit=20)) if self.rollups else 0
        daily_messages = self.daily.count_messages(bot_id=self.bot_id, user_id=self.user_id)
        daily_days = self.daily.count_recent_days(bot_id=self.bot_id, user_id=self.user_id)
        daily_context = self.daily.get_recent_context(bot_id=self.bot_id, user_id=self.user_id, intent="planning")
        facts = await self.semantic.list_facts(
            bot_id=self.bot_id,
            user_id=self.user_id,
            min_confidence=0.0,
            include_archived=False,
            limit=80,
        )
        fact_history = await self.semantic.list_fact_history(
            bot_id=self.bot_id,
            user_id=self.user_id,
            limit=8,
        )
        recent_episodes = self.episodic.list_recent(limit=6, bot_id=self.bot_id, user_id=self.user_id)
        lifecycle_events = await self.semantic.list_lifecycle_events(
            bot_id=self.bot_id,
            user_id=self.user_id,
            limit=16,
        )
        active_session_states = []
        current_session = self._session_id or self.working.current_session
        if current_session:
            active_session_states = [state.to_dict() for state in await self.session_state.list_active_states(current_session)]
        scene_capsule = self._build_scene_capsule(active_session_states)

        trust_view = self._build_memory_trust_view(
            facts=facts,
            relationship=relationship,
            daily_context=daily_context,
            recent_episodes=recent_episodes,
            fact_history=fact_history,
            lifecycle_events=lifecycle_events,
            session_state=active_session_states,
            scene_capsule=scene_capsule,
        )
        continuity_contract = self.continuity_contract_builder.build(
            current_input="",
            retrieved=type(
                "_StatusRetrieved",
                (),
                {
                    "relationship_state": relationship or {},
                    "turn_constraints": [],
                    "session_state": active_session_states or [],
                    "daily_context": daily_context or {},
                },
            )(),
        )
        relationship_projection = self.relationship_projection.build_projection(relationship or {})

        memory_layers = self._build_status_memory_layers(
            working_turns=turn_count,
            daily_messages=daily_messages,
            daily_days=daily_days,
            session_state=active_session_states,
            fact_count=fact_count,
            episodic_count=episodic_count,
            relationship=relationship,
            vector_count=vector_count,
            rollup_count=rollup_count,
            dreaming_status=await self.dreaming.status(),
            scene_capsule=scene_capsule,
        )
        status_authority = {
            "mode": "single_owner",
            "owner_user_id": self.user_id or "default_user",
            "summary": "当前安装按单主人记忆运行；default_user 是 owner profile 的内部标识。",
            "policy": [
                "short_term_state_overrides_long_term_recall",
                "manual_user_understanding_overrides_auto_fact",
                "committed_relationship_overrides_single_turn_tone",
                "vector_and_rollup_are_retrieval_hints_not_authority",
            ],
        }

        return {
            "session_id": sid,
            "working_turns": turn_count,
            "compression_count": health.get("compression_count", 0),
            "summaries_count": summaries_count,
            "episodic_count": episodic_count,
            "fact_count": fact_count,
            "vector_count": vector_count,
            "relationship": relationship,
            "rollup_count": rollup_count,
            "daily_messages": daily_messages,
            "daily_days": daily_days,
            "daily_open_threads": daily_context.get("open_threads", []) if isinstance(daily_context, dict) else [],
            "daily_commitments": daily_context.get("commitments", []) if isinstance(daily_context, dict) else [],
            "memory_trust_view": trust_view,
            "memory_layers": memory_layers,
            "memory_authority": status_authority,
            "scene_capsule": scene_capsule,
            "continuity_contract": continuity_contract.to_dict(),
            "relationship_projection": relationship_projection,
            "evolution_refs": self.evolution.get_link_refs(limit=4),
            "recent_lifecycle_events": lifecycle_events,
            "fact_history": fact_history,
            "user_understanding_path": str(self.user_understanding.path),
            "user_understanding_auto_facts": self.user_understanding.auto_fact_count(),
            "health": health,
            "dreaming": memory_layers.get("operations", {}).get("dreaming", {}),
        }

    def _build_memory_trust_view(
        self,
        *,
        facts: list[dict],
        relationship: dict,
        daily_context: dict,
        recent_episodes: list[dict],
        fact_history: list[dict],
        lifecycle_events: list[dict],
        session_state: list[dict],
        scene_capsule: dict | None = None,
    ) -> dict:
        recent_facts = sorted(
            [fact for fact in facts if not fact.get("archived")],
            key=lambda item: str(item.get("updated_at") or ""),
            reverse=True,
        )
        stable_facts = [
            fact for fact in recent_facts
            if _float(fact.get("confidence")) >= 0.85 or fact.get("manual_override") or fact.get("last_confirmed_at")
        ]
        pending = [
            fact for fact in recent_facts
            if 0.0 < _float(fact.get("confidence")) < 0.78
            and not fact.get("manual_override")
            and not fact.get("last_confirmed_at")
        ]
        archived_events = [
            item for item in lifecycle_events
            if item.get("action") in {"archive", "supersede", "conflict_skip"}
        ]
        daily_recent = daily_context.get("recent_messages") if isinstance(daily_context.get("recent_messages"), list) else []
        stable_keys = {str(fact.get("key") or "") for fact in stable_facts}
        pending_keys = {str(fact.get("key") or "") for fact in pending}
        recently_remembered = []
        for item in daily_recent[-6:]:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            recently_remembered.append(
                {
                    "type": "recent_message",
                    "key": f"{item.get('platform') or 'unknown'}:{item.get('role') or 'message'}",
                    "value": content[:120],
                    "confidence": None,
                    "source": "daily",
                    "updated_at": item.get("created_at"),
                }
            )
        recently_remembered.extend(
            _fact_view_item(fact)
            for fact in recent_facts
            if str(fact.get("key") or "") not in stable_keys
            and str(fact.get("key") or "") not in pending_keys
        )
        recently_remembered.extend(_episode_view_item(item) for item in recent_episodes[:4])

        relationship_moments = relationship.get("key_moments") if isinstance(relationship.get("key_moments"), list) else []
        for moment in relationship_moments[-4:]:
            text = str(moment or "").strip()
            if not text:
                continue
            recently_remembered.append(
                {
                    "type": "relationship_moment",
                    "key": "关系关键时刻",
                    "value": text[:160],
                    "confidence": relationship.get("stage_confidence"),
                    "source": "relationship",
                    "updated_at": relationship.get("updated_at"),
                }
            )

        relationship_anchor = {}
        if relationship:
            relationship_anchor = {
                "label": relationship.get("relationship_label"),
                "status": relationship.get("relationship_status"),
                "score": relationship.get("relationship_score"),
                "narrative": relationship.get("relationship_narrative"),
                "guidance": relationship.get("interaction_guidance"),
                "key_moments": relationship.get("key_moments") or [],
                "open_threads": relationship.get("open_emotional_threads") or [],
            }

        return {
            "recently_remembered": _dedupe_view_items(recently_remembered)[:8],
            "stable_understanding": [_fact_view_item(fact) for fact in stable_facts[:8]],
            "relationship_anchor": relationship_anchor,
            "session_state": [
                {
                    "state_id": item.get("state_id"),
                    "scope": item.get("scope"),
                    "subject": item.get("subject"),
                    "predicate": item.get("predicate"),
                    "value": item.get("value"),
                    "confidence": item.get("confidence"),
                    "status": item.get("status"),
                    "updated_at": item.get("updated_at"),
                    "source_kind": item.get("source_kind"),
                }
                for item in (session_state or [])[:8]
            ],
            "scene_capsule": scene_capsule or {},
            "pending_confirmation": [_fact_view_item(fact) for fact in pending[:8]],
            "corrected_memories": [
                {
                    "key": item.get("key"),
                    "old_value": item.get("old_value"),
                    "new_value": item.get("new_value"),
                    "reason": item.get("reason"),
                    "superseded_at": item.get("superseded_at"),
                }
                for item in fact_history[:8]
            ],
            "archived_or_suppressed": [
                {
                    "type": item.get("memory_type"),
                    "key": item.get("memory_key"),
                    "action": item.get("action"),
                    "reason": item.get("reason"),
                    "created_at": item.get("created_at"),
                }
                for item in archived_events[:8]
            ],
            "open_threads": list(daily_context.get("open_threads") or [])[:6] if isinstance(daily_context, dict) else [],
            "commitments": list(daily_context.get("commitments") or [])[:6] if isinstance(daily_context, dict) else [],
        }

    def _build_status_memory_layers(
        self,
        *,
        working_turns: int,
        daily_messages: int,
        daily_days: int,
        session_state: list[dict],
        fact_count: int,
        episodic_count: int,
        relationship: dict,
        vector_count: int,
        rollup_count: int,
        dreaming_status: dict,
        scene_capsule: dict,
    ) -> dict:
        relationship_label = relationship.get("relationship_label") if isinstance(relationship, dict) else ""
        return {
            "authority": {
                "summary": (
                    f"短期 working={working_turns} 轮，daily={daily_messages} 条/{daily_days} 天，"
                    f"session_state={len(session_state)} 条；长期 semantic={fact_count} 条，"
                    f"episodic={episodic_count} 条，relationship={relationship_label or '未标注'}。"
                ),
                "short_term": {
                    "working_turns": working_turns,
                    "daily_messages": daily_messages,
                    "daily_days": daily_days,
                    "session_state_count": len(session_state),
                    "scene_active": bool(scene_capsule.get("active")),
                },
                "long_term": {
                    "semantic_fact_count": fact_count,
                    "episodic_count": episodic_count,
                    "relationship_label": relationship_label,
                },
            },
            "projection": {
                "summary": f"UserUnderstanding 为长期理解投影，vector={vector_count} 条索引，rollup={rollup_count} 条摘要。",
                "user_understanding": {
                    "path": str(self.user_understanding.path),
                    "auto_fact_count": self.user_understanding.auto_fact_count(),
                    "role": "editable_projection",
                },
                "vector_index": {"count": vector_count, "role": "retrieval_index"},
                "rollups": {"count": rollup_count, "role": "summary_projection"},
            },
            "operations": {
                "summary": "Governor 写入权威层；Maintenance 做轻量维护；Dreaming 是用户可见整理操作。",
                "dreaming": dreaming_status or {},
            },
            "explainability": {
                "summary": "Trust View 解释当前状态；Dreaming Report 解释单次整理；Prompt diagnostics 解释本轮注入。",
                "trust_view": True,
                "prompt_diagnostics": True,
                "scene_capsule": bool(scene_capsule.get("active")),
            },
        }

    async def forget_fact(self, key: str):
        """删除指定语义记忆（供 /forget 命令使用）"""
        await self.semantic.delete_fact(key, bot_id=self.bot_id, user_id=self.user_id)
        await self.user_understanding.delete_auto_fact(key)

    async def rebuild_vector_index(self) -> dict:
        """Rebuild unified vector recall from authoritative memory stores."""
        if not self.vector.enabled():
            return {"enabled": False, "indexed": 0}
        docs: list[VectorMemoryDocument] = []
        facts = await self.semantic.list_facts(
            bot_id=self.bot_id,
            user_id=self.user_id,
            include_archived=False,
            limit=None,
        )
        for fact in facts:
            key = str(fact.get("key") or "").strip()
            value = str(fact.get("value") or "").strip()
            if not key or not value:
                continue
            category = str(fact.get("category") or "general")
            docs.append(
                VectorMemoryDocument(
                    source_type="semantic_fact",
                    source_id=key,
                    text=f"[{category}] {key}: {value}",
                    bot_id=self.bot_id,
                    user_id=self.user_id,
                    category=category,
                    importance=max(0.3, min(1.0, float(fact.get("confidence") or 0.7))),
                    sensitivity="sensitive" if category in {"boundaries", "sensitive", "health"} else "normal",
                    created_at=fact.get("created_at"),
                    updated_at=fact.get("updated_at"),
                    metadata={
                        "confidence": float(fact.get("confidence") or 0.7),
                        "source": fact.get("source") or "",
                        "manual_override": bool(fact.get("manual_override")),
                    },
                )
            )
        docs.extend(self._user_understanding_vector_docs())
        docs.extend(self._daily_summary_vector_docs())
        docs.extend(await self._relationship_vector_docs())
        indexed = await self.vector.upsert_many(docs)
        logger.info("[Memory] unified vector index rebuilt: %s/%s docs", indexed, len(docs))
        return {"enabled": True, "indexed": indexed, "candidate_docs": len(docs)}

    async def index_life_state(self, life_state) -> dict:
        """Index bot life events without making LifeState depend on memory."""
        if not self.vector.enabled() or life_state is None:
            return {"enabled": False, "indexed": 0}
        docs: list[VectorMemoryDocument] = []
        for event in getattr(life_state, "life_events", []) or []:
            doc = self._life_event_vector_doc(event, source_type="life_event")
            if doc:
                docs.append(doc)
        for event in getattr(life_state, "major_life_events", []) or []:
            doc = self._life_event_vector_doc(event, source_type="major_life_event")
            if doc:
                docs.append(doc)
        indexed = await self.vector.upsert_many(docs)
        logger.info("[Memory] indexed life state into vector memory: %s/%s docs", indexed, len(docs))
        return {"enabled": True, "indexed": indexed, "candidate_docs": len(docs)}

    async def close(self):
        if self._compress_task and not self._compress_task.done():
            await self._compress_task
        await self.working.close()
        await self.daily.close()
        await self.episodic.close()
        self.vector.close()
        await self.semantic.close()
        await self.relationship.close()
        await self.rollups.close()
        await self.dreaming.close()

    # ── 内部方法 ─────────────────────────────────────────────

    def _seed_user_understanding_from_builtin(self):
        project_root = Path(__file__).resolve().parents[2]
        seed_path = project_root / "ai_companion" / "data" / "bots" / self.bot_id / "memory" / "user_understanding.json"
        if not seed_path.exists():
            return
        if self.user_understanding.seed_manual_from(seed_path):
            logger.info("[Memory]  已从内置模板补充 user_understanding.manual: %s", seed_path)

    def _user_understanding_vector_docs(self) -> list[VectorMemoryDocument]:
        data = self.user_understanding.load()
        docs: list[VectorMemoryDocument] = []
        layered = data.get("layered") if isinstance(data.get("layered"), dict) else {}
        updated_at = str(data.get("updated_at") or layered.get("generated_at") or "")
        for section_path, value in _flatten_understanding(data):
            text = _understanding_text(section_path, value)
            if not text:
                continue
            docs.append(
                VectorMemoryDocument(
                    source_type="user_understanding",
                    source_id=section_path,
                    text=text,
                    bot_id=self.bot_id,
                    user_id=self.user_id,
                    category=_understanding_category(section_path),
                    importance=_understanding_importance(section_path),
                    sensitivity=_understanding_sensitivity(section_path),
                    updated_at=updated_at,
                    metadata={"section_path": section_path},
                )
            )
        return docs

    def _daily_summary_vector_docs(self) -> list[VectorMemoryDocument]:
        docs: list[VectorMemoryDocument] = []
        for item in self.daily.list_summaries(bot_id=self.bot_id, user_id=self.user_id, limit=60):
            summary = str(item.get("summary") or "").strip()
            local_date = str(item.get("local_date") or "").strip()
            if not summary or not local_date:
                continue
            topics = _jsonish_list(item.get("topics") or item.get("topics_json"))
            open_threads = _jsonish_list(item.get("open_threads") or item.get("open_threads_json"))
            mood = _jsonish_list(item.get("mood") or item.get("mood_json"))
            parts = [
                f"{local_date}: {summary}",
                f"topics: {', '.join(topics)}" if topics else "",
                f"open_threads: {', '.join(open_threads)}" if open_threads else "",
                f"mood: {', '.join(mood)}" if mood else "",
            ]
            docs.append(
                VectorMemoryDocument(
                    source_type="daily_summary",
                    source_id=local_date,
                    text=" | ".join(part for part in parts if part),
                    bot_id=self.bot_id,
                    user_id=self.user_id,
                    category="daily_continuity",
                    importance=0.55,
                    sensitivity=_text_sensitivity(summary, topics + open_threads + mood),
                    created_at=local_date,
                    updated_at=str(item.get("updated_at") or local_date),
                    metadata={
                        "local_date": local_date,
                        "message_count": int(item.get("message_count") or 0),
                    },
                )
            )
        return docs

    async def _relationship_vector_docs(self) -> list[VectorMemoryDocument]:
        state = await self.relationship.get_state(bot_id=self.bot_id, user_id=self.user_id)
        narrative = str(state.get("relationship_narrative") or "").strip()
        posture = str(state.get("current_posture") or "").strip()
        guidance = str(state.get("interaction_guidance") or "").strip()
        key_moments = _jsonish_list(state.get("key_moments"))
        open_threads = _jsonish_list(state.get("open_emotional_threads"))
        parts = [
            narrative,
            f"current_posture: {posture}" if posture else "",
            f"interaction_guidance: {guidance}" if guidance else "",
            f"key_moments: {', '.join(key_moments[:5])}" if key_moments else "",
            f"open_emotional_threads: {', '.join(open_threads[:5])}" if open_threads else "",
        ]
        text = " | ".join(part for part in parts if part)
        if not text:
            return []
        return [
            VectorMemoryDocument(
                source_type="relationship_narrative",
                source_id="current",
                text=text,
                bot_id=self.bot_id,
                user_id=self.user_id,
                category="relationship",
                importance=0.85,
                sensitivity=_text_sensitivity(text, key_moments + open_threads),
                updated_at=str(state.get("updated_at") or ""),
                metadata={
                    "relationship_label": str(state.get("relationship_label") or ""),
                    "relationship_score": float(state.get("relationship_score") or 0),
                    "stage_confidence": float(state.get("stage_confidence") or 0),
                },
            )
        ]

    def _life_event_vector_doc(self, event, *, source_type: str) -> VectorMemoryDocument | None:
        data = event.to_dict() if hasattr(event, "to_dict") else dict(event or {})
        description = str(data.get("description") or "").strip()
        if not description:
            return None
        mood_tags = data.get("mood_tags") if isinstance(data.get("mood_tags"), list) else []
        parts = [
            description,
            f"mood: {data.get('mood_before') or ''}->{data.get('mood_after') or ''}".strip(),
            f"tags: {', '.join(str(item) for item in mood_tags)}" if mood_tags else "",
            f"topic: {data.get('topic_prompt')}" if data.get("topic_prompt") else "",
        ]
        text = " | ".join(part for part in parts if part)
        importance = float(data.get("importance") or 0)
        return VectorMemoryDocument(
            source_type=source_type,
            source_id=str(data.get("id") or data.get("timestamp") or description[:40]),
            text=text,
            bot_id=self.bot_id,
            user_id=self.user_id,
            category=str(data.get("scenario_category") or "life_event"),
            importance=max(0.35, min(1.0, importance / 10 if importance > 1 else importance or 0.5)),
            sensitivity="sensitive" if data.get("related_to_user") else "normal",
            created_at=str(data.get("timestamp") or ""),
            updated_at=str(data.get("timestamp") or ""),
            metadata={
                "shareable": bool(data.get("shareable")),
                "related_to_user": bool(data.get("related_to_user")),
                "scenario_key": str(data.get("scenario_key") or ""),
                "source": str(data.get("source") or ""),
            },
        )

    def _build_scene_capsule(self, session_state: list | None) -> dict:
        scene = extract_scene_summary(session_state or [])
        if not scene:
            return {
                "active": False,
                "location": "",
                "activity": "",
                "next_action": "",
                "spatial": "",
                "state_count": 0,
                "hard_constraint_ready": False,
            }
        return {
            "active": True,
            "location": scene.get("location") or "",
            "activity": scene.get("activity") or "",
            "next_action": scene.get("next_action") or "",
            "spatial": scene.get("spatial") or "",
            "states": scene.get("states") or [],
            "state_count": len(scene.get("states") or []),
            "hard_constraint_ready": bool(scene.get("should_anchor_generation")),
        }

    def _build_memory_authority(self, retrieved, *, scene_capsule: dict) -> dict:
        semantic_items = getattr(retrieved, "semantic_items", []) or []
        relationship = getattr(retrieved, "relationship_state", {}) or {}
        return {
            "mode": "single_owner",
            "owner_user_id": self.user_id or "default_user",
            "policy": [
                "short_term_state_overrides_long_term_recall",
                "manual_user_understanding_overrides_auto_fact",
                "committed_relationship_overrides_single_turn_tone",
                "vector_and_rollup_are_retrieval_hints_not_authority",
            ],
            "layers": {
                "short_term_authority": {
                    "priority": 1,
                    "sources": ["working", "daily", "session_state"],
                    "working_message_count": sum(1 for item in getattr(retrieved, "working_history", []) or [] if isinstance(item, dict) and item.get("role") != "system"),
                    "daily_recent_message_count": len((getattr(retrieved, "daily_context", {}) or {}).get("recent_messages") or []),
                    "session_state_count": len(getattr(retrieved, "session_state", []) or []),
                    "scene_active": bool(scene_capsule.get("active")),
                },
                "long_term_authority": {
                    "priority": 2,
                    "sources": ["semantic", "relationship", "episodic"],
                    "semantic_item_count": len(semantic_items),
                    "relationship_label": relationship.get("relationship_label") if isinstance(relationship, dict) else "",
                    "episodic_count": len(getattr(retrieved, "episodic_recall", []) or []),
                },
                "derived_projection": {
                    "priority": 3,
                    "sources": ["user_understanding", "vector_index", "rollups"],
                    "vector_recall_count": len(getattr(retrieved, "vector_recall", []) or []),
                    "rollup_count": len(getattr(retrieved, "rollup_recall", []) or []),
                    "user_understanding_projection": True,
                },
                "turn_activation": {
                    "priority": 4,
                    "sources": ["activation_plan", "conscious_context", "prompt_builder"],
                    "active_memory_count": len(getattr(getattr(retrieved, "activation_plan", None), "active_memories", []) or []),
                },
            },
        }

    def _build_memory_decision_trace(
        self,
        retrieved,
        *,
        conscious,
        prompt_budget_diagnostics: dict | None,
        scene_capsule: dict,
    ) -> dict:
        activation = getattr(retrieved, "activation_plan", None)
        active_items = [item.to_dict() for item in getattr(activation, "active_memories", []) or []]
        background_items = [item.to_dict() for item in getattr(activation, "background_items", []) or []]
        prompt_blocks = (prompt_budget_diagnostics or {}).get("blocks", {})
        return {
            "intent": getattr(retrieved, "intent", ""),
            "selected_for_prompt": active_items,
            "background_not_selected": background_items[:8],
            "source_counts": getattr(activation, "source_counts", {}) if activation else {},
            "strategy": getattr(activation, "strategy", "") if activation else "",
            "prompt_blocks": {
                name: {
                    "budget_chars": info.get("budget_chars"),
                    "final_body_chars": info.get("final_body_chars"),
                    "truncated": bool(info.get("truncated")),
                }
                for name, info in prompt_blocks.items()
                if isinstance(info, dict)
            },
            "scene": {
                "active": bool(scene_capsule.get("active")),
                "hard_constraint_ready": bool(scene_capsule.get("hard_constraint_ready")),
                "vector_and_rollup_are_demotable": bool(scene_capsule.get("active")),
            },
            "conscious_active_count": len(getattr(conscious, "active_memory_details", []) or []),
        }

    def _build_prompt_diagnostics(
        self,
        *,
        retrieved,
        system_suffix: str,
        conscious,
        prompt_budget_diagnostics: dict | None = None,
        scene_capsule: dict | None = None,
        memory_decision_trace: dict | None = None,
    ) -> dict:
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
            "activation_active_count": len(retrieved.activation_plan.active_memories) if getattr(retrieved, "activation_plan", None) else 0,
            "activation_source_counts": retrieved.activation_plan.source_counts if getattr(retrieved, "activation_plan", None) else {},
            "activation_strategy": retrieved.activation_plan.strategy if getattr(retrieved, "activation_plan", None) else "",
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
            "vector_recall_count": len(getattr(retrieved, "vector_recall", []) or []),
            "vector_recall_sources": _vector_recall_source_counts(getattr(retrieved, "vector_recall", []) or []),
            "vector_recall_top": _vector_recall_top_items(getattr(retrieved, "vector_recall", []) or []),
            "scene_capsule_active": bool((scene_capsule or {}).get("active")),
            "scene_hard_constraint_ready": bool((scene_capsule or {}).get("hard_constraint_ready")),
            "scene_next_action": (scene_capsule or {}).get("next_action") or "",
            "scene_filter_demotes_vector_rollup": bool((scene_capsule or {}).get("active")),
        }
        if scene_capsule:
            diagnostics["scene_capsule"] = scene_capsule
        if memory_decision_trace:
            diagnostics["memory_decision_trace"] = memory_decision_trace
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

    def _get_bot_current_date(self) -> str:
        try:
            life_state_path = self.memory_dir.parent / "life_state.json"
            if not life_state_path.exists():
                return ""
            raw = json.loads(life_state_path.read_text(encoding="utf-8"))
        except Exception:
            return ""
        if not isinstance(raw, dict):
            return ""
        value = raw.get("current_date")
        return str(value).strip() if value else ""

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


def _flatten_understanding(data: dict) -> list[tuple[str, object]]:
    result: list[tuple[str, object]] = []
    if not isinstance(data, dict):
        return result
    allowed_roots = {"manual", "auto", "relationship_memory", "layered"}

    def walk(prefix: str, value: object):
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{prefix}.{key}" if prefix else str(key)
                walk(child_path, child)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                if isinstance(child, (dict, list)):
                    walk(f"{prefix}.{index}", child)
                elif str(child).strip():
                    result.append((f"{prefix}.{index}", child))
        elif str(value or "").strip():
            result.append((prefix, value))

    for root in allowed_roots:
        if root in data:
            walk(root, data.get(root))
    return result[:160]


def _understanding_text(section_path: str, value: object) -> str:
    clean = str(value or "").strip()
    if not clean or clean.lower() in {"none", "null"}:
        return ""
    if len(clean) > 800:
        clean = clean[:797] + "..."
    return f"{section_path}: {clean}"


def _understanding_category(section_path: str) -> str:
    path = section_path.lower()
    for key, category in [
        ("identity", "identity"),
        ("preference", "preferences"),
        ("dislikes", "dislikes"),
        ("communication", "communication_style"),
        ("boundaries", "boundaries"),
        ("current", "current_context"),
        ("open_threads", "open_threads"),
        ("life_context", "life_context"),
        ("goals", "goals"),
        ("routines", "routines"),
        ("relationship", "relationship"),
        ("stressors", "stressors"),
    ]:
        if key in path:
            return category
    return "user_understanding"


def _understanding_importance(section_path: str) -> float:
    if section_path.startswith("manual."):
        return 0.9
    if ".core." in section_path or section_path.startswith("layered.core"):
        return 0.85
    if "relationship_memory" in section_path:
        return 0.75
    return 0.6


def _understanding_sensitivity(section_path: str) -> str:
    path = section_path.lower()
    if any(cue in path for cue in ("sensitive", "boundaries", "stressors", "trauma", "health")):
        return "sensitive"
    return "normal"


def _has_user_explicit_scene_diff(diff: SessionStateDiff) -> bool:
    for item in diff.upserts:
        if not isinstance(item, dict):
            continue
        scope = str(item.get("scope") or "").strip()
        if scope != "current_scene" and not scope.startswith("current_scene/"):
            continue
        if str(item.get("source_kind") or "").strip() != "user_explicit":
            continue
        predicate = str(item.get("predicate") or "").strip()
        if predicate in {
            "current_location",
            "location",
            "current_activity",
            "activity_type",
            "next_action",
            "spatial_relationship",
        }:
            return True
    return False


def _jsonish_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass
        return [text]
    return []


def _text_sensitivity(text: str, extra_items: list[str] | None = None) -> str:
    combined = " ".join([text or "", *(extra_items or [])]).lower()
    sensitive_cues = (
        "sensitive", "boundary", "boundaries", "stress", "trauma", "health", "medical",
        "隐私", "边界", "压力", "创伤", "健康", "疾病", "医疗", "分手", "吵架",
    )
    return "sensitive" if any(cue in combined for cue in sensitive_cues) else "normal"


def _vector_recall_source_counts(items: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        source_type = str(item.get("source_type") or "unknown")
        counts[source_type] = counts.get(source_type, 0) + 1
    return counts


def _vector_recall_top_items(items: list[dict]) -> list[dict]:
    top: list[dict] = []
    for item in items[:6]:
        if not isinstance(item, dict):
            continue
        top.append(
            {
                "source_type": item.get("source_type"),
                "source_id": item.get("source_id"),
                "category": item.get("category"),
                "sensitivity": item.get("sensitivity"),
                "retrieval_score": item.get("retrieval_score"),
                "text": str(item.get("text") or "")[:160],
            }
        )
    return top


def _fact_view_item(fact: dict) -> dict:
    return {
        "type": "semantic_fact",
        "key": fact.get("key"),
        "value": fact.get("value"),
        "category": fact.get("category"),
        "confidence": fact.get("confidence"),
        "source": fact.get("source"),
        "confirmed": bool(fact.get("last_confirmed_at") or fact.get("manual_override")),
        "updated_at": fact.get("updated_at"),
    }


def _episode_view_item(item: dict) -> dict:
    value = str(item.get("summary") or item.get("content") or "").strip()
    return {
        "type": "episodic_memory",
        "key": item.get("summary") or item.get("id") or "情景片段",
        "value": value[:160],
        "confidence": item.get("confidence"),
        "source": "episodic",
        "updated_at": item.get("created_at"),
    }


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _dedupe_view_items(items: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    result: list[dict] = []
    for item in items:
        key = str(item.get("key") or "").strip()
        value = str(item.get("value") or "").strip()
        marker = (key, value)
        if not key or marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result
