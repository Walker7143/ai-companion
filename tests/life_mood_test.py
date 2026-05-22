import tempfile
import unittest
from pathlib import Path

from ai_companion.proactive.life_config import LifeConfig
from ai_companion.proactive.life_engine import LifeEngine
from ai_companion.proactive.life_state import LifeState


class LifeMoodStatusTest(unittest.TestCase):
    def test_life_status_exposes_interaction_mood(self):
        with tempfile.TemporaryDirectory(prefix="life-mood-status-") as td:
            root = Path(td)
            persona_dir = root / "bot-a" / "persona"
            persona_dir.mkdir(parents=True, exist_ok=True)
            (persona_dir / "life.json").write_text("{}", encoding="utf-8")

            config = LifeConfig(_persona_dir=persona_dir)
            state = LifeState("bot-a", root)
            engine = LifeEngine(bot_id="bot-a", config=config, state=state, model=None, memory=None, persona_dir=persona_dir)
            engine.set_relationship_state({
                "tension_score": 50,
                "open_emotional_threads": ["上次那个问题还没聊完"],
            })
            status = engine.get_status()
            self.assertIn("bot_life_mood", status)
            self.assertIn("interaction_mood", status)
            self.assertTrue(status["interaction_mood"])


if __name__ == "__main__":
    unittest.main()
