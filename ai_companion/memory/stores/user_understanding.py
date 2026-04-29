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

    Version 3 treats the file as a relationship-depth understanding dossier:
    user-authored initialization stays in ``manual`` while daily interaction
    gradually refreshes richer ``auto`` observations.
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
        "version": 3,
        "updated_at": None,
        "manual": {
            "summary": "",
            "identity": {},
            "facts": {},
            "preferences": [],
            "communication_style": [],
            "boundaries": [],
            "relationship_expectations": [],
            "important_people": [],
            "current_context": [],
            "open_threads": [],
            "notes": [],
        },
        "auto": {
            "profile_summary": "",
            "facts": {},
            "preferences": [],
            "communication_style": [],
            "boundaries": [],
            "important_people": [],
            "current_context": [],
            "open_threads": [],
            "personality_observations": [],
            "emotional_patterns": [],
            "stressors": [],
            "comfort_strategies": [],
            "attachment_and_distance": [],
            "values_and_principles": [],
            "life_context": [],
            "goals_and_projects": [],
            "routines": [],
            "recent_changes": [],
            "last_refresh_at": None,
        },
        "relationship_memory": {
            "how_user_treats_bot": [],
            "what_user_seems_to_need_from_bot": [],
            "things_that_brought_them_closer": [],
            "things_that_created_tension": [],
            "repair_preferences": [],
        },
        "meta": {
            "confidence_notes": [],
            "contradictions": [],
            "last_reflection_at": None,
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

    AUTO_DEEP_SECTIONS = (
        "personality_observations",
        "emotional_patterns",
        "stressors",
        "comfort_strategies",
        "attachment_and_distance",
        "values_and_principles",
        "life_context",
        "goals_and_projects",
        "routines",
        "recent_changes",
    )

    RELATIONSHIP_SECTIONS = (
        "how_user_treats_bot",
        "what_user_seems_to_need_from_bot",
        "things_that_brought_them_closer",
        "things_that_created_tension",
        "repair_preferences",
    )

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

        if category in self.SECTIONS or category in self.AUTO_DEEP_SECTIONS:
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
        await self.refresh_auto_from_sources(facts=facts)

    async def refresh_auto_from_sources(
        self,
        *,
        facts: list[dict[str, Any]],
        relationship: dict[str, Any] | None = None,
    ):
        data = self.load()
        manual = data.setdefault("manual", self._empty_section())
        auto = self._empty_section(include_refresh=True)
        relationship_memory = self._empty_relationship_memory()
        meta = self._empty_meta()

        manual_fact_keys = set(self._clean_dict(manual.get("facts")).keys())
        manual_lists = {
            section: set(self._clean_list(manual.get(section)))
            for section in (*self.SECTIONS, "relationship_expectations", "notes")
        }

        for fact in facts:
            key = str(fact.get("key") or "").strip()
            value = self._trim(str(fact.get("value") or "").strip())
            category = str(fact.get("category") or "general")
            confidence = _float(fact.get("confidence"), 0.7)
            if not key or not value or key in self.INTERNAL_KEYS:
                continue
            if key in manual_fact_keys:
                meta["contradictions"].append(
                    f"自动事实「{key}: {value}」与用户手动设定同 key，未覆盖。"
                )
                continue
            if category in {"life_context"}:
                self._append_unique(auto["life_context"], value)
                self._append_unique(auto["current_context"], value)
                if any(word in value for word in ["压力", "焦虑", "失眠", "烦", "累", "崩溃", "委屈"]):
                    self._append_unique(auto["stressors"], value)
                    self._append_unique(auto["emotional_patterns"], f"近期容易受此影响：{value}")
            elif category in {"goals"}:
                self._append_unique(auto["goals_and_projects"], value)
                self._append_unique(auto["open_threads"], value)
            elif category in {"routines"}:
                self._append_unique(auto["routines"], value)
            elif category in {"boundaries"}:
                self._append_unique(auto["boundaries"], value)
                self._append_unique(auto["comfort_strategies"], f"尊重边界：{value}")
            elif category in {"communication_style"}:
                self._append_unique(auto["communication_style"], value)
                self._append_unique(auto["comfort_strategies"], value)
            elif category in self.SECTIONS:
                if key in manual_lists[category] or value in manual_lists[category]:
                    continue
                items = auto.setdefault(category, [])
                if value not in items:
                    items.append(value)
            elif category in {"identity"}:
                manual_identity = self._clean_dict(manual.get("identity"))
                if key in manual_identity:
                    meta["contradictions"].append(
                        f"自动身份信息「{key}: {value}」与 manual.identity 冲突，未覆盖。"
                    )
                    continue
                auto.setdefault("facts", {})[key] = value
            elif category in {"preferences"}:
                self._append_unique(auto["preferences"], value)
            elif category in {"important_people"}:
                self._append_unique(auto["important_people"], value)
            else:
                auto.setdefault("facts", {})[key] = value
            if confidence < 0.85:
                self._append_unique(meta["confidence_notes"], f"{key}: {value}（置信度 {confidence:.2f}，使用时保持弹性）")

        if relationship:
            label = str(relationship.get("relationship_label") or "").strip()
            if label:
                self._append_unique(relationship_memory["what_user_seems_to_need_from_bot"], f"当前关系标签：{label}")
            if _float(relationship.get("tension_score"), 0) >= 3:
                self._append_unique(relationship_memory["things_that_created_tension"], "关系状态显示近期存在紧张，需要先修复感受再推进话题。")
                self._append_unique(relationship_memory["repair_preferences"], "关系紧张时先放慢、承认感受、少解释。")
            if _float(relationship.get("trust_score"), 0) > 0 or _float(relationship.get("intimacy_score"), 0) > 0:
                self._append_unique(relationship_memory["things_that_brought_them_closer"], "近期互动提升了信任或亲密感。")
            for moment in relationship.get("key_moments") or []:
                self._append_unique(relationship_memory["things_that_brought_them_closer"], str(moment))
            for thread in relationship.get("open_emotional_threads") or []:
                self._append_unique(auto["open_threads"], str(thread))
                self._append_unique(relationship_memory["what_user_seems_to_need_from_bot"], f"还有未完成的情绪话题：{thread}")

        auto["profile_summary"] = self._build_profile_summary(manual, auto, relationship_memory)
        auto["last_refresh_at"] = datetime.now().isoformat()
        data["auto"] = auto
        data["relationship_memory"] = relationship_memory
        meta["last_reflection_at"] = datetime.now().isoformat()
        data["meta"] = meta
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

        manual_identity = self._clean_dict(manual.get("identity"))
        if manual_identity:
            lines.append("用户手动设定的身份信息：")
            lines.extend([f"  - {k}: {v}" for k, v in manual_identity.items()])

        manual_facts = self._clean_dict(manual.get("facts"))
        if manual_facts:
            lines.append("用户手动设定的事实：")
            lines.extend([f"  - {k}: {v}" for k, v in manual_facts.items()])

        for key, title in [
            ("preferences", "用户手动设定的偏好"),
            ("communication_style", "用户手动设定的沟通方式"),
            ("boundaries", "用户手动设定的边界"),
            ("relationship_expectations", "用户手动设定的关系期待"),
            ("important_people", "用户手动设定的重要关系"),
            ("current_context", "用户手动设定的当前生活状态/压力源"),
            ("open_threads", "用户手动设定的后续话题"),
            ("notes", "用户手动补充说明"),
        ]:
            items = self._clean_list(manual.get(key))
            if items:
                lines.append(f"{title}：")
                lines.extend([f"  - {item}" for item in items])

        auto_summary = str(auto.get("profile_summary") or auto.get("summary") or "").strip()
        if auto_summary:
            lines.append(f"Bot 在相处中逐渐形成的理解：{auto_summary}")

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
            ("emotional_patterns", "观察到的情绪模式"),
            ("stressors", "近期压力源"),
            ("comfort_strategies", "有效的安慰/陪伴方式"),
            ("attachment_and_distance", "亲近与距离模式"),
            ("values_and_principles", "价值观和原则"),
            ("goals_and_projects", "目标和项目"),
            ("routines", "作息和习惯"),
            ("recent_changes", "近期变化"),
        ]:
            items = self._clean_list(auto.get(key))
            if items:
                lines.append(f"{title}：")
                lines.extend([f"  - {item}" for item in items])

        relationship_memory = data.get("relationship_memory") if isinstance(data.get("relationship_memory"), dict) else {}
        for key, title in [
            ("how_user_treats_bot", "用户如何对待 Bot"),
            ("what_user_seems_to_need_from_bot", "用户似乎需要 Bot 提供的关系位置"),
            ("things_that_brought_them_closer", "让关系变近的时刻"),
            ("things_that_created_tension", "制造距离或紧张的点"),
            ("repair_preferences", "关系修复偏好"),
        ]:
            items = self._clean_list(relationship_memory.get(key))
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
            normalized["relationship_memory"] = self._normalize_relationship_memory(data.get("relationship_memory"))
            normalized["meta"] = self._normalize_meta(data.get("meta"))
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
            normalized["relationship_memory"] = self._empty_relationship_memory()
            normalized["meta"] = self._empty_meta()
            normalized["updated_at"] = data.get("updated_at")

        normalized["version"] = 3
        return self._with_compat_aliases(normalized)

    def _normalize_section(self, value: Any, include_refresh: bool = False) -> dict[str, Any]:
        section = self._empty_section(include_refresh=include_refresh)
        if isinstance(value, dict):
            section["summary"] = str(value.get("summary") or "")
            section["profile_summary"] = str(value.get("profile_summary") or value.get("summary") or "")
            section["identity"] = self._clean_dict(value.get("identity"))
            section["facts"] = self._clean_dict(value.get("facts"))
            for key in (*self.SECTIONS, "relationship_expectations", "notes", *self.AUTO_DEEP_SECTIONS):
                section[key] = self._clean_list(value.get(key))
            if include_refresh:
                section["last_refresh_at"] = value.get("last_refresh_at")
        return section

    def _empty_section(self, include_refresh: bool = False) -> dict[str, Any]:
        section: dict[str, Any] = {
            "summary": "",
            "profile_summary": "",
            "identity": {},
            "facts": {},
            "preferences": [],
            "communication_style": [],
            "boundaries": [],
            "relationship_expectations": [],
            "important_people": [],
            "current_context": [],
            "open_threads": [],
            "notes": [],
        }
        for key in self.AUTO_DEEP_SECTIONS:
            section[key] = []
        if include_refresh:
            section["last_refresh_at"] = None
        return section

    def _empty_relationship_memory(self) -> dict[str, Any]:
        return {key: [] for key in self.RELATIONSHIP_SECTIONS}

    def _empty_meta(self) -> dict[str, Any]:
        return {
            "confidence_notes": [],
            "contradictions": [],
            "last_reflection_at": None,
        }

    def _normalize_relationship_memory(self, value: Any) -> dict[str, Any]:
        result = self._empty_relationship_memory()
        if isinstance(value, dict):
            for key in self.RELATIONSHIP_SECTIONS:
                result[key] = self._clean_list(value.get(key))
        return result

    def _normalize_meta(self, value: Any) -> dict[str, Any]:
        result = self._empty_meta()
        if isinstance(value, dict):
            result["confidence_notes"] = self._clean_list(value.get("confidence_notes"))
            result["contradictions"] = self._clean_list(value.get("contradictions"))
            result["last_reflection_at"] = value.get("last_reflection_at")
        return result

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

    def _append_unique(self, items: list[str], value: str, limit: int = 12):
        value = str(value).strip()
        if value and value not in items:
            items.append(value)
        del items[:-limit]

    def _build_profile_summary(self, manual: dict[str, Any], auto: dict[str, Any], relationship_memory: dict[str, Any]) -> str:
        parts: list[str] = []
        if manual.get("summary"):
            parts.append(f"用户手动设定：{manual['summary']}")
        if auto.get("communication_style"):
            parts.append("沟通上更适合：" + "；".join(auto["communication_style"][:2]))
        if auto.get("stressors"):
            parts.append("近期压力源：" + "；".join(auto["stressors"][:2]))
        if auto.get("comfort_strategies"):
            parts.append("有效陪伴方式：" + "；".join(auto["comfort_strategies"][:2]))
        needs = relationship_memory.get("what_user_seems_to_need_from_bot") or []
        if needs:
            parts.append("关系中的需要：" + "；".join(needs[:2]))
        return self._trim("。".join(parts))

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


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
