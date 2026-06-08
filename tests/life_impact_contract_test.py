import asyncio
import tempfile
import unittest
from pathlib import Path

from ai_companion.generation import GenerationContextBuilder
from ai_companion.memory.engine import MemoryEngine
from ai_companion.proactive.life_config import LifeConfig
from ai_companion.proactive.life_engine import LifeEngine
from ai_companion.proactive.life_state import LifeEvent, LifeState


class LifeImpactContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_user_turn_changes_short_term_bot_mood_without_persona_patch(self):
        with tempfile.TemporaryDirectory(prefix="life-impact-turn-") as td:
            root = Path(td)
            persona_dir = root / "impact_bot" / "persona"
            persona_dir.mkdir(parents=True, exist_ok=True)
            (persona_dir / "life.json").write_text("{}", encoding="utf-8")

            memory = MemoryEngine("impact_bot", root, config={"embedding": "none"})
            await memory.init()
            state = LifeState("impact_bot", root)
            engine = LifeEngine(
                bot_id="impact_bot",
                config=LifeConfig(_persona_dir=persona_dir),
                state=state,
                model=None,
                memory=memory,
                persona_dir=persona_dir,
            )

            result = await engine.process_turn_impact(
                user_input="我今天真的很难过，想抱抱你一下。",
                bot_output="过来，我接住你。",
                session_id="s1",
                user_id="default_user",
            )

            self.assertTrue(result["applied"])
            self.assertIn("心疼", state.bot_mood)
            self.assertTrue(state.recent_impacts)
            self.assertFalse(state.recent_impacts[-1]["persona_patch_candidate"])
            await memory.close()

    async def test_shared_experience_writes_episode_and_life_journal(self):
        with tempfile.TemporaryDirectory(prefix="life-impact-episode-") as td:
            root = Path(td)
            persona_dir = root / "episode_bot" / "persona"
            persona_dir.mkdir(parents=True, exist_ok=True)
            (persona_dir / "life.json").write_text("{}", encoding="utf-8")

            memory = MemoryEngine("episode_bot", root, config={"embedding": "none"})
            await memory.init()
            state = LifeState("episode_bot", root)
            engine = LifeEngine(
                bot_id="episode_bot",
                config=LifeConfig(_persona_dir=persona_dir),
                state=state,
                model=None,
                memory=memory,
                persona_dir=persona_dir,
            )

            result = await engine.process_turn_impact(
                user_input="还记得吗，我们第一次一起去海边牵手，我真的很开心。",
                bot_output="记得，那一下我也有点被你弄得心软。",
                session_id="s2",
                user_id="default_user",
            )
            recalled = memory.episodic.recall("海边牵手", top_k=3, bot_id="episode_bot", user_id="default_user")

            self.assertGreaterEqual(result["memory_written"], 1)
            self.assertTrue(recalled)
            self.assertTrue(any(item.get("record_type") == "impact" for item in state.life_journal))
            await memory.close()

    async def test_structured_turn_signal_drives_impact_without_keyword_match(self):
        with tempfile.TemporaryDirectory(prefix="life-impact-structured-") as td:
            root = Path(td)
            persona_dir = root / "structured_bot" / "persona"
            persona_dir.mkdir(parents=True, exist_ok=True)
            (persona_dir / "life.json").write_text("{}", encoding="utf-8")

            state = LifeState("structured_bot", root)
            engine = LifeEngine(
                bot_id="structured_bot",
                config=LifeConfig(_persona_dir=persona_dir),
                state=state,
                model=None,
                memory=None,
                persona_dir=persona_dir,
            )

            result = await engine.process_turn_impact(
                user_input="刚才那件事又来了。",
                bot_output="我在这里。",
                session_id="s-structured",
                user_id="default_user",
                relationship_state={"tension_score": 62, "relationship_status": "修复中"},
            )

            self.assertTrue(result["applied"])
            self.assertIn("绷着", state.bot_mood)
            self.assertEqual("structured_relationship_tension", state.recent_impacts[-1]["reason"])
            self.assertEqual(62, state.recent_impacts[-1]["metadata"]["structured_signals"]["relationship_tension_score"])

    async def test_life_event_updates_mood_activity_and_recent_impacts(self):
        with tempfile.TemporaryDirectory(prefix="life-impact-event-") as td:
            root = Path(td)
            persona_dir = root / "event_bot" / "persona"
            persona_dir.mkdir(parents=True, exist_ok=True)
            (persona_dir / "life.json").write_text("{}", encoding="utf-8")

            state = LifeState("event_bot", root)
            engine = LifeEngine(
                bot_id="event_bot",
                config=LifeConfig(_persona_dir=persona_dir),
                state=state,
                model=None,
                memory=None,
                persona_dir=persona_dir,
            )
            event = LifeEvent(
                description="午后在客栈门口晒太阳，突然觉得这几天都慢下来了。",
                mood_before="平静",
                mood_after="松弛",
                importance=6.0,
                shareable=True,
                scenario_key="slow_afternoon",
            )

            result = await engine.apply_life_event_impact(event, major=False)

            self.assertTrue(result["applied"])
            self.assertEqual(state.bot_mood, "松弛")
            self.assertIn("消化这件事", state.bot_current_activity)
            self.assertTrue(state.recent_impacts)

    def test_generation_contract_renders_priority_and_anchors(self):
        contract = GenerationContextBuilder().build_chat_contract(
            intent="casual_chat",
            current_input="刚才我们在车上说到哪了？",
            memory_awareness={
                "relationship_posture": "自然亲近，但先承接现场。",
                "active_memories": [{"text": "用户和 Bot 刚在车上聊天。"}],
            },
            life_anchor={"summary": "心情：松弛；正在：整理今天的小事", "bot_mood": "松弛"},
            scene_anchor={"summary": "最近真实现场：正在车上。"},
            relationship_state={"relationship_label": "恋人"},
        )

        rendered = contract.render_for_prompt()
        self.assertIn("当前真实现场 > 本轮输入/主动动机 > Bot 当前生活锚点", rendered)
        self.assertIn("正在车上", rendered)
        self.assertIn("整理今天的小事", rendered)
        self.assertIn("自然亲近", rendered)


if __name__ == "__main__":
    unittest.main()
