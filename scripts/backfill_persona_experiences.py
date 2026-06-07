from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_companion.config.loader import Config
from ai_companion.model.factory import ModelFactory


DEFAULT_USER_ID = "default_user"
MAX_EPISODES = 80
MAX_EXPERIENCES = 20
MAX_LIFE_EXPERIENCES = 12

SYSTEM_PROMPT = """你是一个严格的角色成长整理器。

你的任务是根据 bot 的历史记忆，提炼出会长期影响它的运行时人生经历。

请遵守：
1. 只保留长期有意义、会影响关系、性格、判断方式、生活走向的经历。
2. 合并重复事件，避免只是同一件事反复改写。
3. shared_experiences 是 bot 和用户共同经历过的事。
4. life_experiences 是 bot 自己的人生发展、生活状态、时间线中值得保留的经历。
5. 小事如果只是流水账，不要保留；但如果它改变了关系、情绪模式、性格或生活方向，可以保留。
6. 总结必须像“已经发生过的经历”，不要写成建议或设定说明。
7. 必须只输出 JSON，不要输出解释。
"""


def backup_file(path: Path, suffix: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.bak_{suffix}_{ts}")
    shutil.copy2(path, backup)
    return backup


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _dedupe(items: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = " ".join(str(item or "").split())
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _read_episodic_candidates(db_path: Path) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, summary, content, importance, confidence, relationship_effect,
               sensitivity, cue_tags_json, created_at
        FROM episodic_memory
        WHERE COALESCE(archived, 0) = 0
        ORDER BY importance DESC, confidence DESC, id DESC
        LIMIT ?
        """,
        (MAX_EPISODES,),
    ).fetchall()
    conn.close()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["cue_tags"] = json.loads(item.get("cue_tags_json") or "[]")
        except Exception:
            item["cue_tags"] = []
        items.append(item)
    return items


def _read_relationship_state(db_path: Path, bot_id: str, user_id: str) -> dict[str, Any]:
    if not db_path.exists():
        return {}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM relationship_state WHERE bot_id = ? AND user_id = ?",
        (bot_id, user_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else {}


def _read_life_state(bot_root: Path) -> dict[str, Any]:
    path = bot_root / "life_state.json"
    return _load_json(path)


def _merge_existing_experiences(runtime: dict[str, Any], backstory: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "shared_experiences": _dedupe(
            list(backstory.get("shared_experiences", []) or []) + list(runtime.get("shared_experiences", []) or []),
            MAX_EXPERIENCES,
        ),
        "life_experiences": _dedupe(
            list(backstory.get("life_experiences", []) or []) + list(runtime.get("life_experiences", []) or []),
            MAX_LIFE_EXPERIENCES,
        ),
    }


def _build_prompt(
    *,
    bot_id: str,
    profile: dict[str, Any],
    backstory: dict[str, Any],
    runtime: dict[str, Any],
    episodic_candidates: list[dict[str, Any]],
    relationship_state: dict[str, Any],
    life_state: dict[str, Any],
) -> str:
    existing = _merge_existing_experiences(runtime, backstory)
    payload = {
        "bot_id": bot_id,
        "profile": {
            "name": profile.get("name"),
            "age": profile.get("age"),
            "occupation": profile.get("occupation"),
            "personality_tags": profile.get("personality_tags", []),
        },
        "backstory_summary": backstory.get("summary", ""),
        "existing_runtime": {
            "shared_experiences": existing["shared_experiences"],
            "life_experiences": existing["life_experiences"],
            "shared_growth_summary": runtime.get("shared_growth_summary", ""),
            "life_growth_summary": runtime.get("life_growth_summary", ""),
        },
        "relationship_state": {
            "relationship_label": relationship_state.get("relationship_label"),
            "relationship_status": relationship_state.get("relationship_status"),
            "relationship_narrative": relationship_state.get("relationship_narrative"),
            "current_posture": relationship_state.get("current_posture"),
            "interaction_guidance": relationship_state.get("interaction_guidance"),
            "key_moments": _safe_json_list(relationship_state.get("key_moments_json")),
        },
        "episodic_candidates": [
            {
                "summary": item.get("summary", ""),
                "importance": item.get("importance", 0),
                "confidence": item.get("confidence", 0),
                "relationship_effect": item.get("relationship_effect", ""),
                "cue_tags": item.get("cue_tags", []),
                "created_at": item.get("created_at", ""),
            }
            for item in episodic_candidates
        ],
        "life_state": {
            "bot_mood": life_state.get("bot_mood"),
            "bot_current_activity": life_state.get("bot_current_activity"),
            "current_date": life_state.get("current_date"),
            "life_events": [
                {
                    "description": item.get("description", ""),
                    "importance": item.get("importance", 0),
                    "shareable": item.get("shareable", False),
                    "related_to_user": item.get("related_to_user", False),
                    "mood_before": item.get("mood_before", ""),
                    "mood_after": item.get("mood_after", ""),
                    "timestamp": item.get("timestamp", ""),
                }
                for item in list(life_state.get("life_events", []) or [])[-40:]
            ],
            "major_life_events": list(life_state.get("major_life_events", []) or [])[-20:],
            "life_journal": [
                {
                    "record_type": item.get("record_type", ""),
                    "date": item.get("date", ""),
                    "description": item.get("description", ""),
                }
                for item in list(life_state.get("life_journal", []) or [])[-50:]
            ],
        },
    }
    instructions = {
        "output_schema": {
            "shared_experiences": ["字符串"],
            "shared_growth_summary": "字符串",
            "life_experiences": ["字符串"],
            "life_growth_summary": "字符串",
        }
    }
    return (
        "请根据下面的数据，提炼 bot 已经形成的运行时人生经历。\n\n"
        f"数据：\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        f"输出要求：\n{json.dumps(instructions, ensure_ascii=False, indent=2)}"
    )


def _safe_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _extract_json_object(text: str) -> dict[str, Any]:
    text = str(text or "").strip()
    if not text:
        raise ValueError("empty model response")
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("json object not found")
    return json.loads(text[start:end + 1])


def _merge_runtime(runtime: dict[str, Any], generated: dict[str, Any]) -> dict[str, Any]:
    merged = dict(runtime or {})
    shared = _dedupe(
        list(runtime.get("shared_experiences", []) or []) + list(generated.get("shared_experiences", []) or []),
        MAX_EXPERIENCES,
    )
    life = _dedupe(
        list(runtime.get("life_experiences", []) or []) + list(generated.get("life_experiences", []) or []),
        MAX_LIFE_EXPERIENCES,
    )
    if shared:
        merged["shared_experiences"] = shared
    growth = str(generated.get("shared_growth_summary") or runtime.get("shared_growth_summary") or "").strip()
    if growth:
        merged["shared_growth_summary"] = growth
    if life:
        merged["life_experiences"] = life
    life_growth = str(generated.get("life_growth_summary") or runtime.get("life_growth_summary") or "").strip()
    if life_growth:
        merged["life_growth_summary"] = life_growth
    merged["updated_at"] = datetime.now().isoformat()
    return merged


async def _run_model(prompt: str) -> dict[str, Any]:
    config = Config()
    model_cfg = config.get_model_config()
    provider = model_cfg.get("provider", config.default_provider)
    model = ModelFactory.create_from_runtime_config(model_cfg, provider=provider)
    try:
        response = await model.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=2400,
        )
        return _extract_json_object(response)
    finally:
        await model.close()


def _heuristic_fallback(
    *,
    episodic_candidates: list[dict[str, Any]],
    relationship_state: dict[str, Any],
    life_state: dict[str, Any],
) -> dict[str, Any]:
    shared = _dedupe(
        [str(item.get("summary", "")).strip() for item in episodic_candidates if str(item.get("summary", "")).strip()],
        MAX_EXPERIENCES,
    )
    life_sources = [
        str(item.get("description", "")).strip()
        for item in list(life_state.get("major_life_events", []) or [])[-8:]
        if str(item.get("description", "")).strip()
    ]
    if not life_sources:
        life_sources = [
            str(item.get("description", "")).strip()
            for item in list(life_state.get("life_events", []) or [])[-MAX_LIFE_EXPERIENCES:]
            if str(item.get("description", "")).strip() and float(item.get("importance", 0) or 0) >= 5
        ]
    life = _dedupe(life_sources, MAX_LIFE_EXPERIENCES)
    rel = str(
        relationship_state.get("relationship_narrative")
        or relationship_state.get("relationship_label")
        or ""
    ).strip()
    shared_growth = ""
    if shared:
        shared_growth = f"这些共同经历正在不断改变你和用户的关系感受，尤其是最近这段：{shared[-1]}"
        if rel:
            shared_growth += f"。它也在强化你对这段关系的理解：{rel}"
    life_growth = ""
    if life:
        life_growth = f"这些经历让你现在的生活状态和性格更具体了，尤其最近这段：{life[-1]}"
    return {
        "shared_experiences": shared,
        "shared_growth_summary": shared_growth,
        "life_experiences": life,
        "life_growth_summary": life_growth,
    }


def _default_bot_id(config: Config) -> str:
    bots = config.get_enabled_bots()
    if not bots:
        raise SystemExit("no enabled bots found")
    return str(bots[0]["id"])


async def _async_main(args: argparse.Namespace) -> int:
    config = Config()
    bot_id = args.bot_id or _default_bot_id(config)
    data_root = Path(args.memory_root).expanduser()
    bot_root = data_root / bot_id
    persona_dir = bot_root / "persona"
    memory_dir = bot_root / "memory"
    runtime_path = persona_dir / "runtime_profile.json"
    backstory_path = persona_dir / "backstory.json"
    profile_path = persona_dir / "profile.json"

    if not persona_dir.exists() or not memory_dir.exists():
        raise SystemExit(f"bot data not found: {bot_root}")

    profile = _load_json(profile_path)
    backstory = _load_json(backstory_path)
    runtime = _load_json(runtime_path)
    episodic_candidates = _read_episodic_candidates(memory_dir / "episodic.db")
    relationship_state = _read_relationship_state(memory_dir / "relationship.db", bot_id, args.user_id)
    life_state = _read_life_state(bot_root)

    prompt = _build_prompt(
        bot_id=bot_id,
        profile=profile,
        backstory=backstory,
        runtime=runtime,
        episodic_candidates=episodic_candidates,
        relationship_state=relationship_state,
        life_state=life_state,
    )
    model_error = ""
    try:
        generated = await _run_model(prompt)
    except Exception as exc:
        model_error = str(exc)
        generated = _heuristic_fallback(
            episodic_candidates=episodic_candidates,
            relationship_state=relationship_state,
            life_state=life_state,
        )

    merged = _merge_runtime(runtime, generated)
    backups: list[str] = []
    if runtime_path.exists() and not args.dry_run:
        backups.append(str(backup_file(runtime_path, "persona_backfill")))
    if not args.dry_run:
        _write_json(runtime_path, merged)

    result = {
        "bot_id": bot_id,
        "dry_run": args.dry_run,
        "runtime_profile": str(runtime_path),
        "backups": backups,
        "shared_experiences_count": len(merged.get("shared_experiences", []) or []),
        "life_experiences_count": len(merged.get("life_experiences", []) or []),
        "shared_experiences": merged.get("shared_experiences", []),
        "life_experiences": merged.get("life_experiences", []),
        "shared_growth_summary": merged.get("shared_growth_summary", ""),
        "life_growth_summary": merged.get("life_growth_summary", ""),
        "model_error": model_error,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bot-id")
    parser.add_argument("--user-id", default=DEFAULT_USER_ID)
    parser.add_argument("--memory-root", default=str(Path.home() / ".ai-companion" / "data" / "bots"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
