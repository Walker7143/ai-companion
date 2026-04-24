# Phase 5：主动唤醒系统设计方案

> 设计日期：2026-04-24
> 状态：✅ 已实现

---

## 1. 设计目标

让 Bot 具备主动联系用户的能力，而不是被动等待用户发消息。根据对话氛围和关系状态， Bot 会自发地发起问候、提醒、撒娇等行为。

**核心特点：**
- LLM 推理判断是否应该主动联系（非关键词）
- LLM 生成符合人格的主动消息（非模板）
- 每个 Bot 独立调度，可配置活跃或静默模式

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    ProactiveEngine                       │
├─────────────────────────────────────────────────────────┤
│  ProactiveConfig      # 配置管理（可配置所有参数）         │
│  ProactiveState       # 状态管理（持久化到 JSON）           │
│  ProactiveScheduler   # 后台调度器（独立协程）               │
│  ProactivePlatform    # 平台适配器（CLI/飞书/Webhook）      │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐  ┌─────────────────┐
│  MemoryEngine   │  │  BotInstance    │
│  (关系/情绪状态) │  │  (消息发送)     │
└─────────────────┘  └─────────────────┘
```

---

## 3. 配置说明

### 3.1 配置文件位置

```
data/bots/{bot_id}/persona/proactive.json
```

例如：`data/bots/suqing/persona/proactive.json`

### 3.2 完整配置项

```json
{
  "enabled": true,
  "mode": "active",

  "scheduler": {
    "check_interval_seconds": 600,
    "idle_threshold_hours": 24,
    "max_daily": 5,
    "min_interval_hours": 4,
    "max_idle_days": 7
  },

  "triggers": {
    "idle_reminder": {
      "enabled": true,
      "idle_hours": 24
    },
    "emotion_trigger": {
      "enabled": true,
      "keywords": ["不开心", "难过", "累", "生气", "烦", "郁闷", "沮丧"],
      "response_delay_minutes": 5
    }
  },

  "platform": {
    "type": "cli"
  }
}
```

### 3.3 配置项详解

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enabled` | true | 是否启用主动唤醒 |
| `mode` | "active" | `"active"`=活跃模式（会主动发消息），`"silent"`=静默模式 |
| `scheduler.check_interval_seconds` | 600 | 后台检查间隔（秒），600=10分钟 |
| `scheduler.idle_threshold_hours` | 24 | 多久没联系触发提醒（小时） |
| `scheduler.max_daily` | 5 | 每天最多主动消息数 |
| `scheduler.min_interval_hours` | 4 | 两条消息最小间隔（小时） |
| `scheduler.max_idle_days` | 7 | 超过此天数停止主动（天） |
| `triggers.idle_reminder.enabled` | true | 是否启用空闲触发 |
| `triggers.idle_reminder.idle_hours` | 24 | 空闲触发阈值（小时） |
| `triggers.emotion_trigger.enabled` | true | 是否启用情绪触发 |
| `triggers.emotion_trigger.keywords` | [...] | 情绪关键词列表 |
| `triggers.emotion_trigger.response_delay_minutes` | 5 | 检测到情绪后延迟关心（分钟） |
| `platform.type` | "cli" | 发送平台：`"cli"` / `"feishu"` / `"webhook"` |

### 3.4 配置示例

#### 示例 1：活跃模式（默认）
```json
{
  "enabled": true,
  "mode": "active",
  "scheduler": {
    "check_interval_seconds": 600,
    "idle_threshold_hours": 24
  }
}
```

#### 示例 2：静默模式（不主动发消息）
```json
{
  "enabled": true,
  "mode": "silent"
}
```

#### 示例 3：高频率模式（5分钟检查，最多10条/天）
```json
{
  "enabled": true,
  "mode": "active",
  "scheduler": {
    "check_interval_seconds": 300,
    "idle_threshold_hours": 12,
    "max_daily": 10,
    "min_interval_hours": 2
  }
}
```

#### 示例 4：配置情绪关键词
```json
{
  "triggers": {
    "emotion_trigger": {
      "enabled": true,
      "keywords": ["不开心", "难过", "郁闷", "累", "沮丧", "失落", "焦虑"],
      "response_delay_minutes": 3
    }
  }
}
```

---

## 4. 状态持久化

### 4.1 状态文件位置

```
data/bots/{bot_id}/proactive_state.json
```

### 4.2 状态内容

