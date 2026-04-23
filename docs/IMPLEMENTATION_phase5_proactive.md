# Phase 5: 主动唤醒系统

> 实现日期：2026-04-24
> 状态：✅ 核心功能完成

---

## 实现概要

| 组件 | 说明 | 状态 |
|------|------|------|
| ProactiveConfig | 配置管理（可配置间隔/触发条件/平台） | ✅ |
| ProactiveState | 状态管理（持久化到 JSON） | ✅ |
| ProactiveEngine | LLM 推理判断 + 消息生成 | ✅ |
| ProactiveScheduler | 后台调度器（独立协程） | ✅ |
| ProactivePlatform | 平台适配器（CLI/飞书/Webhook） | ✅ |
| BotInstance 集成 | 主动唤醒与 Bot 集成 | ✅ |

---

## 核心功能

### 1. LLM 推理判断

不通过关键词，通过 LLM 判断是否应该主动联系用户：

```
输入：用户关系、心情、距离上次聊天时间、今天的主动消息数
输出：{{"should_contact": true/false, "reason": "...", "urgency": "high/medium/low"}}
```

### 2. LLM 生成消息

根据性格和当前情况生成符合人格的主动消息：

```
输入：bot_name、personality_tags、relationship、feeling_description
输出：符合性格的自然语言消息
```

### 3. 可配置触发

| 触发类型 | 配置项 | 默认值 |
|----------|--------|--------|
| 检查间隔 | `scheduler.check_interval_seconds` | 600秒（10分钟） |
| 空闲触发 | `triggers.idle_reminder.idle_hours` | 24小时 |
| 情绪触发 | `triggers.emotion_trigger.keywords` | ["不开心", "难过", ...] |

### 4. 状态持久化

```json
// data/bots/{bot_id}/proactive_state.json
{
  "last_message_time": "2026-04-24T00:57:51",
  "last_proactive_time": "2026-04-24T00:30:00",
  "annoyance_level": 0,
  "today_proactive_count": 1,
  "total_proactive_sent": 45
}
```

### 5. Bot 独立调度

每个 Bot 有自己的调度器，通过 `mode` 控制：

| mode | 行为 |
|------|------|
| `active` | 启动调度器，达标时主动发消息 |
| `silent` | 不启动调度器，被动响应 |

---

## 配置文件

### proactive.json

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

---

## 验证结果

### 初始化测试
```
config: {enabled: true, mode: "active", is_active: true, check_interval: 600}
scheduler: {running: true, check_interval: 600, is_active: true}
```

### 用户发消息后状态更新
```
last_message_time: 2026-04-24T00:57:51 (已更新)
annoyance_level: 0 (已重置)
idle_hours: 0.0 (刚发过消息)
```

### LLM 判断
```
should_contact: False
reason: 还没到触发时间(0.0h)
urgency: low
```

---

## 验收标准

| Task | 验证内容 | 状态 |
|------|---------|------|
| 5-1 | ProactiveConfig 配置加载 | ✅ |
| 5-2 | ProactiveState 持久化 | ✅ |
| 5-3 | ProactiveEngine LLM 判断 | ✅ |
| 5-4 | ProactiveScheduler 后台调度 | ✅ |
| 5-5 | 平台适配器（CLI） | ✅ |
| 5-6 | BotInstance 集成 | ✅ |
| 5-7 | 情绪触发检测 | ✅ |
| 5-8 | 限流（max_daily/min_interval） | ✅ |
| 5-9 | 生气降级（annoyance_level） | ✅ |