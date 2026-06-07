import asyncio
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_companion.persona.evolution import PersonaEvolutionEngine, load_evolution_state


class _Event:
    def __init__(self, description: str, mood_tags: list[str] | None = None):
        self.description = description
        self.mood_tags = mood_tags or []


def _write_persona_bundle(persona_dir: Path) -> None:
    persona_dir.mkdir(parents=True, exist_ok=True)
    (persona_dir / "profile.json").write_text(
        json.dumps(
            {
                "name": "测试 Bot",
                "birth_date": "2000-01-01",
                "occupation": "学生",
                "personality_tags": ["温柔"],
                "relationship_to_user": "朋友",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (persona_dir / "backstory.json").write_text(
        json.dumps(
            {
                "summary": "最初的背景",
                "key_moments": [],
                "shared_experiences": [],
                "life_experiences": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (persona_dir / "speaking_style.json").write_text(
        json.dumps({"tone": "自然", "style_notes": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    (persona_dir / "values.json").write_text(
        json.dumps({"non_negotiable": ["不要欺骗"], "soft_values": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    (persona_dir / "runtime_profile.json").write_text(json.dumps({}, ensure_ascii=False), encoding="utf-8")


class PersonaEvolutionEngineTest(unittest.IsolatedAsyncioTestCase):
    async def test_shared_turn_creates_signal_without_direct_core_patch(self):
        with TemporaryDirectory(prefix="evolution-turn-runtime-") as td:
            persona_dir = Path(td) / "bot" / "persona"
            _write_persona_bundle(persona_dir)
            engine = PersonaEvolutionEngine(bot_id="bot", persona_dir=persona_dir)

            result = await engine.capture_turn(
                user_input="我们上次一起准备面试的时候，你其实一直在安慰我。",
                bot_output="我记得，那时候我一直想让你放松一点。",
            )

            state = load_evolution_state(persona_dir)
            backstory = json.loads((persona_dir / "backstory.json").read_text(encoding="utf-8"))

        self.assertGreaterEqual(result["captured"], 1)
        self.assertTrue(state["signals"])
        self.assertEqual(backstory["shared_experiences"], [])
        self.assertEqual(backstory["life_experiences"], [])

    async def test_major_life_event_can_generate_pending_and_apply_core_patch(self):
        with TemporaryDirectory(prefix="evolution-major-promote-") as td:
            persona_dir = Path(td) / "bot" / "persona"
            _write_persona_bundle(persona_dir)
            engine = PersonaEvolutionEngine(
                bot_id="bot",
                persona_dir=persona_dir,
                config={"auto_promotion_enabled": False},
            )

            result = await engine.capture_life_event(
                _Event("她认真想过之后，决定重新规划未来半年的生活方向。", ["转折"]),
                event_type="major",
                runtime_update={
                    "life_experience": "她认真想过之后，决定重新规划未来半年的生活方向。",
                    "life_growth_summary": "这件事让她开始更主动地定义自己的未来。",
                },
            )

            state = load_evolution_state(persona_dir)
            pending = list(state.get("pending_promotions") or [])
            self.assertEqual(result["captured"], 1)
            self.assertTrue(pending)

            apply_result = await engine.apply_core_patch(pending[0]["id"], approval_reason="test")
            backstory = json.loads((persona_dir / "backstory.json").read_text(encoding="utf-8"))
            state_after = load_evolution_state(persona_dir)

        self.assertTrue(apply_result["applied"])
        self.assertIn("重新规划未来半年的生活方向", " ".join(backstory.get("life_experiences", [])))
        self.assertEqual(state_after["pending_promotions"], [])
        self.assertTrue(state_after["applied_changes"])

    async def test_protected_fields_are_suppressed(self):
        with TemporaryDirectory(prefix="evolution-protected-field-") as td:
            persona_dir = Path(td) / "bot" / "persona"
            _write_persona_bundle(persona_dir)
            engine = PersonaEvolutionEngine(bot_id="bot", persona_dir=persona_dir)
            state = engine.get_state()
            state["pending_promotions"] = [
                {
                    "id": "candidate-name",
                    "dimension": "personality",
                    "field_path": "profile.name",
                    "summary": "试图自动修改名字",
                    "support_count": 4,
                    "window_count": 3,
                    "candidate_patch": {"profile": {"name": "新名字"}},
                    "status": "pending",
                }
            ]
            engine._save_state(state)

            result = await engine.apply_core_patch("candidate-name", approval_reason="test")
            profile = json.loads((persona_dir / "profile.json").read_text(encoding="utf-8"))
            state_after = load_evolution_state(persona_dir)

        self.assertFalse(result["applied"])
        self.assertEqual(profile["name"], "测试 Bot")
        self.assertTrue(state_after["suppressed_changes"])

    async def test_occupation_requires_major_life_event(self):
        with TemporaryDirectory(prefix="evolution-occupation-guard-") as td:
            persona_dir = Path(td) / "bot" / "persona"
            _write_persona_bundle(persona_dir)
            engine = PersonaEvolutionEngine(bot_id="bot", persona_dir=persona_dir)
            state = engine.get_state()
            state["pending_promotions"] = [
                {
                    "id": "candidate-occupation",
                    "dimension": "backstory",
                    "field_path": "profile.occupation",
                    "summary": "试图自动修改职业",
                    "support_count": 3,
                    "window_count": 2,
                    "candidate_patch": {"profile": {"occupation": "画家"}},
                    "status": "pending",
                }
            ]
            engine._save_state(state)

            blocked = await engine.apply_core_patch("candidate-occupation", approval_reason="test")
            profile_after_block = json.loads((persona_dir / "profile.json").read_text(encoding="utf-8"))

            state = engine.get_state()
            state["signals"].append(
                {
                    "id": "major-signal",
                    "created_at": "2026-06-07T12:00:00+08:00",
                    "source_kind": "life_event",
                    "dimension": "backstory",
                    "subtype": "life_experience",
                    "direction": "intensify",
                    "confidence": 0.95,
                    "stability": 0.9,
                    "novelty": 0.8,
                    "importance": 0.95,
                    "summary": "她完成了一次明确的人生转折。",
                    "evidence_refs": ["major life change"],
                    "candidate_patch": {"profile": {"occupation": "画家"}},
                    "status": "merged",
                    "window_index": 1,
                    "reason": "major",
                    "life_event_type": "major",
                }
            )
            state["pending_promotions"] = [
                {
                    "id": "candidate-occupation-major",
                    "dimension": "backstory",
                    "field_path": "profile.occupation",
                    "summary": "verified major life change 改写职业",
                    "support_count": 1,
                    "window_count": 1,
                    "candidate_patch": {"profile": {"occupation": "画家"}},
                    "status": "pending",
                }
            ]
            engine._save_state(state)

            allowed = await engine.apply_core_patch("candidate-occupation-major", approval_reason="test")
            profile_after_allow = json.loads((persona_dir / "profile.json").read_text(encoding="utf-8"))

        self.assertFalse(blocked["applied"])
        self.assertEqual(profile_after_block["occupation"], "学生")
        self.assertTrue(allowed["applied"])
        self.assertEqual(profile_after_allow["occupation"], "画家")

    async def test_turn_cadence_reflects_after_eight_effective_turns(self):
        with TemporaryDirectory(prefix="evolution-turn-cadence-") as td:
            persona_dir = Path(td) / "bot" / "persona"
            _write_persona_bundle(persona_dir)
            engine = PersonaEvolutionEngine(bot_id="bot", persona_dir=persona_dir)

            last_result = None
            for index in range(8):
                last_result = await engine.capture_turn(
                    user_input=f"我们这周第 {index + 1} 次认真聊到一起面对压力时的感觉。",
                    bot_output="我会先接住你的情绪，再慢慢回应。",
                )

            state = load_evolution_state(persona_dir)

        self.assertIsNotNone(last_result)
        self.assertTrue(last_result["reflected"])
        self.assertTrue(state["last_reflection_at"])
        self.assertGreaterEqual(state["last_reflection_turn"], 8)

    async def test_bot_day_cadence_reflects_once_per_new_bot_day(self):
        with TemporaryDirectory(prefix="evolution-bot-day-cadence-") as td:
            persona_dir = Path(td) / "bot" / "persona"
            _write_persona_bundle(persona_dir)
            engine = PersonaEvolutionEngine(
                bot_id="bot",
                persona_dir=persona_dir,
                config={"reflection": {"turn_cadence": 99, "bot_day_cadence": 1}},
            )

            first = await engine.capture_turn(
                user_input="我们昨晚一起认真聊了你最近越来越会安慰人的变化。",
                bot_output="我也感觉自己最近更会先接住你的情绪了。",
                turn_context={"bot_current_date": "2026-06-07"},
            )
            state_after_first = load_evolution_state(persona_dir)

            second = await engine.capture_turn(
                user_input="今天还是想接着聊聊那次对话给我们的影响。",
                bot_output="嗯，我也一直记着那次聊完以后心里更稳了。",
                turn_context={"bot_current_date": "2026-06-07"},
            )
            state_after_second = load_evolution_state(persona_dir)

            third = await engine.capture_turn(
                user_input="新的一天了，我发现你说话还是比以前更温柔一点。",
                bot_output="被你这样说，我会更想把这种温柔认真留下来。",
                turn_context={"bot_current_date": "2026-06-08"},
            )
            state_after_third = load_evolution_state(persona_dir)

        self.assertTrue(first["reflected"])
        self.assertEqual(state_after_first["last_reflection_bot_date"], "2026-06-07")
        self.assertFalse(second["reflected"])
        self.assertEqual(state_after_second["last_reflection_bot_date"], "2026-06-07")
        self.assertTrue(third["reflected"])
        self.assertEqual(state_after_third["last_reflection_bot_date"], "2026-06-08")

    async def test_short_or_command_input_does_not_trigger_empty_reflection(self):
        with TemporaryDirectory(prefix="evolution-empty-reflection-") as td:
            persona_dir = Path(td) / "bot" / "persona"
            _write_persona_bundle(persona_dir)
            engine = PersonaEvolutionEngine(bot_id="bot", persona_dir=persona_dir)

            await engine.capture_turn(user_input="/memory", bot_output="收到")
            await engine.capture_turn(user_input="好的", bot_output="嗯")
            state = load_evolution_state(persona_dir)

        self.assertEqual(state["effective_turn_count"], 0)
        self.assertFalse(state["last_reflection_at"])


if __name__ == "__main__":
    unittest.main()
