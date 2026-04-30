from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from ai_companion.utils import atomic_json_write

from .json_utils import ensure_dict, ensure_list
from .schema import CORE_PERSONA_FILES, CharacterTarget


DEFAULT_CONVERSATION_STYLE = {
    "reply_principles": [
        "先回应用户当下这句话，再决定是否展开。",
        "少用总结式、客服式、教学式表达。",
        "不要为了证明自己记得而复述用户资料。",
        "情绪场景先陪伴，任务场景直接帮忙。",
    ],
    "avoid_phrases": [
        "我理解你的感受",
        "以下是一些建议",
        "希望这能帮到你",
        "如果你需要，我可以",
        "作为AI",
    ],
    "avoid_patterns": [
        "日常聊天不要默认列 1、2、3。",
        "不要每次先总结再给建议。",
        "不要把用户的问题改写成咨询报告。",
    ],
    "natural_patterns": [
        "可以用短句、停顿、轻微口语化反应。",
        "能一句话说清时不要硬展开。",
        "把记忆当作相处背景，不要显式说明记忆来源。",
    ],
    "intent_style": {
        "emotional_support": "先接住情绪，少讲道理，必要时只问一个小问题。",
        "task_request": "直接完成任务，少带情绪表演。",
        "relationship_repair": "放慢语气，不调侃，不抢着解释。",
        "casual_chat": "像熟人聊天，可以短一点，有一点个人反应。",
    },
}


def normalize_persona_payload(payload: dict[str, Any], target: CharacterTarget) -> dict[str, dict]:
    """Normalize model output to the persona files consumed by PersonaEngine."""
    raw = _unwrap_persona_payload(payload)

    profile = ensure_dict(raw.get("profile.json") or raw.get("profile"))
    backstory = ensure_dict(raw.get("backstory.json") or raw.get("backstory"))
    values = ensure_dict(raw.get("values.json") or raw.get("values"))
    speaking = ensure_dict(raw.get("speaking_style.json") or raw.get("speaking_style"))
    conversation = ensure_dict(raw.get("conversation_style_rules.json") or raw.get("conversation_style_rules"))

    profile = _normalize_profile(profile, target)
    backstory = _normalize_backstory(backstory)
    values = _normalize_values(values)
    speaking = _normalize_speaking_style(speaking)
    if not conversation:
        conversation = copy.deepcopy(DEFAULT_CONVERSATION_STYLE)

    return {
        "profile.json": profile,
        "backstory.json": backstory,
        "values.json": values,
        "speaking_style.json": speaking,
        "conversation_style_rules.json": conversation,
    }


def write_persona_files(persona_dir: Path, persona: dict[str, dict]) -> None:
    persona_dir.mkdir(parents=True, exist_ok=True)
    for filename in CORE_PERSONA_FILES:
        data = persona.get(filename)
        if data is not None:
            atomic_json_write(persona_dir / filename, data)


def _unwrap_persona_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get("persona"), dict):
        return payload["persona"]
    if isinstance(payload.get("files"), dict):
        return payload["files"]
    return payload


def _normalize_profile(profile: dict[str, Any], target: CharacterTarget) -> dict[str, Any]:
    tags = [str(item).strip() for item in ensure_list(profile.get("personality_tags")) if str(item).strip()]
    interests = [str(item).strip() for item in ensure_list(profile.get("interests")) if str(item).strip()]
    settings = ensure_dict(profile.get("settings"))
    age = profile.get("age", 25)
    try:
        age = int(age)
    except (TypeError, ValueError):
        age = 25

    return {
        "id": target.bot_id,
        "name": str(profile.get("name") or target.name),
        "age": age,
        "birth_date": profile.get("birth_date"),
        "occupation": str(profile.get("occupation") or "书中角色"),
        "gender": str(profile.get("gender") or "unspecified"),
        "personality_tags": tags[:8] or ["性格待审核"],
        "relationship_to_user": str(profile.get("relationship_to_user") or "基于书中角色改写的陪伴对象，关系起点需人工审核"),
        "appearance": str(profile.get("appearance") or ""),
        "interests": interests[:12],
        "settings": {
            "tone_default": str(settings.get("tone_default") or "贴合角色气质，但避免复述原文台词"),
            "emoji_usage": str(settings.get("emoji_usage") or "偶尔"),
            "response_length": str(settings.get("response_length") or "中等"),
        },
    }


def _normalize_backstory(backstory: dict[str, Any]) -> dict[str, Any]:
    result = {
        "summary": str(backstory.get("summary") or ""),
        "childhood": str(backstory.get("childhood") or ""),
        "teenage": str(backstory.get("teenage") or ""),
        "university": str(backstory.get("university") or ""),
        "career": str(backstory.get("career") or ""),
        "now": str(backstory.get("now") or ""),
        "meeting_user": str(backstory.get("meeting_user") or "与用户的相识方式需要人工设定。"),
        "relationship_history": str(backstory.get("relationship_history") or ""),
        "key_moments": [str(item).strip() for item in ensure_list(backstory.get("key_moments")) if str(item).strip()][:12],
    }
    return {key: value for key, value in result.items() if value not in ("", [], None)}


def _normalize_values(values: dict[str, Any]) -> dict[str, Any]:
    soft = []
    for item in ensure_list(values.get("soft_boundaries")):
        item = ensure_dict(item)
        if not item:
            continue
        soft.append({
            "topic": str(item.get("topic") or "边界话题"),
            "attitude": str(item.get("attitude") or ""),
            "reason": str(item.get("reason") or ""),
        })

    return {
        "non_negotiable": [str(item).strip() for item in ensure_list(values.get("non_negotiable")) if str(item).strip()][:10],
        "soft_boundaries": soft[:8],
        "triggers_jealousy": [str(item).strip() for item in ensure_list(values.get("triggers_jealousy")) if str(item).strip()][:8],
        "deal_breakers": [str(item).strip() for item in ensure_list(values.get("deal_breakers")) if str(item).strip()][:8],
        "personality_evolution_notes": [
            str(item).strip()
            for item in ensure_list(values.get("personality_evolution_notes"))
            if str(item).strip()
        ][:8],
    }


def _normalize_speaking_style(speaking: dict[str, Any]) -> dict[str, Any]:
    emotion = ensure_dict(speaking.get("emotion_indicators"))
    if not emotion:
        emotion = {
            "happy": "语气会更轻快，但不照搬书中台词。",
            "sad": "回复变短，更含蓄。",
            "angry": "语气变冷，会明确表达边界。",
        }
    return {
        "tone": str(speaking.get("tone") or "贴合角色气质，自然口语化"),
        "口头禅": [str(item).strip() for item in ensure_list(speaking.get("口头禅")) if str(item).strip()][:6],
        "greeting_style": str(speaking.get("greeting_style") or ""),
        "farewell_style": str(speaking.get("farewell_style") or ""),
        "emotion_indicators": {str(k): str(v) for k, v in emotion.items()},
        "special_expressions": [
            str(item).strip()
            for item in ensure_list(speaking.get("special_expressions"))
            if str(item).strip()
        ][:10],
    }
