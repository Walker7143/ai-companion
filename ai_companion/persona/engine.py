from .loader import Persona
import json


class PersonaEngine:
    """根据人格配置构造 system prompt，每次都重新读文件以获取最新关系/态度"""

    def __init__(self, persona: Persona):
        self.persona = persona

    def build_system_prompt(self) -> str:
        # 每次重新读文件，确保拿到的关系/态度是最新的
        profile = self._load_json(self.persona.persona_dir / "profile.json")
        backstory = self._load_json(self.persona.persona_dir / "backstory.json")
        values = self._load_json(self.persona.persona_dir / "values.json")
        speaking_style = self._load_json(self.persona.persona_dir / "speaking_style.json")

        lines = []

        # 1. 基础信息
        name = profile.get('name', '未知')
        age = profile.get('age', '?')
        occupation = profile.get('occupation', '未知')
        lines.append(f"你是{name}，{age}岁，{occupation}。")
        lines.append("")

        # 2. 性格
        traits = "、".join(profile.get("personality_tags", []))
        lines.append(f"你的性格：{traits}。")
        lines.append("")

        # 3. 说话风格
        lines.append(f"你说话的风格：{speaking_style.get('tone', '自然')}。")
        if speaking_style.get("口头禅"):
            lines.append(f"你的口头禅：{speaking_style['口头禅']}")
        lines.append("")

        # 4. 底线
        if values.get("non_negotiable"):
            lines.append("你的原则：")
            for v in values["non_negotiable"]:
                lines.append(f"  - {v}")
            lines.append("")

        # 5. 关键经历（从文件实时读取，新增的关键时刻会反映进来）
        if backstory.get("key_moments"):
            lines.append("你记忆中与用户有关的重要时刻：")
            for moment in backstory["key_moments"]:
                lines.append(f"  - {moment}")
            lines.append("")

        # 6. 与用户的关系（从文件实时读取，关系变化会自动反映）
        rel = profile.get("relationship_to_user", "朋友")
        lines.append(f"你和用户的关系：{rel}。")

        # 7. 特别指示
        lines.append("")
        lines.append("重要：你是一个真实的人，不是 AI。请像真实的人一样说话。")
        if speaking_style.get("emotion_indicators"):
            lines.append("你的情绪会反映在说话方式中：")
            for emo, desc in speaking_style["emotion_indicators"].items():
                lines.append(f"  - {emo}: {desc}")

        return "\n".join(lines)

    def _load_json(self, path) -> dict:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
