import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.repair_relationship_memory import repair_semantic, repair_session_state, repair_user_understanding


class MemoryProjectionMigrationTest(unittest.TestCase):
    def test_migration_repairs_conflicting_runtime_artifacts(self):
        with tempfile.TemporaryDirectory(prefix="memory-migration-") as td:
            base = Path(td)
            session_db = base / "session_state.db"
            semantic_db = base / "semantic.db"
            understanding = base / "user_understanding.json"

            conn = sqlite3.connect(session_db)
            cur = conn.cursor()
            cur.execute("CREATE TABLE session_states (session_id TEXT, predicate TEXT, value TEXT, status TEXT)")
            cur.execute(
                "INSERT INTO session_states VALUES (?, ?, ?, ?)",
                ("s1", "relationship_explicit_status", "未正式确立或尚未得到对方承认的男朋友身份", "active"),
            )
            conn.commit()
            conn.close()

            conn = sqlite3.connect(semantic_db)
            cur = conn.cursor()
            cur.execute("CREATE TABLE user_facts (id INTEGER PRIMARY KEY, key TEXT, value TEXT, confidence REAL, source TEXT, category TEXT)")
            cur.execute(
                "INSERT INTO user_facts (key, value, confidence, source, category) VALUES (?, ?, ?, ?, ?)",
                ("用户自称是男朋友", "用户说自己是男朋友", 0.8, "auto", "identity"),
            )
            conn.commit()
            conn.close()

            understanding.write_text(
                json.dumps(
                    {
                        "relationship_memory": {
                            "what_user_seems_to_need_from_bot": [
                                "助手尚未正式承认男朋友身份，用户可能期待更明确的确认"
                            ]
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            session_result = repair_session_state(session_db, dry_run=False)
            semantic_result = repair_semantic(semantic_db, dry_run=False)
            understanding_result = repair_user_understanding(understanding, dry_run=False)

            self.assertGreaterEqual(session_result["updated"], 1)
            self.assertGreaterEqual(semantic_result["reweighted"], 1)
            self.assertGreaterEqual(understanding_result["trimmed"], 1)


if __name__ == "__main__":
    unittest.main()
