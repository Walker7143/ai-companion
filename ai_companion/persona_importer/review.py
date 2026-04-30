from __future__ import annotations

from pathlib import Path
from typing import Any

from .json_utils import json_dumps


def build_review_markdown(
    manifest: dict[str, Any],
    character_payloads: list[dict[str, Any]],
    warnings: list[str],
) -> str:
    lines = [
        "# Persona Import Review",
        "",
        "这个目录是书籍角色导入草稿。请先审核，再执行 `ai-companion persona apply`。",
        "",
        "## Book",
        "",
        f"- title: {manifest.get('book', {}).get('title', '')}",
        f"- path: {manifest.get('book', {}).get('path', '')}",
        f"- source_format: {manifest.get('book', {}).get('source_format', '')}",
        f"- chars: {manifest.get('book', {}).get('chars', 0)}",
        f"- chunks_total: {manifest.get('chunks', {}).get('total', 0)}",
        f"- chunks_selected: {manifest.get('chunks', {}).get('selected', 0)}",
        "",
    ]
    if warnings:
        lines.extend(["## Warnings", ""])
        lines.extend([f"- {item}" for item in warnings])
        lines.append("")

    lines.extend(["## Characters", ""])
    for item in character_payloads:
        target = item.get("target", {})
        profile = item.get("persona", {}).get("profile.json", {})
        dossier = item.get("dossier", {})
        uncertainties = dossier.get("uncertainties", []) or []
        lines.extend([
            f"### {profile.get('name') or target.get('name')} (`{target.get('bot_id')}`)",
            "",
            f"- persona_dir: `{item.get('persona_dir')}`",
            f"- occupation: {profile.get('occupation', '')}",
            f"- personality_tags: {'、'.join(profile.get('personality_tags', []) or [])}",
            f"- relationship_to_user: {profile.get('relationship_to_user', '')}",
            f"- evidence_refs: {len(dossier.get('evidence_index', []) or [])}",
            f"- uncertainties: {len(uncertainties)}",
            "",
            "审核重点：",
            "- 确认年龄、身份、关系起点是否需要改写。",
            "- 删除或改写过于贴近原文的台词、短语和专有表达。",
            "- 检查性格推断是否有证据，低把握内容不要写成确定事实。",
            "- 多角色之间的关系如果要进入 Bot 设定，确认不会和用户关系冲突。",
            "",
        ])
        if uncertainties:
            lines.append("模型标记的不确定点：")
            for uncertain in uncertainties[:8]:
                lines.append(f"- {uncertain}")
            lines.append("")

    lines.extend([
        "## Apply",
        "",
        "审核后执行：",
        "",
        "```bash",
        f"ai-companion persona apply {manifest.get('draft_dir', '.')}",
        "```",
        "",
    ])
    return "\n".join(lines)


def print_draft_summary(draft_dir: Path) -> str:
    manifest_path = draft_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"找不到 manifest.json: {manifest_path}")
    import json

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    lines = [
        f"草稿目录: {draft_dir}",
        f"书籍: {manifest.get('book', {}).get('title', '')}",
        f"选中分块: {manifest.get('chunks', {}).get('selected', 0)} / {manifest.get('chunks', {}).get('total', 0)}",
        "角色:",
    ]
    for character in manifest.get("characters", []):
        lines.append(f"  - {character.get('name')} -> {character.get('bot_id')}")
    report_path = draft_dir / "review.md"
    if report_path.exists():
        lines.append(f"审核报告: {report_path}")
    return "\n".join(lines)


def write_json_debug(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dumps(data) + "\n", encoding="utf-8")
