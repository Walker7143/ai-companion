import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_companion.persona.runtime_profile import (
    apply_runtime_profile_overlay,
    load_runtime_profile,
    merge_runtime_profile,
    runtime_profile_path_from_persona_dir,
    write_runtime_profile,
)


class RuntimeProfileTest(unittest.TestCase):
    def test_apply_runtime_profile_overlay_merges_profile_and_backstory(self):
        profile = {
            "name": "Test Bot",
            "relationship_to_user": "朋友",
        }
        backstory = {
            "key_moments": ["第一次见面"],
            "shared_experiences": ["一起淋过雨"],
            "life_experiences": ["独自搬家"],
        }
        runtime = {
            "relationship_to_user": "暧昧中",
            "attitude_score": 78,
            "key_moments": ["深夜和好"],
            "shared_experiences": ["一起淋过雨", "在客栈门口一起收桌布"],
            "shared_growth_summary": "这些共同经历让她越来越习惯把用户放进自己的日常节奏里。",
            "life_experiences": ["独自搬家", "决定重新安排未来半年的生活"],
            "life_growth_summary": "这些人生经历让她对自己的生活方向更有掌控感。",
        }

        merged_profile, merged_backstory = apply_runtime_profile_overlay(profile, backstory, runtime)

        self.assertEqual(merged_profile["relationship_to_user"], "暧昧中")
        self.assertEqual(merged_profile["attitude_score"], 78)
        self.assertEqual(
            merged_backstory["key_moments"],
            ["第一次见面", "深夜和好"],
        )
        self.assertEqual(
            merged_backstory["shared_experiences"],
            ["一起淋过雨", "在客栈门口一起收桌布"],
        )
        self.assertEqual(
            merged_backstory["life_experiences"],
            ["独自搬家", "决定重新安排未来半年的生活"],
        )
        self.assertEqual(
            merged_backstory["shared_growth_summary"],
            "这些共同经历让她越来越习惯把用户放进自己的日常节奏里。",
        )
        self.assertEqual(
            merged_backstory["life_growth_summary"],
            "这些人生经历让她对自己的生活方向更有掌控感。",
        )

    def test_merge_runtime_profile_dedupes_lists_and_preserves_existing_fields(self):
        runtime_profile = {
            "shared_experiences": ["一起淋过雨"],
            "life_experiences": ["独自搬家"],
            "relationship_to_user": "朋友",
        }
        patch = {
            "shared_experiences": ["  一起淋过雨  ", "在客栈门口一起收桌布"],
            "life_experiences": ["独自搬家", "决定重新安排未来半年的生活"],
            "relationship_to_user": "暧昧中",
            "shared_growth_summary": "关系正在慢慢靠近。",
        }

        merged, changed = merge_runtime_profile(
            runtime_profile,
            patch,
            list_limits={
                "shared_experiences": 20,
                "life_experiences": 20,
            },
        )

        self.assertTrue(changed)
        self.assertEqual(
            merged["shared_experiences"],
            ["一起淋过雨", "在客栈门口一起收桌布"],
        )
        self.assertEqual(
            merged["life_experiences"],
            ["独自搬家", "决定重新安排未来半年的生活"],
        )
        self.assertEqual(merged["relationship_to_user"], "暧昧中")
        self.assertEqual(merged["shared_growth_summary"], "关系正在慢慢靠近。")

    def test_runtime_profile_round_trip(self):
        with TemporaryDirectory(prefix="runtime-profile-roundtrip-") as td:
            persona_dir = Path(td) / "bot" / "persona"
            path = runtime_profile_path_from_persona_dir(persona_dir)
            payload = {
                "shared_experiences": ["在客栈门口一起收桌布"],
                "life_experiences": ["决定重新安排未来半年的生活"],
                "relationship_state": {"stage": "暧昧中"},
            }

            written = write_runtime_profile(path, payload)
            loaded = load_runtime_profile(path)

            self.assertTrue(written)
            self.assertTrue(path.exists())
            self.assertEqual(loaded["shared_experiences"], payload["shared_experiences"])
            self.assertEqual(loaded["life_experiences"], payload["life_experiences"])
            self.assertEqual(loaded["relationship_state"], payload["relationship_state"])
            self.assertIn("updated_at", loaded)
            json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
