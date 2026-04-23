from typing import Optional

from .instance import BotInstance


class BotManager:
    """管理所有 Bot 实例"""

    def __init__(self):
        self.bots: dict[str, BotInstance] = {}

    def register(self, bot: BotInstance):
        self.bots[bot.id] = bot

    def get_bot(self, bot_id: str) -> Optional[BotInstance]:
        return self.bots.get(bot_id)

    def list_bots(self) -> list[dict]:
        return [
            {"id": b.id, "name": b.name, "description": b.description}
            for b in self.bots.values()
        ]

    @property
    def first_bot(self) -> Optional[BotInstance]:
        return next(iter(self.bots.values()), None)
