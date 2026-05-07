import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_companion.proactive.life_config import LifeConfig
from ai_companion.proactive.life_engine import LifeEngine
from ai_companion.proactive.life_state import LifeState


class EmptyLifeModel:
    provider = "test"

    async def chat(self, messages, system_prompt="", **kwargs):
        text = messages[-1].get("content", "") if messages else ""
        if "输出一个 JSON 对象" in text:
            return '{"is_major": false, "reason": "test"}'
        return "[]"


class LifeEngineTickTest(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_milestones_do_not_break_daily_tick_checkpoint(self):
        with TemporaryDirectory(prefix="life-milestone-bad-config-") as td:
            state = LifeState("bad_milestone_bot", Path(td))
            state.current_date = "2024-01-01"
            state.initial_age = 20
            state.bot_age_days = 364
            state.last_checked_age = 19
            state.last_daily_tick = datetime.now() - timedelta(days=1, seconds=1)
            previous_tick = state.last_daily_tick

            cfg = LifeConfig(
                daily_interval_seconds=86400,
                major_interval_seconds=604800,
                time_ratio=1,
                milestones=[
                    {"event": "缺少 age 的坏配置"},
                    {"age": "21", "event": "合法里程碑"},
                ],
            )
            engine = LifeEngine("bad_milestone_bot", cfg, state, model=EmptyLifeModel())

            await engine.tick_daily()

            data = state.to_dict()
            self.assertEqual(data["current_date"], "2024-01-02")
            self.assertEqual(data["bot_age_days"], 365)
            self.assertIsNotNone(state.last_daily_tick)
            self.assertGreater(state.last_daily_tick, previous_tick)
            self.assertEqual(data["last_checked_age"], 21)
            self.assertEqual(data["triggered_milestones"], [21])
            self.assertEqual(len(data["major_life_events"]), 1)
            self.assertEqual(data["major_life_events"][0]["description"], "合法里程碑")

    async def test_all_invalid_milestones_are_skipped_without_repeat_tick_risk(self):
        with TemporaryDirectory(prefix="life-milestone-all-bad-") as td:
            state = LifeState("all_bad_milestone_bot", Path(td))
            state.current_date = "2024-01-01"
            state.initial_age = 20
            state.bot_age_days = 364
            state.last_checked_age = 19
            state.last_daily_tick = datetime.now() - timedelta(days=1, seconds=1)
            previous_tick = state.last_daily_tick

            cfg = LifeConfig(
                daily_interval_seconds=86400,
                major_interval_seconds=604800,
                time_ratio=1,
                milestones=[
                    {"event": "缺少 age 的坏配置"},
                    {"age": "二十一", "event": "中文年龄不是合法数字"},
                    "not-a-dict",
                ],
            )
            engine = LifeEngine("all_bad_milestone_bot", cfg, state, model=EmptyLifeModel())

            await engine.tick_daily()

            data = state.to_dict()
            self.assertEqual(data["current_date"], "2024-01-02")
            self.assertEqual(data["bot_age_days"], 365)
            self.assertIsNotNone(state.last_daily_tick)
            self.assertGreater(state.last_daily_tick, previous_tick)
            self.assertEqual(data["last_checked_age"], 21)
            self.assertEqual(data["triggered_milestones"], [])
            self.assertEqual(data["major_life_events"], [])


if __name__ == "__main__":
    unittest.main()
