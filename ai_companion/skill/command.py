"""Explicit commands for built-in companion capabilities."""

from __future__ import annotations

import json
import re
from typing import Any

from .base import SkillContext, SkillResult
from .dispatcher import SkillDispatcher


_SENSITIVE_TOKEN_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?i)(?:api[_ -]?key|secret|token|密钥|令牌)\s*(?:是|=|:|：)?\s*[A-Za-z0-9][A-Za-z0-9_-]{23,}"),
)


def is_skill_command(text: str) -> bool:
    stripped = (text or "").strip()
    return stripped == "/skills" or stripped.startswith("/skill ")


def contains_sensitive_token(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in _SENSITIVE_TOKEN_PATTERNS)


def redact_sensitive_tokens(text: str) -> str:
    redacted = text or ""
    for pattern in _SENSITIVE_TOKEN_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    return redacted


def parse_skill_command(text: str) -> tuple[str, dict[str, Any]]:
    stripped = (text or "").strip()
    if stripped == "/skills":
        return "list", {}
    if not stripped.startswith("/skill"):
        raise ValueError("不是 skill 命令")

    rest = stripped[len("/skill"):].strip()
    if not rest:
        return "help", {}

    parts = rest.split(maxsplit=1)
    skill_name = parts[0]
    raw_args = parts[1].strip() if len(parts) > 1 else ""
    if not raw_args:
        return skill_name, {}

    if raw_args.startswith("{"):
        try:
            params = json.loads(raw_args)
        except json.JSONDecodeError as exc:
            raise ValueError(f"参数 JSON 无效: {exc.msg}") from exc
        if not isinstance(params, dict):
            raise ValueError("参数 JSON 必须是对象")
        return skill_name, params

    return skill_name, {"input": raw_args, "text": raw_args, "prompt": raw_args}


def format_skill_list(dispatcher: SkillDispatcher) -> str:
    infos = dispatcher.list_skills()
    if not infos:
        return "没有已注册的能力。"

    lines = ["已注册能力："]
    for info in infos:
        status = "可用" if info.is_available else "不可用"
        caps = ", ".join(info.capabilities) if info.capabilities else "-"
        lines.append(f"- {info.name}: {info.description or '-'} [{status}; {caps}]")
    return "\n".join(lines)


def format_runtime_skill_capabilities(capabilities: dict[str, Any]) -> str:
    skills = (capabilities or {}).get("skills") or {}
    if not skills:
        return "没有可用的运行时能力。"

    lines = ["运行时能力："]
    for name, status in skills.items():
        source = status.get("source", "builtin")
        enabled = "启用" if status.get("enabled") else "禁用"
        auto = "自动" if status.get("auto") else "手动"
        available = "可用" if status.get("available") else "不可用"
        reason = status.get("reason") or "-"
        provider = status.get("provider") or "-"
        model = status.get("model") or "-"
        lines.append(f"- {name}: {source} [{enabled}; {auto}; {available}; {provider}/{model}; {reason}]")
    return "\n".join(lines)


def format_skill_result(result: SkillResult) -> str:
    if not result.success:
        return f"[Skill Error] {result.content or '执行失败'}"

    content = "" if result.content is None else str(result.content)
    if result.content_type == "image":
        return f"[图片] {content}\nMEDIA:{content}"
    if result.content_type == "voice":
        return f"[[audio_as_voice]]\nMEDIA:{content}"
    if result.content_type in {"video", "file"}:
        return f"MEDIA:{content}"
    return content


async def execute_skill_command(
    dispatcher: SkillDispatcher,
    text: str,
    context: SkillContext,
    capabilities: dict[str, Any] | None = None,
) -> str:
    stripped = (text or "").strip()
    if stripped == "/skills":
        if capabilities is not None:
            return format_runtime_skill_capabilities(capabilities)
        return format_skill_list(dispatcher)

    skill_name, params = parse_skill_command(text)
    if skill_name in {"help", "list"}:
        if capabilities is not None:
            return format_runtime_skill_capabilities(capabilities)
        return format_skill_list(dispatcher)

    skill = dispatcher.get(skill_name)
    if skill:
        caps = skill.get_capabilities()
        raw_input = params.get("input")
        if raw_input and "text" not in params and "tts" in caps:
            params["text"] = raw_input
        if raw_input and "prompt" not in params and "image_generation" in caps:
            params["prompt"] = raw_input

    result = await dispatcher.execute(skill_name, params, context)
    return format_skill_result(result)


def parse_cli_params(raw_args: list[str]) -> dict[str, Any]:
    if not raw_args:
        return {}
    joined = " ".join(raw_args).strip()
    if joined.startswith("{"):
        data = json.loads(joined)
        if not isinstance(data, dict):
            raise ValueError("参数 JSON 必须是对象")
        return data
    return {"input": joined, "text": joined, "prompt": joined}
