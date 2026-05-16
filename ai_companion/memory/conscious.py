"""Conscious working context for human-like memory activation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .retriever import RetrievedMemory


@dataclass
class ActiveMemory:
    """A scored memory candidate and how it should surface this turn."""

    text: str
    source: str
    score: float
    expression_mode: str
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConsciousContext:
    """Small, explicit set of memories that should feel active this turn."""

    current_focus: str = ""
    emotional_read: str = ""
    relationship_posture: str = ""
    active_memories: list[str] = field(default_factory=list)
    active_memory_details: list[dict[str, Any]] = field(default_factory=list)
    avoid: list[str] = field(default_factory=list)
    recall_style: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def render(self, *, max_chars: int = 1600) -> str:
        lines: list[str] = []
        if self.current_focus:
            lines.append(f"- 当前焦点：{self.current_focus}")
        if self.emotional_read:
            lines.append(f"- 情绪读取：{self.emotional_read}")
        if self.relationship_posture:
            lines.append(f"- 关系姿态：{self.relationship_posture}")
        if self.active_memory_details:
            lines.append("- 此刻被唤起的记忆：")
            for item in self.active_memory_details[:5]:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                mode = _mode_label(str(item.get("expression_mode") or "silent_influence"))
                score = item.get("score")
                score_text = f"，激活 {score:.2f}" if isinstance(score, (int, float)) else ""
                lines.append(f"  - {text}（使用：{mode}{score_text}）")
        elif self.active_memories:
            lines.append("- 此刻被唤起的记忆：")
            lines.extend(f"  - {item}" for item in self.active_memories[:5])
        if self.avoid:
            lines.append("- 本轮避免：")
            lines.extend(f"  - {item}" for item in self.avoid[:5])
        if self.recall_style:
            lines.append(f"- 记忆使用方式：{self.recall_style}")
        rendered = "\n".join(lines)
        if len(rendered) > max_chars:
            return rendered[: max_chars - 3].rstrip() + "..."
        return rendered


class ConsciousContextBuilder:
    """Build a compact awareness layer from retrieved memory."""

    SENSITIVE_ALLOWED_INTENTS = {"recall_past", "relationship_repair", "emotional_support"}
    EXPLICIT_RECALL_INTENTS = {"recall_past", "relationship_repair", "emotional_support"}

    EMOTION_LABELS = {
        "emotional_support": "用户可能需要先被接住情绪，再谈建议。",
        "relationship_repair": "关系里可能有紧张或修复需求，先放慢、少反驳。",
        "recall_past": "用户在召唤共同经历，适合轻轻承接具体记忆。",
        "planning": "用户在推进安排或未完事项，适合把记忆转成下一步。",
        "task_request": "用户主要想把事情办清楚，记忆只作偏好和边界参考。",
        "casual_chat": "日常互动，优先回应当下，不刻意展示记忆。",
    }

    FOCUS_LABELS = {
        "emotional_support": "情绪陪伴",
        "relationship_repair": "关系修复",
        "recall_past": "共同回忆",
        "planning": "计划和未完事项",
        "task_request": "任务请求",
        "casual_chat": "日常闲聊",
        "proactive_generation": "主动延续关系",
    }
    SELF_MEMORY_KIND_LABELS = {
        "idle_reminder": "我主动问候过用户",
        "deferred_reply": "我承诺晚点回复并回来履约",
        "topic_continuation": "我想接上之前没聊完的话题",
        "emotion_followup": "我主动跟进用户状态",
        "life_event": "我主动分享过自己的生活事件",
    }

    def build(self, retrieved: RetrievedMemory, current_input: str) -> ConsciousContext:
        intent = retrieved.intent or "casual_chat"
        active_memory_details = self._active_memory_details(retrieved, intent=intent, current_input=current_input)
        active_memories = [item.text for item in active_memory_details]
        return ConsciousContext(
            current_focus=self._current_focus(intent, current_input),
            emotional_read=self.EMOTION_LABELS.get(intent, self.EMOTION_LABELS["casual_chat"]),
            relationship_posture=self._relationship_posture(retrieved.relationship_state),
            active_memories=active_memories,
            active_memory_details=[item.to_dict() for item in active_memory_details],
            avoid=self._avoid_rules(retrieved, intent=intent),
            recall_style=self._recall_style(intent, active_memories),
        )

    def _current_focus(self, intent: str, current_input: str) -> str:
        label = self.FOCUS_LABELS.get(intent, self.FOCUS_LABELS["casual_chat"])
        text = " ".join(str(current_input or "").split())
        if len(text) > 48:
            text = text[:45].rstrip() + "..."
        return f"{label}：{text}" if text else label

    def _relationship_posture(self, state: dict[str, Any]) -> str:
        if not state:
            return "关系状态未知，保持自然、克制、别过度亲密。"
        narrative = str(state.get("relationship_narrative") or "").strip()
        posture = str(state.get("current_posture") or "").strip()
        guidance = str(state.get("interaction_guidance") or "").strip()
        if narrative or posture or guidance:
            parts = [item for item in [narrative, posture, guidance] if item]
            return "；".join(parts[:3])
        label = state.get("relationship_label") or state.get("relationship_level") or "未标注"
        score = _float(state.get("relationship_score"))
        tension = _float(state.get("tension_score"))
        intimacy = _float(state.get("intimacy_score"))
        if tension >= 45:
            tone = "有紧张感，先修复和安抚。"
        elif intimacy >= 45 or score >= 60:
            tone = "可以熟悉、亲近，但不要为了展示记忆而用力。"
        else:
            tone = "保持轻松和分寸。"
        return f"{label}；{tone}"

    def _active_memory_details(self, retrieved: RetrievedMemory, *, intent: str, current_input: str) -> list[ActiveMemory]:
        candidates: list[ActiveMemory] = []
        for item in retrieved.episodic_recall[:3]:
            summary = str(item.get("summary") or "").strip()
            if summary:
                if self._is_sensitive_episode(item) and intent not in self.SENSITIVE_ALLOWED_INTENTS:
                    continue
                text = self._format_episode_memory(item, intent=intent)
                candidates.append(
                    ActiveMemory(
                        text=text,
                        source="episodic",
                        score=self._activation_score(
                            current_input,
                            text,
                            intent=intent,
                            source="episodic",
                            relationship_effect=str(item.get("relationship_effect") or ""),
                            sensitivity=str(item.get("sensitivity") or "normal"),
                            cue_tags=item.get("cue_tags") if isinstance(item.get("cue_tags"), list) else [],
                        ),
                        expression_mode=self._expression_mode(
                            intent,
                            source="episodic",
                            sensitivity=str(item.get("sensitivity") or "normal"),
                        ),
                        reason="共同经历召回",
                    )
                )

        daily = retrieved.daily_context or {}
        summaries = daily.get("summaries") if isinstance(daily.get("summaries"), list) else []
        for item in summaries[:2]:
            if not isinstance(item, dict):
                continue
            summary = str(item.get("summary") or "").strip()
            date = item.get("local_date") or "最近"
            if summary:
                text = f"{date} 的连续性：{summary[:100]}"
                candidates.append(
                    ActiveMemory(
                        text=text,
                        source="daily",
                        score=self._activation_score(current_input, text, intent=intent, source="daily"),
                        expression_mode=self._expression_mode(intent, source="daily"),
                        reason="近期日常连续性",
                    )
                )

        known_keys, known_values = _known_understanding_items(retrieved.user_understanding)
        for item in retrieved.semantic_items[:4]:
            key = str(item.get("key") or "").strip()
            value = str(item.get("value") or "").strip()
            category = str(item.get("category") or "general")
            if key in known_keys or value in known_values:
                continue
            if key and value:
                text = f"{category}：{key}={value[:80]}"
                candidates.append(
                    ActiveMemory(
                        text=text,
                        source="semantic",
                        score=self._activation_score(current_input, text, intent=intent, source="semantic"),
                        expression_mode=self._expression_mode(intent, source="semantic"),
                        reason="相关语义事实",
                    )
                )

        layered = _layered(retrieved.user_understanding)
        if intent in {"emotional_support", "relationship_repair"}:
            deep = layered.get("deep") if isinstance(layered.get("deep"), dict) else {}
            for item in _list(deep.get("comfort_strategies"))[:2]:
                text = f"有效陪伴方式：{item[:80]}"
                candidates.append(
                    ActiveMemory(
                        text=text,
                        source="understanding.deep",
                        score=self._activation_score(current_input, text, intent=intent, source="understanding.deep"),
                        expression_mode="silent_influence",
                        reason="情绪支持方式",
                    )
                )
            for item in _list(deep.get("emotional_patterns"))[:2]:
                text = f"情绪模式：{item[:80]}"
                candidates.append(
                    ActiveMemory(
                        text=text,
                        source="understanding.deep",
                        score=self._activation_score(current_input, text, intent=intent, source="understanding.deep"),
                        expression_mode="silent_influence",
                        reason="情绪模式",
                    )
                )
        elif intent in {"casual_chat", "task_request", "planning"}:
            current = layered.get("current") if isinstance(layered.get("current"), dict) else {}
            for key, label in [
                ("current_context", "当前状态"),
                ("recent_changes", "近期变化"),
                ("goals_and_projects", "目标和项目"),
                ("routines", "作息和习惯"),
            ]:
                for item in _list(current.get(key)):
                    text = f"{label}：{item[:80]}"
                    score = self._activation_score(
                        current_input,
                        text,
                        intent=intent,
                        source="understanding.current",
                    )
                    if score < 0.38:
                        continue
                    candidates.append(
                        ActiveMemory(
                            text=text,
                            source="understanding.current",
                            score=score,
                            expression_mode=self._expression_mode(intent, source="understanding.current"),
                            reason="当前输入命中用户理解",
                        )
                    )
            for item in _list(current.get("open_threads"))[:1]:
                text = f"未完话题：{item[:80]}"
                candidates.append(
                    ActiveMemory(
                        text=text,
                        source="understanding.current",
                        score=self._activation_score(current_input, text, intent=intent, source="understanding.current"),
                        expression_mode=self._expression_mode(intent, source="understanding.current"),
                        reason="未完话题",
                    )
                )

        relationship = retrieved.relationship_state or {}
        for thread in relationship.get("open_emotional_threads") or []:
            text = str(thread).strip()
            if text:
                memory_text = f"未完成情绪话题：{text[:80]}"
                candidates.append(
                    ActiveMemory(
                        text=memory_text,
                        source="relationship",
                        score=self._activation_score(current_input, memory_text, intent=intent, source="relationship"),
                        expression_mode=self._expression_mode(intent, source="relationship"),
                        reason="关系中未完成情绪话题",
                    )
                )

        for item in self._self_memories(retrieved)[:3]:
            text = item["text"]
            candidates.append(
                ActiveMemory(
                    text=text,
                    source="self_memory",
                    score=self._activation_score(current_input, text, intent=intent, source="self_memory"),
                    expression_mode=self._self_memory_expression_mode(intent, item),
                    reason=item.get("reason", "Bot 自己发起过的消息"),
                )
            )

        limit = 5 if intent in {"recall_past", "relationship_repair", "emotional_support"} else 3
        return _dedupe_active_memories(sorted(candidates, key=lambda item: item.score, reverse=True))[:limit]

    def _avoid_rules(self, retrieved: RetrievedMemory, *, intent: str) -> list[str]:
        rules = [
            "不要生硬说“我记得你的资料里写着”。",
            "不要机械复述用户画像，先回应当下这句话。",
        ]
        if intent == "task_request":
            rules.append("任务型请求优先把事情办清楚，少加入关系回忆。")
        if intent in {"casual_chat", "planning", "task_request"}:
            rules.append("敏感经历和身体隐私只在用户主动提起或高度相关时使用。")
        if any(self._is_sensitive_episode(item) for item in retrieved.episodic_recall):
            if intent not in self.SENSITIVE_ALLOWED_INTENTS:
                rules.append("本轮有敏感经历被召回，但不要主动提起具体内容，只让它影响分寸。")
            else:
                rules.append("提到敏感经历时要模糊、轻放，先确认用户愿不愿意继续。")
        layered = _layered(retrieved.user_understanding)
        sensitive = layered.get("sensitive") if isinstance(layered.get("sensitive"), dict) else {}
        if _list(sensitive.get("topics")):
            for item in _list(sensitive.get("guidance"))[:2]:
                rules.append(item)
        tension = _float((retrieved.relationship_state or {}).get("tension_score"))
        if tension >= 45:
            rules.append("关系紧张时不要调侃压过去，先承认感受。")
        return rules

    def _recall_style(self, intent: str, active_memories: list[str]) -> str:
        if not active_memories:
            return "本轮没有强相关记忆时，只让长期理解影响语气。"
        if intent == "recall_past":
            return "可以自然提起具体记忆，但允许带一点不完全确定的人味。"
        if intent in {"emotional_support", "relationship_repair"}:
            return "记忆主要用来拿捏分寸和安抚方式，不要炫耀记得多。"
        return "只在自然、有帮助时顺手带出一两处细节。"

    def _activation_score(
        self,
        current_input: str,
        text: str,
        *,
        intent: str,
        source: str,
        relationship_effect: str = "",
        sensitivity: str = "normal",
        cue_tags: list[Any] | None = None,
    ) -> float:
        score = 0.2
        overlap = _cue_overlap(current_input, text, cue_tags or [])
        score += min(0.35, overlap * 0.08)
        if source == "episodic":
            score += 0.22 if intent in self.EXPLICIT_RECALL_INTENTS else 0.08
        elif source == "daily":
            score += 0.16 if intent in {"casual_chat", "planning", "proactive_generation"} else 0.10
        elif source == "relationship":
            score += 0.20 if intent in {"relationship_repair", "emotional_support"} else 0.08
        elif source == "self_memory":
            score += 0.24 if intent in {"casual_chat", "planning", "proactive_generation"} else 0.16
        elif source.startswith("understanding"):
            score += 0.14
        elif source == "semantic":
            score += 0.10
        if relationship_effect in {"拉近", "修复", "紧张"}:
            score += 0.12
        if sensitivity == "sensitive":
            score -= 0.25 if intent not in self.SENSITIVE_ALLOWED_INTENTS else 0.05
        if intent == "task_request" and source in {"episodic", "relationship"}:
            score -= 0.18
        return round(max(0.0, min(1.0, score)), 3)

    def _expression_mode(self, intent: str, *, source: str, sensitivity: str = "normal") -> str:
        if sensitivity == "sensitive":
            if intent in self.SENSITIVE_ALLOWED_INTENTS:
                return "ask_before_entering"
            return "avoid"
        if intent == "task_request":
            return "silent_influence"
        if source == "self_memory":
            return "light_reference"
        if intent == "recall_past":
            return "explicit_recall" if source == "episodic" else "light_reference"
        if intent in {"emotional_support", "relationship_repair"}:
            if source in {"relationship", "understanding.deep"} or source.startswith("understanding"):
                return "silent_influence"
            return "light_reference"
        if intent == "planning":
            return "light_reference" if source in {"daily", "understanding.current"} else "silent_influence"
        return "light_reference" if source in {"daily", "understanding.current"} else "silent_influence"

    def _self_memories(self, retrieved: RetrievedMemory) -> list[dict[str, str]]:
        daily = retrieved.daily_context or {}
        items = daily.get("self_memory") if isinstance(daily.get("self_memory"), list) else []
        result: list[dict[str, str]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            kind = str(item.get("kind") or "assistant_initiated")
            label = self.SELF_MEMORY_KIND_LABELS.get(kind, "我主动发起过一条消息")
            date = str(item.get("local_date") or "最近")
            result.append({
                "text": f"{date} 的自传体线索：{label}：“{content[:80]}”",
                "kind": kind,
                "reason": label,
            })
        return result

    def _self_memory_expression_mode(self, intent: str, item: dict[str, str]) -> str:
        kind = item.get("kind")
        if kind in {"deferred_reply", "topic_continuation", "emotion_followup"}:
            return "light_reference"
        if intent == "task_request":
            return "silent_influence"
        return "light_reference"

    def _is_sensitive_episode(self, item: dict[str, Any]) -> bool:
        return str(item.get("sensitivity") or "normal").lower() == "sensitive"

    def _format_episode_memory(self, item: dict[str, Any], *, intent: str) -> str:
        summary = str(item.get("summary") or "").strip()[:120]
        relationship_effect = str(item.get("relationship_effect") or "").strip()
        sensitivity = str(item.get("sensitivity") or "normal").strip()
        recall_style = str(item.get("recall_style") or "").strip()
        cue_tags = item.get("cue_tags") if isinstance(item.get("cue_tags"), list) else []

        if sensitivity == "sensitive":
            prefix = "敏感共同经历"
        elif relationship_effect and relationship_effect != "普通":
            prefix = f"共同经历（{relationship_effect}）"
        else:
            prefix = "共同经历"

        extras: list[str] = []
        if cue_tags and intent == "recall_past":
            extras.append("线索：" + "、".join(str(tag) for tag in cue_tags[:4]))
        if recall_style:
            extras.append(f"使用：{recall_style[:80]}")
        return f"{prefix}：{summary}" + (f"；{'；'.join(extras)}" if extras else "")


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = " ".join(str(item or "").split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _dedupe_active_memories(items: list[ActiveMemory]) -> list[ActiveMemory]:
    seen: set[str] = set()
    result: list[ActiveMemory] = []
    for item in items:
        normalized = " ".join(str(item.text or "").split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        item.text = normalized
        result.append(item)
    return result


def _mode_label(mode: str) -> str:
    labels = {
        "silent_influence": "只影响语气和分寸，不主动说破",
        "light_reference": "自然时轻轻带一句",
        "explicit_recall": "可以明确承接回忆",
        "ask_before_entering": "先确认用户愿不愿继续",
        "avoid": "本轮不要主动触碰",
    }
    return labels.get(mode, labels["silent_influence"])


def _cue_overlap(current_input: str, text: str, cue_tags: list[Any]) -> int:
    source = str(current_input or "").lower()
    target = str(text or "").lower()
    source_cues = set(_short_cues(source))
    tag_cues = {str(tag).strip().lower() for tag in cue_tags if str(tag).strip()}
    overlap = sum(1 for cue in source_cues if cue and cue in target)
    overlap += sum(1 for cue in tag_cues if cue and cue in source)
    return overlap


def _short_cues(text: str) -> list[str]:
    compact = "".join(str(text or "").split())
    cues: list[str] = []
    for size in (4, 3, 2):
        for idx in range(0, max(0, len(compact) - size + 1)):
            chunk = compact[idx : idx + size]
            if _is_meaningful_cue(chunk):
                cues.append(chunk)
    lowered_compact = compact.lower()
    for cue in _SALIENT_SHORT_CUES:
        normalized = cue.lower()
        if normalized in lowered_compact:
            cues.append(normalized)
    ascii_words = []
    current = []
    for ch in compact:
        if ch.isascii() and ch.isalnum():
            current.append(ch.lower())
        else:
            if len(current) >= 3:
                ascii_words.append("".join(current))
            current = []
    if len(current) >= 3:
        ascii_words.append("".join(current))
    cues.extend(ascii_words)
    return _dedupe(cues)[:24]


def _is_meaningful_cue(value: str) -> bool:
    if not value:
        return False
    stop = {
        "我想", "你说", "我们", "这个", "那个", "一下", "还是", "就是", "什么",
        "怎么", "可以", "不是", "今天", "明天", "之前", "上次",
    }
    return value not in stop and any("\u4e00" <= ch <= "\u9fff" or ch.isalnum() for ch in value)


_SALIENT_SHORT_CUES = {
    "猫",
    "狗",
    "车",
    "布丁",
    "奥利奥",
    "布偶",
    "孟买",
    "宠物",
    "咖啡",
    "妹妹",
    "游戏",
    "永劫",
    "pubg",
    "csgo",
    "北京",
    "大理",
    "数学老师",
    "喝酒",
    "酒",
    "抽烟",
    "吸烟",
    "腿脚",
    "腿",
    "脚",
    "膝盖",
    "腰",
    "身体",
    "健康",
    "跑步",
    "跑",
}


def _layered(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    layered = data.get("layered")
    return layered if isinstance(layered, dict) else {}


def _list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _known_understanding_items(data: dict[str, Any]) -> tuple[set[str], set[str]]:
    keys: set[str] = set()
    values: set[str] = set()
    if not isinstance(data, dict):
        return keys, values
    for container_key in ("manual", "auto"):
        container = data.get(container_key) if isinstance(data.get(container_key), dict) else {}
        identity = container.get("identity") if isinstance(container.get("identity"), dict) else {}
        facts = container.get("facts") if isinstance(container.get("facts"), dict) else {}
        keys.update(str(key).strip() for key in identity.keys())
        keys.update(str(key).strip() for key in facts.keys())
        values.update(str(value).strip() for value in identity.values())
        values.update(str(value).strip() for value in facts.values())
    layered = _layered(data)
    core = layered.get("core") if isinstance(layered.get("core"), dict) else {}
    for dict_key in ("identity", "facts"):
        section = core.get(dict_key) if isinstance(core.get(dict_key), dict) else {}
        keys.update(str(key).strip() for key in section.keys())
        values.update(str(value).strip() for value in section.values())
    return keys, values
