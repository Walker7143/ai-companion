import unittest

from ai_companion.bot.instance import BotInstance


class BrokenModel:
    async def chat(self, messages, system_prompt="", **kwargs):
        raise TypeError("'NoneType' object is not subscriptable")


class BotInstanceModelFallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_chat_with_fallback_handles_unexpected_model_exceptions(self):
        bot = BotInstance({"id": "shen_nian", "name": "沈念"}, model=BrokenModel())

        with self.assertLogs("ai_companion.bot.instance", level="ERROR") as logs:
            result = await bot._chat_with_fallback([{"role": "user", "content": "hi"}])

        self.assertIsNone(result)
        self.assertTrue(any("对话异常" in item for item in logs.output))


if __name__ == "__main__":
    unittest.main()
