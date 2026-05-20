"""Generation-time guards for keeping chat replies aligned with the current time."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def build_local_time_context(now: datetime | None = None) -> dict[str, str]:
    """Build a minimal local clock context when the life engine is unavailable."""
    current = now.astimezone() if now else datetime.now().astimezone()
    time_of_day = time_of_day_label(current.hour)
    return {
        "current_date": current.strftime("%Y-%m-%d"),
        "day_of_week": WEEKDAYS[current.weekday()],
        "local_time": current.strftime("%H:%M"),
        "time_of_day": time_of_day,
        "current_datetime_text": (
            f"{current.strftime('%Y-%m-%d')} {current.strftime('%H:%M')} "
            f"（{WEEKDAYS[current.weekday()]}，{time_of_day}）"
        ),
    }


def build_generation_time_constraints(life_context: dict | None = None) -> str:
    """Prompt text injected before user-visible LLM generation."""
    context = dict(life_context or {})
    if not any(context.get(key) for key in ("current_datetime_text", "local_time", "current_date")):
        context = build_local_time_context()

    current_text = str(
        context.get("current_datetime_text")
        or _compose_current_datetime_text(context)
        or context.get("current_date")
        or ""
    ).strip()
    if not current_text:
        return ""

    hour = _current_hour(context)
    label = str(context.get("time_of_day") or (time_of_day_label(hour) if hour is not None else "当前时段")).strip()
    period_rule = _period_rule(label, hour)
    local_time = str(context.get("local_time") or "").strip()
    local_time_line = f"- 当前本地时间：{local_time}（{label}）" if local_time else f"- 当前时段：{label}"

    return "\n".join(
        [
            "[当前时间一致性约束]",
            f"- 当前真实时刻：{current_text}",
            local_time_line,
            "- 生成任何会直接发给用户的内容前，先按这个时刻判断早/中/晚、吃饭、上下班、睡前等生活场景。",
            f"- 当前时段规则：{period_rule}",
            "- 记忆、历史消息、人生事件或生活锚点里如果出现与当前时段冲突的活动，只能当作过去、计划或背景，不要说成现在正在发生、刚刚发生或已经发生。",
            "- 没有明确依据时，使用时间中性的说法；不要主动编造早餐、午饭、晚饭、夜宵、睡前、下班后等具体时段活动。",
            "- 回复不要自带 [HH:MM] 或 [日期 时间] 这类时间前缀，除非用户明确要求。",
        ]
    )


def time_of_day_label(hour: int) -> str:
    if 0 <= hour < 6:
        return "凌晨"
    if 6 <= hour < 11:
        return "上午"
    if 11 <= hour < 14:
        return "中午"
    if 14 <= hour < 18:
        return "下午"
    if 18 <= hour < 24:
        return "晚上"
    return "白天"


def is_event_visible_at_current_time(event: Any, life_context: dict | None) -> bool:
    """Return False for same-day life events that are clearly in the future."""
    context = dict(life_context or {})
    hour = _current_hour(context)
    current_date = _parse_date(context.get("current_date"))
    event_date = _event_date(event)

    if current_date and event_date:
        if event_date > current_date:
            return False
        if event_date < current_date:
            return True

    min_hour = infer_event_min_hour(
        " ".join(
            str(part or "")
            for part in (
                _event_field(event, "description"),
                _event_field(event, "topic_prompt"),
                _event_field(event, "scenario_key"),
            )
        )
    )
    if hour is None or min_hour is None:
        return True
    return min_hour <= hour


def scenario_has_compatible_template(scenario: dict[str, Any], *, current_hour: int | None) -> bool:
    templates = scenario.get("templates") if isinstance(scenario, dict) else None
    if not isinstance(templates, list) or not templates or current_hour is None:
        return True
    return any(
        (min_hour := infer_event_min_hour(str(template))) is None or min_hour <= current_hour
        for template in templates
    )


def compatible_templates_for_current_time(templates: list[Any], *, current_hour: int | None) -> list[str]:
    values = [str(item) for item in templates if str(item).strip()]
    if current_hour is None:
        return values
    compatible = []
    for template in values:
        min_hour = infer_event_min_hour(template)
        if min_hour is None or min_hour <= current_hour:
            compatible.append(template)
    return compatible


def infer_event_min_hour(text: str) -> int | None:
    """Infer the earliest hour at which a described event could already have happened."""
    value = str(text or "")
    if not value:
        return None

    rules: list[tuple[int, tuple[str, ...]]] = [
        (0, ("凌晨", "半夜")),
        (6, ("清晨", "早上", "早饭", "早餐", "早高峰")),
        (9, ("上午",)),
        (11, ("中午", "午饭", "午餐")),
        (12, ("午后",)),
        (14, ("下午",)),
        (17, ("下班", "傍晚", "晚高峰", "晚霞")),
        (18, ("晚上", "今晚", "晚间", "晚饭", "晚餐", "晚饭后", "晚餐后", "夜宵")),
        (21, ("睡前", "深夜")),
    ]
    matches = [hour for hour, markers in rules if any(marker in value for marker in markers)]

    scenario_defaults = {
        "lunch_discovery": 11,
        "dessert_queue": 18,
        "night_walk": 18,
        "family_call": 18,
        "skill_learning": 18,
    }
    for key, hour in scenario_defaults.items():
        if key in value:
            matches.append(hour)

    return max(matches) if matches else None


def _period_rule(label: str, hour: int | None) -> str:
    if label == "凌晨":
        return "不要把今天的早饭、午饭、晚饭、下班后或睡前活动说成已经发生；除非用户或历史明确说明，只能说当前是凌晨。"
    if label == "上午":
        return "可以提早上/上午的状态；不要说今天午饭、下午、晚饭、晚饭后、晚上活动已经发生。"
    if label == "中午":
        return "可以提上午已经过去、午饭/中午正在发生或马上发生；不要说今天晚饭、晚饭后、夜宵、睡前或晚上活动已经发生。"
    if label == "下午":
        return "可以提上午和午饭已过去；不要说今天晚饭、晚饭后、夜宵、睡前或晚上活动已经发生。"
    if label == "晚上":
        return "可以提今天白天、晚饭或晚上状态；不要把明天早上/午饭或尚未到来的睡前活动说成已经发生。"
    if hour is not None and hour < 18:
        return "当前还没到晚上；不要把晚饭、晚饭后、夜宵、睡前或晚上活动说成已经发生。"
    return "必须按当前时段判断生活场景，不确定时使用时间中性的说法。"


def _compose_current_datetime_text(context: dict) -> str:
    current_date = str(context.get("current_date") or "").strip()
    local_time = str(context.get("local_time") or "").strip()
    day = str(context.get("day_of_week") or "").strip()
    label = str(context.get("time_of_day") or "").strip()
    if current_date and local_time:
        suffix_parts = [part for part in (day, label) if part]
        suffix = f"（{'，'.join(suffix_parts)}）" if suffix_parts else ""
        return f"{current_date} {local_time}{suffix}"
    return ""


def _current_hour(context: dict) -> int | None:
    for key in ("local_time", "current_datetime_text"):
        text = str(context.get(key) or "")
        match = re.search(r"(?<!\d)([01]?\d|2[0-3]):[0-5]\d", text)
        if match:
            return int(match.group(1))
    return None


def _event_date(event: Any) -> date | None:
    description = str(_event_field(event, "description") or "")
    match = re.search(r"\d{4}-\d{2}-\d{2}", description)
    if match:
        return _parse_date(match.group(0))
    for key in ("date", "local_date", "timestamp", "created_at", "updated_at"):
        parsed = _parse_date(_event_field(event, key))
        if parsed:
            return parsed
    return None


def _event_field(event: Any, key: str) -> Any:
    if isinstance(event, dict):
        return event.get(key)
    return getattr(event, key, None)


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None
