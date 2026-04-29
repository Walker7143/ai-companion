# 人生轨迹系统优化方案

## 概述

优化 Bot 的人生轨迹系统，使其能够"真正活过"每一天，综合考虑：
- 季节变化（春夏秋冬）
- 节假日（春节、中秋、圣诞等）
- 生日自动触发
- 年龄里程碑（中考、高考、毕业等）
- 职业背景和人生阶段
- 事件生成后的用户交互

---

## Part 1: 季节系统

### 1.1 设计目标

模拟真实人生的季节循环，影响：
- 日常事件类型（夏天游泳、冬天滑雪、春天踏青、秋天赏叶）
- Bot 心情状态（夏天可能烦躁，冬天可能慵懒，秋天感慨）
- 主动消息话题（天气变化、节日、季节活动）

### 1.2 季节定义

```python
# 季节定义（北半球）
SEASONS = {
    "春": {"months": [3, 4, 5], "mood_tags": ["温暖", "希望", "慵懒"]},
    "夏": {"months": [6, 7, 8], "mood_tags": ["炎热", "烦躁", "活力"]},
    "秋": {"months": [9, 10, 11], "mood_tags": ["凉爽", "感慨", "收获"]},
    "冬": {"months": [12, 1, 2], "mood_tags": ["寒冷", "慵懒", "期待"]},
}
```

### 1.3 改动文件

| 文件 | 改动 |
|------|------|
| `ai_companion/proactive/life_state.py` | 增加 `current_season`、`current_month`、`birthday_month` |
| `ai_companion/proactive/life_engine.py` | 增加 `get_current_season()`、`_build_life_context()` |
| `ai_companion/proactive/life_scheduler.py` | 每次 tick 更新季节状态 |

---

## Part 2: 年龄里程碑系统

### 2.1 设计目标

支持配置固定年龄事件（中考15岁、高考18岁、毕业22岁、三十岁30岁等），在 Bot 到达对应年龄时自动触发。

### 2.2 里程碑配置（life.json）

```json
{
  "milestones": [
    {"age": 15, "event": "中考", "topic_prompt": "想起当年中考的日子..."},
    {"age": 18, "event": "高考", "topic_prompt": "高考出分了，想起当年..."},
    {"age": 22, "event": "大学毕业", "topic_prompt": "毕业典礼那天..."},
    {"age": 30, "event": "三十岁", "topic_prompt": "三十岁了，感慨时间..."}
  ]
}
```

### 2.3 改动文件

| 文件 | 改动 |
|------|------|
| `ai_companion/proactive/life_config.py` | 增加 `milestones` 列表配置 |
| `ai_companion/proactive/life_state.py` | 增加 `last_checked_age` 追踪 |
| `ai_companion/proactive/life_engine.py` | 增加 `generate_milestone_event()` |
| `ai_companion/proactive/life_scheduler.py` | 检查里程碑触发 |

---

## Part 3: 日期时间线与节假日系统

### 3.1 设计目标

让 Bot 真正"活"在时间里：
- 知道今天是几月几日、星期几
- 知道春节、中秋、端午、圣诞、情人节等节假日
- 每年生日会自动到来
- 随着 time_ratio 流逝，会经历一个个真实的日子

### 3.2 日期状态（life_state.json）

```json
{
  "birth_date": "1998-06-15",
  "current_date": "2024-03-20",
  "day_of_week": "周三",
  "year": 2024,
  "is_weekend": false,
  "current_season": "春",
  "current_month": 3
}
```

### 3.3 节假日配置（life.json）

```json
{
  "holidays": [
    {"name": "元旦", "month": 1, "day": 1, "type": "法定假日"},
    {"name": "春节", "month": 1, "day": 29, "type": "传统节日"},
    {"name": "情人节", "month": 2, "day": 14, "type": "西方节日"},
    {"name": "清明节", "month": 4, "day": 5, "type": "传统节日"},
    {"name": "劳动节", "month": 5, "day": 1, "type": "法定假日"},
    {"name": "端午节", "month": 6, "day": 10, "type": "传统节日"},
    {"name": "中秋节", "month": 9, "day": 17, "type": "传统节日"},
    {"name": "国庆节", "month": 10, "day": 1, "type": "法定假日"},
    {"name": "圣诞节", "month": 12, "day": 25, "type": "西方节日"}
  ]
}
```

### 3.4 生日自动触发

每年到达 `birth_date` 的月日时，自动生成生日事件，无需配置。

### 3.5 改动文件

