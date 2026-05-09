# Phase 5：主动唤醒系统设计方案

> 设计日期：2026-04-24
> 更新日期：2026-05-09
> 状态：✅ 已实现 + Phase 2-4 优化完成

---

## 1. 设计目标

让 Bot 具备主动联系用户的能力，而不是被动等待用户发消息。根据对话氛围和关系状态， Bot 会自发地发起问候、提醒、撒娇等行为。

**核心特点：**
- LLM 推理判断是否应该主动联系（非关键词）
- LLM 生成符合人格的主动消息（非模板）
- 每个 Bot 独立调度，可配置活跃或静默模式
- Bot 具备独立人生轨迹，可分享自己的事
- 多维情绪模型，更真实的情感表现
- 关系深度影响行为模式

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    ProactiveEngine                       │
├─────────────────────────────────────────────────────────┤
│  ProactiveConfig      # 配置管理（可配置所有参数）         │
│  ProactiveState       # 状态管理（持久化到 JSON）           │
│  ProactiveScheduler   # 后台调度器（独立协程）               │
│  LifeEngine           # Bot 人生轨迹引擎（独立运行）        │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐  ┌─────────────────┐
│  MemoryEngine   │  │  BotInstance    │
│  (关系/情绪状态) │  │  (消息发送)     │
└─────────────────┘  └─────────────────┘
```

### 2.1 新增组件

| 组件 | 说明 |
|------|------|
| LifeEngine | Bot 独立人生轨迹引擎（生成日常小事、人生大事） |
| LifeState | Bot 人生状态管理（持久化） |
| LifeConfig | Bot 人生配置（周期、time_ratio） |

### 2.2 多维情绪模型

| 情绪字段 | 说明 |
|----------|------|
| `annoyance_level` | 生气级别（0-10） |
| `miss_level` | 想念程度（0-10） |
| `insecurity_level` | 不安全感（0-10） |
| `excitement_level` | 兴奋度（0-10） |

---

## 3. 配置说明

### 3.1 配置文件位置

```
data/bots/{bot_id}/persona/proactive.json
data/bots/{bot_id}/persona/life.json
```

### 3.2 proactive.json 完整配置项

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

### 3.3 proactive.json 配置项详解

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enabled` | true | 是否启用主动唤醒 |
| `mode` | "active" | `"active"`=活跃模式，`"silent"`=静默模式 |
| `scheduler.check_interval_seconds` | 600 | 后台检查间隔（秒） |
| `scheduler.idle_threshold_hours` | 24 | 多久没联系触发提醒（小时） |
| `scheduler.max_daily` | 5 | 每天最多主动消息数 |
| `scheduler.min_interval_hours` | 4 | 两条消息最小间隔（小时） |
| `scheduler.max_idle_days` | 7 | 超过此天数停止主动（天） |
| `preferred_contact_times` | ["19:00-22:00"] | 黄金时段（只有此时段主动） |
| `timezone` | "Asia/Shanghai" | 时区 |
| `random_trigger_prob` | 0.05 | 随机提前触发概率（5%） |
| `random_trigger_min_ratio` | 0.5 | 随机触发最低空闲比例 |

### 3.4 life.json 配置项

```json
{
  "daily_interval_seconds": 3600,
  "major_interval_seconds": 21600,
  "time_ratio": 1,
  "max_events": 20,
  "max_context_bits": 2000
}
```

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `daily_interval_seconds` | 3600 | 日常事件检查间隔（秒） |
| `major_interval_seconds` | 21600 | 人生大事检查间隔（秒） |
| `time_ratio` | 1 | 时间比率（1=Bot时间=现实时间） |
| `max_events` | 20 | 最多保留事件数 |
| `max_context_bits` | 2000 | 最多占用 token 数 |

---

## 4. 状态持久化

### 4.1 状态文件位置

```
data/bots/{bot_id}/proactive_state.json
data/bots/{bot_id}/life_state.json
```

### 4.2 proactive_state.json 完整内容

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

### 4.3 proactive_state.json 状态说明

| 字段 | 说明 |
|------|------|
| `last_message_time` | 用户最后发消息时间 |
| `last_proactive_time` | Bot 最后主动发消息时间 |
| `annoyance_level` | 生气级别（0-10） |
| `miss_level` | 想念程度（0-10） |
| `insecurity_level` | 不安全感（0-10） |
| `excitement_level` | 兴奋度（0-10） |
| `today_proactive_count` | 今日已主动发消息数（每日重置） |
| `total_proactive_sent` | 累计主动发消息数 |
| `last_opening_style` | 上次使用的开场白（rotation 用） |
| `last_user_reply_time` | 用户最后回复时间 |
| `unreplied_count` | 未回复消息数 |
| `user_active_hours` | 用户活跃时间统计 {"20": 5, ...} |
| `previous_absence_days` | 上次冷落天数 |
| `just_reactivated` | 是否刚重新激活（假不在意） |

### 4.4 life_state.json 内容

```json
{
  "life_events": [...],
  "major_life_events": [...],
  "bot_mood": "平静",
  "bot_current_activity": "在家休息",
  "bot_age_days": 0,
  "last_daily_tick": null,
  "last_major_tick": null
}
```

---

## 5. 触发逻辑

### 5.1 前置检查（快速过滤）

