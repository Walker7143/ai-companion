"""
Human-editable user understanding file.

This store keeps a readable JSON profile next to the bot's runtime memory.
Users can edit the manual sections directly, while automatic extraction only
touches the auto section.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


class UserUnderstandingStore:
    """Readable user profile backed by memory/user_understanding.json.

    Version 2 separates user-authored understanding from automatic projection.
    Backward-compatible top-level aliases are kept for the existing CLI/UI.
    """

    SECTIONS = (
        "preferences",
        "communication_style",
        "boundaries",
        "important_people",
        "current_context",
        "open_threads",
    )

    DEFAULT_DATA: dict[str, Any] = {
        "version": 2,
        "updated_at": None,
        "manual": {
            "summary": "",
            "facts": {},
            "preferences": [],
            "communication_style": [],
            "boundaries": [],
            "important_people": [],
            "current_context": [],
            "open_threads": [],
        },
        "auto": {
            "summary": "",
            "facts": {},
            "preferences": [],
            "communication_style": [],
            "boundaries": [],
            "important_people": [],
            "current_context": [],
            "open_threads": [],
            "last_refresh_at": None,
        },
        # Compatibility aliases for older admin/CLI code.
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

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            broken = self.path.with_suffix(".json.broken")
            try:
                self.path.replace(broken)
            except Exception:
                pass
            self._write(self._default_data())
            return

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
        for container in (data.get("manual"), data.get("auto"), data):
            if isinstance(container, dict):
                values = container.get("facts")
                if isinstance(values, dict):
                    keys.update(str(k) for k in values.keys())
                values = container.get("auto_facts")
                if isinstance(values, dict):
                    keys.update(str(k) for k in values.keys())
        return keys

    def has_manual_key(self, key: str, category: str = "general") -> bool:
        key = str(key).strip()
        if not key:
            return False
        data = self.load()
        manual = data.get("manual") if isinstance(data.get("manual"), dict) else {}
        facts = manual.get("facts") if isinstance(manual.get("facts"), dict) else {}
        if key in facts:
            return True
        if category in self.SECTIONS:
            return key in {str(item).strip() for item in manual.get(category, []) if str(item).strip()}
        return False

    async def upsert_auto_fact(self, key: str, value: str):
        await self.upsert_auto_item(key=key, value=value, category="general")

    async def upsert_auto_item(self, *, key: str, value: str, category: str = "general"):
        key = str(key).strip()
        value = str(value).strip()
        if not key or not value or key in self.INTERNAL_KEYS:
            return

        data = self.load()
        manual = data.setdefault("manual", self._empty_section())
        auto = data.setdefault("auto", self._empty_section(include_refresh=True))
        category = str(category or "general")

        if category in self.SECTIONS:
            manual_items = set(self._clean_list(manual.get(category)))
            if value in manual_items or key in manual_items:
                return
            items = auto.setdefault(category, [])
            trimmed = self._trim(value)
            if trimmed not in items:
                items.append(trimmed)
        else:
            manual_facts = manual.setdefault("facts", {})
            if key in manual_facts:
                return
            auto_facts = auto.setdefault("facts", {})
            trimmed = self._trim(value)
            if auto_facts.get(key) == trimmed:
                return
            auto_facts[key] = trimmed

        auto["last_refresh_at"] = datetime.now().isoformat()
        data["updated_at"] = datetime.now().isoformat()
        self._write(self._with_compat_aliases(data))

    async def refresh_auto_from_facts(self, facts: list[dict[str, Any]]):
        data = self.load()
        manual = data.setdefault("manual", self._empty_section())
        auto = self._empty_section(include_refresh=True)

        manual_fact_keys = set(self._clean_dict(manual.get("facts")).keys())
        manual_lists = {
            section: set(self._clean_list(manual.get(section)))
            for section in self.SECTIONS
        }

        for fact in facts:
            key = str(fact.get("key") or "").strip()
            value = self._trim(str(fact.get("value") or "").strip())
            category = str(fact.get("category") or "general")
            if not key or not value or key in self.INTERNAL_KEYS:
                continue
            if category in self.SECTIONS:
                if key in manual_lists[category] or value in manual_lists[category]:
                    continue
                items = auto.setdefault(category, [])
                if value not in items:
                    items.append(value)
            else:
                if key in manual_fact_keys:
                    continue
                auto.setdefault("facts", {})[key] = value

        auto["last_refresh_at"] = datetime.now().isoformat()
        data["auto"] = auto
        data["updated_at"] = datetime.now().isoformat()
        self._write(self._with_compat_aliases(data))

    async def delete_auto_fact(self, key: str):
        key = str(key).strip()
        if not key:
            return

        data = self.load()
        changed = False
        auto = data.get("auto") if isinstance(data.get("auto"), dict) else {}
        facts = auto.get("facts") if isinstance(auto.get("facts"), dict) else {}
        if key in facts:
            del facts[key]
            changed = True
        auto_facts = data.get("auto_facts")
        if isinstance(auto_facts, dict) and key in auto_facts:
            del auto_facts[key]
            changed = True
        if changed:
            auto["last_refresh_at"] = datetime.now().isoformat()
            data["updated_at"] = datetime.now().isoformat()
            self._write(self._with_compat_aliases(data))

    def auto_fact_count(self) -> int:
        data = self.load()
        auto = data.get("auto") if isinstance(data.get("auto"), dict) else {}
        return len(self._clean_dict(auto.get("facts")))

    def format_for_prompt(self) -> str:
        data = self.load()
        lines: list[str] = []

        manual = data.get("manual") if isinstance(data.get("manual"), dict) else {}
        auto = data.get("auto") if isinstance(data.get("auto"), dict) else {}

        summary = str(manual.get("summary", "")).strip()
        if summary:
            lines.append(f"用户手动设定的整体理解：{summary}")

        manual_facts = self._clean_dict(manual.get("facts"))
        if manual_facts:
            lines.append("用户手动设定的事实：")
            lines.extend([f"  - {k}: {v}" for k, v in manual_facts.items()])

        for key, title in [
            ("preferences", "用户手动设定的偏好"),
            ("communication_style", "用户手动设定的沟通方式"),
            ("boundaries", "用户手动设定的边界"),
            ("important_people", "用户手动设定的重要关系"),
            ("current_context", "用户手动设定的当前生活状态/压力源"),
            ("open_threads", "用户手动设定的后续话题"),
        ]:
            items = self._clean_list(manual.get(key))
            if items:
                lines.append(f"{title}：")
                lines.extend([f"  - {item}" for item in items])

        auto_summary = str(auto.get("summary", "")).strip()
        if auto_summary:
            lines.append(f"从日常对话自动形成的理解：{auto_summary}")

        auto_facts = self._clean_dict(auto.get("facts"))
        if auto_facts:
            lines.append("从日常对话自动补充的事实：")
            lines.extend([f"  - {k}: {v}" for k, v in auto_facts.items()])

        for key, title in [
            ("preferences", "自动补充的用户偏好"),
            ("communication_style", "自动补充的沟通方式"),
            ("boundaries", "自动补充的边界和雷区"),
            ("important_people", "自动补充的重要关系"),
            ("current_context", "自动补充的当前生活状态/压力源"),
            ("open_threads", "自动补充的后续可以关心的话题"),
        ]:
            items = self._clean_list(auto.get(key))
            if items:
                lines.append(f"{title}：")
                lines.extend([f"  - {item}" for item in items])

        return "\n".join(lines)

    def _default_data(self) -> dict[str, Any]:
        return deepcopy(self.DEFAULT_DATA)

    def _normalize(self, data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            return self._default_data()

        normalized = self._default_data()
        if isinstance(data.get("manual"), dict) or isinstance(data.get("auto"), dict):
            normalized.update(data)
            normalized["manual"] = self._normalize_section(data.get("manual"))
            normalized["auto"] = self._normalize_section(data.get("auto"), include_refresh=True)
            # Existing users may still edit the old top-level aliases by hand.
            # Treat those edits as manual input when the v2 manual field is empty.
            if data.get("summary") and not normalized["manual"].get("summary"):
                normalized["manual"]["summary"] = str(data.get("summary") or "")
            if isinstance(data.get("facts"), dict) and not normalized["manual"].get("facts"):
                normalized["manual"]["facts"] = self._clean_dict(data.get("facts"))
            for section in self.SECTIONS:
                if data.get(section) and not normalized["manual"].get(section):
                    normalized["manual"][section] = self._clean_list(data.get(section))
        else:
            # v1 migration: old user-editable top-level fields become manual;
            # old auto_facts becomes auto.facts.
            manual = self._empty_section()
            manual["summary"] = str(data.get("summary") or "")
            manual["facts"] = self._clean_dict(data.get("facts"))
            for section in self.SECTIONS:
                manual[section] = self._clean_list(data.get(section))

            auto = self._empty_section(include_refresh=True)
            auto["facts"] = self._clean_dict(data.get("auto_facts"))
            normalized["manual"] = manual
            normalized["auto"] = auto
            normalized["updated_at"] = data.get("updated_at")

        normalized["version"] = 2
        return self._with_compat_aliases(normalized)

    def _normalize_section(self, value: Any, include_refresh: bool = False) -> dict[str, Any]:
        section = self._empty_section(include_refresh=include_refresh)
        if isinstance(value, dict):
            section["summary"] = str(value.get("summary") or "")
            section["facts"] = self._clean_dict(value.get("facts"))
            for key in self.SECTIONS:
                section[key] = self._clean_list(value.get(key))
            if include_refresh:
                section["last_refresh_at"] = value.get("last_refresh_at")
        return section

    def _empty_section(self, include_refresh: bool = False) -> dict[str, Any]:
        section: dict[str, Any] = {
            "summary": "",
            "facts": {},
            "preferences": [],
            "communication_style": [],
            "boundaries": [],
            "important_people": [],
            "current_context": [],
            "open_threads": [],
        }
        if include_refresh:
            section["last_refresh_at"] = None
        return section

    def _with_compat_aliases(self, data: dict[str, Any]) -> dict[str, Any]:
        data = deepcopy(data)
        manual = data.get("manual") if isinstance(data.get("manual"), dict) else self._empty_section()
        auto = data.get("auto") if isinstance(data.get("auto"), dict) else self._empty_section(include_refresh=True)
        data["summary"] = manual.get("summary", "")
        data["facts"] = deepcopy(manual.get("facts", {}))
        for section in self.SECTIONS:
            data[section] = list(manual.get(section, []))
        data["auto_facts"] = deepcopy(auto.get("facts", {}))
        return data

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