| 文件 | 改动 |
|------|------|
| `ai_companion/proactive/life_state.py` | 增加 `birth_date`、`current_date`、`day_of_week`、`year`、`is_weekend` |
| `ai_companion/proactive/life_engine.py` | 增加 `_advance_date()`、`_is_holiday()`、`_is_birthday()` |
| `ai_companion/proactive/life_scheduler.py` | 增加 `_check_birthday()` |
| `ai_companion/proactive/life_config.py` | 增加 `holidays` 列表 |

---

## Part 4: 完整上下文整合

### 4.1 事件生成时的完整上下文

```python
context = f"""【Bot 角色】
你是{both_name}，{age_years}岁，职业是{occupation}。
出生日期：{birth_date}，今年 {year} 年

【当前时间背景】
日期：{current_date}，{day_of_week}
季节：{season}（{month}月）
{"节假日：今天是" + holiday["name"] if holiday else ""}
{"今天是小明的生日！" if is_birthday else ""}
人生阶段：{life_stage}
{"周末" if is_weekend else "工作日"}

【Bot 状态】
心情：{bot_mood}
最近事件：{recent_events}
"""
```

### 4.2 人生阶段判断

```python
def _calc_life_stage(age_years: int) -> str:
    if age_years < 15:
        return "少年时期"
    elif age_years < 18:
        return "高中时期"
    elif age_years < 22:
        return "大学时期"
    elif age_years < 30:
        return "职场初期"
    elif age_years < 40:
        return "职场中期"
    elif age_years < 60:
        return "中年时期"
    else:
        return "退休时期"
```

---

## Part 5: profile.json 新增字段

```json
{
  "name": "林晚晴",
  "age": 27,
  "birth_date": "1999-03-12",
  "occupation": "古籍修复师"
}
```

- `birth_date`: 出生日期，用于计算 Bot 当前年龄和生日触发

---

## 改动汇总

### Part 1-5 改动

| 文件 | 改动 |
|------|------|
| `ai_companion/proactive/life_state.py` | +season, +current_month, +birthday_month, +last_checked_age, +birth_date, +current_date, +day_of_week, +year, +is_weekend |
| `ai_companion/proactive/life_engine.py` | +get_current_season(), +_build_life_context(), +generate_milestone_event(), +_advance_date(), +_is_holiday(), +_is_birthday() |
| `ai_companion/proactive/life_scheduler.py` | 每次tick更新季节/日期, +_check_birthday(), 检查里程碑触发 |
| `ai_companion/proactive/life_config.py` | +season.hemisphere, +season.birthday_month, +milestones, +holidays |
| `ai_companion/bot/instance.py` | 从 profile.json 读取 birth_date, initial_age, birthday_month |

### Part 6 改动（事件分享与用户交互）

| 文件 | 改动 |
|------|------|
| `ai_companion/proactive/life_engine.py` | +send_proactive_message(), +_maybe_share_event(), +_build_share_message() |
| `ai_companion/proactive/life_state.py` | +shared_with_user, +user_response, +conversation_id, +shared_at |
| `ai_companion/bot/instance.py` | life_engine.set_proactive_engine(proactive_engine) |

---

## 验证方案

### Part 1-5 验证

1. 设置 `time_ratio=1440`（每分钟=1天）
2. 观察 `current_date` 是否逐日推进，跨月跨年
3. 验证节假日时生成的事件与节日相关（春节生成回家、团圆饭相关事件）
4. 验证 Bot 生日时自动触发生日事件
5. 验证周几/是否周末正确（周末生成逛街、休闲相关事件）
6. 验证 18 岁的 Bot 在夏季生成高考相关事件
7. 验证里程碑（中考、高考、毕业）正确触发

### Part 6 验证（事件分享与用户交互）

8. 生日时 Bot 是否主动发消息给用户
9. 节假日时 Bot 是否分享相关事件
10. 高 importance 事件是否按概率分享
11. attitude_score 越高，分享概率越高
12. 语气随好感度渐变（-10 冷淡 vs +10 亲密）

---

## Part 6: 事件分享与用户交互

### 6.1 设计目标

Bot 发生的重要事件（生日、节假日、里程碑、日常生活感悟）需要主动分享给用户，形成类似真实人际关系的对话互动。

### 6.2 事件分类与分享策略

分享策略基于 `attitude_score`（-10 到 +10）动态调整，分数越高分享越积极。

#### 好感度与分享概率

```python
def _get_share_prob(self, attitude_score: int, event_type: str) -> float:
    """根据好感度和事件类型计算分享概率"""

    # 基础概率由 attitude_score 决定
    # attitude_score 范围 -10 到 +10，映射到 0.05 到 0.95
    base_prob = (attitude_score + 10) / 20 * 0.9 + 0.05  # 0.05 ~ 0.95

    # 不同事件类型有不同的概率系数
    multipliers = {
        "birthday": 1.0,        # 生日：必分享
        "holiday": 0.8,         # 节假日：高概率
        "milestone": 1.0,       # 里程碑：必分享
        "high_importance": 0.5,  # 高重要性事件：基础概率的 50%
        "mood_change": 0.3,     # 情绪波动：基础概率的 30%
        "daily": 0.1,          # 日常生活：低概率
    }

    return base_prob * multipliers.get(event_type, 0.3)
```

