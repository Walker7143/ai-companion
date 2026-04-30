from __future__ import annotations

import json
import re
from typing import Any


def extract_json_object(text: str) -> Any:
    """Parse a JSON object from an LLM response."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("模型返回为空")

    fenced = re.search(r"```(?:json)?\s*(.*?)```", raw, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        raw = fenced.group(1).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        candidate = raw[start:end + 1]
        return json.loads(candidate)
    raise ValueError("模型返回不是有效 JSON")


def json_dumps(data: Any, *, indent: int | None = 2) -> str:
    return json.dumps(data, ensure_ascii=False, indent=indent)


def compact_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def ensure_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def ensure_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}
