import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from ai_companion.memory.activation import MemoryActivationPlanner
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

    def test_lifecycle_supersedes_old_fact_with_history_and_skips_weak_conflict(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="memory-lifecycle-fact-") as td:
                engine = MemoryEngine("lifecycle_bot", Path(td), config={"embedding": "none"})
                await engine.init()
                first = await engine.governor.apply(
                    [
                        MemoryCandidate(
                            type="user_fact",
                            key="当前城市",
                            value="上海",
                            category="identity",
                            confidence=0.92,
                            source="user_confirmed",
                            evidence=["s1"],
                        )
                    ],
                    bot_id="lifecycle_bot",
                    user_id="default_user",
                    session_id="s1",
                )
                weak = await engine.governor.apply(
                    [
                        MemoryCandidate(
                            type="user_fact",
                            key="当前城市",
                            value="杭州",
                            category="identity",
                            confidence=0.62,
                            source="auto",
                            evidence=["s2"],
                        )
                    ],
                    bot_id="lifecycle_bot",
                    user_id="default_user",
                    session_id="s2",
                )
                corrected = await engine.governor.apply(
                    [
                        MemoryCandidate(
                            type="user_fact",
                            key="当前城市",
                            value="杭州",
                            category="identity",
                            confidence=0.9,
                            source="rule_explicit_correction",
                            evidence=["s3"],
                            reason="用户明确纠正当前城市。",
                        )
                    ],
                    bot_id="lifecycle_bot",
                    user_id="default_user",
                    session_id="s3",
                )
                fact = await engine.semantic.get_fact_record(
                    "当前城市",
                    bot_id="lifecycle_bot",
                    user_id="default_user",
                )
                db_path = engine.semantic.db_path
                await engine.close()
                conn = sqlite3.connect(db_path)
                history = conn.execute(
                    "SELECT old_value, superseded_by_value, reason FROM fact_history WHERE key = ?",
                    ("当前城市",),
                ).fetchall()
                events = conn.execute(
                    "SELECT action, reason FROM memory_lifecycle_events WHERE memory_key = ? ORDER BY id",
                    ("当前城市",),
                ).fetchall()
                conn.close()
                return first, weak, corrected, fact, history, events

        first, weak, corrected, fact, history, events = asyncio.run(run())
        self.assertTrue(first.written)
        self.assertTrue(weak.skipped)
        self.assertEqual(weak.skipped[0][1], "weaker_conflict")
        self.assertTrue(corrected.written)
        self.assertEqual(fact["value"], "杭州")
        self.assertEqual(fact["source"], "user_confirmed")
        self.assertGreaterEqual(fact["confidence"], 0.92)
        self.assertTrue(fact["last_confirmed_at"])
        self.assertEqual(history[0][0], "上海")
        self.assertEqual(history[0][1], "杭州")
        self.assertTrue(any(action == "supersede" for action, _reason in events))

    def test_lifecycle_committed_relationship_archives_pre_commitment_threads(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="memory-lifecycle-relationship-") as td:
                engine = MemoryEngine("relationship_lifecycle_bot", Path(td), config={"embedding": "none"})
                await engine.init()
                await engine.semantic.set_fact(
                    "关系确认待办",
                    "用户可能想就此确认正式关系，等待助手明确答复。",
                    bot_id="relationship_lifecycle_bot",
                    user_id="default_user",
                    category="open_threads",
                    confidence=0.82,
                    source="auto",
                    evidence=["s1"],
                )
                result = await engine.governor.apply(
                    [
                        MemoryCandidate(
                            type="relationship_event",
                            key="relationship_state",
                            value="恋人",
                            confidence=0.72,
                            source="user_explicit",
                            evidence=["s2"],
                            metadata={
                                "label": "恋人",
                                "intimacy_delta": 5,
                                "trust_delta": 5,
                                "affection_delta": 5,
                            },
                        )
                    ],
                    bot_id="relationship_lifecycle_bot",
                    user_id="default_user",
                    session_id="s2",
                )
                state = await engine.relationship.get_state(
                    bot_id="relationship_lifecycle_bot",
                    user_id="default_user",
                )
                facts = await engine.semantic.list_facts(
                    bot_id="relationship_lifecycle_bot",
                    user_id="default_user",
                    include_archived=False,
                )
                db_path = engine.semantic.db_path
                await engine.close()
                conn = sqlite3.connect(db_path)
                archived = conn.execute(
                    "SELECT key, archived FROM user_facts WHERE key = ?",
                    ("关系确认待办",),
                ).fetchall()
                events = conn.execute(
                    "SELECT action, reason FROM memory_lifecycle_events WHERE memory_type = ? ORDER BY id",
                    ("relationship",),
                ).fetchall()
                conn.close()
                return result, state, facts, archived, events

        result, state, facts, archived, events = asyncio.run(run())
        self.assertTrue(result.written)
        self.assertEqual(state["relationship_label"], "恋人")
        self.assertFalse(any(fact["key"] == "关系确认待办" for fact in facts))
        self.assertEqual(archived[0][1], 1)
        self.assertTrue(any(action == "stabilize" for action, _reason in events))


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

    def test_committed_relationship_refresh_discards_pre_commitment_threads(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="memory-evolution-committed-") as td:
                engine = MemoryEngine("committed_bot", Path(td), config={"embedding": "none"})
                await engine.init()
                data = engine.user_understanding.load()
                data["auto"]["open_threads"] = ["用户可能想就此确认正式关系", "29号出行前后的互动期待"]
                data["relationship_memory"]["what_user_seems_to_need_from_bot"] = [
                    "你们目前像恋人，关系很亲近。",
                    "当前关系标签：恋人",
                ]
                engine.user_understanding._write(data)

                await engine.user_understanding.refresh_auto_from_sources(
                    facts=[],
                    relationship={
                        "relationship_label": "恋人",
                        "relationship_narrative": "你们已经确认恋人/男女朋友关系，关系很亲近。",
                    },
                )
                loaded = engine.user_understanding.load()
                await engine.close()
                return loaded

        loaded = asyncio.run(run())
        self.assertNotIn("用户可能想就此确认正式关系", loaded["auto"]["open_threads"])
        self.assertNotIn("你们目前像恋人，关系很亲近。", loaded["relationship_memory"]["what_user_seems_to_need_from_bot"])
        self.assertIn("29号出行前后的互动期待", loaded["auto"]["open_threads"])
        self.assertTrue(
            any("已确认恋人/男女朋友关系" in item for item in loaded["relationship_memory"]["what_user_seems_to_need_from_bot"])
        )


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
    def test_recent_memory_language_is_classified_as_recall(self):
        retriever = MemoryRetriever(
            working_store=None,
            episodic_store=None,
            semantic_store=None,
            relationship_store=None,
            user_understanding=None,
        )

        self.assertEqual(retriever.classify_intent("你怎么又忘了，刚才我明明说过了"), "recall_past")
        self.assertEqual(retriever.classify_intent("今天我们确定过这件事，你记得吗"), "recall_past")
        self.assertEqual(retriever.classify_intent("刚才那段优化方案你还记得吗"), "recall_past")

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

    def test_prompt_builder_promotes_short_term_continuity(self):
        from ai_companion.memory.prompt_builder import MemoryPromptBuilder

        retrieved = RetrievedMemory(
            intent="recall_past",
            working_history=[
                {"role": "user", "content": "我刚刚说今天先把记忆召回优化掉"},
                {"role": "assistant", "content": "好，我会先看召回入口。"},
                {"role": "user", "content": "还有压缩别把刚才的话吞了"},
            ],
            daily_context={
                "recent_messages": [
                    {"platform": "feishu", "role": "user", "content": "跨会话也要记住最近说过的话"},
                ],
            },
        )

        suffix = MemoryPromptBuilder(max_chars=2600).build(retrieved)

        self.assertIn("【本轮记忆激活窗口】", suffix)
        self.assertIn("当前会话最近几条", suffix)
        self.assertIn("刚刚说今天先把记忆召回优化掉", suffix)
        self.assertIn("跨会话也要记住最近说过的话", suffix)

    def test_context_summary_keeps_recent_raw_turns(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="memory-working-summary-") as td:
                from ai_companion.memory.stores.working import WorkingMemoryStore

                store = WorkingMemoryStore(Path(td) / "working.db")
                await store.init()
                store.start_session("s1")
                for index in range(10):
                    await store.append(f"用户第{index}轮：重要事实{index}", f"助手第{index}轮", session_id="s1")
                applied = await store.apply_summary("早期摘要", "s1")
                messages = store.load_context("s1", max_working_turns=20, max_summaries=2)
                await store.close()
                return applied, messages

        applied, messages = asyncio.run(run())
        self.assertTrue(applied)
        raw_contents = [item["content"] for item in messages if item.get("role") != "system"]
        self.assertIn("用户第9轮：重要事实9", raw_contents)
        self.assertIn("用户第2轮：重要事实2", raw_contents)
        self.assertNotIn("用户第0轮：重要事实0", raw_contents)

    def test_activation_plan_surfaces_recent_events_without_recall_words(self):
        retrieved = RetrievedMemory(
            intent="casual_chat",
            working_history=[
                {"role": "user", "content": "我们已经确定男女朋友关系了"},
                {"role": "assistant", "content": "嗯，我答应你了。"},
                {"role": "user", "content": "那你以后别又当没发生"},
                {"role": "assistant", "content": "我会把这件事当成我们关系里的事实。"},
            ],
            relationship_state={
                "relationship_label": "恋人",
                "relationship_narrative": "你们已经确认恋人/男女朋友关系，关系很亲近。",
            },
        )

        plan = MemoryActivationPlanner().build(retrieved, "所以你现在怎么称呼我")
        retrieved.activation_plan = plan
        conscious = ConsciousContextBuilder().build(retrieved, "所以你现在怎么称呼我")
        from ai_companion.memory.prompt_builder import MemoryPromptBuilder

        suffix = MemoryPromptBuilder(max_chars=2600).build(retrieved, conscious=conscious)

        active_text = "\n".join(item.text for item in plan.active_memories)
        self.assertIn("已经确定男女朋友关系", active_text)
        self.assertIn("working_recent", plan.source_counts)
        self.assertIn("【本轮记忆激活窗口】", suffix)
        self.assertIn("默认当作刚发生的上下文承接", suffix)
        self.assertIn("不要表现得像被提醒后才临时检索", suffix)
        self.assertTrue(
            any(item.get("source") == "working_recent" for item in conscious.active_memory_details)
        )

    def test_memory_engine_activation_plan_promotes_immediate_turn_on_plain_followup(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="memory-activation-engine-") as td:
                engine = MemoryEngine("activation_bot", Path(td), config={"embedding": "none"})
                await engine.init()
                engine.start_session("s1")
                await engine.record_turn("我们确认今天一起整理记忆系统", "好，我会接着做。")
                ctx = await engine.load_context("那下一步呢")
                await engine.close()
                return ctx

        ctx = asyncio.run(run())
        active_text = "\n".join(
            item.get("text", "")
            for item in ctx["memory_activation_plan"].get("active_memories", [])
        )
        self.assertIn("确认今天一起整理记忆系统", active_text)
        self.assertIn("working_recent", ctx["memory_prompt_diagnostics"]["activation_source_counts"])
        self.assertIn("本轮记忆激活窗口", ctx["system_suffix"])


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
    def test_prompt_builder_anchors_committed_relationship_as_continuity_fact(self):
        from ai_companion.memory.prompt_builder import MemoryPromptBuilder

        retrieved = RetrievedMemory(
            intent="casual_chat",
            relationship_state={
                "relationship_label": "恋人",
                "relationship_status": "稳定",
                "relationship_score": 95,
                "stage_confidence": 0.8,
                "relationship_narrative": "你们目前像恋人，关系很亲近。",
            },
        )

        suffix = MemoryPromptBuilder(max_chars=2200).build(retrieved)

        self.assertIn("关系阶段：恋人", suffix)
        self.assertIn("已经确认恋人/男女朋友关系", suffix)
        self.assertIn("不要否认已经确认关系本身", suffix)

    def test_relationship_narrative_states_committed_relationship_directly(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="memory-evolution-relationship-committed-") as td:
                engine = MemoryEngine("relationship_bot", Path(td), config={"embedding": "none"})
                await engine.init()
                state = await engine.relationship.apply_event(
                    bot_id="relationship_bot",
                    user_id="default_user",
                    label="恋人",
                    intimacy_delta=80,
                    trust_delta=80,
                    affection_delta=80,
                    attitude_delta=30,
                    key_moment="正式确认恋人关系",
                )
                await engine.close()
                return state

        state = asyncio.run(run())
        self.assertIn("已经确认恋人/男女朋友关系", state["relationship_narrative"])
        self.assertNotIn("像恋人", state["relationship_narrative"])
        self.assertIn("不要否认关系事实", state["interaction_guidance"])

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
