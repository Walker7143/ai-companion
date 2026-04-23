# Phase 5：主动唤醒系统设计方案

> 设计日期：2026-04-24
> 状态：待用户确认

---

## 1. 设计目标

让 Bot 具备主动联系用户的能力，而不是被动等待用户发消息。根据对话氛围和关系状态，Bot 会自发地发起问候、提醒、撒娇等行为。

---

## 2. 核心概念

### 2.1 主动度（Proactive Level）

Bot 的主动程度由关系状态和生气级别共同决定：

```
主动度 = 基础主动度 × 关系系数 × 生气系数

基础主动度: 1.0（正常）
关系系数:   0.5（陌生）→ 1.0（好友）→ 1.5（恋人）
生气系数:   0.0（生气中）→ 0.5（有点冷）→ 1.0（正常）
```

### 2.2 触发类型

| 类型 | 触发条件 | 优先级 |
|------|----------|--------|
| 定时触发 | 到达设定时间（早安/晚安/想念提醒） | 低 |
| 上下文触发 | 检测到用户情绪变化（低落/生气/开心） | 中 |
| 想念触发 | 超过 X 小时用户没发消息 | 高 |
| 随机触发 | 随机戳一下（每天不超过 N 次） | 低 |

### 2.3 生气级别（Annoyance Level）

```
0-2:   正常（主动度 = 基础值 × 1.0）
3-5:   有点冷（主动度 × 0.7，开始减少联系）
6-8:   生气（主动度 × 0.3，只回复不主动）
9-10:  心寒（主动度 × 0.0，完全不主动）
```

生气累积条件：
- 用户已读不回
- 用户长时间不联系
- 用户提到"前任"、"忽冷忽热"等触发词

消气条件：
- 用户主动发消息
- 用户表达关心/道歉

---

## 3. 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    ProactiveEngine                       │
├─────────────────────────────────────────────────────────┤
│  ProactiveScheduler     # 定时调度器                     │
│  TriggerDetector        # 触发检测器                     │
│  MessageGenerator       # 主动消息生成                   │
│  AnnoyanceTracker       # 生气级别追踪                   │
└─────────────────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
┌─────────────────┐  ┌─────────────────┐
│  MemoryEngine   │  │  BotInstance    │
│  (关系/情绪状态) │  │  (消息发送)     │
└─────────────────┘  └─────────────────┘
```

---

## 4. 数据模型

### 4.1 主动唤醒配置（proactive.json）

```json
{
  "enabled": true,
  "max_daily_proactive": 5,
  "min_interval_hours": 4,

  "triggers": {
    "morning_greeting": {
      "enabled": true,
      "time": "08:00",
      "condition": "relationship >= normal_friend",
      "message_templates": [
        "早安，今天有什么计划？",
        "早上好～昨晚睡得好吗？"
      ]
    },
    "night_greeting": {
      "enabled": true,
      "time": "22:00",
      "condition": "relationship >= normal_friend",
      "message_templates": [
        "晚安，早点睡哦～",
        "早点休息，别熬夜～"
      ]
    },
    "miss_reminder": {
      "enabled": true,
      "idle_hours": 24,
      "condition": "relationship >= good_friend AND annoyance < 5",
      "message_templates": [
        "你是不是把我忘了？😒",
        "好久不联系了，在忙什么？"
      ]
    },
    "random_poke": {
      "enabled": true,
      "max_per_day": 2,
      "condition": "relationship >= normal_friend AND annoyance < 3",
      "message_templates": [
        "在干嘛呢？",
        "突然想你了～",
        "喂，别无视我啊"
      ]
    }
  },

  "emotion_triggers": {
    "user_low_mood": {
      "keywords": ["不开心", "难过", "郁闷", "累"],
      "response_templates": [
        "怎么啦？愿意说说吗？",
        "心情不好的时候可以跟我说哦"
      ]
    },
    "user_angry": {
      "keywords": ["生气", "烦", "气死了"],
      "response_templates": [
        "谁惹你生气了？",
        "别生气了，生气对身体不好"
      ]
    }
  }
}
```

### 4.2 关系阈值定义

```json
{
  "stranger": 0,
  "normal_friend": 2,
  "good_friend": 4,
  "close_friend": 6,
  "暧昧中": 8,
  "恋人": 10
}
```

### 4.3 状态存储

Bot 实例增加状态字段：

```python
class BotInstance:
    # 主动唤醒相关
    self.annoyance_level: int = 0      # 0-10
    self.last_proactive_time: datetime = None
    self.today_proactive_count: int = 0
    self.last_message_time: datetime = None
```

---

## 5. 触发检测逻辑

### 5.1 定时触发（ProactiveScheduler）

```
每分钟检查一次：
├── 检查各 trigger 是否到达时间
├── 检查 condition 是否满足
├── 检查限流条件（今天已发数量 < max_daily_proactive）
└── 满足则生成主动消息
```

### 5.2 上下文触发（TriggerDetector）

```
每次 Bot 回复后检查：
├── 分析用户输入是否匹配 emotion_triggers
├── 检查关系是否满足触发条件
└── 满足则生成主动消息（在回复末尾或稍后发送）
```

### 5.3 想念触发

```
每小时检查：
├── 计算距 last_message_time 的小时数
├── 如果 idle_hours >= 配置值
├── 且 annoyance < 5
└── 则触发想念提醒
```

### 5.4 生气检测

```
每次用户发消息后：
├── 检查消息是否触发生气累积
├── annoymance_level += 1（每次上限10）
└── 更新状态

