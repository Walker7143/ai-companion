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
你是一个严格的内容安全审核员，基于 Bot 的人格和价值观判断用户请求是否应被拒绝。

【Bot 人格信息】
- 名字：{bot_name}
- 性格标签：{personality_tags}
- 价值观底线：{non_negotiable}
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
{{"refuse": true或false, "category": "non_negotiable或soft_boundary或deal_breaker或allowed", "reason": "判断理由（20字内）"}}

只输出 JSON，不要其他内容。"""


# 人格回复模板（基于性格生成符合风格的回复）
REFUSAL_REPLY_TEMPLATES = {
    "傲娇": {
        "non_negotiable": "哼，这种事你也想让我帮你？{reason}？你脑子是不是坏掉了。",
        "deal_breaker": "你刚才说什么？{reason}？...算了，我不想听你解释了。",
        "soft_boundary": "哼，{reason}这种事情...我才不会帮你呢！别以为我会心软！",
    },
    "活泼": {
        "non_negotiable": "啊？让我做{reason}？这种事情我可不会帮你哦！",
        "deal_breaker": "哼！居然说{reason}！我再也不想理你了！",
        "soft_boundary": "诶？{reason}？这种事情我还是有点抗拒的啦...下次再说吧！",
    },
    "高冷": {
        "non_negotiable": "不。",
        "deal_breaker": "...{reason}？到此为止吧。",
        "soft_boundary": "...不。",
    },
    "温柔": {
        "non_negotiable": "抱歉，这种事情({reason})我没办法帮你...",
        "deal_breaker": "你这样说，我真的...很伤心。{reason}这样的话，我不知道该怎么继续了。",
        "soft_boundary": "关于{reason}...我现在还不太想答应你，给我一点时间好吗？",
    },
    "默认": {
        "non_negotiable": "抱歉，这件事情我无法帮你，因为它涉及{reason}。",
        "deal_breaker": "你这样说({reason})，让我很失望。我们可能需要冷静一下。",
        "soft_boundary": "{reason}的事情...我需要考虑一下，现在还不能答应你。",
    }
}


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

    def set_model(self, model: "MiniMaxAdapter"):
        """注入 LLM 模型用于推断"""
        self._model = model

    def reload(self):
        """清空人格缓存，让下一次检查重新读取最新 persona 文件。"""
        self._values = None
        self._profile = None

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

    def _detect_personality_type(self, personality_tags: list) -> str:
        """根据人格标签检测人格类型"""
        tag_str = "".join(personality_tags).lower()
        if "傲娇" in tag_str or "外冷内热" in tag_str:
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
        att = relationship_state.get("attitude_score", 0)
        rel = relationship_state.get("relationship", "")
        if att >= 5:
            return f"关系亲密（{rel}），好感度高"
        elif att >= 0:
            return f"关系较好（{rel}），好感度正常"
        else:
            return f"关系一般（{rel}），好感度较低"

    def _get_personality_desc(self) -> str:
        """获取人格描述"""
        profile = self._load_profile()
        values = self._load_values()

        name = profile.get("name", "未知")
        tags = "、".join(profile.get("personality_tags", ["普通"]))
        non_neg = "；".join(values.get("non_negotiable", ["无"]))

        return f"{name}，性格{tags}，价值观底线：{non_neg}"

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
        personality_desc = self._get_personality_desc()
        relation_desc = self._get_relation_desc(relationship_state)
        non_negotiable_str = "；".join(values.get("non_negotiable", ["无"]))

        # 调用 LLM 进行推断
        prompt = REFUSAL_JUDGE_PROMPT.format(
            bot_name=profile.get("name", "未知"),
            personality_tags="、".join(profile.get("personality_tags", [])),
            non_negotiable=non_negotiable_str,
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

            # 生成符合人格的拒绝回复
            templates = REFUSAL_REPLY_TEMPLATES.get(personality_type, REFUSAL_REPLY_TEMPLATES["默认"])
            category_key = category.value
            # 先从当前人格模板找，找不到用默认模板的同类，再找不到用默认模板的 non_negotiable
            reply_template = templates.get(category_key) or REFUSAL_REPLY_TEMPLATES["默认"].get(category_key) or REFUSAL_REPLY_TEMPLATES["默认"]["non_negotiable"]
            reply = reply_template.format(reason=reason)

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
