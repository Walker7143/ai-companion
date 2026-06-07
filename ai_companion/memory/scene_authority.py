from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SceneAuthorityDiff:
    upserts: list[dict[str, Any]] = field(default_factory=list)
    invalidations: list[dict[str, Any]] = field(default_factory=list)
    no_change: bool = False
    confidence_explanations: list[str] = field(default_factory=list)


_VEHICLE_CUES = (
    "车上",
    "车内",
    "车旁",
    "驾驶座",
    "副驾",
    "方向盘",
    "安全带",
    "发动机",
    "开车",
    "行驶",
    "驶出",
    "路上",
    "回大理",
    "到大理",
    "去大理",
)

_MEAL_CUES = (
    "吃饭",
    "进餐",
    "餐桌",
    "午饭",
    "晚饭",
    "早餐",
    "点菜",
    "上菜",
    "饭店",
    "餐厅",
)

_SLEEP_CUES = (
    "睡觉",
    "睡着",
    "醒来",
    "起床",
    "床上",
    "床头",
    "被子",
    "躺着",
    "枕头",
)

_BATHROOM_CUES = (
    "浴室",
    "洗澡",
    "淋浴",
    "卫生间",
    "换衣服",
    "穿衣服",
)

_INTIMATE_ROOM_CUES = (
    "客栈",
    "房间",
    "关门",
    "门锁",
    "床上",
    "床边",
    "床头",
    "脱衣",
    "衣服",
    "正事",
)

_OUTING_CUES = (
    "出门",
    "门外",
    "街上",
    "古城",
    "人民路",
    "洋人街",
    "逛",
    "游览",
    "到了",
    "抵达",
)

_ROOM_RESET_CUES = (
    "客栈房间",
    "房间内",
    "床头",
    "床上",
    "被子",
    "浴室",
    "掀被角",
    "没穿",
    "未着",
    "下装",
    "裸露",
)

_SCENE_CATEGORY_CUES: dict[str, tuple[str, ...]] = {
    "vehicle": _VEHICLE_CUES,
    "meal": _MEAL_CUES,
    "sleep": _SLEEP_CUES,
    "bathroom": _BATHROOM_CUES,
    "intimate_room": _INTIMATE_ROOM_CUES,
    "outing": _OUTING_CUES,
    "room_reset": _ROOM_RESET_CUES,
}

_SCENE_CONFLICTS: dict[str, set[str]] = {
    "vehicle": {"room_reset", "sleep", "bathroom", "meal"},
    "outing": {"room_reset", "sleep", "bathroom"},
    "meal": {"sleep", "bathroom", "room_reset", "vehicle"},
    "sleep": {"vehicle", "outing", "meal"},
    "bathroom": {"vehicle", "outing", "meal"},
    "intimate_room": {"vehicle", "outing", "meal", "bathroom"},
}

_SCENE_DURABILITY_HOURS: dict[str, int] = {
    "bathroom": 1,
    "room_reset": 1,
    "meal": 2,
    "outing": 3,
    "vehicle": 4,
    "intimate_room": 2,
    "sleep": 6,
}

_SCENE_FRESHNESS_MINUTES: dict[str, int] = {
    "bathroom": 10,
    "room_reset": 10,
    "meal": 30,
    "outing": 45,
    "vehicle": 75,
    "intimate_room": 20,
    "sleep": 90,
}