```json
{
  "last_message_time": "2026-04-24T10:30:00",
  "last_proactive_time": "2026-04-24T09:00:00",
  "annoyance_level": 2,
  "today_proactive_count": 2,
  "last_reset_date": "2026-04-24",
  "total_proactive_sent": 45,
  "last_emotion_trigger_time": null,
  "cooldowns": {}
}
```

### 4.3 状态说明

| 字段 | 说明 |
|------|------|
| `last_message_time` | 用户最后发消息时间 |
| `last_proactive_time` | Bot 最后主动发消息时间 |
| `annoyance_level` | 生气级别（0-10），用户冷落 Bot 时上升 |
| `today_proactive_count` | 今日已主动发消息数（每日重置） |
| `total_proactive_sent` | 累计主动发消息数 |
| `cooldowns` | 各触发器的冷却时间 |

---

## 5. 触发逻辑

### 5.1 前置检查（快速过滤）

```
1. enabled == true 且 mode == "active"
2. today_proactive_count < max_daily
3. annoyance_level < 9（生气时不主动）
4. 不在冷却中
5. idle_hours >= idle_threshold_hours
```

### 5.2 LLM 判断

通过 LLM 推理判断是否应该主动联系，综合考虑：
- 关系深度（1=陌生，10=恋人）
- 心情状态（根据 annoyance_level）
- 距离上次聊天时间
- 今天已发消息数

### 5.3 LLM 生成消息

根据 Bot 性格和当前情况生成符合人格的主动消息：
- 傲娇：「哼，好久不见呢，你是不是把我忘了？...才不是，我只是刚好想起你而已。」
- 温柔：「最近怎么样？好久没聊了，有点想你。」
- 活泼：「哈喽！！最近怎么样！！想你了～」

### 5.4 情绪触发

检测用户输入中的情绪关键词：
- 用户说「不开心」「难过」「累」等
- 延迟 response_delay_minutes 后主动关心

---

## 6. 限流机制

| 条件 | 限制 |
|------|------|
| 每日上限 | max_daily（默认5条） |
| 最小间隔 | min_interval_hours（默认4小时） |
| 生气降级 | annoyance >= 7 时，max_daily 降为 1 |
| 最大空闲 | max_idle_days（默认7天）后停止主动 |

---

## 7. 平台适配

### 7.1 支持的平台

| 平台 | 说明 |
|------|------|
| `cli` | CLI 终端，打印到控制台 |
| `feishu` | 飞书，通过 Webhook 发送 |
| `webhook` | 通用 Webhook |

### 7.2 配置平台

```json
{
  "platform": {
    "type": "cli"
  }
}
```

或通过代码设置：
```python
bot.set_proactive_platform("cli")
bot.set_proactive_platform("feishu", webhook_url="https://...")
```

---

## 8. 与 BotInstance 集成

```python
# Bot 初始化时自动加载配置
bot = BotInstance(config, model=model)
await bot.init()  # 启动主动唤醒调度器

# 获取状态
status = bot.get_proactive_status()

# 用户发消息时自动更新状态
await bot.handle_message("你好")
# → annoyance_level 下降，last_message_time 更新
```

---

## 9. 验证结果

| Test | 功能 | 结果 |
|------|------|------|
| 1 | ProactiveConfig 配置加载 | ✅ |
| 2 | ProactiveState 状态持久化 | ✅ |
| 3 | BotInstance 初始化 + 调度器启动 | ✅ |
| 4 | 用户发消息后状态更新（消气） | ✅ |
| 5 | 情绪触发检测 | ✅ |
| 6 | LLM 判断不应联系（刚发过消息） | ✅ |
| 7 | LLM 判断应联系（25小时idle） | ✅ |
| 8 | LLM 生成傲娇风格消息 | ✅ |
| 9 | 限流（达每日上限） | ✅ |
| 10 | 生气降级（annoyance=9） | ✅ |
| 11 | 冷却机制 | ✅ |
| 12 | 获取状态 | ✅ |
| 13 | 静默模式 | ✅ |

---

## 10. LLM 判断示例

```
输入状态：
- idle_hours: 25.0
- relationship: 普通朋友
- annoyance_level: 0
- today_proactive_count: 0

LLM 判断结果：
- should_contact: True
- reason: 傲娇关心
- urgency: medium

生成消息：
「哼，好久不见呢，你是不是把我忘了？...才不是，我只是刚好想起你而已。」
```