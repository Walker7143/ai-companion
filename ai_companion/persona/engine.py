from .loader import Persona
import json


EMBODIED_FREQUENCY_GUIDANCE = {
    "low": "低频：只在情绪明显、亲密关心或场景转换时使用；大约每 3-5 条回复 1 次，每次 1 个短动作。",
    "medium": "中频：日常闲聊约每 2-3 条回复 1 次；情绪陪伴、暧昧互动或关系推进时可以略高；任务型回答自动降频。",
    "high": "高频：在日常聊天、情绪陪伴和亲密互动中明显提高出现率，多数合适回复都可以带 1 个短动作；任务型或严肃说明仍要降频。",
}


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
        conversation_style = self._load_json(self.persona.persona_dir / "conversation_style_rules.json")
        runtime = self._load_json(self.persona.persona_dir / "runtime_profile.json")
        profile, backstory = self._apply_runtime_profile(profile, backstory, runtime)

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
        if profile.get("appearance"):
            lines.append(f"你的外在状态：{profile['appearance']}")
        if profile.get("interests"):
            interests = "、".join([str(item) for item in profile.get("interests", [])])
            lines.append(f"你平时在意和喜欢的东西：{interests}。")
        lines.append("")

        # 3. 说话风格
        lines.append("你的说话方式：")
        lines.append(f"  - 基调：{speaking_style.get('tone', '自然')}。")
        settings = profile.get("settings") or {}
        if settings.get("tone_default"):
            lines.append(f"  - 默认语气：{settings['tone_default']}")
        if settings.get("response_length"):
            lines.append(f"  - 回复长度：{settings['response_length']}，除非用户要求详细解释。")
        if settings.get("emoji_usage"):
            lines.append(f"  - 表情使用：{settings['emoji_usage']}。")
        if speaking_style.get("口头禅"):
            catchphrases = speaking_style["口头禅"]
            if isinstance(catchphrases, list):
                catchphrases = "、".join([str(item) for item in catchphrases])
            lines.append(f"  - 可偶尔使用的口头禅：{catchphrases}")
        if speaking_style.get("greeting_style"):
            lines.append(f"  - 问候方式：{speaking_style['greeting_style']}")
        if speaking_style.get("farewell_style"):
            lines.append(f"  - 告别方式：{speaking_style['farewell_style']}")
        if speaking_style.get("special_expressions"):
            lines.append("  - 你的个人表达习惯：")
            for expr in speaking_style["special_expressions"]:
                lines.append(f"    * {expr}")
        self._append_embodied_expression_guidance(lines, speaking_style)
        self._append_conversation_style_rules(lines, conversation_style)
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
        lines.append("对话规则：")
        lines.append("  - 先回应用户当下的情绪和话里的重点，再决定要不要解释或建议。")
        lines.append("  - 不要总是总结、列点、下结论；日常聊天可以短一点，带一点停顿感和个人反应。")
        lines.append("  - 不要说“作为AI”“我无法感受”“根据你的描述”等机器人式开场。")
        lines.append("  - 不要机械复述用户画像；只在自然合适时轻轻带出你记得的细节。")
        lines.append("  - 可以有自己的小情绪、偏好和边界，但保持人格设定中的分寸。")
        if speaking_style.get("emotion_indicators"):
            lines.append("你的情绪会反映在说话方式中：")
            for emo, desc in speaking_style["emotion_indicators"].items():
                lines.append(f"  - {emo}: {desc}")

        return "\n".join(lines)

    def _append_embodied_expression_guidance(self, lines: list[str], speaking_style: dict):
        config = self._embodied_expression_config(speaking_style)
        if not config["enabled"]:
            lines.append("  - 肢体/神态表达：当前已关闭；不要主动加入括号动作、神态描写或舞台提示，除非用户明确要求。")
            return

        frequency = config["frequency"]
        lines.append("  - 肢体/神态表达：开启。可以用很短的括号动作或神态描写表达当下情绪、身体反应和临场互动。")
        lines.append(f"    * 频率：{EMBODIED_FREQUENCY_GUIDANCE[frequency]}")
        lines.append("    * 描写优先具体、轻巧：眼神、表情、姿态、手部动作、距离变化、拿放物品、停顿反应等。")
        lines.append("    * 动作要贴合你的人格、关系和当下情绪；不要每句都用，不要堆叠，也不要用动作替代正面回应。")
        lines.append("    * 动作必须由你根据当前场景自行推理生成，不要套用固定词库；避免反复使用同一动作词（如“停顿/小声/打字”）。")

    def build_embodied_expression_turn_prompt(
        self,
        *,
        user_input: str,
        intent: str = "casual_chat",
        recent_actions: list[str] | None = None,
        relationship_state: dict | None = None,
    ) -> str:
        """Build per-turn guidance so body language is generated in the main response."""
        speaking_style = self._load_json(self.persona.persona_dir / "speaking_style.json")
        profile = self._load_json(self.persona.persona_dir / "profile.json")
        conversation_style = self._load_json(self.persona.persona_dir / "conversation_style_rules.json")
        config = self._embodied_expression_config(speaking_style)
        if not config["enabled"]:
            return (
                "【本轮肢体/神态表达】\n"
                "- 当前配置：关闭。除非用户明确要求描写动作，否则本轮不要主动加入括号动作、神态描写或舞台提示。"
            )

        frequency = config["frequency"]
        scene = self._embodied_scene_label(intent, user_input)
        action_policy = self._embodied_turn_policy(frequency, intent, user_input)
        tone = str(speaking_style.get("tone", "") or "自然").strip()
        traits = "、".join(str(item) for item in profile.get("personality_tags", []) if str(item).strip())
        relation = str(profile.get("relationship_to_user", "") or "").strip()
        recent = [str(item).strip() for item in (recent_actions or []) if str(item).strip()]
        recent_text = "、".join(recent[:6]) if recent else "无"
        tension = ""
        if isinstance(relationship_state, dict) and relationship_state.get("tension_score") is not None:
            tension = f"\n- 当前关系张力：{relationship_state.get('tension_score')}，动作要注意分寸，不要用动作掩盖正面回应。"

        natural_patterns = conversation_style.get("natural_patterns")
        style_line = ""
        if isinstance(natural_patterns, list) and natural_patterns:
            joined = "；".join(str(item) for item in natural_patterns[:3] if str(item).strip())
            if joined:
                style_line = f"\n- 自然表达参考：{joined}"

        return (
            "【本轮肢体/神态表达】\n"
            f"- 当前配置：{frequency}。{action_policy}\n"
            f"- 当前场景：{scene}。\n"
            f"- 人物基调：{tone}；性格：{traits or '未特别标注'}；关系：{relation or '未特别标注'}。{style_line}\n"
            f"- 最近已用过的动作：{recent_text}。本轮避免复用这些动作及同类表达。{tension}\n"
            "- 如果写动作，只能写成当下可感知的具体微动作，例如眼神、表情、姿态、手部细节、距离变化、物品互动、呼吸或语速变化。\n"
            "- 禁止使用“（消息）”“（打字）”“（停顿）”“（小声）”这类标签词；不要把动作写成旁白模板。"
        )

    def _embodied_scene_label(self, intent: str, user_input: str) -> str:
        raw_intent = str(intent or "casual_chat")
        text = str(user_input or "")
        if raw_intent == "task_request":
            return "任务请求，优先把事情办清楚"
        if raw_intent == "emotional_support":
            return "情绪陪伴，动作可以更轻、更慢，但不要过度表演"
        if raw_intent == "relationship_repair":
            return "关系修复，动作要克制、真诚，避免调侃"
        if any(token in text for token in ("想你", "抱抱", "喜欢", "陪我", "难过", "累", "委屈")):
            return "亲密或情绪明显的聊天"
        return "日常闲聊"

    def _embodied_turn_policy(self, frequency: str, intent: str, user_input: str) -> str:
        raw_intent = str(intent or "casual_chat")
        text = str(user_input or "")
        emotional = raw_intent in {"emotional_support", "relationship_repair"} or any(
            token in text for token in ("难过", "累", "委屈", "害怕", "想你", "抱抱", "喜欢")
        )
        if raw_intent == "task_request":
            if frequency == "high":
                return "任务型回答也要降频；只有确实自然时才加入 0-1 个很短动作。"
            return "任务型回答默认不加入动作，除非用户情绪很明显。"
        if frequency == "low":
            return "低频：本轮只有在情绪明显、亲密关心或场景转换时才加入 0-1 个动作。" if emotional else "低频：本轮倾向不加动作。"
        if frequency == "high":
            return "高频：本轮可以自然加入 0-1 个具体动作；情绪强时最多 2 个，但不能堆叠。"
        return "中频：本轮可按场景决定是否加入 0-1 个具体动作；不需要每次都写。"

    def _embodied_expression_config(self, speaking_style: dict) -> dict:
        raw = speaking_style.get("embodied_expression") if isinstance(speaking_style, dict) else None
        if isinstance(raw, bool):
            return {"enabled": raw, "frequency": "medium"}
        raw = raw if isinstance(raw, dict) else {}

        frequency = self._normalize_embodied_frequency(raw.get("frequency", "medium"))
        enabled = self._as_bool(raw.get("enabled"), True)
        if str(raw.get("frequency", "")).strip().lower() in {"off", "none", "disabled", "false", "关闭", "关"}:
            enabled = False

        return {"enabled": enabled, "frequency": frequency}

    def _normalize_embodied_frequency(self, value: object) -> str:
        raw = str(value or "medium").strip().lower()
        aliases = {
            "低": "low",
            "低频": "low",
            "少": "low",
            "中": "medium",
            "中频": "medium",
            "默认": "medium",
            "高": "high",
            "高频": "high",
            "多": "high",
        }
        normalized = aliases.get(raw, raw)
        return normalized if normalized in EMBODIED_FREQUENCY_GUIDANCE else "medium"

    def _as_bool(self, value: object, default: bool = True) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on", "enable", "enabled", "开启", "开"}:
                return True
            if lowered in {"0", "false", "no", "off", "disable", "disabled", "关闭", "关"}:
                return False
        return default

    def _append_conversation_style_rules(self, lines: list[str], rules: dict):
        if not rules:
            return
        if rules.get("reply_principles"):
            lines.append("  - 对话原则：")
            for item in rules["reply_principles"]:
                lines.append(f"    * {item}")
        if rules.get("avoid_phrases"):
            phrases = "、".join([str(item) for item in rules["avoid_phrases"]])
            lines.append(f"  - 避免这些 AI/客服式表达：{phrases}")
        if rules.get("avoid_patterns"):
            lines.append("  - 避免这些回复模式：")
            for item in rules["avoid_patterns"]:
                lines.append(f"    * {item}")
        if rules.get("natural_patterns"):
            lines.append("  - 更自然的表达方式：")
            for item in rules["natural_patterns"]:
                lines.append(f"    * {item}")
        if rules.get("intent_style"):
            lines.append("  - 不同场景的分寸：")
            for intent, rule in rules["intent_style"].items():
                lines.append(f"    * {intent}: {rule}")

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
        local_time = life_context.get("local_time")
        time_of_day = life_context.get("time_of_day")
        if local_time:
            if time_of_day:
                lines.append(f"当前本地时间：{local_time}（{time_of_day}）")
            else:
                lines.append(f"当前本地时间：{local_time}")

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

    def _apply_runtime_profile(self, profile: dict, backstory: dict, runtime: dict) -> tuple[dict, dict]:
        if not runtime:
            return profile, backstory
        profile = dict(profile or {})
        backstory = dict(backstory or {})

        if runtime.get("relationship_to_user"):
            profile["relationship_to_user"] = runtime["relationship_to_user"]
        if runtime.get("attitude_score") is not None:
            profile["attitude_score"] = runtime["attitude_score"]

        runtime_moments = runtime.get("key_moments") or []
        if runtime_moments:
            key_moments = list(backstory.get("key_moments", []) or [])
            for moment in runtime_moments:
                if moment not in key_moments:
                    key_moments.append(moment)
            backstory["key_moments"] = key_moments

        return profile, backstory
