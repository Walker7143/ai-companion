import unittest
from unittest.mock import AsyncMock

from ai_companion.skill.auto_router import AutoSkillRouter
from ai_companion.skill.base import SkillContext, SkillResult
from ai_companion.skill.dispatcher import SkillDispatcher
from ai_companion.skill.image_generation import ImageGenerationSkill
from ai_companion.skill.image_understanding import ImageUnderstandingSkill


class AutoRouterTest(unittest.IsolatedAsyncioTestCase):
    def _ctx(self) -> SkillContext:
        return SkillContext(
            bot_id="test_bot",
            user_id="u1",
            conversation_history=[],
            personality_tags=[],
        )

    async def test_draw_intent_auto_routes_to_image_generation(self):
        dispatcher = SkillDispatcher()
        skill = ImageGenerationSkill({"enabled": True, "api_key": "x", "model": "gpt-image-1", "base_url": "https://example.com/v1"})
        skill.execute = AsyncMock(
            return_value=SkillResult(
                success=True,
                content="/tmp/generated.png",
                content_type="image",
            )
        )
        dispatcher.register(skill)
        router = AutoSkillRouter(dispatcher)

        result = await router.try_handle(
            runtime_input={"text": "帮我画一张雪山日出", "media_urls": [], "media_types": []},
            context=self._ctx(),
            capability_statuses={
                "image_generation": {
                    "enabled": True,
                    "auto": True,
                }
            },
        )

        self.assertTrue(result.handled)
        self.assertIn("MEDIA:/tmp/generated.png", result.direct_response)

    async def test_image_understanding_with_auto_false_does_not_intercept(self):
        dispatcher = SkillDispatcher()
        skill = ImageUnderstandingSkill(
            {
                "enabled": True,
                "provider": "custom",
                "custom": {"auth_type": "none", "api_url": "https://example.com"},
            }
        )
        skill.execute = AsyncMock(
            return_value=SkillResult(
                success=True,
                content={
                    "summary": "test",
                    "objects": [],
                    "text_ocr": "",
                    "safety_notes": [],
                    "confidence": 0.9,
                },
            )
        )
        dispatcher.register(skill)
        router = AutoSkillRouter(dispatcher)

        result = await router.try_handle(
            runtime_input={
                "text": "这是什么？",
                "media_urls": ["/tmp/fake.jpg"],
                "media_types": ["image/jpeg"],
            },
            context=self._ctx(),
            capability_statuses={
                "image_understanding": {
                    "enabled": True,
                    "auto": False,
                }
            },
        )

        self.assertFalse(result.handled)
        self.assertEqual(result.bot_visible_context, "")
        self.assertEqual(result.user_facing_hint, "")
        skill.execute.assert_not_awaited()

    async def test_image_message_auto_routes_to_image_understanding_context(self):
        dispatcher = SkillDispatcher()
        skill = ImageUnderstandingSkill(
            {
                "enabled": True,
                "provider": "custom",
                "custom": {"auth_type": "none", "api_url": "https://example.com"},
            }
        )
        skill.execute = AsyncMock(
            return_value=SkillResult(
                success=True,
                content={
                    "summary": "一只猫",
                    "objects": ["猫"],
                    "text_ocr": "hello",
                    "safety_notes": [],
                    "confidence": 0.88,
                },
            )
        )
        dispatcher.register(skill)
        router = AutoSkillRouter(dispatcher)

        result = await router.try_handle(
            runtime_input={
                "text": "图里是什么",
                "media_urls": ["/tmp/fake.jpg"],
                "media_types": ["image/jpeg"],
            },
            context=self._ctx(),
            capability_statuses={
                "image_understanding": {
                    "enabled": True,
                    "auto": True,
                }
            },
        )

        self.assertFalse(result.handled)
        self.assertIn("[图片理解结果]", result.bot_visible_context)
        self.assertIn("图片摘要: 一只猫", result.bot_visible_context)

    async def test_photo_capture_intent_routes_to_image_generation_with_camera_style_prompt(self):
        dispatcher = SkillDispatcher()
        skill = ImageGenerationSkill({"enabled": True, "api_key": "x", "model": "gpt-image-1", "base_url": "https://example.com/v1"})
        captured_prompt = {"value": ""}

        async def _fake_execute(params, _context):
            captured_prompt["value"] = str(params.get("prompt") or "")
            return SkillResult(success=True, content="/tmp/camera.png", content_type="image")

        skill.execute = AsyncMock(side_effect=_fake_execute)
        dispatcher.register(skill)
        router = AutoSkillRouter(dispatcher)

        result = await router.try_handle(
            runtime_input={"text": "你现在给我拍一张窗外的照片", "media_urls": [], "media_types": []},
            context=self._ctx(),
            capability_statuses={
                "image_generation": {
                    "enabled": True,
                    "auto": True,
                }
            },
        )

        self.assertTrue(result.handled)
        self.assertIn("MEDIA:/tmp/camera.png", result.direct_response)
        self.assertIn("模拟聊天对象当下随手拍的真实照片效果", captured_prompt["value"])

    async def test_installed_skill_keyword_auto_route(self):
        dispatcher = SkillDispatcher()

        class _InstalledEcho:
            name = "knowledge_lookup"
            description = "知识检索"
            capabilities = ["lookup"]
            default_model = ""

            def is_available(self):
                return True

        skill = _InstalledEcho()
        skill.execute = AsyncMock(
            return_value=SkillResult(
                success=True,
                content="lookup-result",
                content_type="text",
            )
        )
        dispatcher.register(skill)
        router = AutoSkillRouter(dispatcher)

        result = await router.try_handle(
            runtime_input={"text": "帮我查一下今天的汇率", "media_urls": [], "media_types": []},
            context=self._ctx(),
            capability_statuses={
                "knowledge_lookup": {
                    "name": "knowledge_lookup",
                    "source": "installed",
                    "enabled": True,
                    "auto": True,
                    "available": True,
                    "routing_keywords": ["查一下", "汇率"],
                    "confidence_threshold": 0.72,
                }
            },
        )

        self.assertTrue(result.handled)
        self.assertEqual(result.direct_response, "lookup-result")

    async def test_installed_skill_auto_false_not_triggered(self):
        dispatcher = SkillDispatcher()

        class _InstalledEcho:
            name = "knowledge_lookup"
            description = "知识检索"
            capabilities = ["lookup"]
            default_model = ""

            def is_available(self):
                return True

        skill = _InstalledEcho()
        skill.execute = AsyncMock(
            return_value=SkillResult(success=True, content="lookup-result", content_type="text")
        )
        dispatcher.register(skill)
        router = AutoSkillRouter(dispatcher)

        result = await router.try_handle(
            runtime_input={"text": "帮我查一下今天的汇率", "media_urls": [], "media_types": []},
            context=self._ctx(),
            capability_statuses={
                "knowledge_lookup": {
                    "name": "knowledge_lookup",
                    "source": "installed",
                    "enabled": True,
                    "auto": False,
                    "available": True,
                    "routing_keywords": ["查一下", "汇率"],
                    "confidence_threshold": 0.72,
                }
            },
        )

        self.assertFalse(result.handled)
        self.assertEqual(result.direct_response, "")
        skill.execute.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
