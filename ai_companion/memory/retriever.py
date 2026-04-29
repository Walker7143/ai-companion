"""Intent-aware memory retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievedMemory:
    intent: str
    working_history: list[dict] = field(default_factory=list)
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

    FACT_CATEGORIES_BY_INTENT = {
        "emotional_support": {"communication_style", "boundaries", "life_context", "important_people"},
        "recall_past": {"identity", "important_people", "life_context", "goals"},
        "planning": {"goals", "life_context", "open_threads", "routines"},
        "relationship_repair": {"boundaries", "communication_style", "important_people"},
        "task_request": {"identity", "preferences", "communication_style"},
        "casual_chat": {"identity", "preferences", "communication_style", "boundaries"},
        "proactive_generation": {"life_context", "goals", "open_threads", "communication_style"},
    }

    def __init__(
        self,
        *,
        working_store,
        episodic_store,
        semantic_store,
        relationship_store,
        user_understanding,
        max_working_turns: int = 20,
    ):
        self.working = working_store
        self.episodic = episodic_store
        self.semantic = semantic_store
        self.relationship = relationship_store
        self.user_understanding = user_understanding
        self.max_working_turns = max_working_turns

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
        working = self.working.load_context(session_id, max_working_turns=self.max_working_turns)
        understanding = self.user_understanding.load()
        relationship = await self.relationship.get_state(bot_id=bot_id, user_id=user_id)

        categories = self.FACT_CATEGORIES_BY_INTENT.get(detected_intent, self.FACT_CATEGORIES_BY_INTENT["casual_chat"])
        semantic_items = await self.semantic.list_facts(
            bot_id=bot_id,
            user_id=user_id,
            categories=categories,
            include_archived=False,
            limit=20,
        )
        semantic_facts = {item["key"]: item["value"] for item in semantic_items}

        top_k = 5 if detected_intent in {"recall_past", "relationship_repair"} else 2
        episodic = []
        if detected_intent in {"recall_past", "emotional_support", "relationship_repair", "casual_chat"}:
            episodic = self.episodic.recall(
                current_input,
                top_k=top_k,
                session_id=None if detected_intent == "recall_past" else session_id,
                bot_id=bot_id,
                user_id=user_id,
                include_archived=False,
            )

        return RetrievedMemory(
            intent=detected_intent,
            working_history=working,
            episodic_recall=episodic,
            semantic_facts=semantic_facts,
            semantic_items=semantic_items,
            relationship_state=relationship,
            user_understanding=understanding,
        )

    def classify_intent(self, text: str) -> str:
        text = text or ""
        for intent, keywords in self.INTENT_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                return intent
        return "casual_chat"
