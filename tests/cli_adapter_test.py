import asyncio
import unittest

from ai_companion.cli.adapter import CLIAdapter


class _DummyManager:
    def list_bots(self):
        return []


class CLIAdapterTest(unittest.IsolatedAsyncioTestCase):
    async def test_queue_proactive_message_schedules_immediate_flush(self):
        adapter = CLIAdapter(_DummyManager())
        flushed: list[list[tuple[str, str]]] = []

        async def fake_flush():
            flushed.append(list(adapter._pending_proactive))
            adapter._pending_proactive.clear()
            adapter._proactive_flush_task = None

        adapter._flush_proactive_messages = fake_flush

        result = await adapter._queue_proactive_message("Bot", "你好呀")
        await asyncio.sleep(0)

        self.assertTrue(result)
        self.assertEqual(flushed, [[("Bot", "你好呀")]])
        self.assertEqual(adapter._pending_proactive, [])


if __name__ == "__main__":
    unittest.main()
