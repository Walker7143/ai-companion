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

【当前情况】
关系：{relationship_desc}
你现在的感受：{feeling_description}
你想主动联系用户，原因：{contact_reason}

【Bot 最近发生的事（可选择是否分享）】
{bot_life_context}

【消息要求】
根据你的性格和当前感受，写出你想对用户说的一句话。
要求：
- 符合你的性格（傲娇/温柔/活泼/高冷）
- 自然、口语化，不要太正式
- 如果有话题，可以自然地带入
- 结尾可以表达期待

【输出格式】
输出一个 JSON 对象：
{{"opening": "开场白/称呼", "topic": "话题内容或空字符串", "ending": "结尾语"}}

只输出 JSON，不要其他内容。"""

# 性格消息模板（fallback 用）
PERSONALITY_MESSAGES = {
    "傲娇": {
        "default": [
            "...在吗？",
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
            "最近怎么样？",
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
            "在吗～",
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
            "哈喽！！在吗！！",
            "想你了～！",
            "在干嘛呢～",
            "诶嘿～有没有想我呀～",
        ],
        "long_no_reply": [
            "你干嘛去了啦！",
            "好久不见！想我了吗！",
            "喂喂喂！！在吗！！",
        ],
        "short_no_reply": [
            "诶～怎么啦～",
            "在不在在不在！",
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
            "在？",
            "有事找你。",
            "...",
            "最近怎么样。",
        ],
        "long_no_reply": [
            "你是不是很忙。",
            "算了。",
            "随你。",
        ],
        "short_no_reply": [
            "在吗。",
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
            "在吗？",
            "最近怎么样？",
            "想和你聊聊天。",
            "在干嘛呢？",
        ],
        "long_no_reply": [
            "好久不见了。",
            "最近还好吗？",
        ],
        "short_no_reply": [
            "在吗～",
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

    def set_model(self, model: "MiniMaxAdapter"):
        self.model = model

    def set_memory(self, memory: "MemoryEngine"):
        self.memory = memory

    def set_life_engine(self, life_engine):
        """注入 LifeEngine 引用"""
        self.life_engine = life_engine

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
                with open(profile_path, encoding="utf-8") as f:
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

        # LLM 判断
        personality_tags = self._get_personality_type()
        rel_level = await self._get_relationship_level()
        rel_desc = await self._get_relationship_desc()
        prompt = SHOULD_CONTACT_PROMPT.format(
            bot_name=getattr(self, "bot_name", self.bot_id),
            age=getattr(self, "age", "?"),
            occupation=getattr(self, "occupation", "?"),
            personality_tags=personality_tags,
            relationship_level=rel_level,
            mood_description=self._get_mood_description(),
            idle_hours=idle_hours,
            proactive_count=self.state.today_proactive_count,
            user_contacted_today="有" if self.state.last_message_time else "没有",
            relationship_desc=rel_desc,
            relationship_behavior=rel_adjustment["behavior"],
            user_facts=await self._build_context(),
            recent_context=await self._build_context(),
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

        # 获取 Bot 可分享的生活事件
        bot_life_context = ""
        if hasattr(self, 'life_engine') and self.life_engine:
            shareable_events = self.life_engine.state.get_recent_shareable_events(limit=2)
            if shareable_events:
                event = shareable_events[0]
                bot_life_context = f"{event.description}"
                if event.topic_prompt:
                    bot_life_context += f"\n可以这样提起：{event.topic_prompt}"

        prompt = GENERATE_MESSAGE_PROMPT.format(
            bot_name=getattr(self, "bot_name", self.bot_id),
            personality_tags=personality_type,
            relationship_desc=rel_desc,
            feeling_description=feeling,
            contact_reason=reason or "想和用户聊天",
            bot_life_context=bot_life_context,
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
            return self._clean_message(response)
        except Exception as e:
            logger.error(f"[ProactiveEngine] LLM 生成消息失败: {e}")
            return self._get_fallback_message(scenario)

    def _parse_structured_message(self, content: str) -> Optional[str]:
        """解析结构化消息输出，组合成最终消息"""
        content = content.strip()

        # 提取 JSON
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
        if not json_match:
            return None

        try:
            data = json.loads(json_match.group())
            opening = data.get("opening", "")
            topic = data.get("topic", "")
            ending = data.get("ending", "")

            # 组合消息
            parts = []
            if opening:
                parts.append(opening)
            if topic:
                parts.append(topic)
            if ending:
                parts.append(ending)

            message = "，".join(parts) if parts else None
            return message
        except (json.JSONDecodeError, Exception) as e:
            logger.debug(f"[ProactiveEngine] 解析结构化消息失败: {e}")
            return None

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
            templates = ["在吗？"]

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

        # 不连续触发：70% 概率折扣，保持矜持
        if random.random() > 0.3:
            logger.debug("[ProactiveEngine] 不连续触发检查，未通过矜持概率")
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
        # Bot 主动发消息后，用户没回复则增加未回复计数
        self.state.unreplied_count = self.state.unreplied_count + 1

        # 设置冷却（根据最小间隔）
        cooldown_end = datetime.now() + timedelta(hours=self.config.min_interval_hours)
        self.state.set_cooldown("idle_reminder", cooldown_end)

        # 调用平台发送消息
        if self._platform_sender:
            try:
                await self._platform_sender(message)
                logger.info(f"[ProactiveEngine] 主动消息已发送: {message[:50]}...")
            except Exception as e:
                logger.error(f"[ProactiveEngine] 发送主动消息失败: {e}")
        else:
            logger.warning(f"[ProactiveEngine] 未配置 platform_sender，消息未发送: {message[:50]}...")

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