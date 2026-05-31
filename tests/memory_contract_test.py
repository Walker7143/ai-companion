import unittest

from ai_companion.memory.continuity import ContinuityContractBuilder
from ai_companion.memory.retriever import RetrievedMemory


class MemoryContractTest(unittest.TestCase):
    def test_contract_marks_committed_relationship_as_hard_fact(self):
        retrieved = RetrievedMemory(
            intent="casual_chat",
            relationship_state={
                "relationship_label": "恋人",
                "relationship_narrative": "你们已经确认恋人/男女朋友关系，关系很亲近。",
                "interaction_guidance": "承接已确认关系，不要否认。",
            },
            session_state=[
                {
                    "predicate": "relationship_explicit_status",
                    "value": "未正式确立或尚未得到对方承认的男朋友身份",
                }
            ],
        )
        contract = ContinuityContractBuilder().build(current_input="你忘了我是你男朋友？", retrieved=retrieved)
        self.assertTrue(any("已确认" in item.text or "恋人" in item.text for item in contract.hard_facts))
        self.assertTrue(any(item.metadata.get("downgraded") for item in contract.soft_context))
        self.assertIn("committed_relationship", contract.risk_flags)


if __name__ == "__main__":
    unittest.main()
