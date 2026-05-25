import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from ai_companion.memory.conscious import ConsciousContextBuilder
from ai_companion.memory.engine import MemoryEngine
from ai_companion.memory.extractor import MemoryExtractor
from ai_companion.memory.retriever import MemoryRetriever, RetrievedMemory
from ai_companion.proactive.config import ProactiveConfig
from ai_companion.proactive.engine import ProactiveEngine
from ai_companion.proactive.state import ProactiveState


class DailyMemoryTest(unittest.TestCase):
    def test_rule_extractor_does_not_store_name_correction_as_identity(self):
        extractor = MemoryExtractor()
        candidates = asyncio.run(
            extractor.extract("我说，你为什么叫我米老头", "", session_id="s1")
        )

        self.assertFalse(
            [item for item in candidates if item.type == "user_fact" and item.category == "identity"]
        )

    def test_rule_extractor_stores_explicit_name_statement_as_identity(self):
        extractor = MemoryExtractor()
        candidates = asyncio.run(
            extractor.extract("我叫王啸威", "", session_id="s1")
        )

        self.assertTrue(
            [item for item in candidates if item.type == "user_fact" and item.category == "identity"]
        )

    def test_rule_extractor_stores_explicit_corrections_and_body_limits(self):
        extractor = MemoryExtractor()
        alcohol = asyncio.run(extractor.extract("我不喝酒的", "", session_id="s1"))
        body = asyncio.run(extractor.extract("本来我的腿脚就不好，怎么跑啊", "", session_id="s1"))

        self.assertTrue(
            [
                item
                for item in alcohol
                if item.type == "user_fact" and item.key == "用户不喝酒" and item.category == "dislikes"
            ]
        )
        self.assertTrue(
            [
                item
                for item in body
                if item.type == "user_fact" and item.key == "用户的身体状况" and item.category == "life_context"
            ]
        )

    def test_intent_classifier_prefers_task_request_for_code_repair(self):
        retriever = MemoryRetriever(
            working_store=None,
            daily_store=None,
            episodic_store=None,
            semantic_store=None,
            relationship_store=None,
            user_understanding=None,
        )

        self.assertEqual(retriever.classify_intent("帮我修复这段代码的 bug"), "task_request")
        self.assertEqual(retriever.classify_intent("你刚才那样说我有点生气，我们和好吧"), "relationship_repair")

    def test_conscious_context_scores_active_memories_and_expression_modes(self):
        retrieved = RetrievedMemory(
            intent="recall_past",
            episodic_recall=[
                {
                    "summary": "用户曾在海边想象牵手唱歌，助手害羞但被触动。",
                    "relationship_effect": "拉近",
                    "sensitivity": "normal",
                    "recall_style": "可轻轻提起，不要炫耀记忆。",
                    "cue_tags": ["海边", "牵手", "唱歌"],
                }
            ],
            relationship_state={"relationship_label": "暧昧中", "intimacy_score": 60},
            user_understanding={},
        )

        conscious = ConsciousContextBuilder().build(retrieved, "你还记得海边牵手唱歌吗")

        self.assertIn("共同经历", conscious.active_memories[0])
        self.assertGreater(conscious.active_memory_details[0]["score"], 0.5)
        self.assertEqual(conscious.active_memory_details[0]["expression_mode"], "explicit_recall")
        self.assertIn("使用：可以明确承接回忆", conscious.render())

    def test_user_understanding_relevant_current_context_is_not_dropped(self):
        from ai_companion.memory.prompt_builder import MemoryPromptBuilder

        cat_fact = "用户养了两只猫：布丁和奥利奥。"
        retrieved = RetrievedMemory(
            intent="casual_chat",
            user_understanding={
                "layered": {
                    "core": {"summary": "用户喜欢真实自然的陪伴。"},
                    "current": {
                        "current_context": [
                            "用户目前一个人在北京生活。",
                            "用户不太喜欢当前工作，但因收入高仍继续做。",
                            "用户有游戏账号运营副业。",
                            "用户 2025 年买了小米 SU7 Max。",
                            cat_fact,
                        ],
                    },
                },
            },
        )

        conscious = ConsciousContextBuilder().build(retrieved, "我的猫！")
        suffix = MemoryPromptBuilder(max_chars=2400).build(retrieved, conscious=conscious)

        self.assertIn(cat_fact, suffix)
        self.assertIn("当前输入命中用户理解", conscious.active_memory_details[0]["reason"])
        self.assertIn(cat_fact, conscious.active_memory_details[0]["text"])

    def test_prompt_builder_anchors_current_city_and_body_facts(self):
        from ai_companion.memory.prompt_builder import MemoryPromptBuilder

        retrieved = RetrievedMemory(
            intent="casual_chat",
            user_understanding={
                "layered": {
                    "core": {
                        "identity": {"current_city": "北京", "living_status": "一个人在北京生活"},
                    },
                    "current": {
                        "current_context": ["用户目前一个人在北京生活，从事 Java 开发。"],
                    },
                }
            },
            semantic_items=[
                {
                    "key": "用户的身体状况",
                    "value": "用户有“腿脚不好”的身体情况。",
                    "category": "life_context",
                    "confidence": 1.0,
                    "retrieval_reasons": {"query_cue_overlap": 1, "salient_overlap": 1},
                },
                {
                    "key": "location",
                    "value": "用户人在北京",
                    "category": "life_context",
                    "confidence": 0.9,
                    "retrieval_reasons": {"query_cue_overlap": 1, "salient_overlap": 1},
                },
            ],
        )

        suffix = MemoryPromptBuilder(max_chars=2400).build(retrieved)

        self.assertIn("【本轮必须承接的记忆】", suffix)
        self.assertIn("用户当前在北京", suffix)
        self.assertIn("腿脚不好", suffix)
        self.assertIn("不要反问已知事实", suffix)

    def test_prompt_builder_filters_sensitive_core_facts_in_casual_chat(self):
        from ai_companion.memory.prompt_builder import MemoryPromptBuilder

        understanding = {
            "layered": {
                "core": {
                    "summary": "用户喜欢真实陪伴，但身体有长期不适。",
                    "identity": {"current_city": "北京"},
                    "facts": {
                        "身体情况": "用户腿脚不好。",
                        "猫": "用户养了猫。",
                    },
                    "communication_style": ["少说教"],
                },
                "sensitive": {
                    "topics": ["身体", "腿"],
                    "guidance": ["涉及身体隐私只在用户主动提起或高度相关时使用。"],
                    "source_keys": ["core.facts.身体情况"],
                },
            }
        }
        casual = RetrievedMemory(intent="casual_chat", user_understanding=understanding)
        emotional = RetrievedMemory(intent="emotional_support", user_understanding=understanding)

        casual_suffix = MemoryPromptBuilder(max_chars=2400).build(casual)
        emotional_suffix = MemoryPromptBuilder(max_chars=2400).build(emotional)

        self.assertNotIn("长期不适", casual_suffix)
        self.assertNotIn("用户腿脚不好", casual_suffix)
        self.assertIn("用户养了猫", casual_suffix)
        self.assertIn("只在用户主动提起", casual_suffix)
        self.assertIn("用户腿脚不好", emotional_suffix)

    def test_prompt_builder_manual_facts_override_anchored_semantic_items(self):
        from ai_companion.memory.prompt_builder import MemoryPromptBuilder

        retrieved = RetrievedMemory(
            intent="casual_chat",
            user_understanding={
                "manual": {"facts": {"城市": "杭州"}},
                "layered": {"core": {"facts": {"城市": "杭州"}}},
            },
            semantic_items=[
                {
                    "key": "城市",
                    "value": "上海",
                    "category": "identity",
                    "confidence": 0.95,
                    "retrieval_reasons": {"query_cue_overlap": 1, "salient_overlap": 0},
                }
            ],
        )

        suffix = MemoryPromptBuilder(max_chars=2400).build(retrieved)

        self.assertIn("城市: 杭州", suffix)
        self.assertNotIn("城市: 上海", suffix)

    def test_memory_engine_promotes_explicit_correction_for_next_turn(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="explicit-correction-") as tmp:
                engine = MemoryEngine("explicit_correction_bot", Path(tmp), config={"embedding": "none"})
                await engine.init()
                engine.start_session("s1")
                await engine.on_message("我不喝酒的", "记住啦", turn_context={"session_id": "s1"})
                ctx = await engine.load_context("你还让我喝酒吗")
                loaded = engine.user_understanding.load()
                await engine.close()
                return ctx, loaded

        ctx, loaded = asyncio.run(run())

        self.assertIn("用户明确说自己不喝酒", ctx["system_suffix"])
        self.assertIn("用户不喝酒", ctx["semantic_facts"])
        self.assertTrue(
            any("用户明确说自己不喝酒" in item for item in loaded["layered"]["core"]["dislikes"])
        )

    def test_user_understanding_manual_layer_overrides_auto_fact(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="understanding-manual-layer-") as tmp:
                engine = MemoryEngine("manual_layer_bot", Path(tmp), config={"embedding": "none"})
                await engine.init()
                data = engine.user_understanding.load()
                data["manual"]["facts"]["猫"] = "布丁"
                data["auto"]["facts"]["猫"] = "奥利奥"
                engine.user_understanding._write(data)
                loaded = engine.user_understanding.load()
                ctx = await engine.load_context("我的猫叫什么？")
                await engine.close()
                return loaded, ctx

        loaded, ctx = asyncio.run(run())

        self.assertEqual(loaded["layered"]["core"]["facts"]["猫"], "布丁")
        self.assertIn("猫: 布丁", ctx["system_suffix"])
        self.assertNotIn("猫: 奥利奥", ctx["system_suffix"])

    def test_dislikes_memory_category_survives_projection_and_prompt(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="understanding-dislikes-") as tmp:
                engine = MemoryEngine("dislikes_bot", Path(tmp), config={"embedding": "none"})
                await engine.init()
                await engine.semantic.set_fact(
                    "用户不喜欢的称呼",
                    "用户不喜欢被叫老板",
                    session_id="s1",
                    bot_id="dislikes_bot",
                    user_id="default_user",
                    category="dislikes",
                    confidence=0.9,
                )
                await engine.governor.refresh_projection(bot_id="dislikes_bot", user_id="default_user")
                ctx = await engine.load_context("随便聊聊")
                loaded = engine.user_understanding.load()
                await engine.close()
                return loaded, ctx

        loaded, ctx = asyncio.run(run())

        self.assertIn("用户不喜欢被叫老板", loaded["layered"]["core"]["dislikes"])
        self.assertIn("不喜欢/避开的事", ctx["system_suffix"])
        self.assertIn("用户不喜欢被叫老板", ctx["system_suffix"])
        self.assertNotIn("[dislikes] 用户不喜欢的称呼", ctx["system_suffix"])

    def test_semantic_retrieval_searches_all_facts_before_prompt_limit(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="semantic-hybrid-") as tmp:
                engine = MemoryEngine("semantic_hybrid_bot", Path(tmp), config={"embedding": "none"})
                await engine.init()
                for index in range(35):
                    await engine.semantic.set_fact(
                        f"recent_noise_{index}",
                        f"最近但无关的事实 {index}",
                        bot_id="semantic_hybrid_bot",
                        user_id="default_user",
                        category="preferences",
                        confidence=1.0,
                    )
                await engine.semantic.set_fact(
                    "宠物布丁的品种",
                    "布丁是白色布偶猫",
                    bot_id="semantic_hybrid_bot",
                    user_id="default_user",
                    category="life_context",
                    confidence=0.92,
                )
                ctx = await engine.load_context("那布偶的名字你应该也记得吧")
                await engine.close()
                return ctx

        ctx = asyncio.run(run())

        self.assertIn("布丁是白色布偶猫", ctx["system_suffix"])
        self.assertIn("宠物布丁的品种", ctx["semantic_facts"])

    def test_user_understanding_refresh_preserves_existing_auto_profile_items(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="understanding-refresh-preserve-") as tmp:
                engine = MemoryEngine("refresh_preserve_bot", Path(tmp), config={"embedding": "none"})
                await engine.init()
                data = engine.user_understanding.load()
                data["auto"]["current_context"].append("用户养了两只猫：布丁和奥利奥。")
                data["auto"]["important_people"].append("布丁：白色布偶猫。")
                engine.user_understanding._write(data)
                await engine.user_understanding.refresh_auto_from_sources(
                    facts=[
                        {
                            "key": "咖啡口味偏好",
                            "value": "用户喜欢微甜拿铁",
                            "category": "preferences",
                            "confidence": 0.9,
                        }
                    ]
                )
                loaded = engine.user_understanding.load()
                await engine.close()
                return loaded

        loaded = asyncio.run(run())

        self.assertIn("用户养了两只猫：布丁和奥利奥。", loaded["layered"]["current"]["current_context"])
        self.assertIn("布丁：白色布偶猫。", loaded["auto"]["important_people"])
        self.assertIn("用户喜欢微甜拿铁", loaded["layered"]["core"]["preferences"])

    def test_prompt_builder_renders_self_memory_without_other_daily_context(self):
        from ai_companion.memory.prompt_builder import MemoryPromptBuilder

        retrieved = RetrievedMemory(
            intent="casual_chat",
            daily_context={
                "self_memory": [
                    {
                        "local_date": "2026-05-12",
                        "kind": "topic_continuation",
                        "content": "刚才那个话题我还在想，想接着跟你聊聊。",
                    }
                ]
            },
        )

        suffix = MemoryPromptBuilder(max_chars=1600).build(retrieved)

        self.assertIn("Bot 自己最近主动做过的事", suffix)
        self.assertIn("topic_continuation", suffix)
        self.assertIn("刚才那个话题我还在想", suffix)

    def test_daily_memory_cross_session_context_without_working_merge(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="daily-memory-") as tmp:
                engine = MemoryEngine(
                    "daily_bot",
                    Path(tmp),
                    config={
                        "embedding": "none",
                        "daily": {
                            "summarize_after_messages": 100,
                            "summarize_after_chars": 999999,
                        },
                    },
                )
                await engine.init()
                engine.start_session("gw_feishu")
                await engine.on_message(
                    "我今天在飞书说项目发布压力很大",
                    "我会记着，晚上可以再一起拆一下。",
                    turn_context={
                        "platform": "feishu",
                        "session_id": "gw_feishu",
                        "user_id": "default_user",
                        "channel_type": "dm",
                    },
                )

                engine.start_session("gw_weixin")
                ctx = await engine.load_context("刚才我们聊了什么？")
                working_text = "\n".join(item.get("content", "") for item in ctx["working_history"])
                suffix = ctx["system_suffix"]
                diagnostics = ctx["memory_prompt_diagnostics"]

                await engine.close()
                return working_text, suffix, ctx, diagnostics

        working_text, suffix, ctx, diagnostics = asyncio.run(run())
        self.assertNotIn("项目发布压力很大", working_text)
        self.assertIn("项目发布压力很大", suffix)
        self.assertIn("feishu", suffix)
        self.assertEqual(ctx["daily_context"]["recent_messages"][0]["platform"], "feishu")
        self.assertGreater(diagnostics["system_suffix_tokens_est"], 0)
        self.assertIn("final_tokens_est", diagnostics["prompt_budget"])

    def test_daily_memory_can_be_disabled(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="daily-memory-off-") as tmp:
                engine = MemoryEngine(
                    "daily_off_bot",
                    Path(tmp),
                    config={"embedding": "none", "daily": {"enabled": False}},
                )
                await engine.init()
                engine.start_session("s1")
                await engine.on_message("短期信息", "收到", turn_context={"platform": "cli"})
                engine.start_session("s2")
                ctx = await engine.load_context("你记得吗")
                status = await engine.get_memory_status()
                await engine.close()
                return ctx, status

        ctx, status = asyncio.run(run())
        self.assertEqual(ctx.get("daily_context"), {})
        self.assertEqual(status.get("daily_messages"), 0)

    def test_turn_context_session_controls_background_memory_write(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="daily-memory-session-") as tmp:
                engine = MemoryEngine(
                    "daily_session_bot",
                    Path(tmp),
                    config={"embedding": "none"},
                )
                await engine.init()
                engine.start_session("cli-session")
                await engine.on_message(
                    "gateway user text",
                    "gateway reply",
                    turn_context={
                        "platform": "weixin",
                        "session_id": "gw-session",
                        "user_id": "gateway-user",
                        "channel_type": "dm",
                        "message_id": "msg-1",
                    },
                )
                working_gw = engine.working.get_all_messages("gw-session")
                working_cli = engine.working.get_all_messages("cli-session")
                daily_ctx = engine.daily.get_recent_context(
                    bot_id="daily_session_bot",
                    user_id="gateway-user",
                )
                await engine.close()
                return working_gw, working_cli, daily_ctx

        working_gw, working_cli, daily_ctx = asyncio.run(run())
        self.assertEqual([item["content"] for item in working_gw], ["gateway user text", "gateway reply"])
        self.assertEqual(working_cli, [])
        self.assertEqual(daily_ctx["recent_messages"][0]["session_id"], "gw-session")

    def test_assistant_originated_message_is_recorded_without_user_turn(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="daily-memory-assistant-") as tmp:
                engine = MemoryEngine(
                    "daily_assistant_bot",
                    Path(tmp),
                    config={"embedding": "none"},
                )
                await engine.init()
                engine.start_session("gw-weixin-home")
                await engine.record_assistant_message(
                    "我刚刚主动分享了家里的小事",
                    turn_context={
                        "platform": "weixin",
                        "session_id": "gw-weixin-home",
                        "user_id": "gateway-user",
                        "channel_type": "dm",
                        "chat_id": "wx-user",
                    },
                )
                working = engine.working.get_all_messages("gw-weixin-home")
                daily_ctx = engine.daily.get_recent_context(
                    bot_id="daily_assistant_bot",
                    user_id="gateway-user",
                )
                await engine.close()
                return working, daily_ctx

        working, daily_ctx = asyncio.run(run())
        self.assertEqual([item["role"] for item in working], ["assistant"])
        self.assertEqual(working[0]["content"], "我刚刚主动分享了家里的小事")
        self.assertEqual(len(daily_ctx["recent_messages"]), 1)
        self.assertEqual(daily_ctx["recent_messages"][0]["role"], "assistant")

    def test_proactive_assistant_message_keeps_origin_metadata_in_working_context(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="daily-memory-proactive-origin-") as tmp:
                root = Path(tmp)
                persona_dir = root / "persona"
                persona_dir.mkdir(parents=True, exist_ok=True)
                (persona_dir / "proactive.json").write_text(
                    '{"enabled": true, "mode": "active"}',
                    encoding="utf-8",
                )
                memory = MemoryEngine("proactive_origin_bot", root, config={"embedding": "none"})
                await memory.init()
                memory.start_session("gw-home")
                engine = ProactiveEngine(
                    bot_id="proactive_origin_bot",
                    config=ProactiveConfig(persona_dir),
                    state=ProactiveState("proactive_origin_bot", root),
                    memory=memory,
                )

                async def sender(message: str):
                    return True

                engine._platform_sender = sender
                engine.set_next_record_context(
                    {
                        "platform": "weixin",
                        "session_id": "gw-home",
                        "user_id": "default_user",
                        "channel_type": "dm",
                        "chat_id": "wx-user",
                    }
                )
                sent = await engine._send_proactive_message("主动消息来源标记测试")
                working_context = memory.working.load_context("gw-home")
                daily_ctx = memory.daily.get_recent_context(
                    bot_id="proactive_origin_bot",
                    user_id="default_user",
                )
                loaded_ctx = await memory.load_context("在")
                await memory.close()
                return sent, working_context, daily_ctx, loaded_ctx

        sent, working_context, daily_ctx, loaded_ctx = asyncio.run(run())
        self.assertTrue(sent)
        self.assertEqual(working_context[-1]["content"], "主动消息来源标记测试")
        self.assertTrue(working_context[-1]["metadata"]["proactive"])
        self.assertTrue(working_context[-1]["metadata"]["assistant_initiated"])
        self.assertEqual(daily_ctx["self_memory"][0]["kind"], "idle_reminder")
        self.assertIn("主动消息来源标记测试", daily_ctx["self_memory"][0]["content"])
        self.assertGreaterEqual(loaded_ctx["memory_prompt_diagnostics"]["self_memory_count"], 1)
        detail_sources = [
            item.get("source")
            for item in loaded_ctx["conscious_context"].get("active_memory_details", [])
        ]
        self.assertIn("self_memory", detail_sources)
        self.assertIn("自传体线索", loaded_ctx["system_suffix"])

    def test_contextual_proactive_message_records_motive_kind(self):
        async def run():
            from ai_companion.proactive.motives import ProactiveMotive, ProactiveMotiveType

            with tempfile.TemporaryDirectory(prefix="daily-memory-proactive-kind-") as tmp:
                root = Path(tmp)
                persona_dir = root / "persona"
                persona_dir.mkdir(parents=True, exist_ok=True)
                (persona_dir / "proactive.json").write_text(
                    '{"enabled": true, "mode": "active"}',
                    encoding="utf-8",
                )
                memory = MemoryEngine("proactive_kind_bot", root, config={"embedding": "none"})
                await memory.init()
                memory.start_session("gw-kind")
                engine = ProactiveEngine(
                    bot_id="proactive_kind_bot",
                    config=ProactiveConfig(persona_dir),
                    state=ProactiveState("proactive_kind_bot", root),
                    memory=memory,
                )

                async def sender(message: str, target=None):
                    return True

                engine._platform_sender = sender
                motive = ProactiveMotive(
                    type=ProactiveMotiveType.DEFERRED_REPLY,
                    priority=100,
                    reason="继续刚才承诺的稍后回复",
                    prompt_context="用户刚才问过一个问题，Bot 说晚点回来。",
                )
                sent = await engine.send_contextual_proactive_message(motive)
                daily_ctx = memory.daily.get_recent_context(
                    bot_id="proactive_kind_bot",
                    user_id="default_user",
                )
                await memory.close()
                return sent, daily_ctx

        sent, daily_ctx = asyncio.run(run())
        self.assertTrue(sent)
        self.assertEqual(daily_ctx["self_memory"][0]["kind"], "deferred_reply")

    def test_contextual_proactive_prompt_prefers_latest_task_session_context(self):
        class CaptureModel:
            def __init__(self):
                self.prompt = ""

            async def chat(self, messages, system_prompt=None, **kwargs):
                self.prompt = messages[0]["content"]
                return '{"message":"我接着刚才的话说。"}'

        async def run():
            from datetime import datetime, timedelta
            from ai_companion.proactive.motives import (
                ConversationTask,
                ConversationTaskStatus,
                ConversationTaskType,
                ProactiveMotive,
                ProactiveMotiveType,
            )

            root = Path(tempfile.mkdtemp(prefix="daily-memory-task-session-anchor-"))
            persona_dir = root / "persona"
            persona_dir.mkdir(parents=True, exist_ok=True)
            (persona_dir / "proactive.json").write_text(
                '{"enabled": true, "mode": "active"}',
                encoding="utf-8",
            )
            memory = MemoryEngine("proactive_task_anchor_bot", root, config={"embedding": "none"})
            await memory.init()
            try:
                memory.start_session("gw-anchor")
                await memory.record_turn(
                    "你晚点把那件事接着说完。",
                    "好，我过一会儿回来接着说。",
                    turn_context={"session_id": "gw-anchor", "user_id": "default_user", "platform": "weixin"},
                )
                await memory.record_turn(
                    "不是那件旧事，我现在是说租房那个预算。",
                    "行，那我就按你刚说的租房预算来想。",
                    turn_context={"session_id": "gw-anchor", "user_id": "default_user", "platform": "weixin"},
                )

                model = CaptureModel()
                engine = ProactiveEngine(
                    bot_id="proactive_task_anchor_bot",
                    config=ProactiveConfig(persona_dir),
                    state=ProactiveState("proactive_task_anchor_bot", root),
                    memory=memory,
                )
                engine.set_model(model)

                now = datetime.now()
                task = ConversationTask(
                    id="task-anchor",
                    bot_id="proactive_task_anchor_bot",
                    type=ConversationTaskType.DEFERRED_REPLY,
                    status=ConversationTaskStatus.PENDING,
                    session_id="gw-anchor",
                    user_id="default_user",
                    platform="weixin",
                    target={"platform": "weixin"},
                    created_at=now,
                    due_at=now + timedelta(minutes=8),
                    expires_at=now + timedelta(hours=2),
                    source_user_message="你晚点把那件事接着说完。",
                    source_bot_message="好，我过一会儿回来接着说。",
                    topic_summary="稍后回来继续用户提过的话题",
                    priority=100,
                )
                motive = ProactiveMotive(
                    type=ProactiveMotiveType.DEFERRED_REPLY,
                    priority=100,
                    reason="继续刚才承诺的稍后回复",
                    prompt_context="用户在等你回来把刚才的话说完。",
                    task=task,
                    target={"platform": "weixin"},
                )
                await engine.generate_contextual_message(motive)
                return model.prompt
            finally:
                await memory.close()

        prompt = asyncio.run(run())
        self.assertIn("本次主动消息必须承接的最近现场", prompt)
        self.assertIn("租房那个预算", prompt)
        self.assertIn("按你刚说的租房预算来想", prompt)
        self.assertIn("不要另起炉灶", prompt)

    def test_proactive_generation_prompt_includes_recent_name_correction_guard(self):
        class CaptureModel:
            def __init__(self):
                self.prompt = ""

            async def chat(self, messages, system_prompt=None):
                self.prompt = messages[0]["content"]
                return '{"opening":"","topic":"我知道了。","ending":""}'

        async def run():
            with tempfile.TemporaryDirectory(prefix="daily-memory-proactive-name-") as tmp:
                root = Path(tmp)
                persona_dir = root / "persona"
                persona_dir.mkdir(parents=True, exist_ok=True)
                (persona_dir / "proactive.json").write_text(
                    '{"enabled": true, "mode": "active"}',
                    encoding="utf-8",
                )
                memory = MemoryEngine("proactive_name_bot", root, config={"embedding": "none"})
                await memory.init()
                memory.start_session("gw-name")
                await memory.record_turn(
                    "我不是米高",
                    "对不起，那我不这么叫了。",
                    turn_context={"session_id": "gw-name", "user_id": "default_user", "platform": "weixin"},
                )
                model = CaptureModel()
                engine = ProactiveEngine(
                    bot_id="proactive_name_bot",
                    config=ProactiveConfig(persona_dir),
                    state=ProactiveState("proactive_name_bot", root),
                    memory=memory,
                )
                engine.set_model(model)
                await engine.generate_message("想和用户聊天")
                await memory.close()
                return model.prompt

        prompt = asyncio.run(run())
        self.assertTrue(prompt)
        self.assertIn("我不是米高", prompt)
        self.assertIn("不要继续使用那个被否定的称呼", prompt)
        self.assertIn("条件式旧称呼", prompt)

    def test_working_recent_can_exclude_proactive_messages(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="daily-memory-working-recent-filter-") as tmp:
                root = Path(tmp)
                persona_dir = root / "persona"
                persona_dir.mkdir(parents=True, exist_ok=True)
                (persona_dir / "proactive.json").write_text(
                    '{"enabled": true, "mode": "active"}',
                    encoding="utf-8",
                )
                memory = MemoryEngine("recent_filter_bot", root, config={"embedding": "none"})
                await memory.init()
                try:
                    memory.start_session("gw-filter")
                    await memory.record_turn(
                        "晚上我去陪妹妹过生日",
                        "行，那你先去陪她。",
                        turn_context={"session_id": "gw-filter", "user_id": "default_user", "platform": "weixin"},
                    )
                    await memory.record_assistant_message(
                        "都八点多了，你还没吃饭吧？",
                        turn_context={
                            "session_id": "gw-filter",
                            "user_id": "default_user",
                            "platform": "weixin",
                            "metadata": {"proactive": True, "assistant_initiated": True, "proactive_kind": "idle_reminder"},
                        },
                    )
                    with_proactive = memory.working.get_recent("gw-filter", turns=3)
                    without_proactive = memory.working.get_recent("gw-filter", turns=3, include_proactive=False)
                    return with_proactive, without_proactive
                finally:
                    await memory.close()

        with_proactive, without_proactive = asyncio.run(run())
        self.assertEqual(with_proactive[0]["content"], "都八点多了，你还没吃饭吧？")
        self.assertTrue(with_proactive[0]["metadata"]["proactive"])
        self.assertEqual(without_proactive[0]["content"], "行，那你先去陪她。")
        self.assertFalse(any(item.get("metadata", {}).get("proactive") for item in without_proactive))

    def test_simple_summary_extracts_open_threads_commitments_and_mood(self):
        from ai_companion.memory.stores.daily import DailyMemoryStore

        store = DailyMemoryStore(":memory:")
        payload = store._simple_summary(
            existing=None,
            messages=[
                {"role": "user", "content": "我刚醒，下午还得上班，先点个外卖。"},
                {"role": "assistant", "content": "行，那你赶紧吃点东西，晚点记得去上班。"},
                {"role": "user", "content": "今天有点烦，开会开麻了。"},
                {"role": "assistant", "content": "等你忙完我拍几张照片给你看。"},
            ],
        )

        self.assertTrue(payload["open_threads"])
        self.assertTrue(payload["commitments"])
        self.assertTrue(payload["mood"])
        self.assertIn("我刚醒", payload["open_threads"][0])
        self.assertTrue(any("拍几张照片给你看" in item for item in payload["commitments"]))
        self.assertTrue(any("有点烦" in item for item in payload["mood"]))

    def test_proactive_engine_records_successful_sends(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="daily-memory-proactive-") as tmp:
                root = Path(tmp)
                persona_dir = root / "persona"
                persona_dir.mkdir(parents=True, exist_ok=True)
                (persona_dir / "proactive.json").write_text(
                    '{"enabled": true, "mode": "active"}',
                    encoding="utf-8",
                )
                memory = MemoryEngine("proactive_memory_bot", root, config={"embedding": "none"})
                await memory.init()
                memory.start_session("default-proactive-session")
                engine = ProactiveEngine(
                    bot_id="proactive_memory_bot",
                    config=ProactiveConfig(persona_dir),
                    state=ProactiveState("proactive_memory_bot", root),
                    memory=memory,
                )

                async def sender(message: str):
                    return True

                engine._platform_sender = sender
                engine.set_next_record_context(
                    {
                        "platform": "cli",
                        "session_id": "cli-proactive-session",
                        "user_id": "default_user",
                        "channel_type": "local",
                    }
                )
                sent = await engine._send_proactive_message("主动消息统一出口测试")
                working = memory.working.get_all_messages("cli-proactive-session")
                daily_ctx = memory.daily.get_recent_context(
                    bot_id="proactive_memory_bot",
                    user_id="default_user",
                )
                await memory.close()
                return sent, working, daily_ctx

        sent, working, daily_ctx = asyncio.run(run())
        self.assertTrue(sent)
        self.assertEqual([item["content"] for item in working], ["主动消息统一出口测试"])
        self.assertEqual(daily_ctx["recent_messages"][0]["content"], "主动消息统一出口测试")

    def test_proactive_engine_does_not_record_failed_sends(self):
        async def run():
            with tempfile.TemporaryDirectory(prefix="daily-memory-proactive-failed-") as tmp:
                root = Path(tmp)
                persona_dir = root / "persona"
                persona_dir.mkdir(parents=True, exist_ok=True)
                (persona_dir / "proactive.json").write_text(
                    '{"enabled": true, "mode": "active"}',
                    encoding="utf-8",
                )
                memory = MemoryEngine("proactive_failed_bot", root, config={"embedding": "none"})
                await memory.init()
                memory.start_session("proactive-failed-session")
                engine = ProactiveEngine(
                    bot_id="proactive_failed_bot",
                    config=ProactiveConfig(persona_dir),
                    state=ProactiveState("proactive_failed_bot", root),
                    memory=memory,
                )

                async def sender(message: str):
                    return False

                engine._platform_sender = sender
                sent = await engine._send_proactive_message("不该入库")
                working = memory.working.get_all_messages("proactive-failed-session")
                daily_count = memory.daily.count_messages(
                    bot_id="proactive_failed_bot",
                    user_id="default_user",
                )
                await memory.close()
                return sent, working, daily_count

        sent, working, daily_count = asyncio.run(run())
        self.assertFalse(sent)
        self.assertEqual(working, [])
        self.assertEqual(daily_count, 0)


if __name__ == "__main__":
    unittest.main()
