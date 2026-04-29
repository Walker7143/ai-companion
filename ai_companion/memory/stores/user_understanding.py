"""
Human-editable user understanding file.

This store keeps a readable JSON profile next to the bot's runtime memory.
Users can edit the manual sections directly, while automatic extraction only
touches the auto_facts section.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


class UserUnderstandingStore:
    """Readable user profile backed by memory/user_understanding.json."""

    DEFAULT_DATA: dict[str, Any] = {
        "version": 1,
        "updated_at": None,
        "summary": "",
        "facts": {},
        "preferences": [],
        "communication_style": [],
        "boundaries": [],
        "important_people": [],
        "current_context": [],
        "open_threads": [],
        "auto_facts": {},
    }

    INTERNAL_KEYS = {
        "attitude_score",
        "relationship_to_user",
        "relationship_level",
        "key_moment",
    }

    def __init__(self, path: str | Path, max_value_chars: int = 4400):
        self.path = Path(path)
        self.max_value_chars = max_value_chars

    async def init(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write(self._default_data())
            return

        data = self.load()
        normalized = self._normalize(data)
        if normalized != data:
            self._write(normalized)

    def load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return self._default_data()
        return self._normalize(data)

    def known_fact_keys(self) -> set[str]:
        data = self.load()
        keys = set()
        for section in ("facts", "auto_facts"):
            values = data.get(section)
            if isinstance(values, dict):
                keys.update(str(k) for k in values.keys())
        return keys

    async def upsert_auto_fact(self, key: str, value: str):
        key = str(key).strip()
        value = str(value).strip()
        if not key or not value or key in self.INTERNAL_KEYS:
            return

        data = self.load()
        auto_facts = data.setdefault("auto_facts", {})
        trimmed = self._trim(value)
        if auto_facts.get(key) == trimmed:
            return
        auto_facts[key] = trimmed
        data["updated_at"] = datetime.now().isoformat()
        self._write(data)

    async def delete_auto_fact(self, key: str):
        key = str(key).strip()
        if not key:
            return

        data = self.load()
        auto_facts = data.get("auto_facts")
        if isinstance(auto_facts, dict) and key in auto_facts:
            del auto_facts[key]
            data["updated_at"] = datetime.now().isoformat()
            self._write(data)

    def format_for_prompt(self) -> str:
        data = self.load()
        lines: list[str] = []

        summary = str(data.get("summary", "")).strip()
        if summary:
            lines.append(f"整体理解：{summary}")

        manual_facts = self._clean_dict(data.get("facts"))
        if manual_facts:
            lines.append("用户手动设定的事实：")
            lines.extend([f"  - {k}: {v}" for k, v in manual_facts.items()])

        for key, title in [
            ("preferences", "用户偏好"),
            ("communication_style", "希望的相处/沟通方式"),
            ("boundaries", "边界和雷区"),
            ("important_people", "重要关系"),
            ("current_context", "当前生活状态/压力源"),
            ("open_threads", "后续可以关心的话题"),
        ]:
            items = self._clean_list(data.get(key))
            if items:
                lines.append(f"{title}：")
                lines.extend([f"  - {item}" for item in items])

        auto_facts = self._clean_dict(data.get("auto_facts"))
        if auto_facts:
            lines.append("从日常对话自动补充的事实：")
            lines.extend([f"  - {k}: {v}" for k, v in auto_facts.items()])

        return "\n".join(lines)

    def _default_data(self) -> dict[str, Any]:
        return deepcopy(self.DEFAULT_DATA)

    def _normalize(self, data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            return self._default_data()

        normalized = self._default_data()
        normalized.update(data)

        for section in ("facts", "auto_facts"):
            if not isinstance(normalized.get(section), dict):
                normalized[section] = {}

        for section in (
            "preferences",
            "communication_style",
            "boundaries",
            "important_people",
            "current_context",
            "open_threads",
        ):
            if isinstance(normalized.get(section), str):
                normalized[section] = [normalized[section]]
            elif not isinstance(normalized.get(section), list):
                normalized[section] = []

        normalized["version"] = 1
        return normalized

    def _write(self, data: dict[str, Any]):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(self.path)

    def _trim(self, value: str) -> str:
        if len(value) > self.max_value_chars:
            return value[: self.max_value_chars - 3] + "..."
        return value

    def _clean_dict(self, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        result = {}
        for k, v in value.items():
            key = str(k).strip()
            val = str(v).strip()
            if key and val:
                result[key] = val
        return result

    def _clean_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]