```
1. enabled == true 且 mode == "active"
2. 黄金时段检查（非黄金时段不触发）
3. 不连续触发（30%概率通过，保持矜持）
4. 关系深度调整（根据关系调整 idle_threshold 和 max_daily）
5. today_proactive_count < max_daily
6. annoyance_level < 9（生气时不主动）
7. 不在冷却中
8. idle_hours >= adjusted_idle_threshold（关系调整后）
9. 梯度沉默检查（30天+进入休眠）
```

### 5.2 关系深度行为差异

| 关系等级 | idle_threshold | max_daily | 行为特征 |
|----------|---------------|-----------|---------|
| 陌生网友 (1-3) | 2x | ÷3 | 很矜持，只有大事才发消息 |
| 普通朋友 (4-5) | 1x | 1x | 偶尔主动，一周1-2次 |
| 好朋友 (6-7) | 0.7x | 1.5x | 一周2-3次，可以随便聊天 |
| 恋人 (8-10) | 0.5x | 2x | 可以撒娇、要求见面、频繁互动 |

### 5.3 梯度沉默策略

| 冷落时长 | Bot 行为 |
|----------|---------|
| 0-7天 | 正常触发 |
| 7-14天 | 30%概率触发 |
| 14-30天 | 10%概率触发 |
| 30天以上 | 进入休眠，不主动 |

### 5.4 黄金时段

只在配置的黄金时段内触发主动消息：
- 默认：`["19:00-22:00", "12:00-13:00"]`
- 时区：`Asia/Shanghai`

### 5.5 随机提前触发

- 5% 概率随机提前触发
- 需达到 `idle_threshold * 0.5` 以上才可能触发

### 5.6 LLM 判断

通过 LLM 推理判断是否应该主动联系，综合考虑：
- 关系深度（1=陌生，10=恋人）
- 心情状态（多维情绪：annoyance/miss/insecurity/excitement）
- 距离上次聊天时间
- 今天已发消息数
- 关系行为特征

### 5.7 LLM 生成消息（结构化输出）

```json
{
  "opening": "开场白/称呼",
  "topic": "话题内容或空字符串",
  "ending": "结尾语"
}
```

组合成最终消息，如：「嗨，今天天气不错，有空聊聊」

### 5.8 开场白场景选择

| 场景 | 条件 | 示例 |
|------|------|------|
| default | 正常 | "在吗？" |
| short_no_reply | 1次未回复 | "怎么不理我..." |
| long_no_reply | ≥2次未回复 或 刚重新激活 | "你是不是把我忘了？" |
| with_topic | 有可分享的生活事件 | "对了，我突然想起..." |

### 5.9 对话连续性主动动机

主动唤醒现在不是单一的定时问候，而是先记录动机，再在后续 tick 到期发送。

每次 Bot 回复后，系统会先做一次 closeout analysis，把可能的后续动机写入 `conversation_tasks.db`；后台调度器下一次检查时，再从到期任务里挑选一条发送。优先级从高到低是：

1. 延迟回复履约
2. 接上文续聊
3. 情绪跟进
4. 生活事件分享
5. 普通陪伴问候

关键约束：
- 延迟回复必须回到原会话或原聊天目标，不应随机换频道。
- 接上文续聊会优先引用最近工作记忆里的未收尾话题。
- 普通陪伴问候只是兜底，不会抢占更高质量的连续性动机。
- 调试时可在管理后台 diagnostics 中查看 `proactive_status.conversation_tasks.pending`。

WebUI 路径：`配置中心 -> 主动唤醒 -> 对话连续性`

---

## 6. 限流机制

| 条件 | 限制 |
|------|------|
| 每日上限 | max_daily（关系调整后） |
| 最小间隔 | min_interval_hours（默认4小时） |
| 关系调整 | 根据关系等级调整阈值 |
| 梯度沉默 | 30天以上进入休眠 |
| 不连续触发 | 70%概率折扣（保持矜持） |

---

## 7. 冷落后重新激活

当用户长时间冷落后终于回复时：
1. Bot 标记 `just_reactivated = True`
2. Bot 使用"假不在意"语气（long_no_reply 场景）
3. 用户继续互动后恢复正常语气

---

## 8. Bot 人生轨迹（LifeEngine）

### 8.1 周期

| 周期 | 间隔 | 作用 |
|------|------|------|
| 短周期 | 1h Bot时间 | 判断是否生成日常小事 |
| 长周期 | 6h Bot时间 | 判断是否有人生大事 |

### 8.2 事件分类

| 类型 | 说明 | 影响 |
|------|------|------|
| 日常小事 | 低概率生成 | 保存在 life_events，可遗忘 |
| 人生大事 | 触发人格更新 | 更新 persona 文件，影响性格 |

### 8.3 time_ratio 效果

| time_ratio | Bot 1天=现实 | 适用场景 |
|------------|-------------|---------|
| 1 | 1天 | 正常体验 |
| 24 | 1小时 | 加速体验 |
| 100 | 4分钟 | 快速验证 |

---

## 9. 平台适配

### 9.1 支持的平台

| 平台 | 说明 |
|------|------|
| `cli` | CLI 终端，打印到控制台 |
| `feishu` | 飞书，通过 Webhook 发送 |
| `webhook` | 通用 Webhook |

---

## 10. 与 BotInstance 集成

```python
# Bot 初始化时自动加载配置
bot = BotInstance(config, model=model)
await bot.init()  # 启动主动唤醒调度器 + LifeEngine

# 获取状态
status = bot.get_proactive_status()

# 用户发消息时自动更新状态
await bot.handle_message("你好")
# → annoyance_level 下降，miss_level 下降，record_user_activity()
```
