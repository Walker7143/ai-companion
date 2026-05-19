import asyncio
import tempfile
import unittest
from pathlib import Path

from ai_companion.memory.conscious import ConsciousContextBuilder
from ai_companion.memory.engine import MemoryEngine
from ai_companion.memory.extractor import MemoryCandidate, MemoryExtractor
from ai_companion.memory.retriever import MemoryRetriever, RetrievedMemory
from ai_companion.memory.stores.memory_rollup import MemoryRollupStore
from ai_companion.memory.stores.daily import DailyMemoryStore, MemoryTurnContext


class MemoryEvolutionExtractorTest(unittest.TestCase):
    def test_rule_extractor_attaches_evidence_to_fact_candidates(self):
        extractor = MemoryExtractor()
        candidates = asyncio.run(extractor.extract("我叫王啸威", "", session_id="s1"))

        facts = [item for item in candidates if item.type == "user_fact"]
        self.assertTrue(facts)
        self.assertEqual(facts[0].evidence, ["s1"])
        self.assertGreater(facts[0].confidence, 0.0)

    def test_rule_extractor_marks_episode_cues(self):
        extractor = MemoryExtractor()
        candidates = asyncio.run(extractor.extract("那天我们第一次去海边散步，我很开心", "", session_id="s2"))

        episodes = [item for item in candidates if item.type == "episode"]
        self.assertTrue(episodes)
        self.assertIn("海边", episodes[0].summary)
        self.assertIsInstance(episodes[0].metadata, dict)


class MemoryEvolutionGovernorTest(unittest.TestCase):
    def test_manual_understanding_blocks_weak_auto_write(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="memory-evolution-governor-") as td:
                engine = MemoryEngine("evo_bot", Path(td), config={"embedding": "none"})
                await engine.init()
                data = engine.user_understanding.load()
                data["manual"]["facts"]["城市"] = "杭州"
                engine.user_understanding._write(data)
                candidates = [
                    MemoryCandidate(
                        type="user_fact",
                        key="城市",
                        value="上海",
                        category="identity",
                        confidence=0.65,
                        importance=0.5,
                        evidence=["s1"],
                    )
                ]
                result = await engine.governor.apply(candidates, bot_id="evo_bot", user_id="default_user", session_id="s1")
                ctx = await engine.load_context("我现在在哪个城市")
                await engine.close()
                return result, ctx

        result, ctx = asyncio.run(run())
        self.assertTrue(result.skipped)
        self.assertIn("城市: 杭州", ctx["system_suffix"])
        self.assertNotIn("城市: 上海", ctx["system_suffix"])


class MemoryEvolutionUnderstandingTest(unittest.TestCase):
    def test_refresh_auto_from_sources_absorbs_daily_context_and_relationship(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="memory-evolution-understanding-") as td:
                engine = MemoryEngine("understanding_bot", Path(td), config={"embedding": "none"})
                await engine.init()
                await engine.daily.upsert_summary(
                    bot_id="understanding_bot",
                    user_id="default_user",
                    local_date="2026-05-19",
                    payload={
                        "summary": "用户今天在准备面试，晚上再回来复盘。",
                        "open_threads": ["面试后复盘"],
                        "commitments": ["晚上回来复盘"],
                        "mood": ["有点紧张"],
                    },
                    last_message_id=1,
                    message_count=1,
                )
                relationship = await engine.relationship.apply_event(
                    bot_id="understanding_bot",
                    user_id="default_user",
                    label="好朋友",
                    intimacy_delta=6,
                    trust_delta=4,
                    key_moment="一起约定晚上再聊",
                    open_thread="面试后复盘",
                )
                facts = await engine.semantic.list_facts(bot_id="understanding_bot", user_id="default_user", min_confidence=0.0)
                await engine.user_understanding.refresh_auto_from_sources(
                    facts=facts,
                    relationship=relationship,
                    daily_context=engine.daily.get_recent_context(bot_id="understanding_bot", user_id="default_user", intent="planning"),
                )
                loaded = engine.user_understanding.load()
                await engine.close()
                return loaded

        loaded = asyncio.run(run())
        self.assertIn("面试后复盘", loaded["auto"]["open_threads"])
        self.assertIn("晚上回来复盘", loaded["auto"]["goals_and_projects"])
        self.assertIn("有点紧张", loaded["auto"]["emotional_patterns"])
        self.assertIn("关系中的需要", loaded["auto"]["profile_summary"])


class MemoryEvolutionDailyTest(unittest.TestCase):
    def test_daily_memory_returns_cross_session_continuity(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="memory-evolution-daily-") as td:
                store = DailyMemoryStore(Path(td) / "daily.db")
                await store.init()
                await store.append_turn(
                    bot_id="bot-a",
                    user_id="default_user",
                    user_input="我今天要面试，晚上再聊",
                    bot_output="好，我记住了",
                    session_id="session-1",
                    context=MemoryTurnContext(platform="weixin", session_id="session-1", user_id="default_user"),
                )
                ctx = store.get_recent_context(bot_id="bot-a", user_id="default_user", current_session_id="session-2", intent="planning")
                return ctx

        ctx = asyncio.run(run())
        self.assertIn("recent_messages", ctx)
        self.assertTrue(ctx["recent_messages"])
        self.assertIn("open_threads", ctx)
        self.assertIn("commitments", ctx)
        self.assertIn("mood", ctx)


