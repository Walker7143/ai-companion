"""Skill: hello"""

from ai_companion.skill.base import Skill, SkillContext, SkillResult


class HelloSkill(Skill):
    """自定义技能"""

    name = "hello"
    description = "测试技能"
    capabilities = ["hello"]

    def __init__(self, config: dict = None):
        super().__init__(config)

    async def execute(self, params: dict, context: SkillContext) -> SkillResult:
        """执行技能"""
        # TODO: 实现技能逻辑
        return SkillResult(
            success=True,
            content=f"Skill hello executed successfully",
            content_type="text",
            metadata={"skill": self.name}
        )


# 快捷函数：返回 Skill 实例供注册使用
def create_skill():
    return HelloSkill()