_SCENE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "name": "vehicle",
        "cues": _VEHICLE_CUES,
        "user_cues": ("车上", "车内", "车旁", "你开我开", "开车", "回大理", "到大理"),
        "transition_cues": ("上车", "坐进车里", "发动车", "开车", "车上", "车内", "路上", "回大理", "到大理", "去大理"),
        "location": "车上/车内，正在出行路线中",
        "activity": lambda text: "乘车前往大理古城"
        if any(cue in text for cue in ("回大理", "大理古城", "到大理", "去大理"))
        else "在车内同行或行驶中",
        "spatial": "两人在车内同行，驾驶位/乘客位关系已进入出行场景",
        "spatial_cues": ("驾驶座", "方向盘", "你开我开"),
    },
    {
        "name": "meal",
        "cues": _MEAL_CUES,
        "user_cues": ("吃饭", "吃午饭", "吃晚饭", "吃早饭", "点菜"),
        "transition_cues": ("坐下吃饭", "吃饭", "点菜", "上菜", "开吃", "进餐", "餐桌"),
        "location": "餐桌/餐厅场景",
        "activity": "共同进餐",
    },
    {
        "name": "outing",
        "cues": _OUTING_CUES,
        "user_cues": ("出门", "到了", "抵达", "去哪玩", "逛"),
        "transition_cues": ("出门", "逛街", "逛", "散步", "到了", "抵达", "走到街上", "到了古城", "去逛"),
        "location": "户外/目的地游览场景",
        "activity": "外出游览或抵达目的地",
    },
    {
        "name": "intimate_room",
        "cues": ("回客栈", *_INTIMATE_ROOM_CUES),
        "user_cues": ("回客栈", "客栈", "房间", "关门", "门锁", "床上", "脱衣服", "脱衣", "正事"),
        "transition_cues": ("回客栈", "回房间", "进房间", "进屋", "关门", "门锁", "床上", "脱衣服", "脱衣"),
        "location": "客栈房间/床边亲密场景",
        "activity": "房间内亲密互动或夜间安排执行中",
    },
    {
        "name": "sleep",
        "cues": _SLEEP_CUES,
        "user_cues": ("睡觉", "睡醒", "起床", "醒了", "起床啦"),
        "transition_cues": ("躺下", "睡觉", "睡着", "睡醒", "醒了", "起床", "被子", "床上"),
        "location": "床边/休息场景",
        "activity": "睡眠、醒来或起床相关状态",
    },
    {
        "name": "bathroom",
        "cues": _BATHROOM_CUES,
        "user_cues": ("洗澡", "淋浴", "去浴室", "换衣服", "穿衣服"),
        "transition_cues": ("洗澡", "淋浴", "去浴室", "去卫生间", "换衣服", "穿衣服"),
        "location": "浴室/换衣场景",
        "activity": "洗漱、沐浴或换衣相关状态",
    },
)

_SHARED_SCENE_SUBJECTS = {"shared", ""}
_USER_FIRST_PERSON_CUES = ("我", "我先", "我去", "我回", "我到", "我在", "我刚")
_ASSISTANT_SECOND_PERSON_CUES = ("你怎么", "你还", "你先", "你去", "你回", "你在", "你到", "你还没")
_SHARED_PARTY_CUES = ("我们", "咱们", "一起", "陪你", "跟你", "和你", "带你")
_SHARED_ACTION_CUES = ("吧", "走", "一起", "先去", "回客栈", "去吃饭", "上车")

_FUTURE_VISIT_CUES = (
    "去找你",
    "去你那",
    "过去找你",
    "过去看你",
    "过去陪你",
    "自驾去找你",
    "开车去找你",
    "去大理找你",
    "去客栈找你",
    "等我过去",
)
_FUTURE_TIMING_CUES = (
    "准备",
    "打算",
    "计划",
    "等我",
    "以后",
    "下次",
    "将来",
    "过段时间",
    "回头",
    "之后",
    "辞职",
)
_SELF_LOCATION_RE = re.compile(
    r"(?:我|我还|我人|我现在|我这会儿|我这边|我目前|我暂时)\s*在([^\s，。！？；：“”\"'（）()]{1,12})"
)
_SELF_ARRIVAL_RE = re.compile(
    r"(?:我到|我回到|我人在|我回了|我回)([^\s，。！？；：“”\"'（）()]{1,12})"
)
_SELF_LOCATION_VERB_PREFIXES = (
    "想",
    "说",
    "看",
    "听",
    "问",
    "等",
    "准备",
    "打算",
    "琢磨",
    "考虑",
    "纠结",
    "找",
)


def _recent_user_lines(conversation_context: str) -> list[str]:
    return [
        line
        for line in str(conversation_context or "").splitlines()
        if "用户" in line or line.strip().startswith("User:")
    ]


def _user_weighted_scene_text(user_input: str, conversation_context: str) -> str:
    return "\n".join([str(user_input or ""), *list(_recent_user_lines(conversation_context))])


