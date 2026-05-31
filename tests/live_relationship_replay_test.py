import asyncio
import tempfile
import unittest
from pathlib import Path

from ai_companion.memory.engine import MemoryEngine


class LiveRelationshipReplayTest(unittest.TestCase):
    def test_committed_relationship_query_exposes_generation_guard(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="relationship-replay-") as td:
                engine = MemoryEngine("replay_bot", Path(td), config={"embedding": "none"})
                await engine.init()
                await engine.relationship.apply_event(
                    bot_id="replay_bot",
                    user_id="default_user",
                    label="恋人",
                    intimacy_delta=80,
                    trust_delta=80,
                    affection_delta=80,
                    attitude_delta=30,
                    key_moment="正式确认恋人关系",
                )
                ctx = await engine.load_context("你忘了我是你男朋友？")
                await engine.close()
                return ctx

        ctx = asyncio.run(run())
        suffix = ctx.get("system_suffix", "")
        contract = ctx.get("continuity_contract", {})
        hard_facts = contract.get("hard_facts") or []
        self.assertTrue(any("不能否认" in str(item.get("text")) or "已确认" in str(item.get("text")) for item in hard_facts))
        self.assertIn("连续性硬约束", suffix)


if __name__ == "__main__":
    unittest.main()
