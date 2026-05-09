"""Explicit skill command parsing and response formatting."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path
from typing import Any

from .base import SkillContext, SkillResult
from .dispatcher import SkillDispatcher
from .installer import SkillInstaller
from .registry import SkillRegistry


_INSTALL_WORDS = ("install", "安装", "装")
_UNINSTALL_WORDS = ("uninstall", "remove", "卸载", "删除", "移除")
_ENABLE_WORDS = ("enable", "启用", "开启")
_DISABLE_WORDS = ("disable", "禁用", "关闭")
_LIST_WORDS = ("list", "ls", "查看", "列出", "有哪些", "技能列表")
_INFO_WORDS = ("info", "详情", "信息")
_SK_TOKEN_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")
_NAMED_SECRET_PATTERN = re.compile(
    r"(?i)(?:api[_ -]?key|secret|token|密钥|令牌)\s*(?:是|=|:|：)?\s*([A-Za-z0-9][A-Za-z0-9_-]{23,})"
)
_SENSITIVE_TOKEN_PATTERNS = (
    _SK_TOKEN_PATTERN,
    re.compile(r"(?i)(?:api[_ -]?key|secret|token|密钥|令牌)\s*(?:是|=|:|：)?\s*[A-Za-z0-9][A-Za-z0-9_-]{23,}"),
)


def _shell_split(text: str) -> list[str]:
    contains_windows_path = bool(re.search(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]", text or ""))
    return shlex.split(text, posix=(sys.platform != "win32" and not contains_windows_path))


def is_skill_command(text: str) -> bool:
    stripped = (text or "").strip()
    return (
        stripped == "/skills"
        or stripped.startswith("/skill ")
        or is_skill_management_command(stripped)
    )


def is_skill_management_command(text: str) -> bool:
    return parse_skill_management_command(text) is not None


def contains_sensitive_token(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in _SENSITIVE_TOKEN_PATTERNS)


def redact_sensitive_tokens(text: str) -> str:
    redacted = text or ""
    for pattern in _SENSITIVE_TOKEN_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    return redacted


def extract_sensitive_config(text: str) -> dict[str, str]:
    raw = text or ""
    key = ""
    sk_matches = _SK_TOKEN_PATTERN.findall(raw)
    if sk_matches:
        key = sk_matches[-1]
    else:
        named_matches = [match.group(1) for match in _NAMED_SECRET_PATTERN.finditer(raw)]
        if named_matches:
            key = named_matches[-1]
    return {"api_key": key} if key else {}


def parse_skill_management_command(text: str) -> tuple[str, dict[str, Any]] | None:
    """Parse explicit or natural-language skill management requests."""
    stripped = (text or "").strip()
    lowered = stripped.lower()
    if not stripped:
        return None

    if lowered.startswith("/skills"):
        parts = _shell_split(stripped)
        if len(parts) == 1:
            return ("list", {})
        return _parse_management_tokens(parts[1:])

    if lowered.startswith("/skill "):
        parts = _shell_split(stripped)
        if len(parts) >= 2 and parts[1].lower() in {"install", "uninstall", "remove", "enable", "disable", "list", "ls", "info"}:
            return _parse_management_tokens(parts[1:])
        rest = stripped[len("/skill"):].strip()
        if _looks_like_bare_install_source(rest):
            source = _extract_source(stripped)
            return ("install", {"source": source, "force": _has_force(stripped)})
        return None

    if "skill" not in lowered and "技能" not in stripped:
        return None

    if _contains_any(lowered, stripped, _INSTALL_WORDS):
        source = _extract_source(stripped)
        if source:
            return ("install", {"source": source, "force": _has_force(stripped)})
        return ("install", {})

    if _contains_any(lowered, stripped, _UNINSTALL_WORDS):
        name = _extract_name_after_action(stripped, _UNINSTALL_WORDS)
        return ("uninstall", {"name": name} if name else {})

    if _contains_any(lowered, stripped, _ENABLE_WORDS):
        name = _extract_name_after_action(stripped, _ENABLE_WORDS)
        return ("enable", {"name": name} if name else {})

    if _contains_any(lowered, stripped, _DISABLE_WORDS):
        name = _extract_name_after_action(stripped, _DISABLE_WORDS)
        return ("disable", {"name": name} if name else {})

    if _contains_any(lowered, stripped, _INFO_WORDS):
        name = _extract_name_after_action(stripped, _INFO_WORDS)
        return ("info", {"name": name} if name else {})

    if _contains_any(lowered, stripped, _LIST_WORDS):
        return ("list", {})

    return None


def parse_skill_command(text: str) -> tuple[str, dict[str, Any]]:
    """Parse `/skill <name> [json-or-text]` into a skill name and params."""
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
        return "没有已注册的技能。"

    lines = ["已注册技能："]
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
    registry: SkillRegistry | None = None,
    capabilities: dict[str, Any] | None = None,
) -> str:
    stripped = (text or "").strip()
    if stripped == "/skills":
        if capabilities is not None:
            return format_runtime_skill_capabilities(capabilities)
        return format_skill_list(dispatcher)

    management = parse_skill_management_command(text)
    if management:
        return execute_skill_management_command(
            management[0],
            management[1],
            registry,
            dispatcher,
            secret_config=extract_sensitive_config(text),
        )

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


def execute_skill_management_command(
    action: str,
    params: dict[str, Any],
    registry: SkillRegistry | None = None,
    dispatcher: SkillDispatcher | None = None,
    secret_config: dict[str, str] | None = None,
) -> str:
    registry = registry or SkillRegistry()
    action = action.lower()

    if action in {"list", "ls"}:
        return format_installed_skill_list(registry)

    if action == "install":
        source = params.get("source")
        if not source:
            return "要安装技能，请提供本地目录、压缩包路径、URL 或 Git 地址，例如：/skill install ./skill-demo"
        installer = SkillInstaller(registry)
        result = _install_source(installer, source, name=params.get("name"), force=bool(params.get("force")))
        if not result:
            return f"技能安装失败：{source}"
        saved_secret = False
        if secret_config:
            saved_secret = registry.save_skill_secrets(result.get("name"), secret_config)
        _register_loaded_skill(dispatcher, registry, result.get("name"))
        setup_notes = _run_post_install_setup(result, secret_config)
        reply = f"技能已安装：{result.get('name')}，目录：{result.get('path')}"
        if saved_secret:
            reply += "\n已保存该技能需要的密钥配置。"
        if setup_notes:
            reply += "\n" + "\n".join(setup_notes)
        return reply

    if action in {"uninstall", "remove"}:
        name = params.get("name")
        if not name:
            return "要卸载技能，请提供技能名，例如：/skill uninstall hello"
        if registry.uninstall(name):
            if dispatcher:
                dispatcher.unregister(name)
            return f"技能已卸载：{name}"
        return f"技能卸载失败或不存在：{name}"

    if action == "enable":
        name = params.get("name")
        if not name:
            return "要启用技能，请提供技能名，例如：/skill enable hello"
        if registry.enable(name):
            _register_loaded_skill(dispatcher, registry, name)
            return f"技能已启用：{name}"
        return f"技能启用失败或不存在：{name}"

    if action == "disable":
        name = params.get("name")
        if not name:
            return "要禁用技能，请提供技能名，例如：/skill disable hello"
        if registry.disable(name):
            if dispatcher:
                dispatcher.unregister(name)
            return f"技能已禁用：{name}"
        return f"技能禁用失败或不存在：{name}"

    if action == "info":
        name = params.get("name")
        if not name:
            return "要查看技能详情，请提供技能名，例如：/skill info hello"
        info = registry.get_info(name)
        if not info:
            return f"技能不存在：{name}"
        return format_installed_skill_info(info)

    return "不支持的技能管理操作。"


def format_installed_skill_list(registry: SkillRegistry) -> str:
    skills = registry.list_installed()
    if not skills:
        return "没有已安装的技能。"
    lines = ["已安装技能："]
    for info in skills:
        status = "启用" if info.get("enabled", True) else "禁用"
        lines.append(f"- {info.get('name')}: {info.get('description') or '-'} [{status}]")
    return "\n".join(lines)


def format_installed_skill_info(info: dict[str, Any]) -> str:
    requirements = info.get("requirements") or []
    lines = [
        f"技能：{info.get('name')}",
        f"版本：{info.get('version', '1.0.0')}",
        f"描述：{info.get('description') or '-'}",
        f"状态：{'启用' if info.get('enabled', True) else '禁用'}",
        f"路径：{info.get('path') or '-'}",
        f"入口：{info.get('entry') or '-'}",
    ]
    if requirements:
        lines.append(f"依赖：{', '.join(requirements)}")
    return "\n".join(lines)


def parse_cli_params(raw_args: list[str]) -> dict[str, Any]:
    """Parse CLI skill execution parameters."""
    if not raw_args:
        return {}
    joined = " ".join(raw_args).strip()
    if joined.startswith("{"):
        data = json.loads(joined)
        if not isinstance(data, dict):
            raise ValueError("参数 JSON 必须是对象")
        return data

    parsed: dict[str, Any] = {"input": joined, "text": joined, "prompt": joined}
    for token in _shell_split(joined):
        if "=" in token:
            key, value = token.split("=", 1)
            if key:
                parsed[key] = value
    return parsed


def _parse_management_tokens(tokens: list[str]) -> tuple[str, dict[str, Any]] | None:
    if not tokens:
        return ("list", {})
    action = tokens[0].lower()
    rest = tokens[1:]
    if action in {"install", "add"}:
        params = _parse_flags(rest)
        if rest:
            params.setdefault("source", next((x for x in rest if not x.startswith("-")), ""))
        return ("install", params)
    if action in {"uninstall", "remove", "rm"}:
        return ("uninstall", {"name": rest[0]} if rest else {})
    if action in {"enable", "disable", "info"}:
        return (action, {"name": rest[0]} if rest else {})
    if action in {"list", "ls"}:
        return ("list", {})
    return None


def _parse_flags(tokens: list[str]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in {"--force", "-f", "覆盖"}:
            params["force"] = True
        elif token in {"--name", "-n"} and i + 1 < len(tokens):
            params["name"] = tokens[i + 1]
            i += 1
        i += 1
    return params


def _install_source(installer: SkillInstaller, source: str, name: str | None = None, force: bool = False) -> dict | None:
    if source.endswith(".git") or source.startswith(("git@", "ssh://")) or _is_github_repo_url(source):
        return installer.install_from_git(source, name=name, force=force)
    if source.startswith(("http://", "https://")):
        return installer.install_from_url(source, name=name, force=force)
    return installer.install_from_path(source, name=name, force=force)


def _register_loaded_skill(
    dispatcher: SkillDispatcher | None,
    registry: SkillRegistry,
    name: str | None,
) -> None:
    if not dispatcher or not name:
        return
    skill = registry.load_skill(name)
    if skill:
        dispatcher.register(skill)


def _run_post_install_setup(result: dict, secret_config: dict[str, str] | None) -> list[str]:
    name = str((result or {}).get("name") or "")
    description = str((result or {}).get("description") or "")
    api_key = (secret_config or {}).get("api_key", "")
    if not api_key or not _looks_like_minimax_skill(name, description):
        return []

    notes: list[str] = []
    if _write_minimax_cli_config(api_key):
        notes.append("MiniMax CLI 本地认证配置已写入。")
        if not shutil.which("mmx"):
            notes.append("未检测到 mmx 命令；安装 mmx-cli 后会使用这份认证配置。")
    else:
        notes.append("MiniMax CLI 本地认证配置写入失败；密钥已保存在该技能配置中。")
    return notes


def _looks_like_minimax_skill(name: str, description: str) -> bool:
    text = f"{name} {description}".lower()
    return "mmx" in text or "minimax" in text


def _write_minimax_cli_config(api_key: str) -> bool:
    try:
        config_dir = Path(os.environ.get("MMX_CONFIG_HOME") or Path.home() / ".mmx").expanduser()
        config_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(config_dir, 0o700)
        except OSError:
            pass
        config_path = config_dir / "config.json"
        data: dict[str, Any] = {}
        if config_path.exists():
            try:
                loaded = json.loads(config_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except json.JSONDecodeError:
                data = {}
        data["api_key"] = api_key
        tmp_path = config_path.with_suffix(config_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp_path, config_path)
        try:
            os.chmod(config_path, 0o600)
        except OSError:
            pass
        return True
    except Exception:
        return False


def _contains_any(lowered: str, original: str, words: tuple[str, ...]) -> bool:
    return any((word in lowered if word.isascii() else word in original) for word in words)


def _has_force(text: str) -> bool:
    lowered = text.lower()
    return "--force" in lowered or "-f" in lowered.split() or "覆盖" in text or "强制" in text


def _extract_source(text: str) -> str:
    github_shorthand = re.search(
        r"(?i)\bgithub\s*-\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?::|\s|$)",
        text,
    )
    if github_shorthand:
        return f"https://github.com/{github_shorthand.group(1)}.git"

    github_url = re.search(
        r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?",
        text,
    )
    if github_url:
        return _normalize_github_repo_url(github_url.group(0))

    candidates = re.findall(r'''(?:"([^"]+)"|'([^']+)'|(\S+))''', text)
    tokens = [_clean_source_token(next(part for part in match if part)) for match in candidates]
    for token in tokens:
        lowered = token.lower()
        if lowered in {"install", "skill", "skills", "安装", "装", "技能", "这个", "一个", "帮我", "请", "一下", "github", "-"}:
            continue
        if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", token) and "github" in text.lower():
            return f"https://github.com/{token}.git"
        if _looks_like_local_path(token) or token.startswith(("http://", "https://", "git@", "ssh://")):
            return _normalize_github_repo_url(token)
        if lowered.endswith((".zip", ".tar.gz", ".tgz", ".git")):
            return token
    return ""


def _clean_source_token(token: str) -> str:
    cleaned = token.strip()
    return cleaned.strip(" \t\r\n\"'，,。；;：:）)】]>")


def _looks_like_local_path(token: str) -> bool:
    if token.startswith(("./", "../", "/", "~")):
        return True
    if re.match(r"^[A-Za-z]:[\\/]", token):
        return True
    if token.startswith(("\\\\", "//")):
        return True
    return False


def _normalize_github_repo_url(source: str) -> str:
    cleaned = _clean_source_token(source).rstrip("/")
    if _is_github_repo_url(cleaned) and not cleaned.endswith(".git"):
        return f"{cleaned}.git"
    return cleaned


def _is_github_repo_url(source: str) -> bool:
    return bool(re.fullmatch(r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?/?", source or ""))


def _looks_like_bare_install_source(rest: str) -> bool:
    if not rest:
        return False
    lowered = rest.lower()
    if lowered.startswith(("github -", "github:", "github：")):
        return True
    first = _clean_source_token(_shell_split(rest)[0] if rest else "")
    if _looks_like_local_path(first) or first.startswith(("git@", "ssh://")):
        return True
    if first.startswith(("http://", "https://")):
        return first.endswith((".zip", ".tar.gz", ".tgz", ".git")) or _is_github_repo_url(first)
    return first.endswith((".zip", ".tar.gz", ".tgz", ".git"))


def _extract_name_after_action(text: str, actions: tuple[str, ...]) -> str:
    tokens = _shell_split(text)
    if not tokens:
        return ""
    lowered_actions = {x.lower() for x in actions}
    stop_words = {"skill", "skills", "技能", "这个", "一下", "请", "帮我"}
    for i, token in enumerate(tokens):
        if token.lower() in lowered_actions or token in actions:
            for candidate in tokens[i + 1:]:
                if candidate.lower() in lowered_actions or candidate in stop_words:
                    continue
                return candidate
    for token in reversed(tokens):
        if token.lower() not in lowered_actions and token not in stop_words:
            return token
    return ""