def _match_scene_spec_by_cues(text: str, cue_key: str) -> dict[str, Any] | None:
    value = str(text or "").strip()
    if not value:
        return None
    best: tuple[int, int, dict[str, Any]] | None = None
    for spec in _SCENE_SPECS:
        cues = tuple(str(item) for item in spec.get(cue_key, ()) if str(item).strip())
        last_index = -1
        last_len = -1
        for cue in cues:
            idx = value.rfind(cue)
            if idx < 0:
                continue
            cue_len = len(cue)
            if idx > last_index or (idx == last_index and cue_len > last_len):
                last_index = idx
                last_len = cue_len
        if last_index < 0:
            continue
        candidate = (last_index, last_len, spec)
        if best is None or candidate[0] > best[0] or (candidate[0] == best[0] and candidate[1] > best[1]):
            best = candidate
    return best[2] if best is not None else None


def is_shared_scene_subject(subject: object) -> bool:
    return str(subject or "").strip() in _SHARED_SCENE_SUBJECTS


def infer_scene_subject(*, user_input: str, scene_name: str) -> str:
    text = str(user_input or "").strip()
    if any(cue in text for cue in _SHARED_PARTY_CUES):
        return "shared"
    if any(cue in text for cue in _ASSISTANT_SECOND_PERSON_CUES) and not any(cue in text for cue in _USER_FIRST_PERSON_CUES):
        return "assistant"
    if any(cue in text for cue in _USER_FIRST_PERSON_CUES) and not any(cue in text for cue in _SHARED_PARTY_CUES):
        return "user"
    if any(cue in text for cue in _SHARED_ACTION_CUES):
        return "shared"
    if scene_name in {"vehicle", "meal", "outing", "intimate_room"}:
        return "shared"
    return "user"


def detect_user_scene_match(
    *,
    user_input: str,
    conversation_context: str,
) -> dict[str, Any] | None:
    """Match only user-provided scene cues, preferring the latest user evidence."""
    current_match = _match_scene_spec_by_cues(user_input, "user_cues")
    if current_match is not None:
        return current_match
    for line in reversed(_recent_user_lines(conversation_context)):
        matched = _match_scene_spec_by_cues(line, "user_cues")
        if matched is not None:
            return matched
    return None


