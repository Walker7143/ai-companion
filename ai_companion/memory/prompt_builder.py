"""Build memory prompt suffixes from retrieved memory."""

from __future__ import annotations

from .retriever import RetrievedMemory


class MemoryPromptBuilder:
    """Convert retrieved memory into a compact system prompt suffix."""

    def __init__(self, max_chars: int = 4400):
        self.max_chars = max_chars

    def build(self, retrieved: RetrievedMemory) -> str:
        parts: list[str] = []

        understanding_text = self._format_understanding(retrieved)
        if understanding_text:
            parts.append(
                "【你对用户的理解】\n"
                + understanding_text
                + "\n使用方式：把这些当作相处背景，而不是答案清单。"
                + "回复时优先照顾用户当下这句话；只有在自然、有帮助的时候，才顺手提到相关细节。"
                + "不要生硬地说“我记得你的资料里写着”。"
            )

        relationship_text = self._format_relationship(retrieved)
        if relationship_text:
            parts.append(
                "【关系状态】\n"
                + relationship_text
                + "\n使用方式：这只影响语气和分寸，不要直接向用户报数值。"
            )

        fact_lines = self._format_semantic_items(retrieved)
        if fact_lines:
            parts.append(
                "【语义记忆补充】\n"
                + "\n".join(fact_lines)
                + "\n使用方式：这些是和当前意图相关的零散事实，只在自然、有帮助时使用。"
            )

        if retrieved.episodic_recall:
            moment_lines = [f"  - {m.get('summary', '')[:120]}" for m in retrieved.episodic_recall if m.get("summary")]
            if moment_lines:
                parts.append(
                    "【可能相关的共同经历】\n"
                    + "\n".join(moment_lines)
                    + "\n使用方式：这些经历只在能让回应更贴近用户时引用；不要为了展示记忆而引用。"
                )

        suffix = "\n".join(parts)
        if len(suffix) > self.max_chars:
            return suffix[: self.max_chars - 3] + "..."
        return suffix

    def _format_understanding(self, retrieved: RetrievedMemory) -> str:
        data = retrieved.user_understanding or {}
        lines: list[str] = []

        # v2 shape: manual/auto. v1 shape is also supported below.
        manual = data.get("manual") if isinstance(data.get("manual"), dict) else {}
        auto = data.get("auto") if isinstance(data.get("auto"), dict) else {}
        if not manual and not auto:
            manual = data
            auto = {"facts": data.get("auto_facts", {})} if isinstance(data, dict) else {}

        summary = str(manual.get("summary") or "").strip()
        if summary:
            lines.append(f"用户手动设定的整体理解：{summary}")

        manual_facts = _clean_dict(manual.get("facts"))
        if manual_facts:
            lines.append("用户手动设定的事实：")
            lines.extend([f"  - {k}: {v}" for k, v in manual_facts.items()])

        for key, title in [
            ("preferences", "用户手动设定的偏好"),
            ("communication_style", "用户手动设定的沟通方式"),
            ("boundaries", "用户手动设定的边界"),
            ("relationship_expectations", "用户手动设定的关系期待"),
            ("important_people", "用户手动设定的重要关系"),
            ("current_context", "用户手动设定的当前状态"),
            ("open_threads", "用户手动设定的后续话题"),
            ("notes", "用户手动补充说明"),
        ]:
            items = _clean_list(manual.get(key))
            if items:
                lines.append(f"{title}：")
                lines.extend([f"  - {item}" for item in items])

        auto_summary = str(auto.get("profile_summary") or auto.get("summary") or "").strip()
        if auto_summary:
            lines.append(f"Bot 在相处中逐渐形成的理解：{auto_summary}")

        auto_facts = _clean_dict(auto.get("facts"))
        if auto_facts:
            lines.append("从日常对话自动补充的事实：")
            lines.extend([f"  - {k}: {v}" for k, v in auto_facts.items()])

        for key, title in [
            ("preferences", "自动补充的偏好"),
            ("communication_style", "自动补充的沟通方式"),
            ("boundaries", "自动补充的边界"),
            ("important_people", "自动补充的重要关系"),
            ("current_context", "自动补充的当前状态"),
            ("open_threads", "自动补充的后续话题"),
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
            items = _clean_list(auto.get(key))
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
            items = _clean_list(relationship_memory.get(key))
            if items:
                lines.append(f"{title}：")
                lines.extend([f"  - {item}" for item in items])

        return "\n".join(lines)

    def _format_relationship(self, retrieved: RetrievedMemory) -> str:
        state = retrieved.relationship_state or {}
        lines: list[str] = []
        label = state.get("relationship_label") or state.get("relationship_level")
        if label:
            lines.append(f"  - 关系：{label}")
        tension = _float(state.get("tension_score"))
        if tension >= 3:
            lines.append("  - 当前关系可能有紧张感，回复需要更克制、先修复情绪。")
        open_threads = state.get("open_emotional_threads") or []
        if isinstance(open_threads, list) and open_threads:
            lines.append("  - 未完成情绪话题：" + "；".join(str(item) for item in open_threads[:3]))
        return "\n".join(lines)

    def _format_semantic_items(self, retrieved: RetrievedMemory) -> list[str]:
        known_keys = set()
        known_values = set()
        understanding = retrieved.user_understanding
        if isinstance(understanding, dict):
            manual = understanding.get("manual") if isinstance(understanding.get("manual"), dict) else {}
            auto = understanding.get("auto") if isinstance(understanding.get("auto"), dict) else {}
            for section in (manual, auto):
                facts = _clean_dict(section.get("facts"))
                known_keys.update(facts.keys())
                known_values.update(facts.values())
                for list_key in (
                    "preferences", "communication_style", "boundaries", "important_people",
                    "current_context", "open_threads", "emotional_patterns", "stressors",
                    "comfort_strategies", "attachment_and_distance", "values_and_principles",
                    "life_context", "goals_and_projects", "routines", "recent_changes",
                ):
                    known_values.update(_clean_list(section.get(list_key)))
            relationship_memory = understanding.get("relationship_memory") if isinstance(understanding.get("relationship_memory"), dict) else {}
            for list_key in (
                "how_user_treats_bot", "what_user_seems_to_need_from_bot",
                "things_that_brought_them_closer", "things_that_created_tension",
                "repair_preferences",
            ):
                known_values.update(_clean_list(relationship_memory.get(list_key)))
            known_keys.update(_clean_dict(understanding.get("facts")).keys())
            legacy_auto = _clean_dict(understanding.get("auto_facts"))
            known_keys.update(legacy_auto.keys())
            known_values.update(legacy_auto.values())
        lines = []
        for item in retrieved.semantic_items:
            key = item.get("key")
            value = item.get("value")
            if not key or not value or key in known_keys or value in known_values:
                continue
            category = item.get("category") or "general"
            lines.append(f"  - [{category}] {key}: {value}")
        return lines


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clean_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, str] = {}
    for key, val in value.items():
        k = str(key).strip()
        v = str(val).strip()
        if k and v:
            result[k] = v
    return result


def _clean_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
