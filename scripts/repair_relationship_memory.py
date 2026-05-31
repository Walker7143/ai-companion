from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


COMMITTED_LABELS = {"恋人", "男女朋友", "男朋友", "女朋友", "伴侣", "爱人", "老婆", "老公"}
CONFLICT_PHRASES = ("未正式确立", "尚未得到对方承认", "尚未正式承认", "没批准", "谁给你封的官", "未确认")


def backup_file(path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.bak_memory_contract_{ts}")
    shutil.copy2(path, backup)
    return backup


def repair_session_state(db_path: Path, dry_run: bool) -> dict:
    result = {"updated": 0, "archived_candidates": 0}
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT session_id, value FROM session_states WHERE predicate='relationship_explicit_status' AND status='active'")
    rows = cur.fetchall()
    for session_id, value in rows:
        text = str(value or "")
        if any(phrase in text for phrase in CONFLICT_PHRASES):
            result["archived_candidates"] += 1
            if not dry_run:
                new_value = f"表达风格注释：{text}"
                cur.execute(
                    "UPDATE session_states SET value=? WHERE session_id=? AND predicate='relationship_explicit_status' AND status='active'",
                    (new_value, session_id),
                )
                result["updated"] += cur.rowcount
    if not dry_run:
        conn.commit()
    conn.close()
    return result


def repair_user_understanding(path: Path, dry_run: bool) -> dict:
    result = {"trimmed": 0}
    data = json.loads(path.read_text(encoding="utf-8"))
    relationship_memory = data.get("relationship_memory") if isinstance(data.get("relationship_memory"), dict) else {}
    items = relationship_memory.get("what_user_seems_to_need_from_bot") if isinstance(relationship_memory.get("what_user_seems_to_need_from_bot"), list) else []
    filtered = [item for item in items if not any(phrase in str(item) for phrase in CONFLICT_PHRASES)]
    result["trimmed"] = len(items) - len(filtered)
    if not dry_run and result["trimmed"]:
        relationship_memory["what_user_seems_to_need_from_bot"] = filtered
        data["relationship_memory"] = relationship_memory
        data["updated_at"] = datetime.now().isoformat()
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def repair_semantic(db_path: Path, dry_run: bool) -> dict:
    result = {"reweighted": 0}
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, key, value, confidence FROM user_facts WHERE category='identity'")
    rows = cur.fetchall()
    for row_id, key, value, confidence in rows:
        text = f"{key} {value}"
        if "男朋友" in text and float(confidence or 0) < 0.9:
            if not dry_run:
                cur.execute("UPDATE user_facts SET confidence=?, source=? WHERE id=?", (0.95, "user_confirmed", row_id))
            result["reweighted"] += 1
    if not dry_run:
        conn.commit()
    conn.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bot-id", required=True)
    parser.add_argument("--memory-root", default=str(Path.home() / ".ai-companion" / "data" / "bots"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    base = Path(args.memory_root) / args.bot_id / "memory"
    session_state = base / "session_state.db"
    semantic = base / "semantic.db"
    understanding = base / "user_understanding.json"
    if not session_state.exists() or not semantic.exists() or not understanding.exists():
        raise SystemExit("memory files not found")

    backups = []
    if not args.dry_run:
        for target in (session_state, semantic, understanding):
            backups.append(str(backup_file(target)))

    result = {
        "bot_id": args.bot_id,
        "dry_run": args.dry_run,
        "backups": backups,
        "session_state": repair_session_state(session_state, args.dry_run),
        "semantic": repair_semantic(semantic, args.dry_run),
        "user_understanding": repair_user_understanding(understanding, args.dry_run),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
