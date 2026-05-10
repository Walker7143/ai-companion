import unittest

from ai_companion.gateway.config import Platform, PlatformConfig
from ai_companion.gateway.platforms.base import BasePlatformAdapter, SendResult


class DummyAdapter(BasePlatformAdapter):
    def __init__(self):
        super().__init__(PlatformConfig(enabled=True), Platform.LOCAL)
        self.sent = []

    async def connect(self) -> bool:
        return True

    async def disconnect(self) -> None:
        return None

    async def get_chat_info(self, chat_id: str) -> dict:
        return {"chat_id": chat_id, "name": chat_id, "type": "dm"}

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        self.sent.append(content)
        if len(self.sent) == 1:
            return SendResult(success=False, error="format parse failed")
        return SendResult(success=True, message_id="fallback")


class GatewayPlatformBaseTest(unittest.IsolatedAsyncioTestCase):
    async def test_send_with_retry_fallback_does_not_expose_internal_prefix(self):
        adapter = DummyAdapter()
        content = "hello " * 800

        result = await adapter._send_with_retry("chat-1", content)

        self.assertTrue(result.success)
        self.assertEqual(len(adapter.sent), 2)
        self.assertEqual(adapter.sent[1], content[:3500])
        self.assertNotIn("Response formatting failed", adapter.sent[1])


if __name__ == "__main__":
    unittest.main()