#### 分享概率参考表

| attitude_score | 基础分享概率 | 生日/节假日 | 里程碑 | 高 importance | 情绪波动 | 日常生活 |
|---------------|-------------|------------|--------|--------------|---------|---------|
| -10 ~ -6 | 5-14% | ✅ 必发 | ✅ 必发 | ❌ | ❌ | ❌ |
| -5 ~ -1 | 15-32% | ✅ | ✅ | ❌ | ❌ | ❌ |
| 0 ~ 4 | 33-50% | ✅ | ✅ | ~20% | ❌ | ❌ |
| 5 ~ 7 | 51-68% | ✅ | ✅ | ~35% | ~15% | ❌ |
| 8 ~ 10 | 69-95% | ✅ | ✅ | ~50% | ~25% | ~10% |

#### 消息语气随好感度调整

```python
def _build_share_message(self, event, attitude_score: int) -> str:
    """构建分享给用户的消息（根据好感度调整语气）"""

    # 语气随好感度渐变
    if attitude_score >= 7:
        tone = "恋人"
    elif attitude_score >= 3:
        tone = "暧昧中"
    elif attitude_score >= 0:
        tone = "熟朋友"
    elif attitude_score >= -5:
        tone = "普通朋友"
    else:
        tone = "陌生网友"

    # 生日事件
    if self._is_birthday():
        messages = {
            "陌生网友": "今天是我的生日（小声）",
            "普通朋友": "今天是我的生日啦",
            "熟朋友": "今天我生日诶～",
            "暧昧中": "今天本小姐生日！礼物呢？🎂",
            "恋人": "亲爱的，今天是我们在一起后的第几个生日来着？🎂💕",
        }
        return messages.get(tone, "今天是我的生日～")

    # 节假日事件
    holiday = self._is_holiday(self.state.current_date)
    if holiday:
        messages = {
            "陌生网友": f"今天{holiday['name']}，你那边怎么过的？",
            "普通朋友": f"今天{holiday['name']}诶，有什么计划吗？",
            "熟朋友": f"{holiday['name']}到啦！你不会忘了吧？",
            "暧昧中": f"喂，{holiday['name']}！一起过吗？🎉",
            "恋人": f"{holiday['name']}快乐！今年一起吃大餐庆祝吧～🥰",
        }
        return messages.get(tone, f"今天{holiday['name']}～")

    # 里程碑事件
    if event.topic_prompt:
        if tone in ["暧昧中", "恋人"]:
            return f"{event.topic_prompt}，想跟你聊聊～"
        return event.topic_prompt

    # 日常事件
    messages = {
        "陌生网友": f"话说，今天发生了件事：{event.description}",
        "普通朋友": f"诶，跟你说个事：{event.description}",
        "熟朋友": f"{event.description}，挺有意思的",
        "暧昧中": f"{event.description}，你来评评理",
        "恋人": f"{event.description}，刚才想到你就想告诉你～",
    }
    return messages.get(tone, f"{event.description}，和你分享一下～")
```

### 6.3 分享时机

```python
# life_engine.py

async def _maybe_share_event(self, event):
    """判断事件是否应该分享给用户"""

    # 1. 强制分享：里程碑和生日
    if isinstance(event, MajorLifeEvent) or self._is_birthday():
        await self._share_as_proactive_message(event)
        return

    # 2. 节假日事件
    if self._is_holiday(self.state.current_date):
        await self._share_as_proactive_message(event)
        return

    # 3. 高 importance 事件
    if event.importance >= 7.0:
        # 按概率分享（避免太频繁）
        if random.random() < 0.3:
            await self._share_as_proactive_message(event)
        return

    # 4. 情绪波动事件
    if event.mood_before != event.mood_after:
        # 只有较大情绪波动才分享
        if self._calc_mood_delta(event) > 3.0:
            if random.random() < 0.15:
                await self._share_as_proactive_message(event)
```

### 6.4 分享方式：主动消息

