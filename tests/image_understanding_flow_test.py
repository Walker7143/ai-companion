import unittest
from unittest.mock import AsyncMock

from ai_companion.bot.instance import BotInstance
from ai_companion.skill.base import SkillResult


class EchoModel:
    provider = "test"
    model = "echo-model"

    def __init__(self):
        self.last_messages = None
        self.last_system_prompt = ""

    async def chat(self, messages, system_prompt="", **kwargs):
        self.last_messages = messages
        self.last_system_prompt = system_prompt
        return "ok"


class BotImageUnderstandingIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_image_media_injects_understanding_context_when_available(self):
        model = EchoModel()
        bot = BotInstance(
            {
                "id": "shen_nian",
                "name": "沈念",
                "skills": {
                    "image_understanding": {
                        "enabled": True,
                        "provider": "custom",
                        "custom": {
                            "auth_type": "none",
                            "api_url": "https://example.com/vision",
                        },
                    }
                },
            },
            model=model,
            refusal_enabled=False,
        )
        bot._initialized = True
        bot._schedulers_started = True
        skill = bot.skill_dispatcher.get("image_understanding")
        self.assertIsNotNone(skill)
        skill.execute = AsyncMock(
            return_value=SkillResult(
                success=True,
                content={
                    "summary": "一只白色猫咪坐在窗台",
                    "objects": ["猫咪", "窗台"],
                    "text_ocr": "hello",
                    "safety_notes": [],
                    "confidence": 0.88,
                },
            )
        )
        try:
            response = await bot.handle_message(
                "这张图里有什么？",
                memory_turn_context={
                    "media_urls": ["/tmp/fake-image.jpg"],
                    "media_types": ["image/jpeg"],
                },
            )
        finally:
            await bot.close()

        self.assertEqual(response, "ok")
        self.assertIn("[图片理解结果]", model.last_system_prompt)
        self.assertIn("图片摘要: 一只白色猫咪坐在窗台", model.last_system_prompt)
        self.assertIn("识别到元素: 猫咪, 窗台", model.last_system_prompt)

    async def test_image_only_media_uses_non_empty_prompt_for_chat_model(self):
        model = EchoModel()
        bot = BotInstance(
            {
                "id": "shen_nian",
                "name": "test",
                "skills": {
                    "image_understanding": {
                        "enabled": True,
                        "provider": "custom",
                        "custom": {
                            "auth_type": "none",
                            "api_url": "https://example.com/vision",
                        },
                    }
                },
            },
            model=model,
            refusal_enabled=False,
        )
        bot._initialized = True
        bot._schedulers_started = True
        skill = bot.skill_dispatcher.get("image_understanding")
        self.assertIsNotNone(skill)
        skill.execute = AsyncMock(
            return_value=SkillResult(
                success=True,
                content={
                    "summary": "outdoor photo",
                    "objects": ["tree"],
                    "text_ocr": "",
                    "safety_notes": [],
                    "confidence": 0.8,
                },
            )
        )
        try:
            response = await bot.handle_message(
                "",
                memory_turn_context={
                    "media_urls": ["/tmp/wx-image.jpg"],
                    "media_types": ["image/jpeg"],
                },
            )
        finally:
            await bot.close()

        self.assertEqual(response, "ok")
        self.assertEqual(model.last_messages[-1]["content"], "[\u7528\u6237\u53d1\u9001\u4e86\u4e00\u5f20\u56fe\u7247]")
        self.assertIn("outdoor photo", model.last_system_prompt)

    async def test_image_media_with_disabled_capability_shows_clear_hint(self):
        model = EchoModel()
        bot = BotInstance(
            {
                "id": "shen_nian",
                "name": "沈念",
                "skills": {
                    "image_understanding": {
                        "enabled": False,
                    }
                },
            },
            model=model,
            refusal_enabled=False,
        )
        bot._initialized = True
        bot._schedulers_started = True
        try:
            response = await bot.handle_message(
                "帮我看看图里写了什么",
                memory_turn_context={
                    "media_urls": ["/tmp/fake-image.jpg"],
                    "media_types": ["image/jpeg"],
                },
            )
        finally:
            await bot.close()

        self.assertEqual(response, "当前未启用图片理解能力。\nok")
        self.assertNotIn("[图片理解结果]", model.last_system_prompt)

    async def test_image_understanding_failure_does_not_block_text_chat(self):
        model = EchoModel()
        bot = BotInstance(
            {
                "id": "shen_nian",
                "name": "沈念",
                "skills": {
                    "image_understanding": {
                        "enabled": True,
                        "provider": "custom",
                        "custom": {
                            "auth_type": "none",
                            "api_url": "https://example.com/vision",
                        },
                    }
                },
            },
            model=model,
            refusal_enabled=False,
        )
        bot._initialized = True
        bot._schedulers_started = True
        skill = bot.skill_dispatcher.get("image_understanding")
        self.assertIsNotNone(skill)
        skill.execute = AsyncMock(side_effect=RuntimeError("download/cache failed"))
        try:
            response = await bot.handle_message(
                "图里是什么？",
                memory_turn_context={
                    "media_urls": ["/tmp/fake-image.jpg"],
                    "media_types": ["image/jpeg"],
                },
            )
        finally:
            await bot.close()

        self.assertEqual(response, "ok")
        self.assertNotIn("[图片理解结果]", model.last_system_prompt)

    async def test_image_generation_auto_false_only_explicit_skill_can_trigger(self):
        model = EchoModel()
        bot = BotInstance(
            {
                "id": "shen_nian",
                "name": "沈念",
                "skills": {
                    "image_generation": {
                        "enabled": True,
                        "auto": False,
                        "base_url": "https://example.com/v1",
                        "model": "gpt-image-1",
                        "api_key": "test-key",
                    }
                },
            },
            model=model,
            refusal_enabled=False,
        )
        bot._initialized = True
        bot._schedulers_started = True
        gen_skill = bot.skill_dispatcher.get("image_generation")
        self.assertIsNotNone(gen_skill)
        gen_skill.execute = AsyncMock(
            return_value=SkillResult(
                success=True,
                content="/tmp/explicit.png",
                content_type="image",
            )
        )
        try:
            # auto=false: natural language should stay on chat path
            normal = await bot.handle_message("帮我画一张海边日落")
            # explicit /skill should still trigger
            explicit = await bot.handle_message("/skill image_generation 海边日落")
        finally:
            await bot.close()

        self.assertEqual(normal, "ok")
        self.assertIn("MEDIA:/tmp/explicit.png", explicit)

    async def test_explicit_skill_command_still_works_with_auto_router_enabled(self):
        model = EchoModel()
        bot = BotInstance(
            {
                "id": "shen_nian",
                "name": "沈念",
                "skills": {
                    "image_generation": {
                        "enabled": True,
                        "auto": True,
                        "base_url": "https://example.com/v1",
                        "model": "gpt-image-1",
                        "api_key": "test-key",
                    }
                },
            },
            model=model,
            refusal_enabled=False,
        )
        bot._initialized = True
        bot._schedulers_started = True
        gen_skill = bot.skill_dispatcher.get("image_generation")
        self.assertIsNotNone(gen_skill)
        gen_skill.execute = AsyncMock(
            return_value=SkillResult(
                success=True,
                content="/tmp/manual.png",
                content_type="image",
            )
        )
        try:
            explicit = await bot.handle_message("/skill image_generation 一张午后街景")
        finally:
            await bot.close()

        self.assertIn("MEDIA:/tmp/manual.png", explicit)

    async def test_plain_text_without_media_keeps_normal_chat_path(self):
        model = EchoModel()
        bot = BotInstance(
            {
                "id": "shen_nian",
                "name": "沈念",
                "skills": {
                    "image_understanding": {
                        "enabled": True,
                        "auto": True,
                        "provider": "custom",
                        "custom": {
                            "auth_type": "none",
                            "api_url": "https://example.com/vision",
                        },
                    }
                },
            },
            model=model,
            refusal_enabled=False,
        )
        bot._initialized = True
        bot._schedulers_started = True
        vision_skill = bot.skill_dispatcher.get("image_understanding")
        self.assertIsNotNone(vision_skill)
        vision_skill.execute = AsyncMock(
            return_value=SkillResult(
                success=True,
                content={
                    "summary": "不应被调用",
                    "objects": [],
                    "text_ocr": "",
                    "safety_notes": [],
                    "confidence": 0.1,
                },
            )
        )
        try:
            response = await bot.handle_message("我们来正常聊聊天")
        finally:
            await bot.close()

        self.assertEqual(response, "ok")
        vision_skill.execute.assert_not_awaited()
        self.assertNotIn("[图片理解结果]", model.last_system_prompt)

    async def test_gateway_and_cli_draw_intent_behave_consistently(self):
        config = {
            "id": "shen_nian",
            "name": "沈念",
            "skills": {
                "image_generation": {
                    "enabled": True,
                    "auto": True,
                    "base_url": "https://example.com/v1",
                    "model": "gpt-image-1",
                    "api_key": "test-key",
                }
            },
        }

        model_cli = EchoModel()
        bot_cli = BotInstance(config, model=model_cli, refusal_enabled=False)
        bot_cli._initialized = True
        bot_cli._schedulers_started = True
        cli_skill = bot_cli.skill_dispatcher.get("image_generation")
        self.assertIsNotNone(cli_skill)
        cli_skill.execute = AsyncMock(
            return_value=SkillResult(success=True, content="/tmp/consistent.png", content_type="image")
        )

        model_gw = EchoModel()
        bot_gw = BotInstance(config, model=model_gw, refusal_enabled=False)
        bot_gw._initialized = True
        bot_gw._schedulers_started = True
        gw_skill = bot_gw.skill_dispatcher.get("image_generation")
        self.assertIsNotNone(gw_skill)
        gw_skill.execute = AsyncMock(
            return_value=SkillResult(success=True, content="/tmp/consistent.png", content_type="image")
        )

        try:
            cli_resp = await bot_cli.handle_message("帮我画一张夜晚江边照片")
            gw_resp = await bot_gw.handle_message(
                "帮我画一张夜晚江边照片",
                memory_turn_context={
                    "media_urls": [],
                    "media_types": [],
                },
            )
        finally:
            await bot_cli.close()
            await bot_gw.close()

        self.assertEqual(cli_resp, gw_resp)
        self.assertIn("MEDIA:/tmp/consistent.png", cli_resp)


if __name__ == "__main__":
    unittest.main()
