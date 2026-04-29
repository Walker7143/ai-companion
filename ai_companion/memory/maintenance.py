"""Lightweight memory maintenance."""

from __future__ import annotations

from datetime import datetime


class MemoryMaintenance:
    """Decay expired temporary facts and refresh the user understanding projection."""

    def __init__(self, *, semantic_store, episodic_store, user_understanding, relationship_store=None):
        self.semantic = semantic_store
        self.episodic = episodic_store
        self.user_understanding = user_understanding
        self.relationship = relationship_store

    async def run_light(self, *, bot_id: str, user_id: str):
        now = datetime.now().isoformat()
        await self.semantic.archive_expired(now=now, bot_id=bot_id, user_id=user_id)
        await self.episodic.archive_low_value(bot_id=bot_id, user_id=user_id)
        facts = await self.semantic.list_facts(
            bot_id=bot_id,
            user_id=user_id,
            min_confidence=0.75,
            include_archived=False,
        )
        relationship = None
        if self.relationship is not None:
            relationship = await self.relationship.get_state(bot_id=bot_id, user_id=user_id)
        await self.user_understanding.refresh_auto_from_sources(facts=facts, relationship=relationship)