class MemoryEvolutionRollupTest(unittest.TestCase):
    def test_rollup_store_round_trip_and_prompt_visibility(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="memory-evolution-rollup-") as td:
                store = MemoryRollupStore(Path(td) / "rollups.db")
                await store.init()
                await store.append_rollup(
                    bot_id="bot-a",
                    user_id="default_user",
                    scope="day",
                    topic_key="面试",
                    summary="今天用户在准备面试，晚上要回来复盘。",
                    evidence=["turn-1", "turn-2"],
                    confidence=0.8,
                    freshness=0.7,
                    source={"kind": "daily_context"},
                )
                rollups = await store.get_latest_by_scope(bot_id="bot-a", user_id="default_user", scope="day", limit=3)
                retrieved = RetrievedMemory(
                    intent="planning",
                    rollup_recall=rollups,
                    user_understanding={
                        "layered": {
                            "current": {"goals_and_projects": ["晚上复盘面试"]},
                        }
                    },
                )
                from ai_companion.memory.prompt_builder import MemoryPromptBuilder

                suffix = MemoryPromptBuilder(max_chars=2200).build(retrieved)
                conscious = ConsciousContextBuilder().build(retrieved, "我晚点再看")
                return rollups, suffix, conscious

        rollups, suffix, conscious = asyncio.run(run())
        self.assertEqual(len(rollups), 1)
        self.assertIn("面试", rollups[0]["summary"])
        self.assertIn("【记忆 rollup】", suffix)
        self.assertIn("day/面试", suffix)
        self.assertIn("高层记忆概括", conscious.active_memory_details[0]["reason"])

    def test_memory_engine_exposes_rollup_count(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="memory-evolution-rollup-engine-") as td:
                engine = MemoryEngine("rollup_bot", Path(td), config={"embedding": "none"})
                await engine.init()
                status = await engine.get_memory_status()
                await engine.close()
                return status

        status = asyncio.run(run())
        self.assertIn("rollup_count", status)
        self.assertGreaterEqual(status["rollup_count"], 0)


class MemoryEvolutionRetrieverTest(unittest.TestCase):
    def test_intent_aware_retrieval_prefers_daily_and_semantic_background(self):
        retrieved = RetrievedMemory(
            intent="planning",
            daily_context={
                "summaries": [{"local_date": "2026-05-19", "summary": "用户今天在准备面试和回消息", "open_threads": ["面试后再聊"]}],
                "recent_messages": [{"role": "user", "content": "我今天要面试"}],
                "self_memory": [],
                "open_threads": ["面试后再聊"],
                "commitments": ["晚上回来复盘"],
                "mood": ["有点紧张"],
            },
            semantic_items=[
                {"key": "用户偏好", "value": "回复简短直接", "category": "communication_style", "confidence": 0.9, "manual_override": True},
            ],
            user_understanding={
                "layered": {"current": {"goals_and_projects": ["面试结束后整理作品集"]}},
            },
        )

        suffix = MemoryEngine("dummy", Path(tempfile.gettempdir()), config={"embedding": "none"}).prompt_builder.build(retrieved)

        self.assertIn("最近日常连续性", suffix)
        self.assertIn("用户偏好", suffix)
        self.assertIn("跨会话未完话题", suffix)
        self.assertIn("跨会话承诺/待办", suffix)


class MemoryEvolutionConsciousTest(unittest.TestCase):
    def test_conscious_context_surfaces_relevant_memory_without_noise(self):
        retrieved = RetrievedMemory(
            intent="relationship_repair",
            relationship_state={
                "relationship_label": "好朋友",
                "relationship_narrative": "先放慢，先接住情绪。",
                "current_posture": "避免解释太多。",
            },
            episodic_recall=[
                {
                    "summary": "用户主动道歉后气氛缓和。",
                    "relationship_effect": "修复",
                    "sensitivity": "normal",
                    "cue_tags": ["道歉", "和好"],
                }
            ],
        )

        conscious = ConsciousContextBuilder().build(retrieved, "我刚才说重了")
        self.assertIn("关系修复", conscious.current_focus)
        self.assertTrue(conscious.active_memory_details)


class MemoryEvolutionRelationshipTest(unittest.TestCase):
    def test_relationship_state_changes_with_hysteresis_and_renders_narrative(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="memory-evolution-relationship-") as td:
                engine = MemoryEngine("relationship_bot", Path(td), config={"embedding": "none"})
                await engine.init()
                before = await engine.relationship.get_state(bot_id="relationship_bot", user_id="default_user")
                after = await engine.relationship.apply_event(
                    bot_id="relationship_bot",
                    user_id="default_user",
                    label="好朋友",
                    intimacy_delta=2,
                    trust_delta=1,
                    tension_delta=0,
                    key_moment="轻松聊了很久",
                )
                ctx = await engine.load_context("我们现在是什么关系")
                await engine.close()
                return before, after, ctx

        before, after, ctx = asyncio.run(run())
        self.assertEqual(before["relationship_label"], "朋友")
        self.assertIn(after["relationship_label"], {"朋友", "好朋友"})
        self.assertIn("关系叙事", ctx["system_suffix"])
        self.assertIn("互动建议", ctx["system_suffix"])
