"""
SkillDispatcher - 技能调度器

管理所有技能，根据请求调用对应技能，并处理结果。
"""

import logging
from typing import Optional

from .base import Skill, SkillContext, SkillResult, SkillInfo

logger = logging.getLogger(__name__)


class SkillDispatcher:
    """技能调度器"""

    def __init__(self):
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill):
        """注册技能"""
        self._skills[skill.name] = skill
        logger.info(f"[SkillDispatcher] 注册技能: {skill.name}")

    def unregister(self, skill_name: str):
        """注销技能"""
        if skill_name in self._skills:
            del self._skills[skill_name]
            logger.info(f"[SkillDispatcher] 注销技能: {skill_name}")

    def get(self, skill_name: str) -> Optional[Skill]:
        """获取技能"""
        return self._skills.get(skill_name)

    def list_skills(self) -> list[SkillInfo]:
        """列出所有技能信息"""
        return [
            SkillInfo(
                name=skill.name,
                description=skill.description,
                capabilities=skill.get_capabilities(),
                is_available=skill.is_available(),
                default_model=skill.default_model,
                supported_models=getattr(skill, "supported_models", []),
            )
            for skill in self._skills.values()
        ]

    def get_by_capability(self, capability: str) -> list[Skill]:
        """根据能力获取技能列表"""
        return [s for s in self._skills.values() if capability in s.get_capabilities()]

    async def execute(
        self,
        skill_name: str,
        params: dict,
        context: SkillContext
    ) -> SkillResult:
        """执行指定技能"""
        skill = self.get(skill_name)
        if not skill:
            logger.warning(f"[SkillDispatcher] 技能不存在: {skill_name}")
            return SkillResult(success=False, content=None, content_type="error")

        if not skill.is_available():
            logger.warning(f"[SkillDispatcher] 技能不可用: {skill_name}")
            return SkillResult(success=False, content="技能不可用", content_type="error")

        try:
            logger.info(f"[SkillDispatcher] 执行技能: {skill_name}, params={params}")
            result = await skill.execute(params, context)
            return result
        except Exception as e:
            logger.exception(f"[SkillDispatcher] 技能执行失败: {skill_name}, error={e}")
            return SkillResult(success=False, content=str(e), content_type="error")

    async def execute_by_capability(
        self,
        capability: str,
        params: dict,
        context: SkillContext
    ) -> SkillResult:
        """根据能力自动选择技能执行（选择第一个可用的）"""
        skills = self.get_by_capability(capability)
        for skill in skills:
            if skill.is_available():
                return await self.execute(skill.name, params, context)

        return SkillResult(
            success=False,
            content=f"没有可用的技能支持能力: {capability}",
            content_type="error"
        )
