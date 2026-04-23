"""
ProactiveEngine - 主动唤醒引擎（LLM 推理）

核心功能：
1. 判断是否应该主动联系用户（LLM 推理）
2. 生成符合人格的主动消息（LLM 生成）
3. 管理主动消息的发送（限流、冷却）
"""

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..model.minimax_adapter import MiniMaxAdapter
    from ..memory.engine import MemoryEngine

logger = logging.getLogger(__name__)


# LLM 判断 Prompt
SHOULD_CONTACT_PROMPT = """【角色】
你是{bot_name}，{age}岁，{occupation}。
性格特点：{personality_tags}
你和一个用户保持着友谊/恋爱关系。

【当前状态】
关系深度等级：{relationship_level}/10（1=刚认识，5=普通朋友，8=好朋友，10=恋人）
你的心情状态：{mood_description}
距离上次聊天：{idle_hours:.1f}小时
今天你已经主动联系过几次：{proactive_count}次
用户今天有没有主动联系过你：{user_contacted_today}
已发送给用户的主动消息数（今天）：{proactive_count}/5

【用户相关信息】
你们的关系描述：{relationship_desc}
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

【当前情况】
关系：{relationship_desc}
你现在的感受：{feeling_description}
你想主动联系用户，原因：{contact_reason}

【消息要求】
根据你的性格和当前感受，写出你想对用户说的一句话。
要求：
- 符合你的性格（傲娇/温柔/活泼/高冷）
- 自然、口语化，不要太正式
- 1-3句话即可
- 不要太长

直接输出消息内容，不要加引号或解释。"""

