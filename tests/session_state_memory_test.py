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
