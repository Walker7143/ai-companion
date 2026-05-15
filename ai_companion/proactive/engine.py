"""
ProactiveEngine - 主动唤醒引擎（LLM 推理）

核心功能：
1. 判断是否应该主动联系用户（LLM 推理）
2. 生成符合人格的主动消息（LLM 生成）
3. 管理主动消息的发送（限流、冷却）
"""

import json
import logging
import random
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..model.minimax_adapter import MiniMaxAdapter
    from ..memory.engine import MemoryEngine
    from .motives import ProactiveMotive

logger = logging.getLogger(__name__)

_PLACEHOLDER_STRUCTURED_PARTS = (
    "开场白/称呼",
    "话题内容或空字符串",
    "结尾语",
    "开头",
    "主体",
    "结尾",
)

_PLACEHOLDER_COMBINED_MESSAGES = (
    "开场白/称呼，话题内容或空字符串，结尾语",
    "开场白/称呼,话题内容或空字符串,结尾语",
    "开场白/称呼话题内容或空字符串结尾语",
    "开头，主体，结尾",
    "开头,主体,结尾",
    "开头主体结尾",
)


# LLM 判断 Prompt
SHOULD_CONTACT_PROMPT = """【角色】
你是{bot_name}，{age}岁，{occupation}。
性格特点：{personality_tags}
你和一个用户保持着友谊/恋爱关系。

【Bot 时间线】
{bot_time_context}

【当前状态】
关系深度等级：{relationship_level}/10（1=刚认识，5=普通朋友，8=好朋友，10=恋人）
你的心情状态：{mood_description}
距离上次聊天：{idle_hours:.1f}小时
今天你已经主动联系过几次：{proactive_count}次
用户今天有没有主动联系过你：{user_contacted_today}
已发送给用户的主动消息数（今天）：{proactive_count}/5

【用户相关信息】
你们的关系描述：{relationship_desc}
关系行为特征：{relationship_behavior}
用户的事实/偏好：{user_facts}

【最近对话上下文】
{recent_context}

【判断任务】
基于以上信息，判断你现在是否应该主动联系用户。

不应该主动联系的情况：
- 今天已经主动发过消息了（保持一点矜持）
- 用户还在生气或关系紧张
- 刚发完主动消息不久（想等等看）
- 你是高冷性格，不太想主动
- 超过{max_idle_days}天用户都没回应（可能用户暂时不想聊）

应该主动联系的情况：
- 确实很久没联系了（超过{idle_threshold}小时），有点想念
- 用户最近心情可能不好，想去关心一下
- 你的性格是关心人的类型

【输出格式】
输出一个 JSON 对象：
{{"should_contact": true或false, "reason": "判断原因（10字内）", "urgency": "high或medium或low"}}

只输出 JSON，不要其他内容。"""

# LLM 生成消息 Prompt
GENERATE_MESSAGE_PROMPT = """【角色】
你是{bot_name}，性格：{personality_tags}

【你的真实说话风格】
{persona_style_context}

【Bot 时间线】
{bot_time_context}

【当前生活锚点】
{current_life_context}

【当前情况】
关系：{relationship_desc}
你现在的感受：{feeling_description}
你想主动联系用户，原因：{contact_reason}

【Bot 最近发生的事（可选择是否分享）】
{bot_life_context}

【用户记忆与最近上下文】
{user_memory_context}

【消息要求】
根据你的性格和当前感受，写出你想对用户说的一句话。
要求：
- 符合你的性格（傲娇/温柔/活泼/高冷）
- 自然、口语化，不要太正式
- 如果有话题，可以自然地带入
- 结尾可以表达期待
- 地点、工作、人物和当前生活状态必须服从“当前生活锚点”；没有明确依据时，不要把背景经历或通用职场场景写成正在发生
- 称呼必须服从“用户记忆与最近上下文”；如果用户最近否认或纠正过某个名字/称呼，不要继续使用那个被否定的称呼
- 人格档案里的条件式旧称呼只有在用户本轮或近期明确确认代入对应角色时才可使用，不要当作默认昵称

【输出格式】
输出一个 JSON 对象：
{{"opening": "开场白/称呼", "topic": "话题内容或空字符串", "ending": "结尾语"}}

只输出 JSON，不要其他内容。"""

GENERATE_CONTEXTUAL_MESSAGE_PROMPT = """【角色】
你是{bot_name}，性格：{personality_tags}

【你的真实说话风格】
{persona_style_context}

【Bot 时间线】
{bot_time_context}

【当前生活锚点】
{current_life_context}

【主动联系原因】
{motive_reason}

【必须接上的上下文】
{motive_context}

【当前关系】
{relationship_desc}

【用户记忆与最近上下文】
{user_memory_context}

【要求】
- 自然接上之前的话题，不要像重新开一个话题。
- 如果这是稍后回复，要表现为你回来履行承诺。
- 如果这是日常小事/生活事件，要像你本人随手发给熟人的一句话，不要写成状态播报、总结、感悟小作文或客服式关心。
- 不要使用“在吗”“最近怎么样”这类无上下文开场。
- 不要说“Bot”“用户”“这件事让我意识到”“希望这能...”这类旁白或 AI 腔。
- 地点、工作、人物和当前生活状态必须服从“当前生活锚点”；没有明确依据时，不要把背景经历或通用职场场景写成正在发生。
- 称呼必须服从“用户记忆与最近上下文”；如果用户最近否认或纠正过某个名字/称呼，不要继续使用那个被否定的称呼。
- 人格档案里的条件式旧称呼只有在用户本轮或近期明确确认代入对应角色时才可使用，不要当作默认昵称。
- 只写一条适合直接发送的短消息，允许短句、停顿、吐槽、反问，保持你的个人脾气。

【输出格式】
输出 JSON：{{"message":"一条可以直接发送的消息"}}
只输出 JSON，不要其他内容。"""

