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
        "dislikes",
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
            "dislikes": [],
            "communication_style": [],
            "boundaries": [],
            "relationship_expectations": [],
            "interaction_style": {
                "preferred_reply_length": "",
                "accepted_humor": [],
                "disliked_phrases": [],
                "natural_openings": [],
                "avoid_patterns": [],
            },
            "important_people": [],
            "current_context": [],
            "open_threads": [],
            "notes": [],
        },
        "auto": {
            "profile_summary": "",
            "facts": {},
            "preferences": [],
            "dislikes": [],
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
            "interaction_style": {
                "preferred_reply_length": "",
                "accepted_humor": [],
                "disliked_phrases": [],
                "natural_openings": [],
                "avoid_patterns": [],
            },
            "last_refresh_at": None,
        },
        "relationship_memory": {
            "how_user_treats_bot": [],
            "what_user_seems_to_need_from_bot": [],
            "things_that_brought_them_closer": [],
            "things_that_created_tension": [],
            "repair_preferences": [],
        },
        "layered": {
            "core": {
                "summary": "",
                "identity": {},
                "facts": {},
                "preferences": [],
                "dislikes": [],
                "communication_style": [],
                "boundaries": [],
                "relationship_expectations": [],
            },
            "current": {
                "current_context": [],
                "open_threads": [],
                "goals_and_projects": [],
                "recent_changes": [],
                "stressors": [],
                "routines": [],
            },
            "deep": {
                "personality_observations": [],
                "emotional_patterns": [],
                "comfort_strategies": [],
                "attachment_and_distance": [],
                "values_and_principles": [],
                "life_context": [],
                "relationship_memory": {},
            },
            "sensitive": {
                "topics": [],
                "guidance": [],
                "source_keys": [],
            },
            "generated_at": None,
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
        "dislikes": [],
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
        "用户身份信息",
        "用户身份",
        "identity",
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

    def seed_manual_from(self, seed_path: str | Path) -> bool:
        """Seed an empty manual profile from bundled bot defaults."""
        seed_path = Path(seed_path)
        if not seed_path.exists():
            return False
        try:
            if seed_path.resolve() == self.path.resolve():
                return False
        except Exception:
            pass

        try:
            seed_data = json.loads(seed_path.read_text(encoding="utf-8"))
        except Exception:
            return False

        seed = self._normalize(seed_data)
        data = self.load()
        changed = False

        manual = data.get("manual") if isinstance(data.get("manual"), dict) else {}
        seed_manual = seed.get("manual") if isinstance(seed.get("manual"), dict) else {}
        if not self._section_has_content(manual) and self._section_has_content(seed_manual):
            data["manual"] = deepcopy(seed_manual)
            changed = True

        relationship = data.get("relationship_memory") if isinstance(data.get("relationship_memory"), dict) else {}
        seed_relationship = seed.get("relationship_memory") if isinstance(seed.get("relationship_memory"), dict) else {}
        if (
            not self._relationship_has_content(relationship)
            and self._relationship_has_content(seed_relationship)
        ):
            data["relationship_memory"] = deepcopy(seed_relationship)
            changed = True

        if changed:
            data["updated_at"] = datetime.now().isoformat()
            self._write(self._with_compat_aliases(data))
        return changed

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
        auto = self._normalize_section(data.get("auto"), include_refresh=True)
        relationship_memory = self._normalize_relationship_memory(data.get("relationship_memory"))
        meta = self._normalize_meta(data.get("meta"))
        meta["confidence_notes"] = []
        meta["contradictions"] = []

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
            elif category in {"dislikes"}:
                self._append_unique(auto["dislikes"], value)
            elif category in {"important_people"}:
                self._append_unique(auto["important_people"], value)
            else:
                auto.setdefault("facts", {})[key] = value
            if confidence < 0.85:
                self._append_unique(meta["confidence_notes"], f"{key}: {value}（置信度 {confidence:.2f}，使用时保持弹性）")

        if relationship:
            label = str(relationship.get("relationship_label") or "").strip()
            narrative = str(relationship.get("relationship_narrative") or "").strip()
            posture = str(relationship.get("current_posture") or "").strip()
            guidance = str(relationship.get("interaction_guidance") or "").strip()
            if narrative:
                self._append_unique(relationship_memory["what_user_seems_to_need_from_bot"], narrative)
            if posture:
                self._append_unique(relationship_memory["what_user_seems_to_need_from_bot"], posture)
            if guidance:
                self._append_unique(relationship_memory["repair_preferences"], guidance)
            if label:
                self._append_unique(relationship_memory["what_user_seems_to_need_from_bot"], f"当前关系标签：{label}")
            if _float(relationship.get("tension_score"), 0) >= 45:
                self._append_unique(relationship_memory["things_that_created_tension"], "关系状态显示近期存在紧张，需要先修复感受再推进话题。")
                self._append_unique(relationship_memory["repair_preferences"], "关系紧张时先放慢、承认感受、少解释。")
            if _float(relationship.get("trust_score"), 0) > 45 or _float(relationship.get("intimacy_score"), 0) > 35:
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

        interaction_style = self._normalize_interaction_style(manual.get("interaction_style"))
        if any(interaction_style.values()):
            lines.append("用户手动设定的互动风格：")
            lines.extend(self._format_interaction_style(interaction_style))

        for key, title in [
            ("preferences", "用户手动设定的偏好"),
            ("dislikes", "用户手动设定的不喜欢/避开的事"),
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

        for key, title in [
            ("personality_observations", "用户手动设定的性格观察"),
            ("emotional_patterns", "用户手动设定的情绪模式"),
            ("stressors", "用户手动设定的压力源"),
            ("comfort_strategies", "用户手动设定的有效陪伴方式"),
            ("attachment_and_distance", "用户手动设定的亲近与距离模式"),
            ("values_and_principles", "用户手动设定的价值观和原则"),
            ("life_context", "用户手动设定的生活背景"),
            ("goals_and_projects", "用户手动设定的目标和项目"),
            ("routines", "用户手动设定的作息和习惯"),
            ("recent_changes", "用户手动设定的近期变化"),
        ]:
            items = self._clean_list(manual.get(key))
            if items:
                lines.append(f"{title}：")
                lines.extend([f"  - {item}" for item in items])

        manual_extra = self._format_custom_fields(
            manual,
            known_keys=self._section_prompt_keys(),
            title="用户手动补充的自定义字段",
        )
        if manual_extra:
            lines.extend(manual_extra)

        top_extra = self._format_custom_fields(
            data,
            known_keys=self._top_level_prompt_keys(),
            title="用户理解文件中的自定义字段",
        )
        if top_extra:
            lines.extend(top_extra)

        auto_summary = str(auto.get("profile_summary") or auto.get("summary") or "").strip()
        if auto_summary:
            lines.append(f"Bot 在相处中逐渐形成的理解：{auto_summary}")

        auto_identity = self._clean_dict(auto.get("identity"))
        if auto_identity:
            lines.append("自动补充的身份信息：")
            lines.extend([f"  - {k}: {v}" for k, v in auto_identity.items()])

        auto_interaction = self._normalize_interaction_style(auto.get("interaction_style"))
        if any(auto_interaction.values()):
            lines.append("自动学习到的互动风格：")
            lines.extend(self._format_interaction_style(auto_interaction))

        auto_facts = self._clean_dict(auto.get("facts"))
        if auto_facts:
            lines.append("从日常对话自动补充的事实：")
            lines.extend([f"  - {k}: {v}" for k, v in auto_facts.items()])

        for key, title in [
            ("preferences", "自动补充的用户偏好"),
            ("dislikes", "自动补充的不喜欢/避开的事"),
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
            ("life_context", "自动补充的生活背景"),
            ("goals_and_projects", "目标和项目"),
            ("routines", "作息和习惯"),
            ("recent_changes", "近期变化"),
        ]:
            items = self._clean_list(auto.get(key))
            if items:
                lines.append(f"{title}：")
                lines.extend([f"  - {item}" for item in items])

        auto_extra = self._format_custom_fields(
            auto,
            known_keys=self._section_prompt_keys() | {"last_refresh_at"},
            title="自动理解中的自定义字段",
        )
        if auto_extra:
            lines.extend(auto_extra)

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
        normalized["layered"] = self._build_layered_projection(normalized)
        return self._with_compat_aliases(normalized)

    def _normalize_section(self, value: Any, include_refresh: bool = False) -> dict[str, Any]:
        section = self._empty_section(include_refresh=include_refresh)
        if isinstance(value, dict):
            section["summary"] = str(value.get("summary") or "")
            section["profile_summary"] = str(value.get("profile_summary") or value.get("summary") or "")
            section["identity"] = self._clean_dict(value.get("identity"))
            section["facts"] = self._clean_dict(value.get("facts"))
            section["interaction_style"] = self._normalize_interaction_style(value.get("interaction_style"))
            for key in (*self.SECTIONS, "relationship_expectations", "notes", *self.AUTO_DEEP_SECTIONS):
                section[key] = self._clean_list(value.get(key))
            for key, raw in value.items():
                if key not in section and (include_refresh or key != "last_refresh_at"):
                    section[key] = self._normalize_custom_value(raw)
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
            "dislikes": [],
            "communication_style": [],
            "boundaries": [],
            "relationship_expectations": [],
            "interaction_style": {
                "preferred_reply_length": "",
                "accepted_humor": [],
                "disliked_phrases": [],
                "natural_openings": [],
                "avoid_patterns": [],
            },
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

    def _build_layered_projection(self, data: dict[str, Any]) -> dict[str, Any]:
        manual = data.get("manual") if isinstance(data.get("manual"), dict) else self._empty_section()
        auto = data.get("auto") if isinstance(data.get("auto"), dict) else self._empty_section(include_refresh=True)
        relationship = self._normalize_relationship_memory(data.get("relationship_memory"))

        core = {
            "summary": self._trim_layer_text(manual.get("summary") or auto.get("profile_summary") or "", 360),
            "identity": self._layer_dict(manual.get("identity"), auto.get("identity"), limit=8),
            "facts": self._layer_dict(manual.get("facts"), auto.get("facts"), limit=10),
            "preferences": self._layer_list(manual.get("preferences"), auto.get("preferences"), limit=8),
            "dislikes": self._layer_list(manual.get("dislikes"), auto.get("dislikes"), limit=8),
            "communication_style": self._layer_list(manual.get("communication_style"), auto.get("communication_style"), limit=8),
            "boundaries": self._layer_list(manual.get("boundaries"), auto.get("boundaries"), limit=8),
            "relationship_expectations": self._layer_list(manual.get("relationship_expectations"), [], limit=6),
        }
        current = {
            "current_context": self._layer_list(manual.get("current_context"), auto.get("current_context"), limit=8),
            "open_threads": self._layer_list(manual.get("open_threads"), auto.get("open_threads"), limit=8),
            "goals_and_projects": self._layer_list(manual.get("goals_and_projects"), auto.get("goals_and_projects"), limit=8),
            "recent_changes": self._layer_list(manual.get("recent_changes"), auto.get("recent_changes"), limit=8),
            "stressors": self._layer_list(manual.get("stressors"), auto.get("stressors"), limit=8),
            "routines": self._layer_list(manual.get("routines"), auto.get("routines"), limit=6),
        }
        deep_relationship = {
            key: self._layer_list(relationship.get(key), [], limit=8)
            for key in self.RELATIONSHIP_SECTIONS
        }
        deep = {
            "personality_observations": self._layer_list(manual.get("personality_observations"), auto.get("personality_observations"), limit=6),
            "emotional_patterns": self._layer_list(manual.get("emotional_patterns"), auto.get("emotional_patterns"), limit=8),
            "comfort_strategies": self._layer_list(manual.get("comfort_strategies"), auto.get("comfort_strategies"), limit=8),
            "attachment_and_distance": self._layer_list(manual.get("attachment_and_distance"), auto.get("attachment_and_distance"), limit=6),
            "values_and_principles": self._layer_list(manual.get("values_and_principles"), auto.get("values_and_principles"), limit=6),
            "life_context": self._layer_list(manual.get("life_context"), auto.get("life_context"), limit=6),
            "relationship_memory": deep_relationship,
        }
        sensitive = self._build_sensitive_projection(
            {
                "manual": manual,
                "auto": auto,
                "relationship_memory": relationship,
                "core": core,
                "current": current,
                "deep": deep,
            }
        )
        return {
            "core": core,
            "current": current,
            "deep": deep,
            "sensitive": sensitive,
            "generated_at": datetime.now().isoformat(),
        }

    def _layer_dict(self, manual_value: Any, auto_value: Any, *, limit: int) -> dict[str, str]:
        result = {}
        for source in (self._clean_dict(manual_value), self._clean_dict(auto_value)):
            for key, value in source.items():
                if key not in result:
                    result[key] = self._trim_layer_text(value, 180)
        return dict(list(result.items())[:limit])

    def _layer_list(self, manual_value: Any, auto_value: Any, *, limit: int) -> list[str]:
        items: list[str] = []
        for source in (self._clean_list(auto_value), self._clean_list(manual_value)):
            for item in source:
                clean = self._trim_layer_text(item, 220)
                if clean and clean not in items:
                    items.append(clean)
        return items[-limit:]

    def _trim_layer_text(self, value: Any, limit: int) -> str:
        text = " ".join(str(value or "").split())
        if len(text) > limit:
            return text[: max(0, limit - 3)].rstrip() + "..."
        return text

    def _build_sensitive_projection(self, layered_source: dict[str, Any]) -> dict[str, list[str]]:
        topics: list[str] = []
        guidance: list[str] = []
        source_keys: list[str] = []
        for path, value in _walk_values(layered_source):
            text = str(value or "")
            matched = [keyword for keyword in _SENSITIVE_KEYWORDS if keyword in text]
            if not matched:
                continue
            for keyword in matched:
                if keyword not in topics:
                    topics.append(keyword)
            source_key = ".".join(path)
            if source_key not in source_keys:
                source_keys.append(source_key)
        if topics:
            guidance.append("涉及身体、创伤、家庭、前任或隐私的话题，只在用户主动提起或高度相关时使用。")
            guidance.append("不要直接复述敏感事实；先确认用户是否愿意继续，并保持模糊、轻放。")
        return {
            "topics": topics[:12],
            "guidance": guidance,
            "source_keys": source_keys[:12],
        }

    def _normalize_meta(self, value: Any) -> dict[str, Any]:
        result = self._empty_meta()
        if isinstance(value, dict):
            result["confidence_notes"] = self._clean_list(value.get("confidence_notes"))
            result["contradictions"] = self._clean_list(value.get("contradictions"))
            result["last_reflection_at"] = value.get("last_reflection_at")
        return result

    def _normalize_custom_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                clean_key = str(key).strip()
                normalized = self._normalize_custom_value(item)
                if clean_key and self._custom_has_value(normalized):
                    result[clean_key] = normalized
            return result
        if isinstance(value, list):
            result = []
            for item in value:
                normalized = self._normalize_custom_value(item)
                if self._custom_has_value(normalized):
                    result.append(normalized)
            return result
        if isinstance(value, str):
            return self._trim(value.strip())
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        return self._trim(str(value).strip())

    def _custom_has_value(self, value: Any) -> bool:
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, dict):
            return any(self._custom_has_value(item) for item in value.values())
        if isinstance(value, list):
            return any(self._custom_has_value(item) for item in value)
        return value is not None

    def _section_has_content(self, section: Any) -> bool:
        if not isinstance(section, dict):
            return False
        if str(section.get("summary") or section.get("profile_summary") or "").strip():
            return True
        if self._clean_dict(section.get("identity")) or self._clean_dict(section.get("facts")):
            return True
        interaction = self._normalize_interaction_style(section.get("interaction_style"))
        if str(interaction.get("preferred_reply_length") or "").strip():
            return True
        for key in ("accepted_humor", "disliked_phrases", "natural_openings", "avoid_patterns"):
            if interaction.get(key):
                return True
        for key in (*self.SECTIONS, "relationship_expectations", "notes", *self.AUTO_DEEP_SECTIONS):
            if self._clean_list(section.get(key)):
                return True
        known = {
            "summary",
            "profile_summary",
            "identity",
            "facts",
            "preferences",
            "dislikes",
            "communication_style",
            "boundaries",
            "relationship_expectations",
            "interaction_style",
            "important_people",
            "current_context",
            "open_threads",
            "notes",
            *self.AUTO_DEEP_SECTIONS,
            "last_refresh_at",
        }
        if any(self._custom_has_value(value) for key, value in section.items() if key not in known):
            return True
        return False

    def _relationship_has_content(self, relationship: Any) -> bool:
        if not isinstance(relationship, dict):
            return False
        return any(self._clean_list(relationship.get(key)) for key in self.RELATIONSHIP_SECTIONS)

    def _normalize_interaction_style(self, value: Any) -> dict[str, Any]:
        result = {
            "preferred_reply_length": "",
            "accepted_humor": [],
            "disliked_phrases": [],
            "natural_openings": [],
            "avoid_patterns": [],
        }
        if isinstance(value, dict):
            result["preferred_reply_length"] = str(value.get("preferred_reply_length") or "")
            for key in ("accepted_humor", "disliked_phrases", "natural_openings", "avoid_patterns"):
                result[key] = self._clean_list(value.get(key))
        return result

    def _format_interaction_style(self, style: dict[str, Any]) -> list[str]:
        lines: list[str] = []
        if style.get("preferred_reply_length"):
            lines.append(f"  - 回复长度：{style['preferred_reply_length']}")
        mapping = [
            ("accepted_humor", "可接受的幽默"),
            ("disliked_phrases", "不喜欢的表达"),
            ("natural_openings", "自然开场"),
            ("avoid_patterns", "避免模式"),
        ]
        for key, title in mapping:
            values = style.get(key)
            if isinstance(values, list) and values:
                lines.append(f"  - {title}：" + "；".join(str(v) for v in values[:5]))
        return lines

    def _section_prompt_keys(self) -> set[str]:
        return {
            "summary",
            "profile_summary",
            "identity",
            "facts",
            "preferences",
            "dislikes",
            "communication_style",
            "boundaries",
            "relationship_expectations",
            "interaction_style",
            "important_people",
            "current_context",
            "open_threads",
            "notes",
            *self.AUTO_DEEP_SECTIONS,
        }

    def _top_level_prompt_keys(self) -> set[str]:
        return {
            "version",
            "updated_at",
            "manual",
            "auto",
            "relationship_memory",
            "layered",
            "meta",
            "summary",
            "facts",
            "preferences",
            "dislikes",
            "communication_style",
            "boundaries",
            "important_people",
            "current_context",
            "open_threads",
            "auto_facts",
        }

    def _format_custom_fields(self, container: Any, *, known_keys: set[str], title: str) -> list[str]:
        if not isinstance(container, dict):
            return []
        lines = [f"{title}："]
        for key, value in container.items():
            clean_key = str(key).strip()
            if not clean_key or clean_key in known_keys or not self._custom_has_value(value):
                continue
            rendered = self._render_custom_value(value)
            if rendered:
                lines.append(f"  - {clean_key}: {rendered}")
        return lines if len(lines) > 1 else []

    def _render_custom_value(self, value: Any, max_chars: int = 800) -> str:
        if isinstance(value, str):
            rendered = value.strip()
        elif isinstance(value, (int, float, bool)):
            rendered = str(value)
        elif isinstance(value, list):
            parts = [
                self._render_custom_value(item, max_chars=240)
                for item in value
                if self._custom_has_value(item)
            ]
            rendered = "；".join(part for part in parts if part)
        elif isinstance(value, dict):
            rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        else:
            rendered = str(value).strip()

        if len(rendered) > max_chars:
            return rendered[: max_chars - 3] + "..."
        return rendered

    def _with_compat_aliases(self, data: dict[str, Any]) -> dict[str, Any]:
        data = deepcopy(data)
        manual = data.get("manual") if isinstance(data.get("manual"), dict) else self._empty_section()
        auto = data.get("auto") if isinstance(data.get("auto"), dict) else self._empty_section(include_refresh=True)
        data["summary"] = manual.get("summary", "")
        data["facts"] = deepcopy(manual.get("facts", {}))
        for section in self.SECTIONS:
            data[section] = list(manual.get(section, []))
        auto_facts = deepcopy(auto.get("facts", {}))
        for key in list(auto_facts.keys()):
            if key in self.INTERNAL_KEYS:
                auto_facts.pop(key, None)
        data["auto_facts"] = auto_facts
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


_SENSITIVE_KEYWORDS = (
    "身体",
    "隐私",
    "疾病",
    "病",
    "创伤",
    "自伤",
    "自杀",
    "霸凌",
    "骚扰",
    "前任",
    "前女友",
    "前男友",
    "家庭暴力",
    "父亲",
    "母亲",
    "抑郁",
    "诊断",
    "药",
)


def _walk_values(value: Any, path: tuple[str, ...] = ()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk_values(item, (*path, str(key)))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            yield from _walk_values(item, (*path, str(idx)))
    else:
        yield path, value
