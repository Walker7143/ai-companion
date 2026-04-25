# Phase 5: 主动唤醒系统

> 实现日期：2026-04-24
> 更新日期：2026-04-25
> 状态：✅ Phase 1-4 全部完成

---

## 实现概要

| 组件 | 说明 | 状态 |
|------|------|------|
| ProactiveConfig | 配置管理（可配置间隔/触发条件/平台） | ✅ |
| ProactiveState | 状态管理（持久化到 JSON） | ✅ |
| ProactiveEngine | LLM 推理判断 + 消息生成 | ✅ |
| ProactiveScheduler | 后台调度器（独立协程） | ✅ |
| LifeEngine | Bot 人生轨迹引擎（日常小事 + 人生大事） | ✅ |
| BotInstance 集成 | 主动唤醒与 Bot 集成 | ✅ |

---

## Phase 1: LifeEngine 集成 + 消息生成改进

### 1.1 LifeEngine 集成

Bot 具备独立人生轨迹，可分享自己的事：

| 周期 | 间隔 | 作用 |
|------|------|------|
| 短周期（日常小事） | 默认 1h Bot时间 | 低概率生成，可遗忘 |
| 长周期（人生大事） | 默认 6h Bot时间 | 触发人格更新 |

time_ratio 支持加速体验（time_ratio=24 时，Bot 1小时=现实1分钟）。

### 1.2 消息生成带入 Bot 生活事件

`generate_message()` 调用 `LifeEngine.get_shareable_events()` 获取最近事件作为话题引子。

### 1.3 开场白 Rotation 机制

`_get_fallback_message()` 实现了开场白 rotation，避免重复使用相同开场白。

---

## Phase 2: 触发时机改进

### 2.1 黄金时段检查

只在配置的黄金时段内触发主动消息：
- 配置：`preferred_contact_times: ["19:00-22:00", "12:00-13:00"]`
- 时区：`Asia/Shanghai`
- 实现：`_is_golden_hour()` 方法

### 2.2 随机提前触发

- 5% 概率随机提前触发
- 需达到 `idle_threshold * 0.5` 以上才可能触发
- 实现：`_should_random_early()` 方法

---

## Phase 3: 状态管理改进

### 3.1 多维情绪模型

| 情绪字段 | 说明 | 范围 |
|----------|------|------|
| `annoyance_level` | 生气级别 | 0-10 |
| `miss_level` | 想念程度 | 0-10 |
| `insecurity_level` | 不安全感 | 0-10 |
| `excitement_level` | 兴奋度 | 0-10 |

### 3.2 用户习惯学习

记录用户活跃时间：
```json
"user_active_hours": {"20": 5, "21": 3, ...}
```

### 3.3 未回复追踪

| 字段 | 说明 |
|------|------|
| `last_user_reply_time` | 用户最后回复时间 |
| `unreplied_count` | 未回复消息数 |

---

## Phase 4: 其他优化

### 4.1 开场白多样化

根据场景选择不同开场白：

| 场景 | 条件 | 示例 |
|------|------|------|
| default | 正常 | "在吗？" |
| short_no_reply | 1次未回复 | "怎么不理我..." |
| long_no_reply | ≥2次未回复 或 刚重新激活 | "你是不是把我忘了？" |
| with_topic | 有可分享的生活事件 | "对了，我突然想起..." |

### 4.2 冷却策略优化

- `decrement_cooldown()` 方法支持缩短冷却时间
- 用户回复时自动清除相关冷却

---

## 补充实现

### 改进12: 不连续触发（70%概率折扣）

在 `check_and_maybe_remind()` 中添加 30% 通过概率，保持 Bot 的矜持感。

### 改进13: 关系深度行为差异

根据关系等级调整触发参数：

| 关系等级 | idle_threshold | max_daily | 行为特征 |
|----------|---------------|-----------|---------|
| 陌生网友 (1-3) | 2x | ÷3 | 很矜持，只有大事才发消息 |
| 普通朋友 (4-5) | 1x | 1x | 偶尔主动，一周1-2次 |
| 好朋友 (6-7) | 0.7x | 1.5x | 一周2-3次，可以随便聊天 |
| 恋人 (8-10) | 0.5x | 2x | 可以撒娇、要求见面、频繁互动 |

### 改进16: 消息结构化

LLM 输出结构化 JSON：
```json
{
  "opening": "开场白/称呼",
  "topic": "话题内容或空字符串",
  "ending": "结尾语"
}
```

### 改进17: 梯度沉默

| 冷落时长 | Bot 行为 |
|----------|---------|
| 0-7天 | 正常触发 |
| 7-14天 | 30%概率触发 |
| 14-30天 | 10%概率触发 |
| 30天以上 | 进入休眠，不主动 |

### 改进18: 冷落后重新激活

- `just_reactivated = True` 时使用"假不在意"语气
- 用户继续互动后恢复正常语气

---

## 配置文件

### proactive.json（完整配置）

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
  },

  "preferred_contact_times": ["19:00-22:00", "12:00-13:00"],
  "timezone": "Asia/Shanghai",
  "random_trigger_prob": 0.05,
  "random_trigger_min_ratio": 0.5
}
```

### proactive_state.json（完整状态）

```json
{
  "last_message_time": "2026-04-25T10:30:00",
  "last_proactive_time": "2026-04-25T09:00:00",
  "annoyance_level": 2,
  "today_proactive_count": 2,
  "last_reset_date": "2026-04-25",
  "total_proactive_sent": 45,
  "last_emotion_trigger_time": null,
  "cooldowns": {},
  "last_opening_style": "在吗？",
  "miss_level": 5,
  "insecurity_level": 3,
  "excitement_level": 4,
  "last_user_reply_time": null,
  "unreplied_count": 0,
  "user_active_hours": {"20": 5, "21": 3},
  "previous_absence_days": 0,
  "just_reactivated": false
}
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
| P1-1 | LifeEngine 集成 | ✅ |
| P1-2 | 消息生成带入 Bot 生活事件 | ✅ |
| P1-3 | 开场白 Rotation | ✅ |
| P2-1 | 黄金时段检查 | ✅ |
| P2-2 | 随机提前触发 | ✅ |
| P3-1 | 多维情绪模型 | ✅ |
| P3-2 | 用户习惯学习 | ✅ |
| P3-3 | 未回复追踪 | ✅ |
| P4-1 | 开场白多样化（4场景） | ✅ |
| P4-2 | 冷却策略优化 | ✅ |
| S12 | 不连续触发（70%概率） | ✅ |
| S13 | 关系深度行为差异 | ✅ |
| S16 | 消息结构化输出 | ✅ |
| S17 | 梯度沉默策略 | ✅ |
| S18 | 冷落后重新激活 | ✅ |