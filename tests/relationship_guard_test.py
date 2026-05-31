import asyncio
import unittest

from ai_companion.memory.session_state import RelationshipConsistencyChecker


class RelationshipGuardTest(unittest.TestCase):
    def test_rule_check_blocks_denial_for_committed_relationship(self):
        checker = RelationshipConsistencyChecker()
        result = checker.rule_check(
            "……谁给你封的官儿啊？我怎么不记得批准过这任命？",
            {"relationship_label": "恋人"},
        )
        self.assertFalse(result["consistent"])
        self.assertTrue(result["matched_rules"])

    def test_llm_failure_does_not_disable_rule_guard(self):
        checker = RelationshipConsistencyChecker()
        result = asyncio.run(
            checker.check(
                "……没答应过你这个身份。",
                {"relationship_label": "恋人"},
            )
        )
        self.assertFalse(result["consistent"])


if __name__ == "__main__":
    unittest.main()
