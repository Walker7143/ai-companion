import gc
import shutil
import tempfile
import unittest
from pathlib import Path

from ai_companion.memory.engine import MemoryEngine


class SequencedSummarizer:
    def __init__(self, outputs):
        self.outputs = list(outputs)

    async def chat(self, messages, system_prompt=None, max_tokens=None):
        if not self.outputs:
            return {"content": ""}
        return {"content": self.outputs.pop(0)}

    async def summarize_old_conversation(self, old_messages_text):
        return old_messages_text[:120]


class SessionStateIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_realistic_booking_regression_flow(self):
        td = tempfile.mkdtemp(prefix="session-state-integration-")
        try:
            engine = MemoryEngine("state_bot", Path(td), config={"embedding": "none"})
            summarizer = SequencedSummarizer(
                [
                    '{"facts":[],"episodes":[],"relationship":{},"open_threads":[]}',
                    '{"upserts":[{"scope":"trip/lodging","subject":"shared","predicate":"booking_status","value":"酒店还没订","confidence":0.72,"source_kind":"joint_inference","expires_hours":72,"reason":"当前对话仍在询问住哪里"}],"confirmations":[],"invalidations":[],"no_change":false,"confidence_explanations":["从对话看仍未订房"]}',
                    '{"facts":[],"episodes":[],"relationship":{},"open_threads":[]}',
                    '{"upserts":[{"scope":"trip/lodging","subject":"shared","predicate":"booking_status","value":"酒店已订好，房型是豪华大床房","confidence":0.96,"source_kind":"user_explicit","expires_hours":72,"reason":"用户明确说已经定了豪华大床房"}],"confirmations":[],"invalidations":[],"no_change":false,"confidence_explanations":["用户明确更新了订房状态"]}',
                    '{"consistent": false, "severity": "high", "conflicts": ["回复回退到了未订房旧设定"], "rewrite_guidance": "必须承认酒店已经订好"}',
                    "那就先去酒店放行李吧，房已经订好了。",
                ]
            )
            await engine.init()
            engine.set_summarizer(summarizer)

            ctx1 = await engine.record_turn("我们住哪个酒店？", "还没订呢", turn_context={"session_id": "s1"})
            await engine.extract_turn_memory("我们住哪个酒店？", "还没订呢", turn_context=ctx1)
            ctx2 = await engine.record_turn("好，那我定一个豪华大床房", "随便你。", turn_context={"session_id": "s1"})
            await engine.extract_turn_memory("好，那我定一个豪华大床房", "随便你。", turn_context=ctx2)

            active = await engine.session_state.list_active_states("s1")
            self.assertTrue(active)
            self.assertEqual("trip/lodging", active[0].scope)
            self.assertEqual("booking_status", active[0].predicate)

            loaded = await engine.load_context("我们先去酒店吧行李放下吧")
            loaded_active = loaded.get("session_state") or []
            self.assertTrue(loaded_active)
            self.assertEqual("trip/lodging", str(loaded_active[0].get("scope")))
            self.assertEqual("booking_status", str(loaded_active[0].get("predicate")))

            rewritten, check = await engine.ensure_response_state_consistency("也不知道那家客栈还有没有空房。", "s1")
            self.assertFalse(check["consistent"])
            self.assertTrue(rewritten)

            await engine.close()
            del engine
            gc.collect()
        finally:
            shutil.rmtree(td, ignore_errors=True)

    async def test_yangsisi_runtime_trace_shape(self):
        td = tempfile.mkdtemp(prefix="session-state-yangsisi-")
        try:
            engine = MemoryEngine("yangsisi_like", Path(td), config={"embedding": "none"})
            summarizer = SequencedSummarizer(
                [
                    '{"facts":[],"episodes":[],"relationship":{},"open_threads":[]}',
                    '{"upserts":[{"scope":"trip/lodging","subject":"shared","predicate":"booking_status","value":"酒店还没订","confidence":0.72,"source_kind":"joint_inference","expires_hours":72,"reason":"仍在讨论住哪里"}],"confirmations":[],"invalidations":[],"no_change":false,"confidence_explanations":["初始状态仍未订房"]}',
                    '{"facts":[],"episodes":[],"relationship":{},"open_threads":[]}',
                    '{"upserts":[{"scope":"trip/lodging","subject":"shared","predicate":"booking_status","value":"酒店已订好，房型已确认","confidence":0.96,"source_kind":"user_explicit","expires_hours":72,"reason":"用户明确表示已经订好房间"}],"confirmations":[],"invalidations":[],"no_change":false,"confidence_explanations":["用户显式更新状态"]}',
                    '{"facts":[],"episodes":[],"relationship":{},"open_threads":[]}',
                    '{"upserts":[{"scope":"current_scene","subject":"shared","predicate":"next_action","value":"先去酒店放行李","confidence":0.91,"source_kind":"user_explicit","expires_hours":24,"reason":"用户明确提出先去酒店"}],"confirmations":[{"scope":"trip/lodging","predicate":"booking_status","reason":"用户默认承接已订房状态"}],"invalidations":[],"no_change":false,"confidence_explanations":["当前行动改为先去酒店"]}',
                    '{"consistent": false, "severity": "high", "conflicts": ["回复重新引入了未订房旧设定"], "rewrite_guidance": "承认房已订并承接先去酒店"}',
                    "那就先去酒店放行李吧，房间已经订好了。",
                ]
            )
            await engine.init()
            engine.set_summarizer(summarizer)

            sid = "gw_0e8b96602add5da387e35fb8"
            ctx1 = await engine.record_turn("我们住哪个酒店？", "还没订呢。", turn_context={"session_id": sid})
            await engine.extract_turn_memory("我们住哪个酒店？", "还没订呢。", turn_context=ctx1)
            ctx2 = await engine.record_turn("好，那我定一个豪华大床房", "随便你。", turn_context={"session_id": sid})
            await engine.extract_turn_memory("好，那我定一个豪华大床房", "随便你。", turn_context=ctx2)
            ctx3 = await engine.record_turn("我们先去酒店吧行李放下吧", "行吧。", turn_context={"session_id": sid})
            await engine.extract_turn_memory("我们先去酒店吧行李放下吧", "行吧。", turn_context=ctx3)

            active = await engine.session_state.list_active_states(sid)
            slots = {(item.scope, item.predicate): item for item in active}
            self.assertIn(("trip/lodging", "booking_status"), slots)
            self.assertIn(("current_scene", "next_action"), slots)

            rewritten, check = await engine.ensure_response_state_consistency(
                "也不知道那家客栈还有没有空房。",
                sid,
            )
            self.assertFalse(check["consistent"])
            self.assertTrue(rewritten)

            await engine.close()
            del engine
            gc.collect()
        finally:
            shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
