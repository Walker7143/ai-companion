import asyncio
import gc
import shutil
import tempfile
import unittest
from pathlib import Path

from ai_companion.gateway.commands import GatewayCommandHandler, parse_gateway_command
from ai_companion.memory.activation import MemoryActivationPlanner
from ai_companion.memory.engine import MemoryEngine
from ai_companion.memory.extractor import MemoryExtractor
from ai_companion.memory.retriever import MemoryRetriever, RetrievedMemory


class MemoryRegressionScenarioTest(unittest.TestCase):
    def test_fixed_memory_experience_scenarios(self):
        """A small product-facing regression set for memory behavior."""

        retriever = MemoryRetriever(
            working_store=None,
            daily_store=None,
            episodic_store=None,
            semantic_store=None,
            relationship_store=None,
            user_understanding=None,
        )
        classifier_cases = [
            ("刚才那段优化方案你还记得吗", "recall_past"),
            ("你刚才那样说我有点生气，我们和好吧", "relationship_repair"),
            ("帮我优化这段代码", "task_request"),
            ("我今天有点焦虑", "emotional_support"),
            ("我们明天继续整理作品集", "planning"),
        ]
        for text, expected in classifier_cases:
            with self.subTest(text=text):
                self.assertEqual(retriever.classify_intent(text), expected)

        extractor = MemoryExtractor()
        extraction_cases = [
            ("我不喝酒的", "user_fact", "用户不喝酒"),
            ("我不叫老王，我叫小林", "user_fact", "用户称呼"),
            ("我现在不在上海，我在杭州", "user_fact", "当前城市"),
            ("我的猫不叫奥利奥，叫布丁", "user_fact", "宠物信息"),
            ("我们已经确认关系了，你是我女朋友", "relationship_event", "relationship_state"),
            ("我纠正一下，不是周三，是周五", "temporary_context", "user_correction"),
            ("今天不许吃粉，吃点别的", "temporary_context", "turn_constraint_"),
        ]
        for text, expected_type, expected_key in extraction_cases:
            with self.subTest(text=text):
                candidates = asyncio.run(extractor.extract(text, "收到", session_id="s1"))
                self.assertTrue(
                    any(
                        item.type == expected_type
                        and (item.key == expected_key or item.key.startswith(expected_key))
                        for item in candidates
                    ),
                    candidates,
                )
        directive_candidates = asyncio.run(extractor.extract("今天不许吃粉，吃点别的", "收到", session_id="s1"))
        self.assertFalse(any(item.type == "user_fact" and item.category == "boundaries" for item in directive_candidates))

    def test_turn_constraints_stay_out_of_stable_understanding_but_enter_prompt(self):
        async def run():
            td = tempfile.mkdtemp(prefix="memory-regression-turn-constraint-")
            try:
                engine = MemoryEngine("constraint_bot", Path(td), config={"embedding": "none"})
                await engine.init()
                candidates = await MemoryExtractor().extract("今天不许吃粉，吃点别的", "好，换一家。", session_id="s1")
                await engine.governor.apply(
                    candidates,
                    bot_id="constraint_bot",
                    user_id="default_user",
                    session_id="s1",
                )
                ctx = await engine.load_context("你吃的啥，我看看")
                understanding = engine.user_understanding.load()
                facts = await engine.semantic.list_facts(
                    bot_id="constraint_bot",
                    user_id="default_user",
                    categories={"turn_constraints"},
                    min_confidence=0.0,
                )
                await engine.close()
                del engine
                gc.collect()
                return ctx, understanding, facts
            finally:
                shutil.rmtree(td, ignore_errors=True)

        ctx, understanding, facts = asyncio.run(run())
        self.assertTrue(facts)
        self.assertIn("本轮临时约束", ctx["system_suffix"])
        self.assertIn("今天不许吃粉", ctx["system_suffix"])
        rendered_understanding = str(understanding.get("layered", {}))
        self.assertNotIn("今天不许吃粉", rendered_understanding)

    def test_semantic_write_does_not_side_effect_understanding_projection(self):
        async def run():
            td = tempfile.mkdtemp(prefix="memory-regression-projection-")
            try:
                engine = MemoryEngine("projection_bot", Path(td), config={"embedding": "none"})
                await engine.init()
                await engine.semantic.set_fact(
                    "reply_style",
                    "prefers concise replies",
                    bot_id="projection_bot",
                    user_id="default_user",
                    category="preferences",
                    confidence=0.95,
                    source="test",
                    evidence=["s1"],
                )
                immediate = engine.user_understanding.load()
                await engine.governor.refresh_projection(bot_id="projection_bot", user_id="default_user")
                refreshed = engine.user_understanding.load()
                await engine.close()
                del engine
                gc.collect()
                return immediate, refreshed
            finally:
                shutil.rmtree(td, ignore_errors=True)

        immediate, refreshed = asyncio.run(run())
        self.assertNotIn("prefers concise replies", immediate["layered"]["core"]["preferences"])
        self.assertIn("prefers concise replies", refreshed["layered"]["core"]["preferences"])

    def test_memory_trust_view_and_gateway_memory_command(self):
        async def run():
            td = tempfile.mkdtemp(prefix="memory-regression-view-")
            try:
                engine = MemoryEngine("view_bot", Path(td), config={"embedding": "none"})
                await engine.init()
                await engine.governor.apply(
                    [
                        MemoryExtractor()._explicit_correction_candidates(
                            "我不叫老王，我叫小林",
                            session_id="s1",
                        )[0]
                    ],
                    bot_id="view_bot",
                    user_id="default_user",
                    session_id="s1",
                )
                await engine.governor.apply(
                    [
                        MemoryExtractor()._explicit_relationship_confirmation_candidates(
                            "我们已经确认关系了，你是我女朋友",
                            "嗯",
                            session_id="s2",
                        )[0]
                    ],
                    bot_id="view_bot",
                    user_id="default_user",
                    session_id="s2",
                )
                await engine.semantic.set_fact(
                    "待确认喜好",
                    "用户可能喜欢很短的回复。",
                    bot_id="view_bot",
                    user_id="default_user",
                    category="preferences",
                    confidence=0.62,
                    source="auto",
                    evidence=["s3"],
                )
                status = await engine.get_memory_status()

                class _Bot:
                    id = "view_bot"
                    name = "View Bot"
                    memory = engine

                    def reset_history(self):
                        pass

                class _Config:
                    models = {}
                    default_provider = "test"

                command_text = await GatewayCommandHandler(_Config()).handle("/memory", _Bot())
                await engine.close()
                del engine
                gc.collect()
                return status, command_text
            finally:
                shutil.rmtree(td, ignore_errors=True)

        status, command_text = asyncio.run(run())
        trust = status["memory_trust_view"]
        self.assertIn("recently_remembered", trust)
        self.assertTrue(trust["recently_remembered"])
        self.assertTrue(trust["stable_understanding"])
        recent_keys = {item.get("key") for item in trust["recently_remembered"] if item.get("type") == "semantic_fact"}
        stable_keys = {item.get("key") for item in trust["stable_understanding"]}
        pending_keys = {item.get("key") for item in trust["pending_confirmation"]}
        self.assertFalse(recent_keys & stable_keys)
        self.assertFalse(recent_keys & pending_keys)
        self.assertEqual(trust["relationship_anchor"]["label"], "恋人")
        self.assertTrue(trust["pending_confirmation"])
        self.assertIn("记忆信任视图", command_text)
        self.assertIn("关系锚点", command_text)

    def test_gateway_memory_command_is_supported(self):
        parsed = parse_gateway_command("/memory")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.name, "memory")

    def test_activation_strategy_can_be_configured_without_code_changes(self):
        retrieved = RetrievedMemory(
            intent="casual_chat",
            working_history=[
                {"role": "user", "content": "刚刚确认一个普通事项"},
                {"role": "assistant", "content": "我记下了。"},
            ],
            relationship_state={
                "relationship_label": "恋人",
                "relationship_narrative": "你们已经确认恋人/男女朋友关系。",
            },
        )
        normal = MemoryActivationPlanner().build(retrieved, "随便聊聊")
        biased = MemoryActivationPlanner(
            {"source_bias": {"relationship": 0.3}, "active_limits": {"casual_chat": 2}}
        ).build(retrieved, "随便聊聊")

        self.assertGreaterEqual(
            max(item.score for item in biased.active_memories if item.source == "relationship"),
            max(item.score for item in normal.active_memories if item.source == "relationship"),
        )
        self.assertLessEqual(len(biased.active_memories), 2)
