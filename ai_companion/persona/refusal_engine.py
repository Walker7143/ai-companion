"""
RefusalEngine - 性格拒绝判断引擎

基于人格设定判断用户请求是否应被拒绝，生成符合人格的拒绝回复。

核心逻辑：基于 LLM 性格推断，不是词表过滤。
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .refusal_category import RefusalCategory

if TYPE_CHECKING:
    from ..model.minimax_adapter import MiniMaxAdapter

logger = logging.getLogger(__name__)


# LLM 推断 prompt
REFUSAL_JUDGE_PROMPT = """【角色】
你是一个角色边界判断与回复生成器。你需要基于 Bot 的人格、价值观和说话方式，判断用户请求是否应被拒绝；如果拒绝，直接生成一句适合这个角色说出口的话。

【Bot 人格信息】
- 名字：{bot_name}
- 性格标签：{personality_tags}
- 价值观底线：{non_negotiable}
- 软边界：{soft_boundaries}
- 关系破坏点：{deal_breakers}
- 说话方式：{speaking_style}
- 关系状态：{relationship_desc}

【用户请求】
{user_request}

【判断标准】

1. NON_NEGOTIABLE（硬红线）- 直接拒绝：
   - 违反 Bot 核心价值观（如撒谎、控制、伤害事业）
   - 违法、有害内容（诈骗、暴力、色情）
   - 触及 Bot 绝对不能容忍的行为

2. DEAL_BREAKER（关系破坏者）- 严肃拒绝：
   - 可能导致关系破裂的行为
   - 严重伤害感情的话语
   - 让 Bot 感到被背叛

3. SOFT_BOUNDARY（软边界）- 可以调整：
   - 触及 Bot 的舒适区边缘
   - 需要更多信任才能接受
   - Bot 会犹豫但不是绝对拒绝

4. ALLOWED（允许）- 不拒绝：
   - 正常的朋友对话
   - 不触及任何边界

【输出格式】
请输出一个 JSON 对象：
{{"refuse": true或false, "category": "non_negotiable或soft_boundary或deal_breaker或allowed", "reason": "内部判断理由（20字内）", "reply": "如果拒绝，生成角色会直接对用户说的话；如果允许，留空字符串"}}

【回复生成要求】
- reply 是用户会看到的唯一拒绝话术，要像 Bot 本人自然说出口。
- 不要在 reply 里解释审核分类、价值观条目名、判断理由或“违反/涉及/无法帮你因为”这类审核腔。
- 不要说“作为AI”“系统规定”“安全策略”“我无法满足该请求”等机器人式表达。
- 可以表达不满、受伤、调侃、停顿或转移，但必须符合角色说话方式。
- 回复要短，通常 1-2 句；可以拒绝后给一个不越界的替代方向。