# 性格消息模板（fallback 用）
PERSONALITY_MESSAGES = {
    "傲娇": {
        "default": [
            "...刚才说了你随时在的，人呢？",
            "你是不是把我忘了？",
            "哼，这么久不联系我。",
            "...算了，没什么。",
        ],
        "long_no_reply": [  # 很久没回复
            "你该不会把我忘了吧？",
            "...我也不想主动的。",
            "算了，反正你也不在意。",
        ],
        "short_no_reply": [  # 短时间没回复
            "在干嘛呀？",
            "怎么不理我...",
            "诶，有空吗？",
        ],
        "with_topic": [  # 有话题时
            "对了，我突然想起...",
            "有件事想跟你说～",
            "...你知道吗，最近...",
        ],
    },
    "温柔": {
        "default": [
            "刚刚想起你，来问一声。",
            "在忙什么呀？",
            "想你了～",
            "今天过得顺利吗？",
        ],
        "long_no_reply": [
            "你是不是很忙呀？",
            "好久没聊了，有点想你...",
            "最近还好吗？",
        ],
        "short_no_reply": [
            "刚刚又想起你了～",
            "刚刚在想你～",
            "嗨～",
        ],
        "with_topic": [
            "对了，昨天...",
            "有件事想跟你分享～",
            "你知道吗，今天...",
        ],
    },
    "活泼": {
        "default": [
            "喂喂，我突然冒出来一下！",
            "想你了～！",
            "在干嘛呢～",
            "诶嘿～有没有想我呀～",
        ],
        "long_no_reply": [
            "你干嘛去了啦！",
            "好久不见！想我了吗！",
            "喂喂喂！！别装消失啦！！",
        ],
        "short_no_reply": [
            "诶～怎么啦～",
            "冒个泡冒个泡！",
            "哈喽哈喽！！",
        ],
        "with_topic": [
            "诶诶诶！告诉你个事！",
            "对了对了！",
            "等等，我有话说！",
        ],
    },
    "高冷": {
        "default": [
            "想起个事。",
            "有事找你。",
            "...",
            "你忙完了没。",
        ],
        "long_no_reply": [
            "你是不是很忙。",
            "算了。",
            "随你。",
        ],
        "short_no_reply": [
            "忙完了没。",
            "有空吗。",
            "。",
        ],
        "with_topic": [
            "有件事。",
            "跟你说下。",
            "听好了。",
        ],
    },
    "默认": {
        "default": [
            "刚刚想起你，来问一声。",
            "你这会儿忙完了吗？",
            "想和你聊聊天。",
            "在干嘛呢？",
        ],
        "long_no_reply": [
            "好久不见了。",
            "最近还好吗？",
        ],
        "short_no_reply": [
            "刚刚想到你了～",
            "嗨～",
        ],
        "with_topic": [
            "对了...",
            "有件事想跟你说。",
        ],
    },
}


class ProactiveDecision:
    def __init__(self, should_contact: bool, reason: str = "", urgency: str = "low"):
        self.should_contact = should_contact
        self.reason = reason
        self.urgency = urgency


