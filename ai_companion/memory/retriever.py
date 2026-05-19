"""Intent-aware memory retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievedMemory:
    intent: str
    working_history: list[dict] = field(default_factory=list)
    daily_context: dict[str, Any] = field(default_factory=dict)
    vector_recall: list[dict[str, Any]] = field(default_factory=list)
    rollup_recall: list[dict] = field(default_factory=list)
    episodic_recall: list[dict] = field(default_factory=list)
    semantic_facts: dict[str, str] = field(default_factory=dict)
    semantic_items: list[dict] = field(default_factory=list)
    relationship_state: dict[str, Any] = field(default_factory=dict)
    user_understanding: dict[str, Any] = field(default_factory=dict)


class MemoryRetriever:
    """Build a recall plan for the current user input."""

    INTENT_KEYWORDS = {
        "emotional_support": ["难过", "焦虑", "压力", "失眠", "委屈", "崩溃", "烦", "累", "害怕"],
        "recall_past": ["还记得", "上次", "之前", "那天", "以前", "我们聊过"],
        "planning": ["计划", "继续", "明天", "待办", "安排", "目标", "作品集"],
        "relationship_repair": ["生气", "道歉", "冷淡", "吵架", "和好", "原谅"],
        "task_request": ["写代码", "总结", "翻译", "生成", "分析", "实现", "修复", "优化"],
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
        "recall_past": {"identity", "important_people", "life_context", "goals", "dislikes"},
        "planning": {"goals", "life_context", "open_threads", "routines", "dislikes"},
        "relationship_repair": {"boundaries", "communication_style", "important_people", "dislikes"},
        "task_request": {"identity", "preferences", "communication_style", "dislikes"},
        "casual_chat": {"identity", "preferences", "communication_style", "boundaries", "dislikes"},
        "proactive_generation": {"life_context", "goals", "open_threads", "communication_style", "dislikes"},
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
        max_working_turns: int = 20,
        max_summaries: int = 5,
    ):
        self.working = working_store
        self.daily = daily_store
        self.vector = vector_store
        self.episodic = episodic_store
        self.semantic = semantic_store
        self.relationship = relationship_store
        self.rollups = rollup_store
        self.user_understanding = user_understanding
        self.max_working_turns = max_working_turns
        self.max_summaries = max_summaries

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
        rollup_recall = []
        if self.rollups is not None:
            scope = "day" if detected_intent in {"planning", "emotional_support", "proactive_generation"} else "topic"
            rollup_recall = await self.rollups.get_recent_rollups(
                bot_id=bot_id,
                user_id=user_id,
                scope=scope,
                limit=4,
            )

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

        return RetrievedMemory(
            intent=detected_intent,
            working_history=working,
            daily_context=daily_context,
            vector_recall=vector_recall,
            rollup_recall=rollup_recall,
            episodic_recall=episodic,
            semantic_facts=semantic_facts,
            semantic_items=semantic_items,
            relationship_state=relationship,
            user_understanding=understanding,
        )

    def classify_intent(self, text: str) -> str:
        text = text or ""
        lowered = text.lower()
        matched: dict[str, int] = {}
        for intent, keywords in self.INTENT_KEYWORDS.items():
            count = sum(1 for keyword in keywords if keyword in text or keyword.lower() in lowered)
            if count:
                matched[intent] = count
        if not matched:
            return "casual_chat"

        task_context = sum(1 for keyword in self.TASK_CONTEXT_KEYWORDS if keyword in text or keyword.lower() in lowered)
        relationship_context = sum(1 for keyword in self.RELATIONSHIP_CONTEXT_KEYWORDS if keyword in text)

        if matched.get("task_request") and task_context:
            return "task_request"
        if matched.get("relationship_repair") and relationship_context and not task_context:
            return "relationship_repair"
        if matched.get("emotional_support") and not task_context:
            return "emotional_support"
        if matched.get("recall_past"):
            return "recall_past"
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