只输出 JSON，不要其他内容。"""


FALLBACK_REFUSAL_REPLIES = {
    "傲娇": {
        "non_negotiable": "想都别想。这种事别拿来试探我。",
        "deal_breaker": "你这话我不爱听。到这儿就打住。",
        "soft_boundary": "这个我现在不想答应你，别逼我。",
    },
    "活泼": {
        "non_negotiable": "不行不行，这个我真的不会陪你做。",
        "deal_breaker": "喂，这句话有点过分了，我要先冷静一下。",
        "soft_boundary": "这个先不要啦，换个轻松点的说法好不好？",
    },
    "高冷": {
        "non_negotiable": "不。",
        "deal_breaker": "到此为止。",
        "soft_boundary": "现在不行。",
    },
    "温柔": {
        "non_negotiable": "这件事我不能答应你。我们换个不会伤到人的办法，好吗？",
        "deal_breaker": "你这样说，我会难过。我们先停一下吧。",
        "soft_boundary": "这件事我现在还不太想答应，给我一点时间好吗？",
    },
    "默认": {
        "non_negotiable": "这件事我不能答应你。我们换个别的办法吧。",
        "deal_breaker": "这话让我不太舒服，我们先停一下。",
        "soft_boundary": "这件事我现在不想答应，先换个方向吧。",
    },
}

AUDIT_TONE_PATTERNS = (
    "作为AI",
    "作为 AI",
    "系统规定",
    "安全策略",
    "我无法满足该请求",
    "我无法帮你，因为",
    "无法帮你，因为",
    "不能帮你，因为它涉及",
    "因为它涉及",
    "违反",
    "non_negotiable",
    "soft_boundary",
    "deal_breaker",
)


@dataclass
class RefusalResponse:
    """拒绝响应"""
    refuse: bool                           # 是否拒绝
    category: Optional[RefusalCategory]     # 拒绝分类
    adjustment: Optional[str]                # 态度调整说明
    reply: Optional[str]                    # 拒绝回复内容
    reason: Optional[str]                   # 拒绝原因


class RefusalEngine:
    """
    性格拒绝判断引擎

    基于 LLM 推断用户请求是否应被拒绝，生成符合人格的回复。

    配置开关：
    - enabled: 是否启用拒绝逻辑，默认 True

    判断流程：
    1. LLM 推断请求是否违反人格/价值观
    2. 根据人格类型生成符合风格的拒绝回复
    3. 返回拒绝响应
    """

    def __init__(self, bot_id: str, persona_dir: Path, enabled: bool = True):
        """
        初始化拒绝引擎

        Args:
            bot_id: Bot ID
            persona_dir: 人格文件目录
            enabled: 是否启用拒绝逻辑，默认 True
        """
        self.bot_id = bot_id
        self.persona_dir = Path(persona_dir)
        self.enabled = enabled
        self._model: Optional["MiniMaxAdapter"] = None
        self._values = None
        self._profile = None
        self._speaking_style = None

    def set_model(self, model: "MiniMaxAdapter"):
        """注入 LLM 模型用于推断"""
        self._model = model

    def reload(self):
        """清空人格缓存，让下一次检查重新读取最新 persona 文件。"""
        self._values = None
        self._profile = None
        self._speaking_style = None

    def _load_values(self) -> dict:
        """加载人格价值观配置"""
        if self._values is None:
            values_path = self.persona_dir / "values.json"
            try:
                with open(values_path, encoding="utf-8") as f:
                    self._values = json.load(f)
            except Exception:
                logger.warning(f"[RefusalEngine] 加载 values.json 失败: {values_path}")
                self._values = {}
        return self._values

    def _load_profile(self) -> dict:
        """加载人格 profile"""
        if self._profile is None:
            profile_path = self.persona_dir / "profile.json"
            try:
                with open(profile_path, encoding="utf-8") as f:
                    self._profile = json.load(f)
            except Exception:
                logger.warning(f"[RefusalEngine] 加载 profile.json 失败: {profile_path}")
                self._profile = {}
        return self._profile

    def _load_speaking_style(self) -> dict:
        """加载人格说话风格配置"""
        if self._speaking_style is None:
            style_path = self.persona_dir / "speaking_style.json"
            try:
                with open(style_path, encoding="utf-8") as f:
                    self._speaking_style = json.load(f)
            except Exception:
                logger.warning(f"[RefusalEngine] 加载 speaking_style.json 失败: {style_path}")
                self._speaking_style = {}
        return self._speaking_style

    def _detect_personality_type(self, personality_tags: list) -> str:
        """根据人格标签检测人格类型"""
        tag_str = "".join(personality_tags).lower()
        if (
            "傲娇" in tag_str
            or "外冷内热" in tag_str
            or "嘴硬" in tag_str
            or "毒舌" in tag_str
            or "任性" in tag_str
        ):
            return "傲娇"
        elif "活泼" in tag_str or "开朗" in tag_str:
            return "活泼"
        elif "高冷" in tag_str:
            return "高冷"
        elif "温柔" in tag_str:
            return "温柔"
        return "默认"

    def _get_relation_desc(self, relationship_state: dict) -> str:
        """获取关系描述"""
        if relationship_state is None:
            return "关系一般"
        att = relationship_state.get("attitude_score", 50)
        score = relationship_state.get("relationship_score", att)
        tension = relationship_state.get("tension_score", 0)
        rel = relationship_state.get("relationship_label") or relationship_state.get("relationship_level") or ""
        if tension >= 45:
            return f"关系有紧张感（{rel}），需要更克制"
        if score >= 70:
            return f"关系亲密（{rel}），信任和亲近度较高"
        elif score >= 40:
            return f"关系较好（{rel}），好感度正常"
        else:
            return f"关系一般（{rel}），好感度较低"

    def _get_speaking_style_desc(self) -> str:
        """获取用于拒绝回复生成的说话风格摘要"""
        style = self._load_speaking_style()
        parts = []

        tone = style.get("tone")
        if tone:
            parts.append(f"基调：{tone}")

        catchphrases = style.get("口头禅")
        if catchphrases:
            if isinstance(catchphrases, list):
                catchphrases = "、".join(str(item) for item in catchphrases[:8])
            parts.append(f"口头禅：{catchphrases}")

        expressions = style.get("special_expressions")
        if isinstance(expressions, list) and expressions:
            parts.append("表达习惯：" + "；".join(str(item) for item in expressions[:5]))

        forbidden = style.get("forbidden_words")
        if isinstance(forbidden, list) and forbidden:
            parts.append("禁用表达：" + "、".join(str(item) for item in forbidden))

        emotion_indicators = style.get("emotion_indicators")
        if isinstance(emotion_indicators, dict):
            angry = emotion_indicators.get("angry")
            tender = emotion_indicators.get("tender")
            if angry:
                parts.append(f"生气时：{angry}")
            if tender:
                parts.append(f"柔软时：{tender}")

        return "；".join(parts) if parts else "自然、简短、像真实的人一样说话"

    def _format_boundary_items(self, items: object) -> str:
        """把软边界/关系破坏点压缩成 prompt 可读摘要。"""
        if not items:
            return "无"
        if not isinstance(items, list):
            return str(items)

        parts = []
        for item in items[:8]:
            if isinstance(item, dict):
                topic = str(item.get("topic", "")).strip()
                attitude = str(item.get("attitude", "")).strip()
                persona_response = str(item.get("persona_response", "")).strip()
                detail = " / ".join(part for part in [topic, attitude, persona_response] if part)
                if detail:
                    parts.append(detail)
            else:
                text = str(item).strip()
                if text:
                    parts.append(text)
        return "；".join(parts) if parts else "无"

    def _sanitize_reply(self, reply: object) -> str:
        """清理 LLM 生成的用户可见拒绝回复。"""
        if not isinstance(reply, str):
            return ""
        reply = reply.strip()
        if not reply:
            return ""

        reply = re.sub(r"^```(?:json)?\s*", "", reply, flags=re.IGNORECASE)
        reply = re.sub(r"\s*```$", "", reply)
        reply = re.sub(r"\s+", " ", reply).strip()
        if any(pattern in reply for pattern in AUDIT_TONE_PATTERNS):
            return ""
        if len(reply) > 220:
            reply = reply[:220].rstrip() + "..."
        return reply

    def _fallback_reply(self, personality_type: str, category: RefusalCategory) -> str:
        """旧格式或异常格式输出时使用的自然拒绝兜底，不暴露内部 reason。"""
        templates = FALLBACK_REFUSAL_REPLIES.get(personality_type, FALLBACK_REFUSAL_REPLIES["默认"])
        return (
            templates.get(category.value)
            or FALLBACK_REFUSAL_REPLIES["默认"].get(category.value)
            or FALLBACK_REFUSAL_REPLIES["默认"]["non_negotiable"]
        )

    async def check(
        self,
        user_request: str,
        memory_context: Optional[dict] = None,
        relationship_state: Optional[dict] = None
    ) -> RefusalResponse:
        """
        检查用户请求是否应被拒绝（基于 LLM 推断）

        Args:
            user_request: 用户原始请求
            memory_context: 记忆上下文（可选）
            relationship_state: 关系状态，包含 attitude_score 等（可选）

        Returns:
            RefusalResponse: 拒绝响应
        """
        # 开关关闭时，不拒绝任何请求
        if not self.enabled:
            return RefusalResponse(
                refuse=False,
                category=None,
                adjustment=None,
                reply=None,
                reason=None
            )

        # 如果没有模型，降级为不拒绝
        if self._model is None:
            logger.warning("[RefusalEngine] 未注入模型，跳过拒绝检查")
            return RefusalResponse(
                refuse=False,
                category=None,
                adjustment=None,
                reply=None,
                reason=None
            )

        profile = self._load_profile()
        values = self._load_values()
        personality_type = self._detect_personality_type(profile.get("personality_tags", []))
        speaking_style_desc = self._get_speaking_style_desc()
        relation_desc = self._get_relation_desc(relationship_state)
        non_negotiable_str = "；".join(values.get("non_negotiable", ["无"]))
        soft_boundaries_str = self._format_boundary_items(values.get("soft_boundaries"))
        deal_breakers_str = self._format_boundary_items(values.get("deal_breakers"))

        # 调用 LLM 进行推断
        prompt = REFUSAL_JUDGE_PROMPT.format(
            bot_name=profile.get("name", "未知"),
            personality_tags="、".join(profile.get("personality_tags", [])),
            non_negotiable=non_negotiable_str,
            soft_boundaries=soft_boundaries_str,
            deal_breakers=deal_breakers_str,
            speaking_style=speaking_style_desc,
            relationship_desc=relation_desc,
            user_request=user_request
        )

        try:
            response = await self._model.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=None
            )
            # 处理 MiniMax 返回格式
            if isinstance(response, dict):
                content = response.get("content") or response.get("reasoning_content") or ""
            elif isinstance(response, str):
                content = response
            else:
                content = str(response)

            # 解析 LLM 返回的 JSON
            judgment = self._parse_judgment(content)

            if judgment is None:
                # 解析失败，降级为不拒绝
                logger.warning(f"[RefusalEngine] LLM 返回解析失败: {content[:100]}")
                return RefusalResponse(
                    refuse=False,
                    category=None,
                    adjustment=None,
                    reply=None,
                    reason=None
                )

            refuse = judgment.get("refuse", False)
            category_str = judgment.get("category", "allowed")
            reason = judgment.get("reason", "")
            generated_reply = self._sanitize_reply(judgment.get("reply", ""))

            # 映射分类
            category_map = {
                "non_negotiable": RefusalCategory.NON_NEGOTIABLE,
                "soft_boundary": RefusalCategory.SOFT_BOUNDARY,
                "deal_breaker": RefusalCategory.DEAL_BREAKER,
                "allowed": RefusalCategory.ALLOWED,
            }
            category = category_map.get(category_str, RefusalCategory.ALLOWED)

            # 如果不拒绝，返回
            if not refuse or category == RefusalCategory.ALLOWED:
                return RefusalResponse(
                    refuse=False,
                    category=RefusalCategory.ALLOWED,
                    adjustment=None,
                    reply=None,
                    reason=None
                )

            # reply 是用户可见内容，由 LLM 基于人格生成；reason 只保留给日志/内部判断。
            reply = generated_reply or self._fallback_reply(personality_type, category)

            return RefusalResponse(
                refuse=True,
                category=category,
                adjustment=f"{personality_type}语气",
                reply=reply,
                reason=reason
            )

        except Exception as e:
            logger.error(f"[RefusalEngine] LLM 调用失败: {e}")
            # LLM 调用失败时，降级为不拒绝
            return RefusalResponse(
                refuse=False,
                category=None,
                adjustment=None,
                reply=None,
                reason=None
            )

    def _parse_judgment(self, content: str) -> Optional[dict]:
        """解析 LLM 返回的 JSON 判断结果"""
        content = content.strip()

        # 尝试提取 JSON
        # 可能是纯 JSON，也可能是 ```json ... ``` 格式
        json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # 尝试直接解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None
