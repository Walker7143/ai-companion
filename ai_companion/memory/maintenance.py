"""Lightweight memory maintenance."""

from __future__ import annotations

from datetime import datetime


class MemoryMaintenance:
    """Decay expired temporary facts and refresh the user understanding projection."""

    def __init__(self, *, semantic_store, episodic_store, user_understanding, relationship_store=None, daily_store=None, rollup_store=None):
        self.semantic = semantic_store
        self.episodic = episodic_store
        self.user_understanding = user_understanding
        self.relationship = relationship_store
        self.daily = daily_store
        self.rollups = rollup_store

    async def run_light(self, *, bot_id: str, user_id: str, summarizer=None):
        now = datetime.now().isoformat()
        daily_context = {}
        if self.daily is not None:
            await self.daily.summarize_due(bot_id=bot_id, user_id=user_id, summarizer=summarizer)
            await self.daily.prune_old(bot_id=bot_id, user_id=user_id)
            daily_context = self.daily.get_recent_context(bot_id=bot_id, user_id=user_id, intent="planning")
        await self.semantic.archive_expired(now=now, bot_id=bot_id, user_id=user_id)
        await self.episodic.archive_low_value(bot_id=bot_id, user_id=user_id)
        if hasattr(self.episodic, "decay_stale"):
            decay_result = await self.episodic.decay_stale(bot_id=bot_id, user_id=user_id)
            if decay_result.get("archived") or decay_result.get("decayed"):
                await self.semantic.record_lifecycle_event(
                    memory_type="episodic",
                    memory_key="stale_decay",
                    action="decay",
                    reason="maintenance_decay_stale_episodes",
                    after=decay_result,
                    bot_id=bot_id,
                    user_id=user_id,
                )
        facts = await self.semantic.list_facts(
            bot_id=bot_id,
            user_id=user_id,
            min_confidence=0.75,
            include_archived=False,
        )
        relationship = None
        if self.relationship is not None:
            relationship = await self.relationship.get_state(bot_id=bot_id, user_id=user_id)
        await self.user_understanding.refresh_auto_from_sources(
            facts=facts,
            relationship=relationship,
            daily_context=daily_context,
        )
        if hasattr(self, "rollups"):
            await self.build_basic_rollups(rollup_store=self.rollups, bot_id=bot_id, user_id=user_id)

    async def build_basic_rollups(self, *, rollup_store, bot_id: str, user_id: str):
        if rollup_store is None:
            return
        daily_context = {}
        if self.daily is not None:
            daily_context = self.daily.get_recent_context(bot_id=bot_id, user_id=user_id, intent="planning")
        relationship = None
        if self.relationship is not None:
            relationship = await self.relationship.get_state(bot_id=bot_id, user_id=user_id)
        understanding = self.user_understanding.load()

        if daily_context:
            summaries = daily_context.get("summaries") if isinstance(daily_context.get("summaries"), list) else []
            latest_summary = summaries[-1] if summaries and isinstance(summaries[-1], dict) else {}
            summary = str(daily_context.get("today") or latest_summary.get("summary") or "").strip()
            if summary:
                await rollup_store.append_rollup(
                    bot_id=bot_id,
                    user_id=user_id,
                    scope="day",
                    topic_key=str(daily_context.get("today") or "recent_day"),
                    summary=summary,
                    evidence=[str(item) for item in daily_context.get("open_threads") or []][:3],
                    confidence=0.7,
                    freshness=0.8,
                    source={"kind": "daily_context"},
                )

        if relationship:
            rel_summary = str(relationship.get("relationship_narrative") or "").strip()
            if rel_summary:
                await rollup_store.append_rollup(
                    bot_id=bot_id,
                    user_id=user_id,
                    scope="global",
                    topic_key="relationship",
                    summary=rel_summary,
                    evidence=[str(item) for item in relationship.get("open_emotional_threads") or []][:3],
                    confidence=0.8,
                    freshness=0.6,
                    source={"kind": "relationship_state"},
                )

        layered = understanding.get("layered") if isinstance(understanding.get("layered"), dict) else {}
        current = layered.get("current") if isinstance(layered.get("current"), dict) else {}
        goals = current.get("goals_and_projects") if isinstance(current.get("goals_and_projects"), list) else []
        if goals:
            await rollup_store.append_rollup(
                bot_id=bot_id,
                user_id=user_id,
                scope="topic",
                topic_key="goals_and_projects",
                summary="；".join(str(item) for item in goals[:3]),
                evidence=[str(item) for item in goals[:3]],
                confidence=0.75,
                freshness=0.5,
                source={"kind": "user_understanding"},
            )
