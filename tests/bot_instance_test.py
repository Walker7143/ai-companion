import unittest

from ai_companion.bot.instance import BotInstance


class BrokenModel:
    provider = "broken"
    model = "broken-model"

    async def chat(self, messages, system_prompt="", **kwargs):
        raise TypeError("'NoneType' object is not subscriptable")


class BotInstanceModelFallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_chat_with_fallback_handles_unexpected_model_exceptions(self):
        bot = BotInstance({"id": "shen_nian", "name": "沈念"}, model=BrokenModel())

        with self.assertLogs("ai_companion.bot.instance", level="ERROR") as logs:
            result = await bot._chat_with_fallback([{"role": "user", "content": "hi"}])

        self.assertIsNone(result)
        self.assertTrue(any("对话异常" in item for item in logs.output))

    async def test_handle_message_includes_model_failure_diagnostics(self):
        bot = BotInstance(
            {"id": "shen_nian", "name": "沈念"},
            model=BrokenModel(),
            refusal_enabled=False,
        )
        bot._initialized = True
        bot._schedulers_started = True

        try:
            result = await bot.handle_message("hi")
        finally:
            await bot.close()

        self.assertIn("模型请求失败", result)
        self.assertIn("broken / broken-model", result)
        self.assertIn("'NoneType' object is not subscriptable", result)


if __name__ == "__main__":
    unittest.main()
