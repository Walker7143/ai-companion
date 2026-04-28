from .loader import Persona
import json


class PersonaEngine:
    """根据人格配置构造 system prompt，每次都重新读文件以获取最新关系/态度"""

    def __init__(self, persona: Persona):
        self.persona = persona

    def build_system_prompt(self, life_context: dict | None = None) -> str:
        # 每次重新读文件，确保拿到的关系/态度是最新的
        profile = self._load_json(self.persona.persona_dir / "profile.json")
        backstory = self._load_json(self.persona.persona_dir / "backstory.json")
        values = self._load_json(self.persona.persona_dir / "values.json")
        speaking_style = self._load_json(self.persona.persona_dir / "speaking_style.json")

        lines = []

        # 1. 基础信息
        name = profile.get('name', '未知')
        age = self._current_age(profile, life_context)
        occupation = profile.get('occupation', '未知')
        lines.append(f"你是{name}，{age}岁，{occupation}。")
        lines.append("")

        # 1.1 当前人生轨迹状态（如果启用 life timeline）
        life_lines = self._format_life_context(profile, life_context)
        if life_lines:
            lines.extend(life_lines)
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

    def _current_age(self, profile: dict, life_context: dict | None) -> object:
        if life_context and life_context.get("bot_real_age") is not None:
            return life_context["bot_real_age"]
        return profile.get('age', '?')

    def _format_life_context(self, profile: dict, life_context: dict | None) -> list[str]:
        if not life_context:
            birth_date = profile.get("birth_date")
            return [f"出生日期：{birth_date}"] if birth_date else []

        lines = ["【当前人生轨迹状态】"]

        current_date = life_context.get("current_date")
        day_of_week = life_context.get("day_of_week")
        if current_date:
            if day_of_week:
                lines.append(f"当前日期：{current_date}（{day_of_week}）")
            else:
                lines.append(f"当前日期：{current_date}")

        birth_date = life_context.get("birth_date") or profile.get("birth_date")
        if birth_date:
            lines.append(f"出生日期：{birth_date}")

        if life_context.get("bot_real_age") is not None:
            lines.append(f"当前年龄：{life_context['bot_real_age']}岁")

        if life_context.get("life_stage"):
            lines.append(f"当前人生阶段：{life_context['life_stage']}")
        if life_context.get("bot_mood"):
            lines.append(f"当前心情：{life_context['bot_mood']}")
        if life_context.get("bot_current_activity"):
            lines.append(f"当前状态：{life_context['bot_current_activity']}")

        recent_major = life_context.get("recent_major_life_events") or []
        if recent_major:
            lines.append("近期重要人生事件：")
            lines.extend(self._format_recent_events(recent_major))

        recent_daily = life_context.get("recent_life_events") or []
        if recent_daily:
            lines.append("近期日常事件：")
            lines.extend(self._format_recent_events(recent_daily))

        lines.append("重要：当用户询问年龄、出生日期、当前年份、当前生活状态或最近经历时，必须以本段为准；profile.age 只是初始年龄，不代表当前年龄。")
        return lines

    def _format_recent_events(self, events: list) -> list[str]:
        lines = []
        for event in events[-5:]:
            if isinstance(event, dict):
                description = str(event.get("description", "")).strip()
            else:
                description = str(event).strip()
            if not description:
                continue
            lines.append(f"  - {description}")
        return lines

    def _load_json(self, path) -> dict:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
