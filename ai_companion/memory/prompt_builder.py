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

        daily_text = self._format_daily_context(retrieved)
        if daily_text:
            parts.append(
                "【最近日常连续性】\n"
                + daily_text
                + "\n使用方式：这是用户最近十天内跨通道与你相处的短期背景。"
                + "当前会话优先；只在自然、必要时参考，不要逐字复述，也不要表现得像在翻日志。"
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

        manual_identity = _clean_dict(manual.get("identity"))
        if manual_identity:
            lines.append("用户手动设定的身份信息：")
            lines.extend([f"  - {k}: {v}" for k, v in manual_identity.items()])

        manual_facts = _clean_dict(manual.get("facts"))
        if manual_facts:
            lines.append("用户手动设定的事实：")
            lines.extend([f"  - {k}: {v}" for k, v in manual_facts.items()])

        manual_interaction = _clean_interaction_style(manual.get("interaction_style"))
        if any(manual_interaction.values()):
            lines.append("用户手动设定的互动风格：")
            lines.extend(_format_interaction_style(manual_interaction))

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
            items = _clean_list(manual.get(key))
            if items:
                lines.append(f"{title}：")
                lines.extend([f"  - {item}" for item in items])

        manual_extra = _format_extra_fields(
            manual,
            known_keys=_SECTION_KEYS,
            title="用户手动补充的自定义字段",
        )
        if manual_extra:
            lines.extend(manual_extra)

        top_extra = _format_extra_fields(
            data,
            known_keys=_TOP_LEVEL_KEYS,
            title="用户理解文件中的自定义字段",
        )
        if top_extra:
            lines.extend(top_extra)

        auto_summary = str(auto.get("profile_summary") or auto.get("summary") or "").strip()
        if auto_summary:
            lines.append(f"Bot 在相处中逐渐形成的理解：{auto_summary}")

        auto_identity = _clean_dict(auto.get("identity"))
        if auto_identity:
            lines.append("自动补充的身份信息：")
            lines.extend([f"  - {k}: {v}" for k, v in auto_identity.items()])

        auto_interaction = _clean_interaction_style(auto.get("interaction_style"))
        if any(auto_interaction.values()):
            lines.append("自动学习到的互动风格：")
            lines.extend(_format_interaction_style(auto_interaction))

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

        auto_extra = _format_extra_fields(
            auto,
            known_keys=_SECTION_KEYS | {"last_refresh_at"},
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
            items = _clean_list(relationship_memory.get(key))
            if items:
                lines.append(f"{title}：")
                lines.extend([f"  - {item}" for item in items])

        return "\n".join(lines)

    def _format_daily_context(self, retrieved: RetrievedMemory) -> str:
        data = retrieved.daily_context or {}
        summaries = data.get("summaries") if isinstance(data.get("summaries"), list) else []
        messages = data.get("recent_messages") if isinstance(data.get("recent_messages"), list) else []
        if not summaries and not messages:
            return ""

        lines: list[str] = []
        today = data.get("today")
        today_summary = None
        older_summaries = []
        for item in summaries:
            if not isinstance(item, dict):
                continue
            if item.get("local_date") == today:
                today_summary = item
            else:
                older_summaries.append(item)

        if today_summary and today_summary.get("summary"):
            lines.append(f"  - 今天：{str(today_summary.get('summary'))[:240]}")
            for key, title in [
                ("open_threads", "今天未完话题"),
                ("commitments", "今天承诺/待办"),
                ("mood", "今天情绪线索"),
            ]:
                values = _clean_list(today_summary.get(key))
                if values:
                    lines.append(f"    {title}：" + "；".join(values[:3]))

        if older_summaries:
            lines.append("  - 最近几天：")
            for item in older_summaries[:5]:
                date = item.get("local_date") or "未知日期"
                summary = str(item.get("summary") or "").strip()
                if summary:
                    lines.append(f"    - {date}: {summary[:180]}")

        if messages:
            lines.append("  - 其他通道最近几条：")
            for item in messages[-8:]:
                if not isinstance(item, dict):
                    continue
                platform = item.get("platform") or "unknown"
                role = "用户" if item.get("role") == "user" else "助手"
                content = str(item.get("content") or "").strip()
                if content:
                    lines.append(f"    - [{platform}] {role}: {content[:120]}")

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
                identity = _clean_dict(section.get("identity"))
                known_keys.update(identity.keys())
                known_values.update(identity.values())
                facts = _clean_dict(section.get("facts"))
                known_keys.update(facts.keys())
                known_values.update(facts.values())
                for list_key in (
                    "preferences", "communication_style", "boundaries", "important_people",
                    "relationship_expectations", "current_context", "open_threads", "notes",
                    "emotional_patterns", "stressors",
                    "comfort_strategies", "attachment_and_distance", "values_and_principles",
                    "life_context", "goals_and_projects", "routines", "recent_changes",
                ):
                    known_values.update(_clean_list(section.get(list_key)))
                for extra_key, extra_value in _extra_items(section, _SECTION_KEYS):
                    known_keys.add(extra_key)
                    known_values.update(_value_tokens(extra_value))
                interaction = _clean_interaction_style(section.get("interaction_style"))
                for key, value in interaction.items():
                    if isinstance(value, list):
                        known_values.update(value)
                    elif value:
                        known_values.add(str(value))
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
            for extra_key, extra_value in _extra_items(understanding, _TOP_LEVEL_KEYS):
                known_keys.add(extra_key)
                known_values.update(_value_tokens(extra_value))
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


def _clean_interaction_style(value: object) -> dict[str, object]:
    result: dict[str, object] = {
        "preferred_reply_length": "",
        "accepted_humor": [],
        "disliked_phrases": [],
        "natural_openings": [],
        "avoid_patterns": [],
    }
    if isinstance(value, dict):
        result["preferred_reply_length"] = str(value.get("preferred_reply_length") or "").strip()
        for key in ("accepted_humor", "disliked_phrases", "natural_openings", "avoid_patterns"):
            result[key] = _clean_list(value.get(key))
    return result


def _format_interaction_style(style: dict[str, object]) -> list[str]:
    lines: list[str] = []
    if style.get("preferred_reply_length"):
        lines.append(f"  - 回复长度：{style['preferred_reply_length']}")
    for key, title in [
        ("accepted_humor", "可接受的幽默"),
        ("disliked_phrases", "不喜欢的表达"),
        ("natural_openings", "自然开场"),
        ("avoid_patterns", "避免模式"),
    ]:
        values = style.get(key)
        if isinstance(values, list) and values:
            lines.append(f"  - {title}：" + "；".join(str(v) for v in values[:5]))
    return lines


_SECTION_KEYS = {
    "summary",
    "profile_summary",
    "identity",
    "facts",
    "preferences",
    "communication_style",
    "boundaries",
    "relationship_expectations",
    "interaction_style",
    "important_people",
    "current_context",
    "open_threads",
    "notes",
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
}

_TOP_LEVEL_KEYS = {
    "version",
    "updated_at",
    "manual",
    "auto",
    "relationship_memory",
    "meta",
    "summary",
    "facts",
    "preferences",
    "communication_style",
    "boundaries",
    "important_people",
    "current_context",
    "open_threads",
    "auto_facts",
}


def _extra_items(container: object, known_keys: set[str]):
    if not isinstance(container, dict):
        return []
    return [
        (str(key).strip(), value)
        for key, value in container.items()
        if str(key).strip() and str(key).strip() not in known_keys and _has_prompt_value(value)
    ]


def _format_extra_fields(container: object, *, known_keys: set[str], title: str) -> list[str]:
    items = _extra_items(container, known_keys)
    if not items:
        return []
    lines = [f"{title}："]
    for key, value in items:
        rendered = _render_value(value)
        if rendered:
            lines.append(f"  - {key}: {rendered}")
    return lines if len(lines) > 1 else []


def _has_prompt_value(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_prompt_value(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_prompt_value(v) for v in value)
    return value is not None


def _render_value(value: object, max_chars: int = 800) -> str:
    import json

    if isinstance(value, str):
        rendered = value.strip()
    elif isinstance(value, (int, float, bool)):
        rendered = str(value)
    elif isinstance(value, list):
        parts = [_render_value(item, max_chars=240) for item in value if _has_prompt_value(item)]
        rendered = "；".join(part for part in parts if part)
    elif isinstance(value, dict):
        rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        rendered = str(value).strip()

    if len(rendered) > max_chars:
        return rendered[: max_chars - 3] + "..."
    return rendered


def _value_tokens(value: object) -> set[str]:
    if isinstance(value, dict):
        tokens = set()
        for key, val in value.items():
            key = str(key).strip()
            if key:
                tokens.add(key)
            tokens.update(_value_tokens(val))
        return tokens
    if isinstance(value, list):
        tokens = set()
        for item in value:
            tokens.update(_value_tokens(item))
        return tokens
    rendered = _render_value(value)
    return {rendered} if rendered else set()
