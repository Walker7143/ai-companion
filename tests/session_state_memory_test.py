import tempfile
import unittest
from pathlib import Path

from ai_companion.memory.session_state import (
    ResponseStateConsistencyChecker,
    SessionStateDiff,
    SessionStateResolver,
    SessionStateStore,
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
        await self.resolver.apply_diff(
            store=self.store,
            session_id="s1",
            diff=first,
            evidence_turn_id="t1",
        )
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
        result = await self.resolver.apply_diff(
            store=self.store,
            session_id="s1",
            diff=second,
            evidence_turn_id="t2",
        )
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

    async def test_consistency_checker_rewrites_conflicting_reply(self):
        checker = ResponseStateConsistencyChecker(
            FakeSummarizer(
                [
                    '{"consistent": false, "severity": "high", "conflicts": ["回复否认了酒店已订"], "rewrite_guidance": "承认已经订房"}',
                    "那就直接去酒店放行李吧，房都已经订好了。",
                ]
            )
        )
        await self.store.upsert_state(
            __import__("ai_companion.memory.session_state", fromlist=["SessionStateItem"]).SessionStateItem(
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

        with tempfile.TemporaryDirectory(prefix="session-state-boundary-") as td:
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


if __name__ == "__main__":
    unittest.main()
