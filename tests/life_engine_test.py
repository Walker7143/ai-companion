import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_companion.proactive.life_config import LifeConfig
from ai_companion.proactive.life_engine import LifeEngine
from ai_companion.proactive.life_state import LifeEvent, LifeState


class EmptyLifeModel:
    provider = "test"

    async def chat(self, messages, system_prompt="", **kwargs):
        text = messages[-1].get("content", "") if messages else ""
        if "输出一个 JSON 对象" in text:
            return '{"is_major": false, "reason": "test"}'
        return "[]"


class LifeEngineTickTest(unittest.IsolatedAsyncioTestCase):
    def test_daily_life_profile_summary_keeps_current_life_anchor_fields(self):
        with TemporaryDirectory(prefix="life-profile-anchor-") as td:
            cfg = LifeConfig(
                daily_life_profile={
                    "location": "在大理经营一间叫'我在风花雪月里等你'的客栈。",
                    "daily_routine": "打理客栈日常，接待住客，在洱海边散步。",
                    "living_situation": "住在大理客栈里。",
                    "emotional_state": "等待中带着一丝不甘和坚持。",
                },
                sync_with_local_time_when_realtime=False,
            )
            engine = LifeEngine("anchor_bot", cfg, LifeState("anchor_bot", Path(td)), model=EmptyLifeModel())

            summary = engine._daily_life_profile_summary()

            self.assertIn("大理", summary)
            self.assertIn("客栈", summary)
            self.assertIn("洱海", summary)
            self.assertIn("emotional_state", summary)
            self.assertNotEqual(summary, "未配置")

    def test_daily_scenario_weights_respect_current_life_anchor(self):
        with TemporaryDirectory(prefix="life-profile-weight-") as td:
            cfg = LifeConfig(
                daily_life_profile={
                    "location": "在大理经营一间叫'我在风花雪月里等你'的客栈。",
                    "daily_routine": "打理客栈日常，接待住客，在洱海边散步。",
                },
                sync_with_local_time_when_realtime=False,
            )
            engine = LifeEngine("anchor_bot", cfg, LifeState("anchor_bot", Path(td)), model=EmptyLifeModel())

            catalog = {item["key"]: item for item in engine._daily_scenario_catalog()}

            self.assertNotIn("office_gossip", catalog)
            self.assertNotIn("commute_delay", catalog)
            self.assertIn("lunch_discovery", catalog)
            self.assertGreater(catalog["lunch_discovery"]["weight"], 1.0)

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
                sync_with_local_time_when_realtime=False,
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
                sync_with_local_time_when_realtime=False,
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

    async def test_realtime_sync_uses_local_calendar_without_forcing_next_day(self):
        with TemporaryDirectory(prefix="life-realtime-local-sync-") as td:
            state = LifeState("realtime_local_sync_bot", Path(td))
            local_now = datetime.now().astimezone()
            state.current_date = local_now.strftime("%Y-%m-%d")
            state.birth_date = "1990-01-01"
            state.initial_age = 20
            state.bot_age_days = 10

            cfg = LifeConfig(
                daily_interval_seconds=86400,
                major_interval_seconds=604800,
                time_ratio=1,
                sync_with_local_time_when_realtime=True,
            )
            engine = LifeEngine("realtime_local_sync_bot", cfg, state, model=EmptyLifeModel())

            await engine.tick_daily()
            status = engine.get_status()

            self.assertEqual(state.current_date, local_now.strftime("%Y-%m-%d"))
            self.assertEqual(state.day_of_week, ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][local_now.weekday()])
            self.assertEqual(state.current_month, local_now.month)
            self.assertEqual(state.current_season, engine._get_season(local_now.month))
            self.assertEqual(state.bot_age_days, 10)
            self.assertEqual(status["current_date"], local_now.strftime("%Y-%m-%d"))
            self.assertIn(status["time_of_day"], {"凌晨", "上午", "中午", "下午", "晚上", "白天"})

    def test_stale_current_activity_is_hidden_from_prompt_status(self):
        with TemporaryDirectory(prefix="life-stale-activity-") as td:
            state = LifeState("stale_activity_bot", Path(td))
            local_now = datetime.now().astimezone()
            state.current_date = local_now.strftime("%Y-%m-%d")
            state.day_of_week = ["鍛ㄤ竴", "鍛ㄤ簩", "鍛ㄤ笁", "鍛ㄥ洓", "鍛ㄤ簲", "鍛ㄥ叚", "鍛ㄦ棩"][local_now.weekday()]
            state.current_month = local_now.month
            state.current_season = "鏄?"
            state.bot_current_activity = "鍦ㄥ悆鍗堥キ"
            state.bot_current_activity_updated_at = local_now - timedelta(hours=3)

            cfg = LifeConfig(sync_with_local_time_when_realtime=True)
            engine = LifeEngine("stale_activity_bot", cfg, state, model=EmptyLifeModel())

            status = engine.get_status()

            self.assertEqual(status["bot_current_activity"], "")

    def test_current_activity_respects_configured_expire_hours(self):
        with TemporaryDirectory(prefix="life-activity-expire-config-") as td:
            state = LifeState("activity_expire_config_bot", Path(td))
            local_now = datetime.now().astimezone()
            state.current_date = local_now.strftime("%Y-%m-%d")
            state.day_of_week = ["鍛ㄤ竴", "鍛ㄤ簩", "鍛ㄤ笁", "鍛ㄥ洓", "鍛ㄤ簲", "鍛ㄥ叚", "鍛ㄦ棩"][local_now.weekday()]
            state.current_month = local_now.month
            state.current_season = "鏄?"
            state.bot_current_activity = "鍦ㄥ悆鍗堥キ"
            state.bot_current_activity_updated_at = local_now - timedelta(hours=3)

            cfg = LifeConfig(sync_with_local_time_when_realtime=True, current_activity_expire_hours=4)
            engine = LifeEngine("activity_expire_config_bot", cfg, state, model=EmptyLifeModel())

            status = engine.get_status()

            self.assertEqual(status["bot_current_activity"], "鍦ㄥ悆鍗堥キ")

    def test_legacy_activity_without_timestamp_is_hidden(self):
        with TemporaryDirectory(prefix="life-legacy-activity-") as td:
            state = LifeState("legacy_activity_bot", Path(td))
            local_now = datetime.now().astimezone()
            state.current_date = local_now.strftime("%Y-%m-%d")
            state.day_of_week = ["鍛ㄤ竴", "鍛ㄤ簩", "鍛ㄤ笁", "鍛ㄥ洓", "鍛ㄤ簲", "鍛ㄥ叚", "鍛ㄦ棩"][local_now.weekday()]
            state.current_month = local_now.month
            state.current_season = "鏄?"
            state._state["bot_current_activity"] = "鍦ㄥ悆鍗堥キ"
            state._state["bot_current_activity_updated_at"] = None

            cfg = LifeConfig(sync_with_local_time_when_realtime=True)
            engine = LifeEngine("legacy_activity_bot", cfg, state, model=EmptyLifeModel())

            status = engine.get_status()

            self.assertEqual(status["bot_current_activity"], "")

    def test_future_evening_events_are_hidden_from_noon_status(self):
        with TemporaryDirectory(prefix="life-future-evening-event-") as td:
            state = LifeState("future_evening_bot", Path(td))
            cfg = LifeConfig(sync_with_local_time_when_realtime=False)
            engine = LifeEngine("future_evening_bot", cfg, state, model=EmptyLifeModel())
            engine._get_local_now = lambda: datetime(2026, 5, 9, 12, 1).astimezone()
            state.current_date = "2026-05-09"
            state.day_of_week = "周六"
            state.current_month = 5
            state.current_season = "春"
            state.add_event(
                LifeEvent(
                    description="2026-05-09 午饭去楼下新开的牛肉面馆，汤头意外地不错。",
                    scenario_key="lunch_discovery",
                    shareable=True,
                )
            )
            state.add_event(
                LifeEvent(
                    description="2026-05-09 晚饭后去小区快走了3公里，刚开始不想动，走完反而清醒不少。",
                    scenario_key="night_walk",
                    shareable=True,
                )
            )

            status = engine.get_status()

            descriptions = [item["description"] for item in status["recent_life_events"]]
            self.assertTrue(any("午饭去楼下" in item for item in descriptions))
            self.assertFalse(any("晚饭后去小区快走" in item for item in descriptions))

    def test_old_daily_events_are_not_current_recent_status(self):
        with TemporaryDirectory(prefix="life-old-recent-event-") as td:
            state = LifeState("old_recent_bot", Path(td))
            cfg = LifeConfig(sync_with_local_time_when_realtime=False, recent_status_window_days=3)
            engine = LifeEngine("old_recent_bot", cfg, state, model=EmptyLifeModel())
            engine._get_local_now = lambda: datetime(2026, 5, 20, 12, 1).astimezone()
            state.current_date = "2026-05-20"
            state.day_of_week = "周三"
            state.current_month = 5
            state.current_season = "春"
            state.add_event(
                LifeEvent(
                    timestamp="2026-05-12T11:21:24",
                    description="核对完数据后去客栈附近那家云贵小馆，点了一份酸汤牛肉粉。",
                    scenario_key="food_moment_11",
                    shareable=True,
                )
            )
            state.add_event(
                LifeEvent(
                    timestamp="2026-05-20T11:44:49",
                    description="2026-05-20 有人约周末吃饭，她反复看日程，终于空出一段时间。",
                    scenario_key="social_signal_09",
                    shareable=True,
                )
            )

            status = engine.get_status()

            descriptions = [item["description"] for item in status["recent_life_events"]]
            self.assertFalse(any("酸汤牛肉粉" in item for item in descriptions))
            self.assertTrue(any("周末吃饭" in item for item in descriptions))

    def test_daily_candidates_exclude_evening_only_scenarios_at_noon(self):
        with TemporaryDirectory(prefix="life-noon-candidates-") as td:
            state = LifeState("candidate_time_bot", Path(td))
            state.current_date = "2026-05-09"
            cfg = LifeConfig(sync_with_local_time_when_realtime=False)
            engine = LifeEngine("candidate_time_bot", cfg, state, model=EmptyLifeModel())

            candidates = engine._daily_scenario_candidates(set(), current_hour=12, limit=10000)
            keys = {item["key"] for item in candidates}

            self.assertIn("lunch_discovery", keys)
            self.assertNotIn("night_walk", keys)

    def test_render_scenario_uses_time_compatible_template(self):
        with TemporaryDirectory(prefix="life-compatible-template-") as td:
            state = LifeState("render_time_bot", Path(td))
            state.current_date = "2026-05-09"
            cfg = LifeConfig(sync_with_local_time_when_realtime=False)
            engine = LifeEngine("render_time_bot", cfg, state, model=EmptyLifeModel())
            engine._get_local_now = lambda: datetime(2026, 5, 9, 12, 1).astimezone()
            scenario = {
                "key": "mixed_food",
                "templates": [
                    "{date} 晚上试着自己炒菜，盐放得有点重。",
                    "{date} 中午随手买的饭团意外好吃。",
                ],
            }

            description = engine._render_scenario_description(scenario)

            self.assertIn("中午随手买的饭团", description)
            self.assertNotIn("晚上试着自己炒菜", description)


if __name__ == "__main__":
    unittest.main()