```python
async def _share_as_proactive_message(self, event):
    """通过主动消息系统分享给用户"""

    # 构建分享消息
    message = self._build_share_message(event)

    # 调用 proactive engine 发送
    if hasattr(self, 'proactive_engine'):
        await self.proactive_engine.send_proactive_message(message)

def _build_share_message(self, event, relationship: str = "普通朋友") -> str:
    """构建分享给用户的消息（根据关系阶段调整语气）"""

    # 生日事件 - 所有关系阶段都分享，语气随关系变化
    if self._is_birthday():
        messages = {
            "陌生网友": "今天是我的生日（小声）",
            "普通朋友": "今天是我的生日啦",
            "熟朋友": "今天我生日诶～",
            "暧昧中": "今天本小姐生日！礼物呢？🎂",
            "恋人": "亲爱的，今天是我们在一起后的第几个生日来着？🎂💕",
        }
        return messages.get(relationship, "今天是我的生日～")

    # 节假日事件
    holiday = self._is_holiday(self.state.current_date)
    if holiday:
        messages = {
            "陌生网友": f"今天{holiday['name']}，你那边怎么过的？",
            "普通朋友": f"今天{holiday['name']}诶，有什么计划吗？",
            "熟朋友": f"{holiday['name']}到啦！你不会忘了吧？",
            "暧昧中": f"喂，{holiday['name']}！一起过吗？🎉",
            "恋人": f"{holiday['name']}快乐！今年一起吃大餐庆祝吧～🥰",
        }
        return messages.get(relationship, f"今天{holiday['name']}～")

    # 里程碑事件 - 使用配置的话题切入语，语气随关系变化
    if event.topic_prompt:
        if relationship in ["暧昧中", "恋人"]:
            return f"{event.topic_prompt}，想跟你聊聊～"
        return event.topic_prompt

    # 日常事件 - 基于事件描述生成，语气随关系变化
    messages = {
        "陌生网友": f"话说，今天发生了件事：{event.description}",
        "普通朋友": f"诶，跟你说个事：{event.description}",
        "熟朋友": f"{event.description}，挺有意思的",
        "暧昧中": f"{event.description}，你来评评理",
        "恋人": f"{event.description}，刚才想到你就想告诉你～",
    }
    return messages.get(relationship, f"{event.description}，和你分享一下～")
```

### 6.5 用户交互：事件后续

当 Bot 分享事件后，用户可能会回应：
- 祝福生日
- 关心情绪
- 询问详情
- 分享自己的类似经历

Bot 需要能够处理这些回复，形成有意义的对话。

```python
# 事件上下文标记
class LifeEvent:
    def __init__(self, ...):
        self.shared_with_user = False      # 是否已分享
        self.user_response = None          # 用户的回应
        self.conversation_id = None         # 对话 ID（用于关联后续对话）
        self.shared_at = None              # 分享时间
```

### 6.6 主动消息系统集成

```python
# LifeEngine 需要持有 proactive_engine 的引用
class LifeEngine:
    def __init__(self, ...):
        self.proactive_engine = None  # 由 BotInstance 注入

    def set_proactive_engine(self, engine):
        self.proactive_engine = engine

    async def send_proactive_message(self, message: str):
        """通过主动消息系统发送"""
        if self.proactive_engine:
            await self.proactive_engine._platform_sender(message)
```

### 6.7 BotInstance 注入

```python
# BotInstance.init() 中
async def init(self):
    # ... 现有代码 ...

    # 注入 proactive_engine 引用到 life_engine
    if self.life_engine:
        self.life_engine.set_proactive_engine(self.proactive_engine)
```

### 6.8 限流保护

事件分享不能太频繁，需要遵守主动消息的限流规则：
- 每日最大主动消息数
- 最小发送间隔
- 冷却机制

这些由 `ProactiveScheduler` 统一管理，事件分享只是构建消息内容。

### 6.9 改动汇总

| 文件 | 改动 |
|------|------|
| `ai_companion/proactive/life_engine.py` | +send_proactive_message(), +_maybe_share_event(), +_build_share_message(), +_get_share_prob(), +_get_attitude_score() |
| `ai_companion/proactive/life_state.py` | +shared_with_user, +user_response, +conversation_id, +shared_at |
| `ai_companion/bot/instance.py` | life_engine.set_proactive_engine(proactive_engine) |

### 6.10 好感度获取

直接使用 `attitude_score`，不需要推断关系字符串：

```python
async def _get_attitude_score(self) -> int:
    """获取当前好感度分数"""
    if not self.memory:
        return 0  # 默认中立

    semantic_facts = await self.memory.semantic.get_all_facts()
    score = semantic_facts.get("attitude_score", "0")
    try:
        return int(float(score))
    except (ValueError, TypeError):
        return 0
```

**好感度说明：**
- 范围：-10 到 +10
- 每轮对话变化：±5
- 初始值：0（中立）

---

## 验证方案

8. 生日时 Bot 是否主动发消息给用户
9. 节假日时 Bot 是否分享相关事件
10. 高 importance 事件是否按概率分享
11. 用户回复后 Bot 能否正确响应