def detect_turn_scene_progression(
    *,
    user_input: str,
    bot_output: str,
    active_scene_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    active = active_scene_context if isinstance(active_scene_context, dict) else {}
    active_names = {str(item).strip() for item in active.get("scene_names", []) if str(item).strip()}
    active_categories = {str(item).strip() for item in active.get("categories", []) if str(item).strip()}
    if not active_names and not active_categories:
        return None
    matched = _match_scene_spec_by_cues("\n".join([str(user_input or ""), str(bot_output or "")]), "transition_cues")
    if matched is None:
        return None
    matched_name = str(matched.get("name") or "").strip()
    if matched_name and matched_name in active_names:
        return None
    return matched


def non_copresent_scene_reason(user_input: str) -> str | None:
    text = str(user_input or "").strip()
    if not text:
        return None
    if any(cue in text for cue in _FUTURE_VISIT_CUES) and any(marker in text for marker in _FUTURE_TIMING_CUES):
        return "future_visit_plan"
    for pattern in (_SELF_LOCATION_RE, _SELF_ARRIVAL_RE):
        for match in pattern.finditer(text):
            location = match.group(1).strip().rstrip("呢啊呀哦嘛吧啦了")
            if not location:
                continue
            if location.startswith(_SELF_LOCATION_VERB_PREFIXES):
                continue
            if categorize_scene_text(location):
                continue
            return "explicit_user_location"
    return None


def has_non_copresent_scene_cue(user_input: str) -> bool:
    return non_copresent_scene_reason(user_input) is not None


_STATUS_QUESTION_SCENES = {"meal", "sleep", "bathroom"}
_STATUS_QUESTION_TOKENS = ("吗", "么", "?", "？", "没", "了没")
_STATUS_QUESTION_ACTION_TOKENS = (
    "一起",
    "关",
    "去",
    "出来",
    "回去",
    "回客栈",
    "起床",
    "睡觉",
    "洗澡",
    "换衣服",
    "脱衣服",
    "点菜",
    "上菜",
)


def exclusive_state_groups(scope: str, predicate: str) -> set[str]:
    scope = str(scope or "").strip()
    predicate = str(predicate or "").strip()
    if scope == "current_scene" or scope.startswith("current_scene/"):
        groups: set[str] = set()
        if predicate in {"current_activity", "activity_type", "next_action", "activity_progression", "interaction_type"}:
            groups.add("current_scene/activity")
        if predicate in {"spatial_relationship", "physical_state", "body_tension_level", "posture"}:
            groups.add("current_scene/posture")
        if predicate in {"current_location", "location"}:
            groups.add("current_scene/location")
        if predicate in {"clothing_status", "clothing_status_bottom", "clothing_state"}:
            groups.add("current_scene/clothing")
        if predicate in {"anticipation_status", "evening_activity_status"} or "night_activity_expectation" in scope:
            groups.add("current_scene/night_activity_expectation")
        if predicate in {"dominant_role", "current_player_role/dominant_role"} or "current_player_role" in scope:
            groups.add("current_scene/player_role")
        if groups:
            return groups
    if predicate in {"current_location", "location"}:
        return {"current_scene/location"}
    return set()


def categorize_scene_text(text: object) -> set[str]:
    value = str(text or "")
    return {
        category
        for category, cues in _SCENE_CATEGORY_CUES.items()
        if any(cue in value for cue in cues)
    }


def is_scene_authority_predicate(scope: str, predicate: str) -> bool:
    return (scope == "current_scene" or scope.startswith("current_scene/")) and predicate in {
        "current_location",
        "location",
        "current_activity",
        "activity_type",
        "next_action",
        "activity_progression",
        "interaction_type",
        "physical_state",
        "spatial_relationship",
        "posture",
        "clothing_status",
        "clothing_status_bottom",
        "clothing_state",
    }


def scene_conflict_reason(incoming_categories: set[str], active_categories: set[str]) -> str | None:
    if (incoming_categories - {"room_reset"}) & active_categories:
        return None
    for active_category in active_categories:
        conflicts = _SCENE_CONFLICTS.get(active_category, set())
        matched = sorted(incoming_categories & conflicts)
        if matched:
            return f"assistant_or_joint_scene_conflict: active={active_category}, incoming={','.join(matched)}"
    return None


def has_room_reset_cue(text: object) -> bool:
    return bool(categorize_scene_text(text) & {"room_reset"})


def _looks_like_status_question(text: object, scene_name: str) -> bool:
    if scene_name not in _STATUS_QUESTION_SCENES:
        return False
    value = str(text or "").strip()
    if not value:
        return False
    if not any(token in value for token in _STATUS_QUESTION_TOKENS):
        return False
    if any(token in value for token in _STATUS_QUESTION_ACTION_TOKENS):
        return False
    return True


def _scene_expiry_hours(scene_name: str) -> int:
    return _SCENE_DURABILITY_HOURS.get(str(scene_name or "").strip(), 2)


def _scene_metadata(scene_name: str, subject: str, source_kind: str) -> dict[str, Any]:
    normalized_name = str(scene_name or "").strip()
    return {
        "scene_name": normalized_name,
        "scene_categories": sorted(categorize_scene_text(normalized_name) | ({normalized_name} if normalized_name else set())),
        "grounded_by_user": source_kind in {"user_explicit", "joint_inference"},
        "scene_freshness_minutes": _SCENE_FRESHNESS_MINUTES.get(normalized_name, 30),
        "copresence_scope": "shared_copresent" if subject == "shared" else ("user_only" if subject == "user" else "assistant_only"),
    }


def build_scene_authority_diff(
    *,
    user_input: str,
    bot_output: str,
    conversation_context: str,
    active_scene_context: dict[str, Any] | None = None,
) -> SceneAuthorityDiff:
    user_text = str(user_input or "")
    user_weighted_text = _user_weighted_scene_text(user_input, conversation_context)
    combined = "\n".join([user_weighted_text, str(bot_output or "")])
    remote_reason = non_copresent_scene_reason(user_input)
    matched = detect_user_scene_match(
        user_input=user_input,
        conversation_context=conversation_context,
    )
    progression_match = None
    if matched is None:
        progression_match = detect_turn_scene_progression(
            user_input=user_input,
            bot_output=bot_output,
            active_scene_context=active_scene_context,
        )
        matched = progression_match
    if matched is None and remote_reason:
        return SceneAuthorityDiff(
            invalidations=[
                {"scope": "current_scene", "predicate": "current_location", "reason": f"{remote_reason}: clear stale shared scene"},
                {"scope": "current_scene", "predicate": "current_activity", "reason": f"{remote_reason}: clear stale shared scene"},
                {"scope": "current_scene", "predicate": "spatial_relationship", "reason": f"{remote_reason}: clear stale shared scene"},
                {"scope": "current_scene", "predicate": "next_action", "reason": f"{remote_reason}: clear stale shared scene"},
            ],
            no_change=False,
            confidence_explanations=[f"scene_reset_{remote_reason}"],
        )
    if matched is None:
        return SceneAuthorityDiff(no_change=True)
    if any(cue in user_text for cue in matched["user_cues"]) and _looks_like_status_question(user_text, matched["name"]):
        return SceneAuthorityDiff(no_change=True)

    turn_transition_cues = tuple(str(item) for item in matched.get("transition_cues", ()) if str(item).strip())
    user_explicit = any(cue in user_text for cue in matched["user_cues"]) or any(cue in user_text for cue in turn_transition_cues)
    source_kind = "user_explicit" if user_explicit else "joint_inference"
    confidence = 0.96 if user_explicit else 0.82
    subject = infer_scene_subject(user_input=user_text, scene_name=str(matched.get("name") or ""))
    if progression_match is not None and not user_explicit:
        active = active_scene_context if isinstance(active_scene_context, dict) else {}
        active_subject = str(active.get("subject") or "").strip()
        if active_subject:
            subject = active_subject
    scene_name = str(matched.get("name") or "").strip()
    scene_metadata = _scene_metadata(scene_name, subject, source_kind)
    expires_hours = _scene_expiry_hours(scene_name)
    activity_spec = matched["activity"]
    activity = activity_spec(combined) if callable(activity_spec) else str(activity_spec)
    reason_prefix = "scene_progression_cue" if progression_match is not None else "scene_authority_cue"
    upserts = [
        {
            "scope": "current_scene",
            "subject": subject,
            "predicate": "current_location",
            "value": str(matched["location"]),
            "confidence": confidence,
            "source_kind": source_kind,
            "expires_hours": expires_hours,
            "reason": f"{reason_prefix}: {matched['name']} cue in recent turn",
            "metadata": dict(scene_metadata),
        },
        {
            "scope": "current_scene",
            "subject": subject,
            "predicate": "current_activity",
            "value": activity,
            "confidence": confidence,
            "source_kind": source_kind,
            "expires_hours": expires_hours,
            "reason": f"{reason_prefix}: {matched['name']} cue in recent turn",
            "metadata": dict(scene_metadata),
        },
    ]
    spatial = matched.get("spatial")
    spatial_cues = matched.get("spatial_cues") or ()
    if subject == "shared" and spatial and any(cue in combined for cue in spatial_cues):
        upserts.append(
            {
                "scope": "current_scene",
                "subject": "shared",
                "predicate": "spatial_relationship",
                "value": str(spatial),
                "confidence": confidence,
                "source_kind": source_kind,
                "expires_hours": expires_hours,
                "reason": f"{reason_prefix}: {matched['name']} spatial cue in recent turn",
                "metadata": dict(scene_metadata),
            }
        )
    invalidations = []
    if subject != "shared":
        invalidations.append(
            {
                "scope": "current_scene",
                "predicate": "spatial_relationship",
                "reason": "user_only_scene_replaces_previous_shared_proximity",
            }
        )
    return SceneAuthorityDiff(
        upserts=upserts,
        invalidations=invalidations,
        no_change=False,
        confidence_explanations=[f"{'scene_progression' if progression_match is not None else 'scene_authority'}_cue_{matched['name']}"],
    )


def is_memory_compatible_with_scene(scene_categories: set, memory_item: dict) -> bool:
    """Decide whether a recalled life event is compatible with the active scene."""
    if not scene_categories:
        return True
    source = str(memory_item.get("source") or memory_item.get("type") or "")
    if source not in ("life_event", "major_life_event"):
        return True
    text = str(memory_item.get("text") or memory_item.get("summary") or memory_item.get("content") or "")
    if not text:
        return True
    memory_categories = categorize_scene_text(text)
    if not memory_categories:
        return True
    return scene_conflict_reason(memory_categories, scene_categories) is None
