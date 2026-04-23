from .loader import PersonaLoader, Persona


class PersonaEngine:
    """根据人格配置构造 system prompt"""

    def __init__(self, persona: Persona):
        self.persona = persona

    def build_system_prompt(self) -> str:
        p = self.persona
        lines = []

        # 1. 基础信息
        profile = p.profile
        lines.append(
            f"你是{p['name']}，{p['age']}岁，{p['occupation']}。"
        )
        lines.append("")

        # 2. 性格
        traits = "、".join(p.get("personality_tags", []))
        lines.append(f"你的性格：{traits}。")
        lines.append("")

        # 3. 说话风格
        style = p.speaking_style
        lines.append(f"你说话的风格：{style.get('tone', '自然')}。")
        if style.get("口头禅"):
            lines.append(f"你的口头禅：{style['口头禅']}")
        lines.append("")

        # 4. 底线
        values = p.values
        if values.get("non_negotiable"):
            lines.append("你的原则：")
            for v in values["non_negotiable"]:
                lines.append(f"  - {v}")
            lines.append("")

        # 5. 关键经历
        backstory = p.backstory
        if backstory.get("key_moments"):
            lines.append("你记忆中与用户有关的重要时刻：")
            for moment in backstory["key_moments"]:
                lines.append(f"  - {moment}")
            lines.append("")

        # 6. 与用户的关系
        rel = p.get("relationship_to_user", "朋友")
        lines.append(f"你和用户的关系：{rel}。")

        # 7. 特别指示
        lines.append("")
        lines.append("重要：你是一个真实的人，不是 AI。请像真实的人一样说话。")
        if style.get("emotion_indicators"):
            lines.append("你的情绪会反映在说话方式中：")
            for emo, desc in style["emotion_indicators"].items():
                lines.append(f"  - {emo}: {desc}")

        return "\n".join(lines)
