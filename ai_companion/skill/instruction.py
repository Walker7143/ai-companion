"""Instruction-only skills imported from SKILL.md packages."""

from __future__ import annotations

from pathlib import Path

from .base import Skill, SkillContext, SkillResult


class InstructionSkill(Skill):
    """A non-Python skill represented by a SKILL.md instruction file."""

    capabilities = ["instruction"]

    def __init__(self, config: dict = None):
        super().__init__(config)
        metadata = self.config.get("_metadata", {}) if isinstance(self.config, dict) else {}
        self.name = str(metadata.get("name") or self.config.get("name") or "instruction-skill")
        self.description = str(metadata.get("description") or self.config.get("description") or "")
        self.default_model = self.config.get("default_model", "")
        self.instruction_path = Path(
            metadata.get("path") or self.config.get("path") or "."
        ) / str(self.config.get("instruction_file") or "SKILL.md")

    async def execute(self, params: dict, context: SkillContext) -> SkillResult:
        if params.get("show") or params.get("input") in {"show", "显示", "查看"}:
            try:
                content = self.instruction_path.read_text(encoding="utf-8")
            except OSError as exc:
                return SkillResult(success=False, content=f"读取指令失败: {exc}", content_type="error")
            return SkillResult(success=True, content=content, content_type="text")

        return SkillResult(
            success=True,
            content=f"指令型技能已安装：{self.name}\n{self.description}",
            content_type="text",
            metadata={"skill": self.name, "type": "instruction"},
        )
