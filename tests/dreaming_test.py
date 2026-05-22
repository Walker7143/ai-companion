import asyncio
import tempfile
import unittest
from pathlib import Path

from ai_companion.memory.engine import MemoryEngine


class DreamingIntegrationTest(unittest.TestCase):
    def test_memory_engine_exposes_dreaming_status_and_run(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="dreaming-engine-") as td:
                engine = MemoryEngine(
                    "dream_bot",
                    Path(td),
                    config={
                        "embedding": "none",
                        "dreaming": {
                            "enabled": True,
                            "auto_run_enabled": False,
                            "report_retention": 5,
                            "max_candidates": 12,
                            "max_promotions": 3,
                        },
                    },
                )
                await engine.init()
                await engine.semantic.set_fact(
                    "reply_style",
                    "用户更喜欢简短直接的回应。",
                    bot_id="dream_bot",
                    user_id="default_user",
                    category="communication_style",
                    confidence=0.62,
                    source="test",
                )
                result = await engine.dreaming.run(trigger_source="test", trigger_reason="unit_test")
                status = await engine.get_memory_status()
                report = await engine.dreaming.latest_report()
                doctor = await engine.dreaming.doctor_status()
                await engine.close()
                return result, status, report, doctor

        result, status, report, doctor = asyncio.run(run())
        self.assertEqual(result["run"]["status"], "completed")
        self.assertIn("dreaming", status)
        self.assertTrue(status["dreaming"]["enabled"])
        self.assertIsNotNone(report)
        self.assertIn("本次记忆整理完成", report["user_summary"])
        self.assertIn("ok", doctor)


if __name__ == "__main__":
    unittest.main()