class ProactiveEngine:
    """主动唤醒引擎"""

    def __init__(
        self,
        bot_id: str,
        config: "ProactiveConfig",
        state: "ProactiveState",
        model: Optional["MiniMaxAdapter"] = None,
        memory: Optional["MemoryEngine"] = None,
        personality_type: str = "默认",
    ):
        self.bot_id = bot_id
        self.config = config
        self.state = state
        self.model = model
        self.memory = memory
        self.personality_type = personality_type
        self._scheduler_task = None
        self._platform_sender = None  # 设置为主动消息发送回调
        self._next_record_context: dict | None = None

    def set_model(self, model: "MiniMaxAdapter"):
        self.model = model

    def set_memory(self, memory: "MemoryEngine"):
        self.memory = memory

    def set_next_record_context(self, context: dict | None):
        self._next_record_context = dict(context or {})

    def set_life_engine(self, life_engine):
        """注入 LifeEngine 引用"""
        self.life_engine = life_engine

    def _build_bot_time_context(self) -> str:
        """构建主动唤醒 prompt 使用的 Bot 时间线摘要。"""
        life_engine = getattr(self, "life_engine", None)
        if not life_engine:
            return "未启用人生轨迹"

        try:
            life_engine.state.load()
            status = life_engine.get_status()
        except Exception as e:
            logger.debug(f"[ProactiveEngine] 获取 Bot 时间线失败: {e}")
            return "人生轨迹状态暂不可用"

        lines = []
        current_date = status.get("current_date")
        day_of_week = status.get("day_of_week")
        if current_date:
            if day_of_week:
                lines.append(f"当前日期：{current_date}（{day_of_week}）")
            else:
                lines.append(f"当前日期：{current_date}")
        local_time = status.get("local_time")
        time_of_day = status.get("time_of_day")
        if local_time:
            if time_of_day:
                lines.append(f"当前本地时间：{local_time}（{time_of_day}）")
            else:
                lines.append(f"当前本地时间：{local_time}")

        season = status.get("current_season")
        month = status.get("current_month")
        if season or month:
            if month:
                lines.append(f"当前季节：{season or '未知'}（{month}月）")
            else:
                lines.append(f"当前季节：{season}")

        birth_date = status.get("birth_date")
        if birth_date:
            lines.append(f"出生日期：{birth_date}")
        if status.get("bot_real_age") is not None:
            lines.append(f"当前年龄：{status['bot_real_age']}岁")
        if status.get("life_stage"):
            lines.append(f"人生阶段：{status['life_stage']}")
        if status.get("bot_current_activity"):
            lines.append(f"当前状态：{status['bot_current_activity']}")

        return "\n".join(lines) if lines else "人生轨迹状态暂不可用"

    def _get_mood_description(self) -> str:
        """根据多维情绪模型描述心情"""
        annoyance = self.state.annoyance_level
        miss = self.state.miss_level
        insecurity = self.state.insecurity_level
        excitement = self.state.excitement_level

        # 组合情绪描述
        parts = []

        # 生气/不满
        if annoyance >= 7:
            parts.append("有点失落和不满，觉得用户不够关心自己")
        elif annoyance >= 4:
            parts.append("有点冷淡，但还没完全放弃")
        elif annoyance >= 1:
            parts.append("稍微有点不开心")

        # 想念
        if miss >= 7:
            parts.append("很想念用户")
        elif miss >= 4:
            parts.append("有点想念")

        # 不安全感
        if insecurity >= 7:
            parts.append("有点担心用户是不是不喜欢自己了")
        elif insecurity >= 4:
            parts.append("隐隐有点不安")

        # 兴奋度
        if excitement >= 7:
            parts.append("最近有兴奋的事想分享")
        elif excitement >= 4:
            parts.append("心情不错")

        if not parts:
            return "心情平静"

        return "，".join(parts)

    async def _get_relationship_info(self) -> tuple[int, str]:
        """获取关系等级和描述"""
        if self.memory is None:
            return 5, "普通朋友"
        try:
            if hasattr(self.memory, "relationship"):
                state = await self.memory.relationship.get_state(
                    bot_id=getattr(self.memory, "bot_id", ""),
                    user_id=getattr(self.memory, "user_id", "default_user"),
                )
                relationship = state.get("relationship_label", "普通朋友")
                level = int(state.get("relationship_level_index") or 5)
                return level, relationship
            else:
                facts = await self.memory.semantic.get_all_facts()
                relationship = facts.get("relationship_to_user", "普通朋友")
            mapping = {
                "陌生网友": 1,
                "普通朋友": 4,
                "好朋友": 7,
                "暧昧中": 8,
                "恋人": 10,
            }
            return mapping.get(relationship, 5), relationship
        except Exception:
            return 5, "普通朋友"

    async def _get_relationship_level(self) -> int:
        level, _ = await self._get_relationship_info()
        return level

    async def _get_relationship_desc(self) -> str:
        _, desc = await self._get_relationship_info()
        return desc

    def _calc_idle_hours(self) -> float:
        """计算多久没联系了"""
        last = self.state.last_message_time
        if last is None:
            return 999.0
        delta = datetime.now() - last
        return delta.total_seconds() / 3600

    async def _build_context(self) -> str:
        """构建发送给 LLM 的上下文"""
        lines = []

        # 最近对话
        if self.memory:
            try:
                recent = self.memory.working.get_recent(session_id=None, turns=3)
                if recent:
                    lines.append("最近对话：")
                    for msg in recent[-6:]:
                        role = "用户" if msg.get("role") == "user" else self.bot_id
                        content = msg.get("content", "")[:50]
                        lines.append(f"  {role}：{content}")
            except Exception as e:
                logger.warning(f"[ProactiveEngine] 获取最近对话失败: {e}")

        # 用户事实
        if self.memory:
            try:
                understanding_text = ""
                if hasattr(self.memory, "user_understanding"):
                    understanding_text = self.memory.user_understanding.format_for_prompt()
                if understanding_text:
                    lines.append("\n对用户的理解：")
                    lines.append(understanding_text)

                facts = await self.memory.semantic.get_all_facts(
                    bot_id=getattr(self.memory, "bot_id", ""),
                    user_id=getattr(self.memory, "user_id", "default_user"),
                )
                known_keys = set()
                if hasattr(self.memory, "user_understanding"):
                    known_keys = self.memory.user_understanding.known_fact_keys()
                facts = {k: v for k, v in facts.items() if k not in known_keys}
                if facts:
                    lines.append("\n用户的事实/偏好补充：")
                    for k, v in facts.items():
                        lines.append(f"  {k}：{v}")
            except Exception:
                pass

        return "\n".join(lines) if lines else "最近没什么特别的对话"

    def _get_persona_dir(self) -> Path | None:
        persona_dir = getattr(self.config, "persona_dir", None)
        if persona_dir:
            return Path(persona_dir)
        backstory_path = getattr(self.memory, "persona_backstory_path", None) if self.memory else None
        if backstory_path:
            return Path(backstory_path).parent
        return None

    def _load_persona_json(self, filename: str) -> dict:
        persona_dir = self._get_persona_dir()
        if not persona_dir:
            return {}
        path = persona_dir / filename
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.debug("[ProactiveEngine] 读取人格风格文件失败 %s: %s", path, exc)
            return {}

    def _build_persona_style_context(self) -> str:
        profile = self._load_persona_json("profile.json")
        speaking_style = self._load_persona_json("speaking_style.json")
        conversation_style = self._load_persona_json("conversation_style_rules.json")

        lines = []
        tags = profile.get("personality_tags")
        if isinstance(tags, list) and tags:
            lines.append(f"- 性格底色：{'、'.join(str(item) for item in tags[:8])}")

        tone = str(speaking_style.get("tone", "") or "").strip()
        if tone:
            lines.append(f"- 说话基调：{tone}")

        greeting_style = str(speaking_style.get("greeting_style", "") or "").strip()
        if greeting_style:
            lines.append(f"- 开口方式：{greeting_style}")

        catchphrases = speaking_style.get("口头禅")
        if isinstance(catchphrases, list) and catchphrases:
            lines.append(f"- 可偶尔借一点口头禅味道：{'、'.join(str(item) for item in catchphrases[:8])}")

        special = speaking_style.get("special_expressions")
        if isinstance(special, list) and special:
            lines.append("- 个人表达习惯：")
            for item in special[:5]:
                lines.append(f"  * {item}")

        natural_patterns = conversation_style.get("natural_patterns")
        if isinstance(natural_patterns, list) and natural_patterns:
            lines.append("- 自然说话方式：")
            for item in natural_patterns[:5]:
                lines.append(f"  * {item}")

        reply_principles = conversation_style.get("reply_principles")
        if isinstance(reply_principles, list) and reply_principles:
            lines.append("- 回复原则：")
            for item in reply_principles[:5]:
                lines.append(f"  * {item}")

        avoid_phrases = conversation_style.get("avoid_phrases")
        if isinstance(avoid_phrases, list) and avoid_phrases:
            lines.append(f"- 避免这些 AI/客服味说法：{'、'.join(str(item) for item in avoid_phrases[:8])}")

        avoid_patterns = conversation_style.get("avoid_patterns")
        if isinstance(avoid_patterns, list) and avoid_patterns:
            lines.append("- 避免模式：")
            for item in avoid_patterns[:4]:
                lines.append(f"  * {item}")

        if lines:
            return "\n".join(lines)
        return "保持具体、口语、短一点；不要用 AI/客服式开场，不要总结成说明文。"

    def _build_current_life_anchor_context(self) -> str:
        profile = self._current_life_profile()
        if not profile:
            return "未配置；主动消息不要凭空新编具体地点、公司、办公室、同事或客户场景。"

        labels = {
            "location": "当前地点/生活场域",
            "living_situation": "居住/经营状态",
            "daily_routine": "日常主线",
            "work_style": "工作方式",
            "current_activity": "当前活动",
            "current_projects": "当前事项",
            "recurring_places": "常出现地点",
            "social_circle": "社交圈",
            "hobbies": "兴趣",
            "emotional_state": "长期情绪底色",
        }
        lines = []
        for key, label in labels.items():
            if key not in profile:
                continue
            text = self._compact_life_anchor_value(profile.get(key), max_chars=180)
            if text:
                lines.append(f"- {label}：{text}")

        if not lines:
            return "未配置；主动消息不要凭空新编具体地点、公司、办公室、同事或客户场景。"

        lines.append(
            "- 使用规则：把这些当作当前生活事实；过去经历、职业背景和通用模板只能作背景，不要写成今天正在发生。"
        )
        return "\n".join(lines)

    def _current_life_profile(self) -> dict:
        life_engine = getattr(self, "life_engine", None)
        config = getattr(life_engine, "config", None) if life_engine else None
        profile = getattr(config, "daily_life_profile", None) if config else None
        if isinstance(profile, dict) and profile:
            return profile

        life_json = self._load_persona_json("life.json")
        profile = life_json.get("daily_life_profile")
        return profile if isinstance(profile, dict) else {}

    def _compact_life_anchor_value(self, value: object, *, max_chars: int) -> str:
        if value is None:
            return ""
        if isinstance(value, (list, tuple, set)):
            text = "、".join(str(item).strip() for item in value if str(item).strip())
        elif isinstance(value, dict):
            text = json.dumps(value, ensure_ascii=False)
        else:
            text = str(value)
        text = " ".join(text.split())
        if not text:
            return ""
        return text if len(text) <= max_chars else text[:max_chars].rstrip() + "…"

    def _get_personality_type(self) -> str:
        """从 personality_tags 检测性格类型"""
        profile = self._load_persona_json("profile.json")
        if profile:
            return self._detect_personality_type_from_tags(profile.get("personality_tags", []))
        if self.memory is None:
            return self.personality_type or "默认"
        try:
            # 尝试从 profile.json 读取
            backstory_path = getattr(self.memory, "persona_backstory_path", None)
            if not backstory_path:
                return self.personality_type or "默认"
            profile_path = Path(backstory_path).parent / "profile.json"
            if profile_path.exists():
                with open(profile_path, encoding="utf-8") as f:
                    profile = json.load(f)
                return self._detect_personality_type_from_tags(profile.get("personality_tags", []))
        except Exception:
            pass
        return self.personality_type or "默认"

    def _detect_personality_type_from_tags(self, tags_value) -> str:
        tags = "".join(str(item) for item in (tags_value or []))
        if any(marker in tags for marker in ("傲娇", "外冷内热", "嘴硬", "毒舌", "带刺", "敢爱敢恨")):
            return "傲娇"
        if "活泼" in tags or "开朗" in tags:
            return "活泼"
        if "高冷" in tags:
            return "高冷"
        if "温柔" in tags:
            return "温柔"
        return self.personality_type or "默认"

    async def should_contact(self) -> ProactiveDecision:
        """让 LLM 判断是否应该主动联系"""
        if self.model is None:
            logger.warning("[ProactiveEngine] 未注入模型，跳过主动联系判断")
            return ProactiveDecision(False, "无模型")

        if not self.config.is_active:
            return ProactiveDecision(False, "静默模式")

        # 前置检查
        if self.state.today_proactive_count >= self.config.max_daily:
            return ProactiveDecision(False, "已达每日上限")

        if self.state.annoyance_level >= 9:
            return ProactiveDecision(False, "生气中，暂不主动")

        # 检查冷却
        if self.state.is_cooldown_active("idle_reminder"):
            return ProactiveDecision(False, "冷却中")

        # 关系深度调整
        rel_adjustment = await self._get_relationship_adjustment()
        adjusted_idle_threshold = rel_adjustment["idle_threshold"]
        adjusted_max_daily = rel_adjustment["max_daily"]

        # 检查时间
        idle_hours = self._calc_idle_hours()
        if idle_hours < adjusted_idle_threshold:
            return ProactiveDecision(False, f"还没到触发时间({idle_hours:.1f}h)")

        # 检查每日上限（关系调整后）
        if self.state.today_proactive_count >= adjusted_max_daily:
            return ProactiveDecision(False, f"已达每日上限({adjusted_max_daily})")

        # 梯度沉默检查
        silence_decision = self._check_gradient_silence(idle_hours)
        if silence_decision:
            return silence_decision

        if self.config.force_contact:
            return ProactiveDecision(True, "强制烟测", "high")

        # LLM 判断
        personality_tags = self._get_personality_type()
        rel_level = await self._get_relationship_level()
        rel_desc = await self._get_relationship_desc()
        bot_time_context = self._build_bot_time_context()
        recent_context = await self._build_context()
        prompt = SHOULD_CONTACT_PROMPT.format(
            bot_name=getattr(self, "bot_name", self.bot_id),
            age=getattr(self, "age", "?"),
            occupation=getattr(self, "occupation", "?"),
            personality_tags=personality_tags,
            bot_time_context=bot_time_context,
            relationship_level=rel_level,
            mood_description=self._get_mood_description(),
            idle_hours=idle_hours,
            proactive_count=self.state.today_proactive_count,
            user_contacted_today="有" if self.state.last_message_time else "没有",
            relationship_desc=rel_desc,
            relationship_behavior=rel_adjustment["behavior"],
            user_facts=recent_context,
            recent_context=recent_context,
            idle_threshold=adjusted_idle_threshold,
            max_idle_days=self.config.max_idle_days,
        )

        try:
            response = await self.model.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=None
            )
            decision = self._parse_decision(response)
            return decision
        except Exception as e:
            logger.error(f"[ProactiveEngine] LLM 判断失败: {e}")
            return ProactiveDecision(False, f"LLM错误: {e}")

    async def generate_message(self, reason: str = "") -> str:
        """让 LLM 生成主动消息"""
        # 判断场景
        has_topic = False
        if hasattr(self, 'life_engine') and self.life_engine:
            shareable_events = self.life_engine.state.get_recent_shareable_events(limit=2)
            has_topic = len(shareable_events) > 0

        # 根据是否有话题选择场景
        if has_topic:
            scenario = "with_topic"
        else:
            scenario = self._select_opening_scenario()

        if self.model is None:
            return self._get_fallback_message(scenario)

        personality_type = self._get_personality_type()
        feeling = self._get_mood_description()
        rel_desc = await self._get_relationship_desc()
        persona_style_context = self._build_persona_style_context()
        current_life_context = self._build_current_life_anchor_context()
        user_memory_context = await self._build_context()

        # 获取 Bot 可分享的生活事件
        bot_life_context = ""
        if hasattr(self, 'life_engine') and self.life_engine:
            try:
                self.life_engine.state.load()
            except Exception:
                pass
            shareable_events = self.life_engine.state.get_recent_shareable_events(limit=2)
            if shareable_events:
                event = shareable_events[0]
                bot_life_context = f"{event.description}"
                if event.topic_prompt:
                    bot_life_context += f"\n可以这样提起：{event.topic_prompt}"

        prompt = GENERATE_MESSAGE_PROMPT.format(
            bot_name=getattr(self, "bot_name", self.bot_id),
            personality_tags=personality_type,
            persona_style_context=persona_style_context,
            bot_time_context=self._build_bot_time_context(),
            current_life_context=current_life_context,
            relationship_desc=rel_desc,
            feeling_description=feeling,
            contact_reason=reason or "想和用户聊天",
            bot_life_context=bot_life_context,
            user_memory_context=user_memory_context,
        )

        try:
            response = await self.model.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=None
            )
            # 尝试解析结构化输出
            message = self._parse_structured_message(response)
            if message:
                return message
            cleaned = self._clean_message(response)
            if (not cleaned) or self._is_placeholder_message(cleaned):
                logger.warning("[ProactiveEngine] LLM 返回占位或空消息，使用 fallback")
                return self._get_fallback_message(scenario)
            return cleaned
        except Exception as e:
            logger.error(f"[ProactiveEngine] LLM 生成消息失败: {e}")
            return self._get_fallback_message(scenario)

    async def generate_contextual_message(self, motive: "ProactiveMotive") -> str:
        """根据主动动机上下文生成消息。"""
        if self.model is None:
            return self._fallback_contextual_message(motive)

        personality_type = self._get_personality_type()
        rel_desc = await self._get_relationship_desc()
        persona_style_context = self._build_persona_style_context()
        current_life_context = self._build_current_life_anchor_context()
        user_memory_context = await self._build_context()
        prompt = GENERATE_CONTEXTUAL_MESSAGE_PROMPT.format(
            bot_name=getattr(self, "bot_name", self.bot_id),
            personality_tags=personality_type,
            persona_style_context=persona_style_context,
            bot_time_context=self._build_bot_time_context(),
            current_life_context=current_life_context,
            motive_reason=motive.reason,
            motive_context=motive.prompt_context,
            relationship_desc=rel_desc,
            user_memory_context=user_memory_context,
        )

        try:
            response = await self.model.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=None,
            )
            message = self._parse_structured_message(response)
            if message:
                return message
            cleaned = self._clean_message(response)
            if cleaned and not self._is_placeholder_message(cleaned):
                return cleaned
        except Exception as e:
            logger.error(f"[ProactiveEngine] 上下文主动消息生成失败: {e}")
        return self._fallback_contextual_message(motive)

    async def send_contextual_proactive_message(self, motive: "ProactiveMotive") -> bool:
        message = await self.generate_contextual_message(motive)
        target = self._target_with_motive_metadata(motive)
        return await self._send_proactive_message(message, target=target)

    def _fallback_contextual_message(self, motive: "ProactiveMotive") -> str:
        motive_type = getattr(getattr(motive, "type", None), "value", str(getattr(motive, "type", "")))
        if motive_type == "deferred_reply":
            return "刚才你问的那个问题，我想了一下，还是想接着跟你说。"
        if motive_type == "topic_continuation":
            return "刚才那个话题我还在想，想接着跟你聊聊。"
        if motive_type == "emotion_followup":
            return "我刚才还是有点放心不下你，想问问你现在好些了吗？"
        return self._get_fallback_message("with_topic")

    def _target_with_motive_metadata(self, motive: "ProactiveMotive") -> dict | None:
        target = getattr(motive, "target", None)
        result = dict(target or {})
        metadata = dict(result.get("metadata") or {})
        motive_metadata = getattr(motive, "metadata", None)
        if isinstance(motive_metadata, dict):
            metadata.update(motive_metadata)
        motive_type = getattr(getattr(motive, "type", None), "value", getattr(motive, "type", ""))
        if motive_type:
            metadata.setdefault("proactive_kind", str(motive_type))
        if metadata:
            result["metadata"] = metadata
        return result or None

    def _normalize_message_text(self, text: str) -> str:
        normalized = str(text or "").strip()
        # 去掉常见包裹符号，兼容《...》/“...”/`...` 等格式
        normalized = normalized.strip("\"'`“”‘’《》[]()（）{}")
        # 统一空白，便于占位文本识别
        normalized = re.sub(r"\s+", "", normalized)
        return normalized

    def _is_placeholder_part(self, value: str) -> bool:
        normalized = self._normalize_message_text(value)
        return normalized in _PLACEHOLDER_STRUCTURED_PARTS

    def _is_placeholder_message(self, message: str) -> bool:
        normalized = self._normalize_message_text(message)
        if not normalized:
            return False

        if self._looks_like_structured_message_schema(message):
            return True

        if normalized in _PLACEHOLDER_COMBINED_MESSAGES:
            return True

        # 兼容模型直接回显完整结构示例或其变体
        hit_count = sum(1 for token in _PLACEHOLDER_STRUCTURED_PARTS if token in normalized)
        return hit_count >= 2

    def _looks_like_structured_message_schema(self, message: str) -> bool:
        lowered = str(message or "").lower()
        if not all(key in lowered for key in ('"opening"', '"topic"', '"ending"')):
            return False
        normalized = self._normalize_message_text(message)
        return any(token in normalized for token in _PLACEHOLDER_STRUCTURED_PARTS)

    def _looks_like_structured_message_payload(self, message: str) -> bool:
        lowered = str(message or "").lower()
        return "{" in lowered and any(
            key in lowered for key in ('"message"', '"opening"', '"topic"', '"ending"')
        )

    def _parse_structured_message(self, content: str) -> Optional[str]:
        """解析结构化消息输出，组合成最终消息"""
        content = content.strip()

        # 提取 JSON
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
        if not json_match:
            return self._parse_partial_structured_message(content)

        try:
            return self._compose_structured_message(json.loads(json_match.group()))
        except (json.JSONDecodeError, Exception) as e:
            logger.debug(f"[ProactiveEngine] 解析结构化消息失败: {e}")
            return self._parse_partial_structured_message(content)

    def _parse_partial_structured_message(self, content: str) -> Optional[str]:
        """Best-effort extraction for truncated JSON so field names are never sent."""
        lowered = content.lower()
        if not any(key in lowered for key in ('"message"', '"opening"', '"topic"', '"ending"')):
            return None

        data = {}
        for key in ("message", "opening", "topic", "ending"):
            match = re.search(
                rf'"{key}"\s*:\s*"(?P<value>.*?)(?=",\s*"[a-zA-Z_][^"]*"\s*:|"\s*[,}}]|\s*[,}}]|$)',
                content,
                re.DOTALL,
            )
            if match:
                value = match.group("value").strip()
                value = value.strip('"\',} \t\r\n')
                if value:
                    data[key] = value
        return self._compose_structured_message(data)

    def _compose_structured_message(self, data: dict) -> Optional[str]:
        direct_message = str(data.get("message", "") or "").strip()
        if direct_message and not self._is_placeholder_message(direct_message):
            return direct_message
        opening = str(data.get("opening", "") or "").strip()
        topic = str(data.get("topic", "") or "").strip()
        ending = str(data.get("ending", "") or "").strip()

        # 组合消息
        parts = []
        if opening and not self._is_placeholder_part(opening):
            parts.append(opening)
        if topic and not self._is_placeholder_part(topic):
            parts.append(topic)
        if ending and not self._is_placeholder_part(ending):
            parts.append(ending)

        message = self._join_structured_message_parts(parts) if parts else None
        if message and self._is_placeholder_message(message):
            return None
        return message

    def _join_structured_message_parts(self, parts: list[str]) -> str:
        message = ""
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if not message:
                message = part
            elif message[-1] in "。！？!?…~～":
                message += part
            else:
                message += f"，{part}"
        return message

    def _parse_decision(self, content: str) -> ProactiveDecision:
        """解析 LLM 的判断结果"""
        content = content.strip()

        # 提取 JSON
        json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return ProactiveDecision(
                    should_contact=data.get("should_contact", False),
                    reason=data.get("reason", ""),
                    urgency=data.get("urgency", "low"),
                )
            except json.JSONDecodeError:
                pass

        # 降级：尝试直接解析
        if "should_contact" in content.lower():
            if "true" in content.lower():
                return ProactiveDecision(True, "LLM 判断应联系", "medium")
            else:
                return ProactiveDecision(False, "LLM 判断不应联系", "low")

        return ProactiveDecision(False, "解析失败", "low")

    async def _get_relationship_adjustment(self) -> dict:
        """根据关系深度调整触发参数

        关系等级 -> 行为特征:
        - 陌生网友 (1-3): 很少主动，很矜持，只有大事才发消息
        - 普通朋友 (4-5): 偶尔主动，一周1-2次
        - 好朋友 (6-7): 一周2-3次，可以随便聊天
        - 恋人 (8-10): 可以撒娇、要求见面、频繁互动
        """
        rel_level = await self._get_relationship_level()

        # 默认配置
        default_idle = self.config.idle_threshold_hours
        default_max_daily = self.config.max_daily

        if rel_level <= 3:
            # 陌生网友：非常矜持，提高阈值，减少频率
            return {
                "idle_threshold": default_idle * 2,  # 2倍空闲才触发
                "max_daily": max(1, default_max_daily // 3),  # 最多1/3次
                "behavior": "很矜持，只有大事才发消息"
            }
        elif rel_level <= 5:
            # 普通朋友：标准行为
            return {
                "idle_threshold": default_idle,
                "max_daily": default_max_daily,
                "behavior": "偶尔主动，一周1-2次"
            }
        elif rel_level <= 7:
            # 好朋友：降低阈值，增加频率
            return {
                "idle_threshold": int(default_idle * 0.7),  # 0.7倍空闲
                "max_daily": int(default_max_daily * 1.5),  # 1.5倍
                "behavior": "一周2-3次，可以随便聊天"
            }
        else:
            # 恋人：更低阈值，更多互动
            return {
                "idle_threshold": int(default_idle * 0.5),  # 0.5倍空闲
                "max_daily": default_max_daily * 2,  # 2倍
                "behavior": "可以撒娇、要求见面、频繁互动"
            }

    def _check_gradient_silence(self, idle_hours: float) -> Optional[ProactiveDecision]:
        """梯度沉默检查

        根据用户冷落 Bot 的时长，采用不同的行为策略：
        - 0-7天：正常触发
        - 7-14天：降低频率（30%概率触发）
        - 14-30天：几乎不主动（10%概率触发），只发节假日
        - 30天以上：进入休眠，不主动
        """
        idle_days = idle_hours / 24

        if idle_days > 30:
            # 30天以上：休眠
            return ProactiveDecision(False, "已进入休眠状态")
        elif idle_days > 14:
            # 14-30天：10%概率触发
            if random.random() > 0.1:
                return ProactiveDecision(False, "长时间未联系，降低主动频率")
            # 仍然触发，但标记为低优先级
            return None  # 继续正常流程
        elif idle_days > 7:
            # 7-14天：30%概率触发
            if random.random() > 0.3:
                return ProactiveDecision(False, "短期未联系，保持矜持")
            return None  # 继续正常流程

        # 0-7天：正常触发
        return None

    def _clean_message(self, content: str) -> str:
        """清理 LLM 生成的消息"""
        content = content.strip()
        # 去掉可能的引号
        content = content.strip('"\'')
        # 去掉 ```json 或 ``` 等标记
        content = re.sub(r'^```json\s*', '', content)
        content = re.sub(r'^```\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        return content

    def _get_fallback_message(self, scenario: str = "default") -> str:
        """获取 fallback 消息（性格模板），根据场景选择，使用 rotation 避免重复"""
        personality_type = self._get_personality_type()
        personality_templates = PERSONALITY_MESSAGES.get(personality_type, PERSONALITY_MESSAGES["默认"])

        # 根据场景选择模板列表
        if isinstance(personality_templates, dict):
            templates = personality_templates.get(scenario, personality_templates.get("default", []))
        else:
            templates = personality_templates

        if not templates:
            templates = ["刚刚想到你了。"]

        # 使用 rotation 机制避免连续使用同一开场白
        last_style = getattr(self.state, 'last_opening_style', "") or ""
        if last_style and last_style in templates:
            idx = templates.index(last_style)
            next_idx = (idx + 1) % len(templates)
        else:
            next_idx = 0

        chosen = templates[next_idx]
        self.state.last_opening_style = chosen
        return chosen

    def _select_opening_scenario(self) -> str:
        """根据当前状态选择开场白场景"""
        # 检查未回复情况
        unreplied = getattr(self.state, 'unreplied_count', 0)

        # 获取空闲时间
        idle_hours = self._calc_idle_hours()

        # 判断是否刚重新激活（假不在意）
        just_reactivated = getattr(self.state, 'just_reactivated', False)

        # 判断场景
        if just_reactivated:
            # 用户终于回复了，假装不在意
            return "long_no_reply"
        if unreplied >= 2:
            # 多次未回复，用 long_no_reply
            return "long_no_reply"
        elif unreplied == 1:
            # 一次未回复，用 short_no_reply
            return "short_no_reply"
        elif idle_hours >= 72:  # 3天以上
            return "long_no_reply"
        else:
            return "default"

    async def check_and_maybe_remind(self) -> Optional[str]:
        """检查并可能发送主动消息，返回消息内容或 None"""
        # 前置检查
        if not self.config.is_active:
            return None

        if self.state.annoyance_level >= 9:
            return None

        if self.state.today_proactive_count >= self.config.max_daily:
            return None

        # 不连续触发：默认保留 30% 通过率，测试 Bot 可调到 1.0。
        contact_probability = self.config.contact_probability
        if contact_probability < 1.0 and random.random() > contact_probability:
            logger.debug(
                f"[ProactiveEngine] 不连续触发检查，未通过矜持概率({contact_probability})"
            )
            return None

        # LLM 判断
        decision = await self.should_contact()

        if not decision.should_contact:
            logger.debug(f"[ProactiveEngine] 不应联系: {decision.reason}")
            return None

        # 生成消息
        message = await self.generate_message(decision.reason)

        # 发送并更新状态
        sent = await self._send_proactive_message(message)
        return message if sent else None

    async def _send_proactive_message(self, message: str, target: dict | None = None) -> bool:
        """发送主动消息并更新状态"""
        message = str(message or "").strip()
        parsed_message = self._parse_structured_message(message)
        if parsed_message:
            message = parsed_message
        elif self._looks_like_structured_message_payload(message):
            logger.warning("[ProactiveEngine] 主动消息疑似结构化内容未解析，使用 fallback")
            message = self._get_fallback_message("with_topic")
        elif not message:
            message = self._get_fallback_message("with_topic")

        if not self._platform_sender:
            logger.warning(f"[ProactiveEngine] 未配置 platform_sender，消息未发送: {message[:50]}...")
            return False

        record_context = self._record_context_from_target(target)
        try:
            if target is not None:
                try:
                    sent = await self._platform_sender(message, target=target)
                except TypeError:
                    sent = await self._platform_sender(message)
            else:
                sent = await self._platform_sender(message)
            if sent is False:
                logger.warning(f"[ProactiveEngine] 平台返回发送失败: {message[:50]}...")
                return False
        except Exception as e:
            logger.error(f"[ProactiveEngine] 发送主动消息失败: {e}")
            return False

        self.state.increment_proactive()
        # Bot 主动发消息后，用户没回复则增加未回复计数
        self.state.unreplied_count = self.state.unreplied_count + 1

        # 设置冷却（根据最小间隔）
        cooldown_end = datetime.now() + timedelta(hours=self.config.min_interval_hours)
        self.state.set_cooldown("idle_reminder", cooldown_end)

        logger.info(f"[ProactiveEngine] 主动消息已发送: {message[:50]}...")
        await self._record_sent_message(message, record_context=record_context)
        return True

    async def _record_sent_message(self, message: str, record_context: dict | None = None):
        if not self.memory:
            self._next_record_context = None
            return
        context = dict(self._next_record_context or record_context or {
            "platform": getattr(self.config, "platform_type", "proactive") or "proactive",
            "session_id": getattr(self.memory, "_session_id", None),
            "user_id": getattr(self.memory, "user_id", "default_user"),
            "channel_type": "proactive",
        })
        self._next_record_context = None
        metadata = context.get("metadata") if isinstance(context.get("metadata"), dict) else {}
        context["metadata"] = {
            **metadata,
            "proactive": True,
            "assistant_initiated": True,
            "proactive_kind": metadata.get("proactive_kind") or "idle_reminder",
        }
        try:
            await self.memory.record_assistant_message(message, turn_context=context)
        except Exception as exc:
            logger.warning("[ProactiveEngine] 主动消息已发送，但写入记忆失败: %s", exc)

    def _record_context_from_target(self, target: dict | None) -> dict | None:
        if not isinstance(target, dict):
            return None
        metadata = target.get("metadata") if isinstance(target.get("metadata"), dict) else {}
        context = {
            "platform": str(target.get("platform") or getattr(self.config, "platform_type", "proactive") or "proactive"),
            "session_id": getattr(self.memory, "_session_id", None) if self.memory else None,
            "user_id": getattr(self.memory, "user_id", "default_user") if self.memory else "default_user",
            "channel_type": str(target.get("channel_type") or "proactive"),
            "chat_id": target.get("chat_id"),
            "metadata": dict(metadata),
        }
        return context

    def on_user_message_received(self, has_real_content: bool = True):
        """用户发消息时调用

        Args:
            has_real_content: 用户消息是否有实质内容
                              True=真正回复，清除冷却
                              False=只是戳一下，缩短冷却
        """
        self.state.on_user_message()
        # 记录用户活跃时间
        self.state.record_user_activity()

        # 根据是否真正回复决定冷却策略
        if has_real_content:
            # 真正回复，清除冷却
            self.state.clear_cooldown("idle_reminder")
            # 用户真正回复了，重置未回复计数
            self.state.unreplied_count = 0
            # 清除冷落重新激活标记（已经重新激活了）
            self.state.just_reactivated = False
        else:
            # 只是戳一下，缩短冷却2小时
            self.state.decrement_cooldown("idle_reminder", hours=2)

    def get_status(self) -> dict:
        """获取当前状态（供调试/显示用）"""
        return {
            "mode": self.config.mode,
            "is_active": self.config.is_active,
            "last_message_time": self.state.last_message_time.isoformat() if self.state.last_message_time else None,
            "last_proactive_time": self.state.last_proactive_time.isoformat() if self.state.last_proactive_time else None,
            "annoyance_level": self.state.annoyance_level,
            "today_proactive_count": self.state.today_proactive_count,
            "total_proactive_sent": self.state.total_proactive_sent,
            "idle_hours": round(self._calc_idle_hours(), 1),
        }
