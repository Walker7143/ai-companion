import gc
import shutil
import tempfile
import unittest
from pathlib import Path

from ai_companion.memory.session_state import (
    ResponseStateConsistencyChecker,
    SessionStateDiff,
    SessionStateResolver,
    SessionStateStore,
    extract_scene_summary,
)


class FakeSummarizer:
    def __init__(self, responses):
        self.responses = list(responses)

    async def chat(self, messages, system_prompt=None, max_tokens=None):
        if not self.responses:
            return {"content": ""}
        return {"content": self.responses.pop(0)}


class SessionStateMemoryTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = SessionStateStore(Path(self.temp_dir.name) / "session_state.db")
        await self.store.init()
        self.resolver = SessionStateResolver()

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def test_supersedes_previous_booking_state(self):
        first = SessionStateDiff(
            upserts=[
                {
                    "scope": "trip/lodging",
                    "subject": "shared",
                    "predicate": "booking_status",
                    "value": "还没订房",
                    "confidence": 0.7,
                    "source_kind": "joint_inference",
                }
            ]
        )
        await self.resolver.apply_diff(store=self.store, session_id="s1", diff=first, evidence_turn_id="t1")

        second = SessionStateDiff(
            upserts=[
                {
                    "scope": "trip/lodging",
                    "subject": "shared",
                    "predicate": "booking_status",
                    "value": "酒店已订好，房型是豪华大床房",
                    "confidence": 0.95,
                    "source_kind": "user_explicit",
                }
            ]
        )
        result = await self.resolver.apply_diff(store=self.store, session_id="s1", diff=second, evidence_turn_id="t2")
        active = await self.store.list_active_states("s1")
        self.assertEqual(1, len(active))
        self.assertIn("豪华大床房", active[0].value)
        self.assertEqual(1, len(result["superseded_state_ids"]))

    async def test_invalidate_current_scene(self):
        diff = SessionStateDiff(
            upserts=[
                {
                    "scope": "current_scene",
                    "subject": "shared",
                    "predicate": "next_action",
                    "value": "先去吃饭",
                    "confidence": 0.82,
                    "source_kind": "joint_inference",
                }
            ]
        )
        await self.resolver.apply_diff(store=self.store, session_id="s2", diff=diff, evidence_turn_id="t1")
        invalidate = SessionStateDiff(
            upserts=[
                {
                    "scope": "current_scene",
                    "subject": "shared",
                    "predicate": "next_action",
                    "value": "先去酒店放行李",
                    "confidence": 0.93,
                    "source_kind": "user_explicit",
                }
            ]
        )
        active_result = await self.resolver.apply_diff(store=self.store, session_id="s2", diff=invalidate, evidence_turn_id="t2")
        active = await self.store.list_active_states("s2")
        self.assertEqual("先去酒店放行李", active[0].value)
        self.assertTrue(active_result["superseded_state_ids"])

    async def test_current_scene_activity_and_posture_are_exclusive(self):
        await self.resolver.apply_diff(
            store=self.store,
            session_id="scene",
            diff=SessionStateDiff(
                upserts=[
                    {
                        "scope": "current_scene",
                        "subject": "assistant",
                        "predicate": "physical_state",
                        "value": "已在床上被子里",
                        "confidence": 0.95,
                        "source_kind": "joint_inference",
                    },
                    {
                        "scope": "current_scene",
                        "subject": "shared",
                        "predicate": "activity_type",
                        "value": "起床与早餐准备",
                        "confidence": 0.9,
                        "source_kind": "joint_inference",
                    },
                ]
            ),
            evidence_turn_id="t1",
        )
        result = await self.resolver.apply_diff(
            store=self.store,
            session_id="scene",
            diff=SessionStateDiff(
                upserts=[
                    {
                        "scope": "current_scene",
                        "subject": "shared",
                        "predicate": "current_activity",
                        "value": "共同进餐",
                        "confidence": 0.95,
                        "source_kind": "joint_inference",
                    },
                    {
                        "scope": "current_scene",
                        "subject": "shared",
                        "predicate": "spatial_relationship",
                        "value": "两人在餐桌旁同桌就坐",
                        "confidence": 0.9,
                        "source_kind": "joint_inference",
                    },
                ]
            ),
            evidence_turn_id="t2",
        )
        active = await self.store.list_active_states("scene")
        values = [item.value for item in active]
        self.assertIn("共同进餐", values)
        self.assertIn("两人在餐桌旁同桌就坐", values)
        self.assertNotIn("起床与早餐准备", values)
        self.assertNotIn("已在床上被子里", values)
        self.assertGreaterEqual(len(result["superseded_state_ids"]), 2)

    async def test_vehicle_scene_blocks_assistant_room_reset_write(self):
        await self.resolver.apply_diff(
            store=self.store,
            session_id="vehicle",
            diff=SessionStateDiff(
                upserts=[
                    {
                        "scope": "current_scene",
                        "subject": "shared",
                        "predicate": "current_location",
                        "value": "车上/车内，正在出行路线上",
                        "confidence": 0.96,
                        "source_kind": "user_explicit",
                    },
                    {
                        "scope": "current_scene",
                        "subject": "shared",
                        "predicate": "current_activity",
                        "value": "乘车前往大理古城",
                        "confidence": 0.96,
                        "source_kind": "user_explicit",
                    },
                ]
            ),
            evidence_turn_id="t1",
        )
        result = await self.resolver.apply_diff(
            store=self.store,
            session_id="vehicle",
            diff=SessionStateDiff(
                upserts=[
                    {
                        "scope": "current_scene",
                        "subject": "shared",
                        "predicate": "current_location",
                        "value": "客栈房间内，靠在床头，被子还盖着",
                        "confidence": 0.9,
                        "source_kind": "joint_inference",
                    },
                    {
                        "scope": "current_scene",
                        "subject": "user",
                        "predicate": "clothing_status_bottom",
                        "value": "未着下装",
                        "confidence": 0.8,
                        "source_kind": "joint_inference",
                    },
                ]
            ),
            evidence_turn_id="t2",
        )
        active = await self.store.list_active_states("vehicle")
        rendered = "\n".join(item.value for item in active)
        self.assertIn("车上", rendered)
        self.assertIn("乘车前往大理古城", rendered)
        self.assertNotIn("客栈房间", rendered)
        self.assertNotIn("未着下装", rendered)
        self.assertFalse(result["written"])

    async def test_rule_checker_catches_vehicle_to_room_reset_without_llm(self):
        checker = ResponseStateConsistencyChecker()
        from ai_companion.memory.session_state import SessionStateItem

        active = [
            SessionStateItem(
                state_id="v1",
                session_id="vehicle",
                scope="current_scene",
                subject="shared",
                predicate="current_location",
                value="车上/车内，正在出行路线上",
                confidence=0.96,
                status="active",
                effective_at="2026-06-01T15:00:00+08:00",
            )
        ]
        check = await checker.check("她靠在床头，掀了掀被角，说你连客栈大门都出不去。", active)
        self.assertFalse(check["consistent"])
        self.assertEqual("high", check["severity"])
        self.assertIn("vehicle_scene_room_reset", check.get("matched_rules") or [])

    async def test_scene_authority_blocks_meal_to_sleep_reset(self):
        await self.resolver.apply_diff(
            store=self.store,
            session_id="meal",
            diff=SessionStateDiff(
                upserts=[
                    {
                        "scope": "current_scene",
                        "subject": "shared",
                        "predicate": "current_activity",
                        "value": "共同进餐",
                        "confidence": 0.96,
                        "source_kind": "user_explicit",
                    },
                    {
                        "scope": "current_scene",
                        "subject": "shared",
                        "predicate": "current_location",
                        "value": "餐桌/餐厅场景",
                        "confidence": 0.96,
                        "source_kind": "user_explicit",
                    },
                ]
            ),
            evidence_turn_id="t1",
        )
        result = await self.resolver.apply_diff(
            store=self.store,
            session_id="meal",
            diff=SessionStateDiff(
                upserts=[
                    {
                        "scope": "current_scene",
                        "subject": "shared",
                        "predicate": "physical_state",
                        "value": "两人还躺在床上盖着被子",
                        "confidence": 0.86,
                        "source_kind": "joint_inference",
                    }
                ]
            ),
            evidence_turn_id="t2",
        )
        active = await self.store.list_active_states("meal")
        rendered = "\n".join(item.value for item in active)
        self.assertIn("共同进餐", rendered)
        self.assertNotIn("躺在床上", rendered)
        self.assertFalse(result["written"])

    async def test_scene_authority_variant_scope_is_exclusive(self):
        await self.resolver.apply_diff(
            store=self.store,
            session_id="variant",
            diff=SessionStateDiff(
                upserts=[
                    {
                        "scope": "current_scene",
                        "subject": "shared",
                        "predicate": "current_activity",
                        "value": "外出游览或抵达目的地",
                        "confidence": 0.9,
                        "source_kind": "joint_inference",
                    }
                ]
            ),
            evidence_turn_id="t1",
        )
        result = await self.resolver.apply_diff(
            store=self.store,
            session_id="variant",
            diff=SessionStateDiff(
                upserts=[
                    {
                        "scope": "current_scene/current_activity",
                        "subject": "shared",
                        "predicate": "current_activity",
                        "value": "房间内亲密互动或夜间安排执行中",
                        "confidence": 0.95,
                        "source_kind": "user_explicit",
                    }
                ]
            ),
            evidence_turn_id="t2",
        )
        active = await self.store.list_active_states("variant")
        rendered = "\n".join(f"{item.scope}:{item.value}" for item in active)
        self.assertIn("房间内亲密互动", rendered)
        self.assertNotIn("外出游览", rendered)
        self.assertTrue(result["superseded_state_ids"])

    async def test_scene_substate_variants_are_exclusive(self):
        await self.resolver.apply_diff(
            store=self.store,
            session_id="substate",
            diff=SessionStateDiff(
                upserts=[
                    {
                        "scope": "current_scene/night_activity_expectation",
                        "subject": "shared",
                        "predicate": "anticipation_status",
                        "value": "需重新协商夜间安排",
                        "confidence": 0.8,
                        "source_kind": "joint_inference",
                    },
                    {
                        "scope": "current_scene/current_player_role",
                        "subject": "assistant",
                        "predicate": "dominant_role",
                        "value": "助手主导角色已确认",
                        "confidence": 0.8,
                        "source_kind": "joint_inference",
                    },
                ]
            ),
            evidence_turn_id="t1",
        )
        result = await self.resolver.apply_diff(
            store=self.store,
            session_id="substate",
            diff=SessionStateDiff(
                upserts=[
                    {
                        "scope": "current_scene/night_activity_expectation/anticipation_status",
                        "subject": "shared",
                        "predicate": "anticipation_status",
                        "value": "实际执行中，跳过原定协商流程",
                        "confidence": 0.95,
                        "source_kind": "joint_inference",
                    },
                    {
                        "scope": "current_scene",
                        "subject": "shared",
                        "predicate": "current_player_role/dominant_role",
                        "value": "用户主导，助手服从但带一定主动性",
                        "confidence": 0.95,
                        "source_kind": "joint_inference",
                    },
                ]
            ),
            evidence_turn_id="t2",
        )
        active = await self.store.list_active_states("substate")
        rendered = "\n".join(f"{item.scope}:{item.predicate}:{item.value}" for item in active)
        self.assertIn("实际执行中", rendered)
        self.assertIn("用户主导", rendered)
        self.assertNotIn("需重新协商", rendered)
        self.assertNotIn("助手主导角色已确认", rendered)
        self.assertGreaterEqual(len(result["superseded_state_ids"]), 2)

    async def test_rule_checker_catches_meal_to_sleep_reset_without_llm(self):
        checker = ResponseStateConsistencyChecker()
        from ai_companion.memory.session_state import SessionStateItem

        active = [
            SessionStateItem(
                state_id="m1",
                session_id="meal",
                scope="current_scene",
                subject="shared",
                predicate="current_activity",
                value="共同进餐",
                confidence=0.96,
                status="active",
                effective_at="2026-06-01T15:00:00+08:00",
            )
        ]
        check = await checker.check("她缩回被子里，靠在床头说再睡一会。", active)
        self.assertFalse(check["consistent"])
        self.assertEqual("high", check["severity"])
        self.assertIn("scene_authority_conflict", check.get("matched_rules") or [])

    async def test_response_checker_allows_user_scene_transition_over_old_state(self):
        checker = ResponseStateConsistencyChecker()
        from ai_companion.memory.session_state import SessionStateItem

        active = [
            SessionStateItem(
                state_id="o1",
                session_id="outing",
                scope="current_scene",
                subject="shared",
                predicate="current_activity",
                value="外出游览或抵达目的地",
                confidence=0.96,
                status="active",
                effective_at="2026-06-01T18:00:00+08:00",
            )
        ]
        check = await checker.check(
            "她跟着你回到客栈房间，反手把门关上。",
            active,
            user_input="走，回客栈",
        )
        self.assertTrue(check["consistent"])
        self.assertIn("user_scene_transition_overrides_previous_state", check.get("matched_rules") or [])

    async def test_consistency_checker_rewrites_conflicting_reply(self):
        checker = ResponseStateConsistencyChecker(
            FakeSummarizer(
                [
                    '{"consistent": false, "severity": "high", "conflicts": ["回复否认了酒店已订"], "rewrite_guidance": "承认已经订房"}',
                    "那就直接去酒店放行李吧，房都已经订好了。",
                ]
            )
        )
        from ai_companion.memory.session_state import SessionStateItem

        await self.store.upsert_state(
            SessionStateItem(
                state_id="x1",
                session_id="s3",
                scope="trip/lodging",
                subject="shared",
                predicate="booking_status",
                value="酒店已订好",
                confidence=0.96,
                status="active",
                effective_at="2026-05-30T16:26:52+08:00",
            )
        )
        active = await self.store.list_active_states("s3")
        check = await checker.check("也不知道还有没有空房。", active)
        self.assertFalse(check["consistent"])
        rewritten = await checker.rewrite("也不知道还有没有空房。", active, check["conflicts"])
        self.assertIn("订好了", rewritten)

    async def test_booking_flow_matches_real_regression(self):
        await self.resolver.apply_diff(
            store=self.store,
            session_id="yangsisi-session",
            diff=SessionStateDiff(
                upserts=[
                    {
                        "scope": "trip/lodging",
                        "subject": "shared",
                        "predicate": "booking_status",
                        "value": "还没订房",
                        "confidence": 0.68,
                        "source_kind": "joint_inference",
                    }
                ]
            ),
            evidence_turn_id="3122",
        )
        await self.resolver.apply_diff(
            store=self.store,
            session_id="yangsisi-session",
            diff=SessionStateDiff(
                upserts=[
                    {
                        "scope": "trip/lodging",
                        "subject": "shared",
                        "predicate": "booking_status",
                        "value": "酒店已订好，房型是豪华大床房",
                        "confidence": 0.96,
                        "source_kind": "user_explicit",
                    }
                ]
            ),
            evidence_turn_id="3123",
        )
        active = await self.store.list_active_states("yangsisi-session")
        self.assertEqual(1, len(active))
        self.assertIn("豪华大床房", active[0].value)

        checker = ResponseStateConsistencyChecker(
            FakeSummarizer(
                [
                    '{"consistent": false, "severity": "high", "conflicts": ["回复回退到了未订房的旧设定"], "rewrite_guidance": "承认房已经订好"}',
                    "那就先去酒店放行李吧，房已经订好了。",
                ]
            )
        )
        check = await checker.check("也不知道那家客栈还有没有空房。", active)
        self.assertFalse(check["consistent"])
        rewritten = await checker.rewrite("也不知道那家客栈还有没有空房。", active, check["conflicts"])
        self.assertIn("房已经订好", rewritten)

    async def test_session_state_does_not_project_into_understanding(self):
        from ai_companion.memory.engine import MemoryEngine

        td = tempfile.mkdtemp(prefix="session-state-boundary-")
        try:
            engine = MemoryEngine("boundary_bot", Path(td), config={"embedding": "none"})
            await engine.init()
            engine.working.start_session("s-boundary")
            result = await self.resolver.apply_diff(
                store=engine.session_state,
                session_id="s-boundary",
                diff=SessionStateDiff(
                    upserts=[
                        {
                            "scope": "trip/lodging",
                            "subject": "shared",
                            "predicate": "booking_status",
                            "value": "酒店已订好，房型是豪华大床房",
                            "confidence": 0.96,
                            "source_kind": "user_explicit",
                        }
                    ]
                ),
                evidence_turn_id="t-boundary",
            )
            self.assertTrue(result["written"])
            understanding = engine.user_understanding.load()
            rendered = str(understanding.get("layered", {}))
            self.assertNotIn("豪华大床房", rendered)
            await engine.close()
            del engine
            gc.collect()
        finally:
            shutil.rmtree(td, ignore_errors=True)

    async def test_scene_authority_diff_writes_user_explicit_meal_scene(self):
        from ai_companion.memory.engine import MemoryEngine

        td = tempfile.mkdtemp(prefix="scene-authority-")
        try:
            engine = MemoryEngine("scene_bot", Path(td), config={"embedding": "none"})
            diff = engine._build_scene_authority_diff(
                user_input="起来吃饭去吧",
                bot_output="行，去餐桌旁坐下。",
                conversation_context="",
            )
            rendered = "\n".join(str(item.get("value")) for item in diff.upserts)
            self.assertIn("餐桌/餐厅场景", rendered)
            self.assertIn("共同进餐", rendered)
            self.assertTrue(all(item.get("source_kind") == "user_explicit" for item in diff.upserts))
        finally:
            shutil.rmtree(td, ignore_errors=True)

    async def test_scene_authority_diff_user_room_overrides_bot_outing_cue(self):
        from ai_companion.memory.engine import MemoryEngine

        td = tempfile.mkdtemp(prefix="scene-authority-room-")
        try:
            engine = MemoryEngine("scene_bot", Path(td), config={"embedding": "none"})
            diff = engine._build_scene_authority_diff(
                user_input="准备好了吗",
                bot_output="她在游览途中停下脚步。",
                conversation_context="用户：回到客栈，关门，脱衣服",
            )
            rendered = "\n".join(str(item.get("value")) for item in diff.upserts)
            self.assertIn("客栈房间/床边亲密场景", rendered)
            self.assertNotIn("户外/目的地游览场景", rendered)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    async def test_scene_authority_diff_ignores_bot_only_scene_prose(self):
        from ai_companion.memory.engine import MemoryEngine

        td = tempfile.mkdtemp(prefix="scene-authority-bot-only-")
        try:
            engine = MemoryEngine("scene_bot", Path(td), config={"embedding": "none"})
            diff = engine._build_scene_authority_diff(
                user_input="我到北京了",
                bot_output="她单手扶着方向盘，笑着让你先回家睡觉。",
                conversation_context="",
            )
            self.assertFalse(diff.upserts)
            self.assertTrue(diff.no_change)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    async def test_scene_authority_diff_marks_user_only_arrival_as_user_subject(self):
        from ai_companion.memory.engine import MemoryEngine

        td = tempfile.mkdtemp(prefix="scene-authority-user-only-")
        try:
            engine = MemoryEngine("scene_bot", Path(td), config={"embedding": "none"})
            diff = engine._build_scene_authority_diff(
                user_input="我到北京了，先回家睡觉",
                bot_output="好，你先休息。",
                conversation_context="",
            )
            self.assertTrue(diff.upserts)
            self.assertTrue(all(item.get("subject") == "user" for item in diff.upserts))
        finally:
            shutil.rmtree(td, ignore_errors=True)

    async def test_scene_authority_diff_marks_assistant_status_query_as_assistant_subject(self):
        from ai_companion.memory.engine import MemoryEngine

        td = tempfile.mkdtemp(prefix="scene-authority-assistant-only-")
        try:
            engine = MemoryEngine("scene_bot", Path(td), config={"embedding": "none"})
            diff = engine._build_scene_authority_diff(
                user_input="你怎么还没回客栈",
                bot_output="我马上回去。",
                conversation_context="",
            )
            self.assertTrue(diff.upserts)
            self.assertTrue(all(item.get("subject") == "assistant" for item in diff.upserts))
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_extract_scene_summary_ignores_user_only_scene(self):
        active = [
            {
                "scope": "current_scene",
                "subject": "user",
                "predicate": "current_location",
                "value": "北京，刚落地到家",
            },
            {
                "scope": "current_scene",
                "subject": "user",
                "predicate": "current_activity",
                "value": "准备回家睡觉",
            },
        ]
        self.assertIsNone(extract_scene_summary(active))

    async def test_relationship_consistency_rewrites_denial_of_confirmed_partner_status(self):
        from ai_companion.memory.engine import MemoryEngine

        class RelationshipSummarizer:
            async def chat(self, messages, system_prompt=None, max_tokens=None):
                text = str(messages[-1].get("content") or "")
                if "判断回复是否和当前状态冲突" in text:
                    return {"content": '{"consistent": true, "severity": "none", "conflicts": [], "rewrite_guidance": ""}'}
                if "你是关系一致性裁判" in text:
                    return {"content": '{"consistent": false, "severity": "high", "conflicts": ["回复否认了已经确认的恋人关系"], "rewrite_guidance": "承接恋人关系，但可以嘴硬"}'}
                if "你要重写一条回复，使其承接已经确认的关系事实" in text:
                    return {"content": "……男朋友就男朋友，少得意，先过来吃早餐。"}
                return {"content": ""}

            async def summarize_old_conversation(self, old_messages_text):
                return old_messages_text[:120]

        td = tempfile.mkdtemp(prefix="relationship-consistency-")
        try:
            engine = MemoryEngine("relationship_bot", Path(td), config={"embedding": "none"})
            await engine.init()
            engine.set_summarizer(RelationshipSummarizer())
            rewritten, result = await engine.ensure_response_state_consistency(
                "……谁给你封的官儿啊？我怎么不记得批准过这任命？",
                session_id="s-relationship",
                relationship_state={
                    "relationship_label": "恋人",
                    "relationship_narrative": "你们已经确认恋人/男女朋友关系，关系很亲近。",
                    "interaction_guidance": "承接已经确认的恋人关系；可用少量共同记忆和亲近语气，但不要否认关系事实。",
                },
            )
            self.assertFalse(result["consistent"])
            self.assertIn("恋人关系", "".join(result["conflicts"]))
            self.assertIn("男朋友", rewritten)
            await engine.close()
            del engine
            gc.collect()
        finally:
            shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