# 性格消息模板（fallback 用）
PERSONALITY_MESSAGES = {
    "傲娇": [
        "...在吗？",
        "你是不是把我忘了？",
        "哼，这么久不联系我。",
        "...算了，没什么。",
    ],
    "温柔": [
        "最近怎么样？",
        "在忙什么呀？",
        "想你了～",
        "今天过得顺利吗？",
    ],
    "活泼": [
        "哈喽！！在吗！！",
        "想你了～！",
        "在干嘛呢～",
        "诶嘿～有没有想我呀～",
    ],
    "高冷": [
        "在？",
        "有事找你。",
        "...",
        "最近怎么样。",
    ],
    "默认": [
        "在吗？",
        "最近怎么样？",
        "想和你聊聊天。",
        "在干嘛呢？",
    ],
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

    def set_model(self, model: "MiniMaxAdapter"):
        self.model = model

    def set_memory(self, memory: "MemoryEngine"):
        self.memory = memory

    def _get_mood_description(self) -> str:
        """根据生气级别描述心情"""
        level = self.state.annoyance_level
        if level >= 7:
            return "有点失落和不满，觉得用户不够关心自己"
        elif level >= 4:
            return "有点冷淡，但还没完全放弃"
        elif level >= 1:
            return "稍微有点不开心"
        else:
            return "心情不错，想和用户聊天"

    def _get_relationship_level(self) -> int:
        """从 relationship_to_user 估计关系等级"""
        if self.memory is None:
            return 5  # 默认普通朋友
        try:
            import asyncio
            facts = asyncio.get_event_loop().run_until_complete(
                self.memory.semantic.get_all_facts()
            )
            relationship = facts.get("relationship_to_user", "普通朋友")
            # 简单映射
            mapping = {
                "陌生网友": 1,
                "普通朋友": 4,
                "好朋友": 7,
                "暧昧中": 8,
                "恋人": 10,
            }
            return mapping.get(relationship, 5)
        except Exception:
            return 5

    def _get_relationship_desc(self) -> str:
        """获取关系描述"""
        if self.memory is None:
            return "普通朋友"
        try:
            import asyncio
            facts = asyncio.get_event_loop().run_until_complete(
                self.memory.semantic.get_all_facts()
            )
            return facts.get("relationship_to_user", "普通朋友")
        except Exception:
            return "普通朋友"

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
                recent = await self.memory.working.get_recent_messages(count=6)
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
                facts = await self.memory.semantic.get_all_facts()
                if facts:
                    lines.append("\n用户的事实/偏好：")
                    for k, v in facts.items():
                        lines.append(f"  {k}：{v}")
            except Exception:
                pass

        return "\n".join(lines) if lines else "最近没什么特别的对话"

    def _get_personality_type(self) -> str:
        """从 personality_tags 检测性格类型"""
        if self.memory is None:
            return self.personality_type or "默认"
        try:
            import asyncio
            # 尝试从 profile.json 读取
            profile_path = Path(self.memory.persona_backstory_path).parent / "profile.json"
            if profile_path.exists():
                with open(profile_path) as f:
                    profile = json.load(f)
                tags = "".join(profile.get("personality_tags", []))
                if "傲娇" in tags or "外冷内热" in tags:
                    return "傲娇"
                elif "活泼" in tags or "开朗" in tags:
                    return "活泼"
                elif "高冷" in tags:
                    return "高冷"
                elif "温柔" in tags:
                    return "温柔"
        except Exception:
            pass
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

        # 检查时间
        idle_hours = self._calc_idle_hours()
        if idle_hours < self.config.idle_threshold_hours:
            return ProactiveDecision(False, f"还没到触发时间({idle_hours:.1f}h)")

        # LLM 判断
        personality_tags = self._get_personality_type()
        prompt = SHOULD_CONTACT_PROMPT.format(
            bot_name=getattr(self, "bot_name", self.bot_id),
            age=getattr(self, "age", "?"),
            occupation=getattr(self, "occupation", "?"),
            personality_tags=personality_tags,
            relationship_level=self._get_relationship_level(),
            mood_description=self._get_mood_description(),
            idle_hours=idle_hours,
            proactive_count=self.state.today_proactive_count,
            user_contacted_today="有" if self.state.last_message_time else "没有",
            relationship_desc=self._get_relationship_desc(),
            user_facts=await self._build_context(),
            recent_context=await self._build_context(),
            idle_threshold=self.config.idle_threshold_hours,
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
        if self.model is None:
            return self._get_fallback_message()

        personality_type = self._get_personality_type()
        feeling = self._get_mood_description()

        prompt = GENERATE_MESSAGE_PROMPT.format(
            bot_name=getattr(self, "bot_name", self.bot_id),
            personality_tags=personality_type,
            relationship_desc=self._get_relationship_desc(),
            feeling_description=feeling,
            contact_reason=reason or "想和用户聊天",
        )

        try:
            response = await self.model.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=None
            )
            return self._clean_message(response)
        except Exception as e:
            logger.error(f"[ProactiveEngine] LLM 生成消息失败: {e}")
            return self._get_fallback_message()

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

    def _get_fallback_message(self) -> str:
        """获取 fallback 消息（性格模板）"""
        personality_type = self._get_personality_type()
        templates = PERSONALITY_MESSAGES.get(personality_type, PERSONALITY_MESSAGES["默认"])
        # 简单选择第一个
        return templates[0]

    async def check_and_maybe_remind(self) -> Optional[str]:
        """检查并可能发送主动消息，返回消息内容或 None"""
        # 前置检查
        if not self.config.is_active:
            return None

        if self.state.annoyance_level >= 9:
            return None

        if self.state.today_proactive_count >= self.config.max_daily:
            return None

        # LLM 判断
        decision = await self.should_contact()

        if not decision.should_contact:
            logger.debug(f"[ProactiveEngine] 不应联系: {decision.reason}")
            return None

        # 生成消息
        message = await self.generate_message(decision.reason)

        # 发送并更新状态
        await self._send_proactive_message(message)

        return message

    async def _send_proactive_message(self, message: str):
        """发送主动消息并更新状态"""
        self.state.increment_proactive()

        # 设置冷却（根据最小间隔）
        cooldown_end = datetime.now() + timedelta(hours=self.config.min_interval_hours)
        self.state.set_cooldown("idle_reminder", cooldown_end)

        logger.info(f"[ProactiveEngine] 发送主动消息: {message[:50]}...")

    def on_user_message_received(self):
        """用户发消息时调用"""
        self.state.on_user_message()
        # 清除主动联系冷却（用户主动联系后，更新触发意愿）
        self.state.clear_cooldown("idle_reminder")

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