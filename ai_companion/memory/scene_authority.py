from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SceneAuthorityDiff:
    upserts: list[dict[str, Any]] = field(default_factory=list)
    no_change: bool = False
    confidence_explanations: list[str] = field(default_factory=list)


_VEHICLE_CUES = (
    "车上", "车内", "车旁", "驾驶座", "副驾", "方向盘", "安全带", "发动引擎",
    "开车", "行驶", "驶出", "路上", "回大理", "到大理", "去大理",
)

_MEAL_CUES = (
    "吃饭", "进餐", "餐桌", "午饭", "晚饭", "早餐", "点菜", "上菜", "饭店", "餐厅",
)

_SLEEP_CUES = (
    "睡觉", "睡着", "醒来", "起床", "床上", "床头", "被子", "躺着", "枕头",
)

_BATHROOM_CUES = (
    "浴室", "洗澡", "淋浴", "卫生间", "换衣服", "穿衣服",
)

_INTIMATE_ROOM_CUES = (
    "客栈", "房间", "关门", "门锁", "床上", "床边", "床头", "脱衣", "衣服", "正事",
)

_OUTING_CUES = (
    "出门", "门外", "街上", "古城", "人民路", "洋人街", "逛", "游览", "到了", "抵达",
)

_ROOM_RESET_CUES = (
    "客栈房间", "房间内", "床头", "床上", "被子", "浴室", "掀被角",
    "没穿", "未着", "下装", "裸露",
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

_SCENE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "name": "vehicle",
        "cues": _VEHICLE_CUES,
        "user_cues": ("车上", "车内", "车旁", "你开我开", "开车", "回大理", "到大理"),
        "location": "车上/车内，正在出行路线上",
        "activity": lambda text: "乘车前往大理古城" if any(cue in text for cue in ("回大理", "大理古城", "到大理", "去大理")) else "在车内同行或行驶中",
        "spatial": "两人在车内同行，驾驶位/乘客位关系已进入出行场景",
        "spatial_cues": ("驾驶座", "方向盘", "你开我开"),
    },
    {
        "name": "meal",
        "cues": _MEAL_CUES,
        "user_cues": ("吃饭", "吃午饭", "吃晚饭", "吃早餐", "点菜"),
        "location": "餐桌/餐厅场景",
        "activity": "共同进餐",
    },
    {
        "name": "outing",
        "cues": _OUTING_CUES,
        "user_cues": ("出门", "到了", "抵达", "去哪玩", "逛"),
        "location": "户外/目的地游览场景",
        "activity": "外出游览或抵达目的地",
    },
    {
        "name": "intimate_room",
        "cues": ("回客栈", *_INTIMATE_ROOM_CUES),
        "user_cues": ("回客栈", "客栈", "房间", "关门", "门锁", "床上", "脱衣服", "脱衣", "正事"),
        "location": "客栈房间/床边亲密场景",
        "activity": "房间内亲密互动或夜间安排执行中",
    },
    {
        "name": "sleep",
        "cues": _SLEEP_CUES,
        "user_cues": ("睡觉", "睡醒", "起床", "醒了", "起床啦"),
        "location": "床边/休息场景",
        "activity": "睡眠、醒来或起床相关状态",
    },
    {
        "name": "bathroom",
        "cues": _BATHROOM_CUES,
        "user_cues": ("洗澡", "淋浴", "去浴室", "换衣服", "穿衣服"),
        "location": "浴室/换衣场景",
        "activity": "洗漱、洗澡或换衣相关状态",
    },
)

_SHARED_SCENE_SUBJECTS = {"shared", ""}
_USER_FIRST_PERSON_CUES = ("我", "我先", "我去", "我回", "我到", "我在", "我刚")
_ASSISTANT_SECOND_PERSON_CUES = ("你怎么", "你还", "你先", "你去", "你回", "你在", "你到", "你还没")
_SHARED_PARTY_CUES = ("我们", "咱们", "一起", "陪你", "跟你", "和你", "带你")
_SHARED_ACTION_CUES = ("吧", "走", "一起", "先去", "回客栈", "去吃饭", "上车")


def _recent_user_context(conversation_context: str) -> str:
    return "\n".join(
        line for line in str(conversation_context or "").splitlines()
        if "用户" in line or line.strip().startswith("User:")
    )


def _user_weighted_scene_text(user_input: str, conversation_context: str) -> str:
    return "\n".join([str(user_input or ""), _recent_user_context(conversation_context)])


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
    """Match only user-provided scene cues; never infer a new shared scene from bot prose alone."""
    user_weighted_text = _user_weighted_scene_text(user_input, conversation_context)
    for spec in _SCENE_SPECS:
        if any(cue in user_weighted_text for cue in spec["user_cues"]):
            return spec
    return None


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


def build_scene_authority_diff(
    *,
    user_input: str,
    bot_output: str,
    conversation_context: str,
) -> SceneAuthorityDiff:
    user_text = str(user_input or "")
    user_weighted_text = _user_weighted_scene_text(user_input, conversation_context)
    combined = "\n".join([user_weighted_text, str(bot_output or "")])
    matched = detect_user_scene_match(
        user_input=user_input,
        conversation_context=conversation_context,
    )
    if matched is None:
        return SceneAuthorityDiff(no_change=True)

    user_explicit = any(cue in user_text for cue in matched["user_cues"])
    source_kind = "user_explicit" if user_explicit else "joint_inference"
    confidence = 0.96 if user_explicit else 0.82
    subject = infer_scene_subject(user_input=user_text, scene_name=str(matched.get("name") or ""))
    activity_spec = matched["activity"]
    activity = activity_spec(combined) if callable(activity_spec) else str(activity_spec)
    upserts = [
        {
            "scope": "current_scene",
            "subject": subject,
            "predicate": "current_location",
            "value": str(matched["location"]),
            "confidence": confidence,
            "source_kind": source_kind,
            "expires_hours": 6,
            "reason": f"scene_authority_cue: {matched['name']} cue in recent turn",
        },
        {
            "scope": "current_scene",
            "subject": subject,
            "predicate": "current_activity",
            "value": activity,
            "confidence": confidence,
            "source_kind": source_kind,
            "expires_hours": 6,
            "reason": f"scene_authority_cue: {matched['name']} cue in recent turn",
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
                "expires_hours": 6,
                "reason": f"scene_authority_cue: {matched['name']} spatial cue in recent turn",
            }
        )
    return SceneAuthorityDiff(
        upserts=upserts,
        no_change=False,
        confidence_explanations=[f"scene_authority_cue_{matched['name']}"],
    )


def is_memory_compatible_with_scene(scene_categories: set, memory_item: dict) -> bool:
    """判断 memory item 是否与当前场景兼容。life_event 类型可能包含不兼容场景。"""
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