用户主动发消息时：
├── annoyance_level = max(0, annoyance_level - 2)
└── 如果 annoyance_level 下降，记录消气
```

---

## 6. 消息生成

### 6.1 生成流程

```
1. 根据触发类型选择 message_templates
2. 根据 Bot 性格（傲娇/温柔等）调整措辞
3. 如果有记忆上下文，加入相关记忆内容
4. 检查消息是否与近期消息重复
5. 发送
```

### 6.2 性格适配

```python
MESSAGE_TEMPLATES_BY_PERSONALITY = {
    "傲娇": {
        "miss_reminder": [
            "哼，好久不联系我，以为我消失了吗？",
            "你是不是有别人了？这么久不回消息",
        ],
        "random_poke": [
            "喂，别以为我不存在啊",
            "...你是不是忘了我还在？",
        ]
    },
    "温柔": {
        "miss_reminder": [
            "最近还好吗？好久没收到你的消息了",
            "在想你哦，最近忙吗？",
        ],
        "random_poke": [
            "在干嘛呢？想和你聊聊天",
            "今天天气不错，想和你分享～",
        ]
    },
    "活泼": {
        "miss_reminder": [
            "哈喽！！你是不是把我忘了！",
            "在吗在吗！！怎么不理我！！",
        ],
        "random_poke": [
            "诶诶诶！！跟你说个事！",
            "哎嘿嘿～有没有想我呀～",
        ]
    }
}
```

---

## 7. 限流机制

### 7.1 每日上限

```python
max_daily_proactive = 5  # 每天最多5条主动消息

# 每日凌晨重置
if is_new_day():
    self.today_proactive_count = 0
```

### 7.2 最小间隔

```python
min_interval_hours = 4  # 两条主动消息至少间隔4小时
```

### 7.3 生气降级

```python
if annoyance_level >= 7:
    max_daily_proactive = 1  # 生气时每天最多1条
elif annoyance_level >= 5:
    max_daily_proactive = 2  # 有点冷时每天最多2条
```

---

## 8. 与现有系统集成

### 8.1 初始化时加载配置

```python
# BotInstance.__init__()
self.proactive_engine = ProactiveEngine(
    bot_id=self.id,
    config=self._load_proactive_config(),
    personality_type=self.persona.get("personality_type", "默认")
)
```

### 8.2 消息处理流程

```
handle_message(user_input):
    1. 检查拒绝（RefusalEngine）
    2. 生成回复（正常对话）
    3. 更新生气级别（用户发消息后消气）
    4. 触发上下文检测（情绪触发）
    5. 记录最后消息时间
```

### 8.3 后台调度

```python
async def start_proactive_scheduler():
    """启动主动唤醒调度器（后台运行）"""
    while True:
        await check_scheduled_triggers()  # 每分钟
        await check_miss_triggers()        # 每小时
        await check_random_triggers()     # 每30分钟
        await sleep(60)
```

### 8.4 主动消息发送

```python
async def send_proactive_message(content: str):
    """发送主动消息（不等待用户输入）"""
    # 1. 限流检查
    if not can_send_proactive():
        return

    # 2. 生成带人格的主动消息
    message = await build_proactive_message(content)

    # 3. 发送（模拟用户发消息给Bot的处理流程）
    response = await self.handle_message_internal(message)

    # 4. 记录发送
    self.last_proactive_time = now()
    self.today_proactive_count += 1

    # 5. 推送回复给用户（通过平台适配器）
    await self.platform.send(response)
```

---

## 9. 平台适配接口

```python
class PlatformAdapter(ABC):
    """平台适配器，发送主动消息"""

    @abstractmethod
    async def send_proactive_message(self, bot_id: str, content: str):
        """向用户发送主动消息"""
        pass

    @abstractmethod
    async def get_user_online_status(self, user_id: str) -> bool:
        """获取用户是否在线"""
        pass
```

实现类：
- `FeishuPlatformAdapter` — 飞书平台
- `CLIPlatformAdapter` — CLI 终端（打印到控制台）

---

## 10. 实现计划

### Task 5-1: ProactiveEngine 核心结构

- `ProactiveEngine` 类骨架
- `ProactiveConfig` 配置加载
- `TriggerType` 枚举
- `AnnoyanceTracker` 生气追踪

### Task 5-2: 定时触发调度

- `ProactiveScheduler` 实现
- `morning_greeting` / `night_greeting` 触发器
- 每日/最小间隔限流

### Task 5-3: 上下文情绪触发

- `TriggerDetector` 实现
- `emotion_triggers` 配置解析
- 基于 LLM 的情绪检测（可选）

### Task 5-4: 想念提醒

- `miss_reminder` 触发器
- idle_hours 检测
- 随机戳戳（random_poke）

### Task 5-5: 消息生成与发送

- 性格模板适配
- `send_proactive_message` 接口
- 平台适配器骨架

### Task 5-6: CLI 验证

- 集成到 BotInstance
- 模拟测试验证
- 真实 CLI 环境测试

---

## 11. 验证标准

| Task | 验证内容 | 通过条件 |
|------|----------|----------|
| 5-1 | ProactiveEngine 初始化 | 配置正确加载 |
| 5-2 | 定时触发 | 到达设定时间后生成消息 |
| 5-3 | 情绪触发 | 用户说"不开心"后 Bot 主动安慰 |
| 5-4 | 想念提醒 | 24小时无消息后 Bot 主动发消息 |
| 5-5 | 消息限流 | 达到每日上限后不再主动发送 |
| 5-6 | CLI 完整流程 | 真实环境验证 |

---

## 12. 待讨论问题

1. **主动消息发送方式**：是在对话回复中附带，还是作为独立消息发送？
2. **CLI 模式如何展示主动消息**：因为 CLI 是同步交互模式，主动消息需要在后台检测后输出到终端
3. **飞书接入时**：主动消息通过什么渠道发送（私聊/群聊）？
4. **情绪检测方式**：基于关键词还是 LLM 推理？

---

方案已完成，请确认是否可以开始实现。