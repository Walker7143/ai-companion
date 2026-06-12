"""Intent-aware memory retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from .activation import MemoryActivationPlan
from .continuity import ContinuityContract, ContinuityContractBuilder
from .scene_authority import is_memory_compatible_with_scene
from .session_state import get_scene_snapshot, is_generation_relevant_session_state


@dataclass
class RetrievedMemory:
    intent: str
    current_input: str = ""
    working_history: list[dict] = field(default_factory=list)
    session_state: list[dict[str, Any]] = field(default_factory=list)
    daily_context: dict[str, Any] = field(default_factory=dict)
    turn_constraints: list[dict[str, Any]] = field(default_factory=list)
    vector_recall: list[dict[str, Any]] = field(default_factory=list)
    rollup_recall: list[dict] = field(default_factory=list)
    episodic_recall: list[dict] = field(default_factory=list)
    semantic_facts: dict[str, str] = field(default_factory=dict)
    semantic_items: list[dict] = field(default_factory=list)
    relationship_state: dict[str, Any] = field(default_factory=dict)
    user_understanding: dict[str, Any] = field(default_factory=dict)
    activation_plan: MemoryActivationPlan | None = None
    continuity_contract: ContinuityContract | None = None


class MemoryRetriever:
    """Build a recall plan for the current user input."""

    INTENT_KEYWORDS = {
        "emotional_support": ["难过", "焦虑", "压力", "失眠", "委屈", "崩溃", "烦", "累", "害怕"],
        "recall_past": [
            "还记得", "记得吗", "记不记得", "不记得", "忘了", "忘记", "失忆",
            "上次", "之前", "那天", "以前", "我们聊过", "聊过", "说过", "提过",
            "刚才", "刚刚", "刚说", "刚聊", "前面", "上一句", "上一条",
        ],
        "planning": ["计划", "继续", "明天", "待办", "安排", "目标", "作品集"],
        "relationship_repair": ["生气", "道歉", "冷淡", "吵架", "和好", "原谅"],
        "task_request": ["写代码", "总结", "翻译", "生成", "分析", "实现", "修复", "优化"],
    }
    RECENT_RECALL_CUES = {
        "今天", "昨天", "最近", "刚才", "刚刚", "前面", "上次", "之前", "那会",
    }
    RECENT_RECALL_CONTEXT = {
        "聊", "说", "问", "提", "记录", "聊天", "记忆", "记得", "忘", "确认", "确定",
    }
    TASK_CONTEXT_KEYWORDS = {
        "代码", "函数", "报错", "bug", "接口", "测试", "文档", "文件", "实现",
        "优化", "编译", "安装", "部署", "日志", "数据库", "token", "prompt",
        "api", "python", "javascript", "typescript", "react", "sql", "git",
    }
    RELATIONSHIP_CONTEXT_KEYWORDS = {
        "关系", "我们", "你", "我", "感情", "态度", "喜欢", "爱", "冷淡",
        "生气", "道歉", "和好", "原谅", "委屈", "吵架",
    }

    FACT_CATEGORIES_BY_INTENT = {
        "emotional_support": {"communication_style", "boundaries", "life_context", "important_people", "dislikes"},
        "recall_past": {
            "identity", "important_people", "life_context", "goals", "routines",
            "preferences", "communication_style", "boundaries", "open_threads", "dislikes",
            "turn_constraints",
        },
        "planning": {"goals", "life_context", "open_threads", "routines", "dislikes", "turn_constraints"},
        "relationship_repair": {"boundaries", "communication_style", "important_people", "dislikes"},
        "task_request": {"identity", "preferences", "communication_style", "dislikes"},
        "casual_chat": {
            "identity", "preferences", "communication_style", "boundaries", "life_context",
            "important_people", "dislikes", "turn_constraints",
        },
        "proactive_generation": {"life_context", "goals", "open_threads", "communication_style", "dislikes", "turn_constraints"},
    }

    def __init__(
        self,
        *,
        working_store,
        daily_store=None,
        vector_store=None,
        episodic_store,
        semantic_store,
        relationship_store,
        rollup_store=None,
        user_understanding,
        session_state_store=None,
        max_working_turns: int = 20,
        max_summaries: int = 5,
        scene_filter_enabled: bool = True,
    ):
        self.working = working_store
        self.daily = daily_store
        self.vector = vector_store
        self.episodic = episodic_store
        self.semantic = semantic_store
        self.relationship = relationship_store
        self.rollups = rollup_store
        self.user_understanding = user_understanding
        self.session_state_store = session_state_store
        self.max_working_turns = max_working_turns
        self.max_summaries = max_summaries
        self.scene_filter_enabled = scene_filter_enabled
        self.contract_builder = ContinuityContractBuilder()

    async def retrieve(
        self,
        current_input: str,
        *,
        bot_id: str,
        user_id: str,
        session_id: str | None,
        intent: str | None = None,
    ) -> RetrievedMemory:
        detected_intent = intent or self.classify_intent(current_input)
        working = self.working.load_context(
            session_id,
            max_working_turns=self.max_working_turns,
            max_summaries=self.max_summaries,
        )
        session_state = []
        if self.session_state_store is not None and session_id:
            active_states = await self.session_state_store.list_active_states(session_id)
            session_state = [
                item.to_dict()
                for item in active_states
                if is_generation_relevant_session_state(item)
            ]
        daily_context = {}
        if self.daily is not None:
            daily_context = self.daily.get_recent_context(
                bot_id=bot_id,
                user_id=user_id,
                current_session_id=session_id,
                intent=detected_intent,
            )
        understanding = self.user_understanding.load()
        relationship = await self.relationship.get_state(bot_id=bot_id, user_id=user_id)
        turn_constraints = []
        if hasattr(self.semantic, "list_facts"):
            turn_constraints = await self.semantic.list_facts(
                bot_id=bot_id,
                user_id=user_id,
                categories={"turn_constraints"},
                min_confidence=0.0,
                include_archived=False,
                limit=12,
            )
        turn_constraints.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        rollup_recall = []
        if self.rollups is not None:
            seen_rollups: set[tuple[str, str, str]] = set()
            for scope in self._rollup_scopes_for_intent(detected_intent):
                if len(rollup_recall) >= 6:
                    break
                items = await self.rollups.get_recent_rollups(
                    bot_id=bot_id,
                    user_id=user_id,
                    scope=scope,
                    limit=4,
                )
                for item in items:
                    marker = (
                        str(item.get("scope") or ""),
                        str(item.get("topic_key") or ""),
                        str(item.get("summary") or ""),
                    )
                    if marker in seen_rollups:
                        continue
                    seen_rollups.add(marker)
                    rollup_recall.append(item)
                    if len(rollup_recall) >= 6:
                        break

        categories = self.FACT_CATEGORIES_BY_INTENT.get(detected_intent, self.FACT_CATEGORIES_BY_INTENT["casual_chat"])
        semantic_items = await self.semantic.search_facts(
            current_input,
            bot_id=bot_id,
            user_id=user_id,
            categories=categories,
            include_archived=False,
            limit=24,
        )
        semantic_facts = {item["key"]: item["value"] for item in semantic_items}

        vector_recall = []
        if self.vector is not None:
            vector_recall = self.vector.search(
                current_input,
                bot_id=bot_id,
                user_id=user_id,
                source_types=[
                    "semantic_fact",
                    "user_understanding",
                    "life_event",
                    "major_life_event",
                    "daily_summary",
                    "relationship_narrative",
                ],
                limit=self._vector_limit_for_intent(detected_intent),
                include_archived=False,
            )
            vector_recall = self._filter_vector_recall(vector_recall, intent=detected_intent)
            vector_recall = self._filter_vector_recall_by_scene(
                vector_recall,
                session_state,
                current_input=current_input,
            )
        top_k = 5 if detected_intent in {"recall_past", "relationship_repair"} else 2
        episodic = []
        if detected_intent in {"recall_past", "emotional_support", "relationship_repair", "casual_chat", "planning"}:
            episodic = self.episodic.recall(
                current_input,
                top_k=top_k,
                session_id=None if detected_intent == "recall_past" else session_id,
                bot_id=bot_id,
                user_id=user_id,
                include_archived=False,
            )

        if detected_intent in {"planning", "emotional_support"} and self.daily is not None:
            daily_context = self.daily.get_recent_context(
                bot_id=bot_id,
                user_id=user_id,
                current_session_id=session_id,
                intent=detected_intent,
            )

        retrieved = RetrievedMemory(
            intent=detected_intent,
            current_input=current_input,
            working_history=working,
            session_state=session_state,
            daily_context=daily_context,
            turn_constraints=turn_constraints,
            vector_recall=vector_recall,
            rollup_recall=rollup_recall,
            episodic_recall=episodic,
            semantic_facts=semantic_facts,
            semantic_items=semantic_items,
            relationship_state=relationship,
            user_understanding=understanding,
        )
        retrieved.continuity_contract = self.contract_builder.build(current_input=current_input, retrieved=retrieved)
        return retrieved

    def classify_intent(self, text: str) -> str:
        text = text or ""
        lowered = text.lower()
        recall_cue = self._has_recall_cue(text, lowered)
        explicit_memory_question = self._has_explicit_memory_question(text, lowered)
        matched: dict[str, int] = {}
        for intent, keywords in self.INTENT_KEYWORDS.items():
            count = sum(1 for keyword in keywords if keyword in text or keyword.lower() in lowered)
            if count:
                matched[intent] = count

        task_context = sum(1 for keyword in self.TASK_CONTEXT_KEYWORDS if keyword in text or keyword.lower() in lowered)
        relationship_context = sum(1 for keyword in self.RELATIONSHIP_CONTEXT_KEYWORDS if keyword in text)

        if not matched:
            return "casual_chat"
        if matched.get("relationship_repair") and relationship_context and not task_context:
            return "relationship_repair"
        if matched.get("emotional_support") and not task_context:
            return "emotional_support"
        if explicit_memory_question or (recall_cue and not (matched.get("task_request") and task_context)):
            return "recall_past"
        if matched.get("task_request") and task_context:
            return "task_request"
        if matched.get("planning"):
            return "planning"
        if matched.get("task_request"):
            return "task_request"
        if matched.get("relationship_repair"):
            return "relationship_repair"
        for intent in self.INTENT_KEYWORDS:
            if intent in matched:
                return intent
        return "casual_chat"

    def _vector_limit_for_intent(self, intent: str) -> int:
        if intent in {"recall_past", "relationship_repair", "emotional_support"}:
            return 8
        if intent in {"planning", "proactive_generation"}:
            return 6
        if intent == "task_request":
            return 3
        return 5

    def _rollup_scopes_for_intent(self, intent: str) -> list[str]:
        if intent in {"planning", "emotional_support", "proactive_generation"}:
            return ["day", "topic"]
        if intent == "recall_past":
            return ["day", "topic"]
        return ["topic"]

    def _filter_vector_recall(self, items: list[dict[str, Any]], *, intent: str) -> list[dict[str, Any]]:
        if intent == "recall_past":
            return items
        today = date.today()
        result: list[dict[str, Any]] = []
        for item in items:
            if str(item.get("source_type") or "") not in {"life_event"}:
                result.append(item)
                continue
            event_date = _vector_item_date(item)
            if event_date is None:
                result.append(item)
                continue
            if event_date > today:
                continue
            if (today - event_date).days >= 3:
                continue
            result.append(item)
        return result

    def _filter_vector_recall_by_scene(
        self,
        items: list[dict[str, Any]],
        session_states: list,
        *,
        current_input: str = "",
    ) -> list[dict[str, Any]]:
        if not self.scene_filter_enabled:
            return items
        if not session_states:
            return items
        snapshot = get_scene_snapshot(session_states, user_input=current_input)
        if not snapshot.should_anchor_generation:
            return items
        scene_categories = set(snapshot.categories)
        if not scene_categories:
            return items
        result: list[dict[str, Any]] = []
        for item in items:
            source = str(item.get("source_type") or item.get("source") or "")
            if source in ("life_event", "major_life_event"):
                if not is_memory_compatible_with_scene(scene_categories, item):
                    demoted = dict(item)
                    demoted["score"] = round(float(item.get("score", 0.5)) * 0.3, 2)
                    result.append(demoted)
                    continue
            result.append(item)
        return result

    def _has_recall_cue(self, text: str, lowered: str) -> bool:
        if not text:
            return False
        explicit_cues = self.INTENT_KEYWORDS.get("recall_past", [])
        if any(cue in text or cue.lower() in lowered for cue in explicit_cues):
            return True
        has_recent_time = any(cue in text for cue in self.RECENT_RECALL_CUES)
        has_recall_context = any(cue in text for cue in self.RECENT_RECALL_CONTEXT)
        return has_recent_time and has_recall_context

    def _has_explicit_memory_question(self, text: str, lowered: str) -> bool:
        cues = (
            "还记得", "记得吗", "记不记得", "不记得", "忘了", "忘记", "失忆",
            "我们聊过", "聊过", "说过", "提过", "刚说", "刚聊", "上一句", "上一条",
        )
        return any(cue in text or cue.lower() in lowered for cue in cues)


def _vector_item_date(item: dict[str, Any]) -> date | None:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    for key in ("updated_at", "created_at"):
        raw = str(metadata.get(key) or "").strip()
        if not raw:
            continue
        try:
            return datetime.fromisoformat(raw[:19]).date()
        except ValueError:
            try:
                return date.fromisoformat(raw[:10])
            except ValueError:
                continue
    return None
