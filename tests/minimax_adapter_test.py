import unittest

from ai_companion.model.adapters.minimax_adapter import MiniMaxAdapter


class MiniMaxAdapterResponseParsingTest(unittest.TestCase):
    def test_parse_chat_response_rejects_null_choices(self):
        payload = {
            "choices": None,
            "base_resp": {"status_code": 0, "status_msg": ""},
        }

        with self.assertRaisesRegex(RuntimeError, "missing choices"):
            MiniMaxAdapter._parse_chat_response(payload)

    def test_parse_chat_response_reports_base_resp_error(self):
        payload = {
            "choices": None,
            "base_resp": {"status_code": 1008, "status_msg": "rate limited"},
        }

        with self.assertRaisesRegex(RuntimeError, "MiniMax API error 1008: rate limited"):
            MiniMaxAdapter._parse_chat_response(payload)

    def test_parse_chat_response_uses_reasoning_when_content_empty(self):
        payload = {
            "choices": [
                {"message": {"content": "", "reasoning_content": "fallback reply"}}
            ],
            "base_resp": {"status_code": 0, "status_msg": ""},
        }

        self.assertEqual(MiniMaxAdapter._parse_chat_response(payload), "fallback reply")


if __name__ == "__main__":
    unittest.main()
