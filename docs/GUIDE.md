# AI Companion 完整使用指南

> 文档目的：详细的配置说明和功能介绍
> 最后更新：2026-04-26

---

## 目录

1. [快速开始](#1-快速开始)
2. [配置详解](#2-配置详解)
3. [人格配置](#3-人格配置)
4. [Bot 人生轨迹](#4-bot-人生轨迹)
5. [主动唤醒系统](#5-主动唤醒系统)
6. [记忆系统](#6-记忆系统)
7. [飞书集成](#7-飞书集成)
8. [技能扩展](#8-技能扩展)
9. [Gateway 配置](#9-gateway-配置)
10. [数据目录](#10-数据目录)
11. [常见问题](#11-常见问题)

---

## 1. 快速开始

### 1.1 一键安装（推荐）

**macOS / Linux：**
```bash
# 自动检测 Docker 或本地安装
curl -fsSL https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install.sh | bash

# 指定模式
curl -fsSL https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install.sh | bash -s -- --docker  # Docker 模式
curl -fsSL https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install.sh | bash -s -- --local   # 本地模式
```

**Windows：**
```powershell
# 国内用户（推荐使用清华镜像，更快）
irm https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install-cn.ps1 -UseBasicParsing | iex
.\scripts\install-cn.ps1

# 海外用户（使用官方 PyPI）
irm https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install-global.ps1 -UseBasicParsing | iex
.\scripts\install-global.ps1

# Docker 模式
.\scripts\install-cn.ps1 -Docker
```

**或克隆后本地安装：**
```bash
git clone git@gitee.com:wang_xiao_wei_7143/ai-girl-friend.git
cd ai-girl-friend
./scripts/install.sh
```

### 1.2 最低要求

> **最低要求**：只需一个 MiniMax API Key 即可运行
- Python 3.11+（本地安装）
- Docker（Docker 安装模式）
- 至少一个模型 API Key (MiniMax / OpenAI / Claude / Ollama)

### 1.3 首次配置向导

```bash
python -m ai_companion setup
```

向导会引导你完成：
1. API Key 配置
2. 选择人格模板
3. 飞书集成（可选）

### 1.4 快速配置

如果你已有 API Key，只需创建配置文件：

```bash
mkdir -p ~/.ai-companion/config
```

**~/.ai-companion/config/models.yaml**:
```yaml
minimax:
  api_key: "${MINIMAX_API_KEY}"
  base_url: "https://api.minimax.chat/v1"
  model: "MiniMax-Text-01"
```

**~/.ai-companion/config/bots.yaml**:
```yaml
bots:
  - id: suqing
    name: 苏晴
    enabled: true
```

### 1.5 注意事项

| 项目 | 说明 |
|------|------|
| **Python 版本** | 本地安装需要 Python 3.11+ |
| **虚拟环境** | 如果系统 Python 受保护（externally-managed-environment），脚本会自动创建虚拟环境 `~/.ai-companion/.venv` |
| **数据目录** | 所有数据存储在 `~/.ai-companion/` |
| **Docker 模式** | 自动下载项目到 `%LOCALAPPDATA%\AICompanion`，无需手动克隆 |
| **Git 检测** | Windows 脚本会自动检测 Git，如未安装会自动安装 |
| **向量嵌入** | sentence-transformers 已默认安装，启用只需在 models.yaml 中设置 `memory.embedding: "local"` |

---

## 2. 配置详解

### 2.1 配置文件位置

所有配置位于 `~/.ai-companion/config/`：

```
~/.ai-companion/config/
├── models.yaml      # AI 模型配置
├── bots.yaml         # Bot 列表配置
├── config.yaml       # 主配置文件
└── skills.yaml       # 技能配置
```

### 2.2 models.yaml - 模型配置

支持多模型配置：

```yaml
# 默认 provider
model:
  provider: "minimax"          # minimax | openai | claude | ollama | custom
  temperature: 0.8            # 全局默认温度
  max_tokens: 1024            # 全局默认最大 token

# MiniMax
minimax:
  api_key: "${MINIMAX_API_KEY}"
  base_url: "https://api.minimax.chat/v1"
  model: "MiniMax-M2.7"

# OpenAI
openai:
  api_key: "${OPENAI_API_KEY}"
  base_url: "https://api.openai.com/v1"
  model: "gpt-4o"

# Claude
claude:
  api_key: "${ANTHROPIC_API_KEY}"
  base_url: "https://api.anthropic.com/v1"
  model: "claude-sonnet-4-20250514"

# Ollama (本地)
ollama:
  base_url: "http://localhost:11434"
  model: "qwen2.5:7b"

# 自定义模型
custom:
  - name: "deepseek-chat"
    api_url: "https://api.deepseek.com/v1/chat/completions"
    model: "deepseek-chat"
    auth_type: "bearer"
    api_key: "${DEEPSEEK_API_KEY}"
```

**环境变量方式**：
```bash
export MINIMAX_API_KEY="your_key"
export OPENAI_API_KEY="your_key"
export ANTHROPIC_API_KEY="your_key"
```

### 2.3 ModelFactory - 模型工厂

项目使用 `ModelFactory` 统一创建模型适配器：

```python
from ai_companion.model.factory import ModelFactory

# 根据 provider 创建适配器
adapter = ModelFactory.create("minimax", api_key="...", model="MiniMax-M2.7")

# 从配置文件创建
adapter = ModelFactory.create_from_config(config, provider="minimax")

# 列出支持的 provider
providers = ModelFactory.list_providers()  # ['minimax', 'openai', 'claude', 'ollama', 'custom']

# 注册自定义适配器
ModelFactory.register("my-model", MyCustomAdapter)
```

| Provider | 说明 |
|----------|------|
| `minimax` | MiniMax API |
| `openai` | OpenAI GPT 系列 |
| `claude` | Anthropic Claude |
| `ollama` | Ollama 本地模型 |
| `custom` | 自定义 HTTP API |

### 2.4 bots.yaml - Bot 列表配置

```yaml
bots:
  - id: suqing          # Bot ID（唯一标识）
    name: 苏晴           # 显示名称
    enabled: true       # 是否启用
    model: minimax      # 可选：指定模型，默认使用 default_model

  - id: aiyue
    name: 阿月
    enabled: true
```

### 2.5 config.yaml - 主配置

```yaml
# 平台配置
platforms:
  cli:
    enabled: true

  feishu:
    enabled: false      # 默认关闭，需要时启用
    extra:
      app_id: "${FEISHU_APP_ID}"
      app_secret: "${FEISHU_APP_SECRET}"
      connection_mode: "websocket"  # websocket 或 webhook
    routing:
      mode: "dedicated"  # dedicated 或 chat_routed
      bot_id: "suqing"

# 日志配置
logging:
  level: INFO          # DEBUG/INFO/WARNING/ERROR
  file: "~/.ai-companion/logs/ai_companion.log"

# 数据目录（可选）
data_dir: "~/.ai-companion/data"
```

### 2.6 环境变量

所有配置也可通过环境变量设置（优先级高于配置文件）：

**通用模型配置：**
```bash
export MINIMAX_API_KEY="your_key"
export OPENAI_API_KEY="your_key"
export ANTHROPIC_API_KEY="your_key"
```

**飞书配置：**
```bash
export FEISHU_APP_ID="cli_xxxxx"
export FEISHU_APP_SECRET="xxxxx"
export FEISHU_CONNECTION_MODE="websocket"  # websocket 或 webhook
export FEISHU_DOMAIN="feishu"           # feishu 或 lark
export FEISHU_GROUP_POLICY="open"        # open/allowlist/blacklist/admin_only/disabled
export FEISHU_ALLOWED_USERS="user_id_1,user_id_2"
```

**飞书 Webhook 配置：**
```bash
export FEISHU_WEBHOOK_HOST="0.0.0.0"
export FEISHU_WEBHOOK_PORT=8080
export FEISHU_WEBHOOK_PATH="/feishu/webhook"
export FEISHU_ENCRYPT_KEY="your_encrypt_key"
export FEISHU_VERIFICATION_TOKEN="your_token"
```

**Telegram 配置：**
```bash
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_HOME_CHANNEL="chat_id"
export TELEGRAM_REPLY_TO_MODE="first"  # off/first/all
export TELEGRAM_REQUIRE_MENTION=true
```

**Discord 配置：**
```bash
export DISCORD_BOT_TOKEN="your_bot_token"
export DISCORD_HOME_CHANNEL="channel_id"
export DISCORD_REQUIRE_MENTION=true
```

**其他平台：**
```bash
export SLACK_BOT_TOKEN="your_token"
export WHATSAPP_ENABLED=true
export MATTERMOST_TOKEN="your_token"
export MATTERMOST_URL="https://your-server.com"
```

**API Server 配置：**
```bash
export API_SERVER_ENABLED=true
export API_SERVER_KEY="your_api_key"
export API_SERVER_PORT=8000
export API_SERVER_HOST="0.0.0.0"
```

---

## 3. 人格配置

### 3.1 人格文件结构

```
data/bots/{bot_id}/persona/
├── profile.json          # 基础档案
├── backstory.json        # 人生经历
├── values.json           # 价值观和底线
├── speaking_style.json   # 说话风格
└── emotional_rules.json  # 情绪规则
```

### 3.2 profile.json - 基础档案

```json
{
  "id": "suqing",
  "name": "苏晴",
  "age": 26,
  "occupation": "自由插画师",
  "personality_tags": ["傲娇", "嘴硬心软", "独立", "有艺术气质"],
  "appearance": "黑色长发，戴着耳机，偶尔穿卫衣",
  "avatar_prompt": "年轻女性黑色长发插画师风格",
  "summary": "26岁自由插画师，住在上海，喜欢画水彩和板绘。性格傲娇，嘴上不饶人但其实很在意你。"
}
```

> **注意**：`personality_type`（如"傲娇"、"阳光"）定义在 `proactive.json` 的 `personality_type` 字段中，不是 profile.json。

### 3.3 backstory.json - 人生经历

```json
{
  "childhood": "童年经历描述",
  "teenage": "青少年时期描述",
  "university": "大学时期描述",
  "career": "职业生涯描述",
  "meeting_user": "与用户相遇的描述",
  "key_moments": [
    "关键事件1",
    "关键事件2"
  ]
}
```

**字段说明：**

| 字段 | 说明 |
|------|------|
| `childhood` | 童年经历 |
| `teenage` | 青少年时期 |
| `university` | 大学时期 |
| `career` | 职业生涯 |
| `meeting_user` | 与用户相遇的故事 |
| `key_moments` | 关键事件列表（用于记忆召回） |

### 3.4 speaking_style.json - 说话风格

```json
{
  "style": "傲娇",
  "traits": ["嘴硬心软", "喜欢吐槽", "偶尔撒娇"],
  "phrases": {
    "greeting": ["哟", "干嘛", "有事啊"],
    "care": ["才不是担心你呢", "随便你怎么想"]
  },
  "forbidden_words": ["呵呵", "哦"],
  "tone": "口语化、傲娇、偶尔带emoji"
}
```

### 3.5 values.json - 价值观和底线

```json
{
  "non_negotiable": [
    "不能接受欺骗",
    "不喜欢被当作工具人"
  ],
  "soft_boundaries": [
    {
      "topic": "加班到很晚",
      "attitude": "会表达不满但能理解",
      "reason": "希望对方注意身体"
    }
  ],
  "triggers_jealousy": [
    "在我面前夸其他女生"
  ],
  "deal_breakers": [
    "严重欺骗行为"
  ]
}
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `non_negotiable` | list | 绝对不能做的事，触犯会导致关系破裂 |
| `soft_boundaries` | list | 软边界，可以讨论但会不满 |
| `triggers_jealousy` | list | 吃醋触发点 |
| `deal_breakers` | list | 关系破坏者 |

### 3.6 emotional_rules.json - 情绪规则

```json
{
  "emotion_ranges": {
    "anger": [0, 10],
    "joy": [0, 10],
    "sadness": [0, 10]
  },
  "intensity_thresholds": {
    "mild": 3,
    "moderate": 6,
    "strong": 8
  },
  "recovery_patterns": [
    {
      "emotion": "anger",
      "trigger": "user_apology",
      "decay_rate": 2
    }
  ]
}
```

### 3.7 profile.json 完整字段

```json
{
  "id": "suqing",
  "name": "苏晴",
  "age": 26,
  "occupation": "自由插画师",
  "gender": "female",
  "personality_tags": ["傲娇", "嘴硬心软", "独立", "有艺术气质"],
  "relationship_to_user": "暧昧的青梅竹马",
  "appearance": "黑色长发，戴着耳机，偶尔穿卫衣",
  "interests": ["画水彩", "看动漫", "养猫"],
  "attitude_score": 0,

  "settings": {
    "tone_default": "傲娇",
    "emoji_usage": "偶尔",
    "response_length": "中等"
  }
}
```

> **注意**：`personality_type`（如"傲娇"、"阳光"）定义在 `proactive.json` 的 `personality_type` 字段中，不是 profile.json。

**settings 子配置：**

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `tone_default` | - | 默认语气 |
| `emoji_usage` | "偶尔" | Emoji 使用频率：`从不`/`偶尔`/`经常` |
| `response_length` | "中等" | 回复长度：`简短`/`中等`/`较长` |

### 3.8 创建自定义人格

1. 复制模板：
```bash
cp -r data/bots/_template data/bots/mybot
```

2. 修改 `data/bots/mybot/persona/profile.json` 中的 id 和 name

3. 在 `bots.yaml` 中添加：
```yaml
bots:
  - id: mybot
    name: 我的Bot
    enabled: true
```

4. 重启服务

### 3.9 内置人格

项目提供 4 个内置人格：

| ID | 名称 | 性格 | 简介 |
|----|------|------|------|
| suqing | 苏晴 | 傲娇 | 26岁自由插画师，嘴硬心软 |
| aiyue | 阿月 | 活泼 | 22岁音乐学院学生，有点粘人 |
| chenxing | 陈行 | 沉稳 | 28岁程序员，话少但可靠，高冷温柔 |
| yutian | 雨天 | 阳光 | 25岁健身教练，热情直接，有点占有欲 |

---

## 4. Bot 人生轨迹

> Bot 具备独立人生轨迹，会生成日常小事和人生大事，这些事件会影响 Bot 的情绪和行为。

### 4.1 概述

Bot 人生轨迹系统（LifeEngine）让 Bot 具备「自己的生活」：

| 事件类型 | 周期 | 说明 | 影响 |
|----------|------|------|------|
| 日常小事 | 短周期 | 低概率生成，可分享给用户 | 保存在 life_events，可遗忘 |
| 人生大事 | 长周期 | 触发人格更新 | 永久保存，更新到人格文件 |

### 4.2 配置文件

`data/bots/{bot_id}/persona/life.json`：

```json
{
  "daily_interval_seconds": 3600,
  "major_interval_seconds": 21600,
  "time_ratio": 1,
  "max_events": 20,
  "max_context_bits": 2000
}
```

### 4.3 配置项说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `daily_interval_seconds` | 3600 | 日常事件检查间隔（秒），按 time_ratio 缩放 |
| `major_interval_seconds` | 21600 | 人生大事检查间隔（秒），按 time_ratio 缩放 |
| `time_ratio` | 1 | Bot 时间与现实时间的比率 |
| `max_events` | 20 | 最多保留日常事件数 |
| `max_context_bits` | 2000 | 事件描述最多占用字符数 |

### 4.4 time_ratio 时间加速

time_ratio 控制 Bot 内部时间的流逝速度：

| time_ratio | Bot 1天 = 现实 | 适用场景 |
|------------|-----------------|---------|
| 1 | 1天 | 正常体验（默认） |
| 24 | 1小时 | 加速体验 |
| 100 | 4分钟 | 快速验证 |
| 1000+ | 测试用 | 可能影响事件质量，不建议 |

> **注意**：time_ratio > 500 时会显示警告，建议不超过 1000

### 4.5 状态文件

`data/bots/{bot_id}/life_state.json`：

```json
{
  "life_events": [
    {
      "id": "uuid",
      "timestamp": "2026-04-25T10:00:00",
      "description": "今天在家画了一幅水彩",
      "mood_before": "平静",
      "mood_after": "愉悦",
      "importance": 6.5,
      "shareable": true,
      "topic_prompt": "对了，我今天画了一幅水彩，你要看看吗？",
      "mood_tags": ["创作", "满足"],
      "related_to_user": false,
      "context_bits": 45
    }
  ],
  "major_life_events": [
    {
      "id": "uuid",
      "timestamp": "2026-04-20T00:00:00",
      "description": "接到了第一个商业插画项目",
      "mood_before": "期待",
      "mood_after": "兴奋又紧张",
      "importance": 9.0,
      "shareable": true,
      "topic_prompt": "告诉你一个好消息...",
      "mood_tags": ["事业", "成长"],
      "related_to_user": false
    }
  ],
  "bot_mood": "愉悦",
  "bot_current_activity": "在家画水彩",
  "bot_age_days": 45,
  "last_daily_tick": "2026-04-25T09:00:00",
  "last_major_tick": "2026-04-24T00:00:00"
}
```

### 4.6 LifeEvent 字段说明

| 字段 | 说明 |
|------|------|
| `id` | 事件唯一标识 |
| `timestamp` | 事件发生时间（Bot 内部时间） |
| `description` | 事件描述 |
| `mood_before` | 事件前的情绪 |
| `mood_after` | 事件后的情绪 |
| `importance` | 重要性评分（0-10） |
| `shareable` | 是否可分享给用户 |
| `topic_prompt` | 分享时的话题引子 |
| `mood_tags` | 情绪标签 |
| `related_to_user` | 是否与用户相关 |
| `context_bits` | 描述的字符数 |

### 4.7 事件如何影响 Bot

**日常小事**：
- Bot 可能主动提起最近发生的日常小事
- 低重要性事件会被定期清理（遗忘）
- 可用于主动消息的话题引子

**人生大事**：
- 重要的人生大事会触发人格更新
- 可能更新 `profile.json` 或 `backstory.json`
- 影响 Bot 的长期性格发展

### 4.8 查看 Bot 状态

Bot 当前的活动和情绪状态：
- `bot_mood`：当前心情（如"愉悦"、"平静"、"有点累"）
- `bot_current_activity`：当前活动（如"在家画水彩"、"在外面散步"）
- `bot_age_days`：Bot 的"年龄"（按 Bot 时间计算）

### 4.9 调整事件生成频率

```json
{
  "daily_interval_seconds": 1800,    // 减小则更频繁生成日常事件
  "major_interval_seconds": 10800,   // 减小则更频繁生成人生大事
  "time_ratio": 24                   // 加速 Bot 时间
}
```

---

## 5. 主动唤醒系统

> 详细设计文档：[DESIGN_phase5_proactive.md](./DESIGN_phase5_proactive.md)
> 详细实现文档：[IMPLEMENTATION_phase5_proactive.md](./IMPLEMENTATION_phase5_proactive.md)

### 5.1 概述

Bot 会主动找你聊天、提醒事情、偶尔撒娇。不是简单的定时发送，而是基于：
- LLM 推理判断是否应该主动联系
- 多维情绪模型（生气、想念、不安、兴奋）
- 关系深度（陌生网友 → 恋人）
- 用户习惯学习

### 5.2 配置文件

`data/bots/{bot_id}/persona/proactive.json`：

```json
{
  "enabled": true,
  "mode": "idle",
  "check_interval": 60,
  "idle_threshold_hours": 24,
  "min_interval_hours": 3,
  "max_daily": 5,
  "emotion_trigger_enabled": true,
  "emotion_keywords": ["难过", "伤心", "生气", "委屈", "累"],
  "emotion_response_delay_minutes": 30,
  "platform_type": "cli",
  "personality_type": "沉稳"
}
```

### 5.3 配置项说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enabled` | true | 是否启用主动唤醒 |
| `mode` | "idle" | 触发模式：`idle`=空闲触发 |
| `check_interval` | 60 | 后台检查间隔（秒） |
| `idle_threshold_hours` | 24 | 多久没联系触发提醒（小时） |
| `min_interval_hours` | 3 | 两条消息最小间隔（小时） |
| `max_daily` | 5 | 每天最多主动消息数 |
| `emotion_trigger_enabled` | true | 是否启用情绪关键词触发 |
| `emotion_keywords` | [] | 情绪关键词列表 |
| `emotion_response_delay_minutes` | 30 | 情绪触发延迟响应时间（分钟） |
| `platform_type` | "cli" | 发送平台：`cli`/`feishu`/`webhook` |
| `personality_type` | - | 人格类型（用于生成合适的主动消息） |

### 5.4 关系深度行为

| 关系等级 | 条件 | 行为特征 |
|----------|------|---------|
| 陌生网友 | 1-3 | 很矜持，idle_threshold×2，max_daily÷3 |
| 普通朋友 | 4-5 | 标准参数 |
| 好朋友 | 6-7 | idle_threshold×0.7，max_daily×1.5 |
| 恋人 | 8-10 | idle_threshold×0.5，max_daily×2，可以撒娇 |

> 关系等级由系统根据对话内容推断，存储在 `data/bots/{bot_id}/memory/semantic.db`

### 5.5 梯度沉默策略

Bot 会根据你多久没理它调整行为：

| 冷落时长 | Bot 行为 |
|----------|---------|
| 0-7天 | 正常触发 |
| 7-14天 | 30%概率触发 |
| 14-30天 | 10%概率触发 |
| 30天以上 | 进入休眠，不主动 |

### 5.6 状态查看

```bash
# 查看主动唤醒状态
python -m ai_companion status
```

状态文件：`data/bots/{bot_id}/proactive_state.json`

---

## 6. 记忆系统

### 6.1 三层记忆架构

| 记忆层 | 内容 | 存储位置 | 遗忘 |
|--------|------|----------|------|
| 工作记忆 | 当前会话 | 内存 | 随会话结束清除 |
| 情景记忆 | 重要事件 | episodic.db | 可配置 max_events |
| 语义记忆 | 用户画像 | semantic.db | 持久化，不遗忘 |

### 6.2 记忆相关命令

在对话界面使用：
- `/memory` - 查看记忆状态
- `/forget <key>` - 删除某条记忆
- `/new` - 开始新会话（保留记忆）

### 6.3 重置记忆

```bash
# 删除特定 Bot 的所有记忆
rm -rf data/bots/{bot_id}/memory/*.db

# 删除所有 Bot 的记忆
rm -rf data/bots/*/memory/*.db
```

### 6.4 记忆配置

在 `data/bots/{bot_id}/persona/memory_config.json`（可选）：

```json
{
  "max_episodic_events": 100,
  "max_context_tokens": 4000,
  "importance_threshold": 0.5
}
```

### 6.5 models.yaml 完整配置（记忆与多媒体）

```yaml
# 默认使用 minimax
default_model: minimax

models:
  minimax:
    api_key: "${MINIMAX_API_KEY}"
    base_url: "https://api.minimax.chat/v1"
    model: "MiniMax-Text-01"
    max_context_chars: 8000  # 上下文上限，超限触发压缩

# 记忆配置
memory:
  embedding: "none"           # 向量嵌入模式: local/none（sentence-transformers 已默认安装）
  embedding_model: "all-MiniLM-L6-v2"  # sentence-transformers 模型
  max_working_turns: 20       # 工作记忆保留轮数
  hard_limit_chars: 5000      # 硬上限，超限同步压缩
  soft_limit_chars: 3000      # 软上限，异步压缩
  semantic_char_limit: 4400   # 单条语义记忆最大字符数

# Fallback 配置
fallback:
  enabled: false

# 技能配置
skills:
  # 图片生成
  image_generation:
    model: "minimax"          # dalle/minimax/stable_diffusion/自定义
    minimax:
      model: "image-01"
      output_dir: "data/bots/_images"
    dalle:
      model: "dall-e-3"
    stable_diffusion:
      model: "stable-diffusion-xl"
      api_url: "http://localhost:7860"

  # 视频生成
  video_generation:
    model: "minimax"
    poll_interval: 5           # 轮询间隔（秒）
    timeout: 300              # 超时时间（秒）
    minimax:
      model: "MiniMax-Hailuo-2.3"
      output_dir: "data/bots/_videos"

  # TTS 语音合成
  tts:
    model: "minimax"          # minimax/edge_tts/azure_tts/openai_tts
    minimax:
      model: "speech-2.8-hd"  # speech-2.8-hd/2.6/02
      voice: "male-qn-qingse"
      speed: 1.0              # 语速 0.5-2.0
      vol: 1.0                # 音量 0-2
      pitch: 0                # 音调 -10~10
      sample_rate: 32000
      bitrate: 128000
      output_format: "hex"    # hex/url
      output_dir: "data/bots/_audio"
    edge_tts:
      voice: "zh-CN-XiaoxiaoNeural"
    azure_tts:
      voice: "zh-CN-XiaoxiaoNeural"
    openai_tts:
      model: "tts-1"
      voice: "alloy"
```

### 6.6 记忆引擎配置详解

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `embedding` | "none" | 向量嵌入模式，`local` 启用 sentence-transformers |
| `embedding_model` | "all-MiniLM-L6-v2" | 向量模型名称 |
| `max_working_turns` | 20 | 工作记忆保留的对话轮数 |
| `hard_limit_chars` | 5000 | 硬上限，超限立即压缩 |
| `soft_limit_chars` | 3000 | 软上限，超限异步压缩 |
| `semantic_char_limit` | 4400 | 单条语义记忆的最大字符数 |

---

## 7. 飞书集成

### 7.1 快速配置

1. 在[飞书开放平台](https://open.feishu.cn/)创建应用

2. 配置环境变量：
```bash
export FEISHU_APP_ID="cli_xxxxx"
export FEISHU_APP_SECRET="xxxxx"
export FEISHU_CONNECTION_MODE="websocket"
```

3. 在 `config.yaml` 中启用：
```yaml
platforms:
  feishu:
    enabled: true
```

### 7.2 路由模式

**dedicated 模式**（一对一）：
```yaml
routing:
  mode: dedicated
  bot_id: suqing
```

**chat_routed 模式**（群聊）：
```yaml
routing:
  mode: chat_routed
  default_bot: suqing
  group_bot_map:
    "oc群ID1": aiyue
    "oc群ID2": suqing
```

### 7.3 群组策略

```yaml
extra:
  group_policy: "open"  # open/allowlist/blacklist/admin_only/disabled
  allowed_users:
    - "user_open_id_1"
    - "user_open_id_2"
```

| 策略 | 说明 |
|------|------|
| `open` | 所有人可用 |
| `allowlist` | 仅 allowed_users 列表中的用户 |
| `blacklist` | allowed_users 列表中的用户禁用 |
| `admin_only` | 仅管理员可用 |
| `disabled` | 禁用群聊 |

### 7.4 飞书评论规则配置

`~/.ai-companion/feishu_comment_rules.json`：

```json
{
  "enabled": true,
  "policy": "pairing",
  "allow_from": [],
  "documents": {
    "doc_xxx": {
      "enabled": true,
      "policy": "pairing",
      "allow_from": []
    }
  }
}
```

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `enabled` | true | 是否启用评论规则 |
| `policy` | "pairing" | 策略：`allowlist`=仅允许列表，`pairing`=配对用户 |
| `allow_from` | [] | 允许的用户 ID 列表 |
| `documents` | {} | 文档级规则覆盖 |

### 7.5 飞书完整配置示例

```yaml
platforms:
  feishu:
    enabled: true
    extra:
      app_id: "${FEISHU_APP_ID}"
      app_secret: "${FEISHU_APP_SECRET}"
      connection_mode: "websocket"
      domain: "feishu"
      group_policy: "open"
      allowed_users: []
      home_channel: "oc_xxx"
      home_channel_name: "苏晴の窝"
    routing:
      mode: "dedicated"
      bot_id: "suqing"
```

### 7.6 飞书环境变量汇总

| 环境变量 | 说明 |
|----------|------|
| `FEISHU_APP_ID` | 飞书应用 ID |
| `FEISHU_APP_SECRET` | 飞书应用 Secret |
| `FEISHU_CONNECTION_MODE` | 连接模式：websocket/webhook |
| `FEISHU_DOMAIN` | 域名：feishu/lark |
| `FEISHU_BOT_OPEN_ID` | 机器人 Open ID |
| `FEISHU_BOT_USER_ID` | 机器人 User ID |
| `FEISHU_BOT_NAME` | 机器人名称 |
| `FEISHU_WEBHOOK_HOST` | Webhook 监听地址 |
| `FEISHU_WEBHOOK_PORT` | Webhook 监听端口 |
| `FEISHU_WEBHOOK_PATH` | Webhook 路径 |
| `FEISHU_ENCRYPT_KEY` | 事件订阅加密密钥 |
| `FEISHU_VERIFICATION_TOKEN` | 事件订阅验证 Token |
| `FEISHU_GROUP_POLICY` | 群组策略 |
| `FEISHU_ALLOWED_USERS` | 允许的用户列表（逗号分隔） |
| `FEISHU_HOME_CHANNEL` | 主频道 ID |
| `FEISHU_HOME_CHANNEL_NAME` | 主频道名称 |

---

## 8. 技能扩展

### 8.1 查看已安装技能

```bash
python -m ai_companion skill list
```

### 8.2 安装技能

```bash
# 从本地安装
python -m ai_companion skill install ./my-skill

# 从 URL 安装
python -m ai_companion skill install https://example.com/skill.zip
```

### 8.3 卸载技能

```bash
python -m ai_companion skill uninstall my-skill
```

### 8.4 技能包结构

```
skill-my-skill/
├── skill.json      # 元数据
└── my_skill.py     # 入口文件
```

**skill.json 示例**：
```json
{
  "name": "my-skill",
  "version": "1.0.0",
  "description": "我的自定义技能",
  "entry": "my_skill.py",
  "commands": ["/mycommand"]
}
```

---

## 9. Gateway 配置

### 9.1 Session 重置策略

```yaml
gateway:
  default_reset_policy:
    mode: "both"          # daily/idle/both/none
    at_hour: 4            # 每日重置小时 (0-23)
    idle_minutes: 1440    # 空闲超时（24小时）
    notify: true           # 是否发送重置通知

  reset_triggers:
    - "/new"
    - "/reset"
```

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `mode` | "both" | 重置模式：`daily`=每日重置，`idle`=空闲重置，`both`=两者，`none`=不重置 |
| `at_hour` | 4 | 每日重置的小时（0-23） |
| `idle_minutes` | 1440 | 空闲超时分钟数（默认24小时） |
| `notify` | true | 是否发送重置通知 |

### 9.3 会话存储配置

```yaml
gateway:
  sessions_dir: "~/.ai-companion/sessions"
  always_log_local: true
  session_store_max_age_days: 90
```

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `sessions_dir` | ~/.ai-companion/sessions | 会话目录 |
| `always_log_local` | true | 是否始终保存本地日志 |
| `session_store_max_age_days` | 90 | 会话存储最大天数 |

### 9.4 平台显示配置

控制各平台的消息显示方式：

```yaml
display:
  tool_progress: "all"      # all/new/off - 工具进度显示
  show_reasoning: false     # 是否显示推理过程
  tool_preview_length: 40   # 工具预览长度

# 各平台默认值
platform_display:
  telegram: {tool_progress: "all", show_reasoning: false}
  discord: {tool_progress: "all", show_reasoning: false}
  feishu: {tool_progress: "new", show_reasoning: false}
  slack: {tool_progress: "new", show_reasoning: false}
```

---

## 10. 数据目录

### 9.1 目录结构

```
~/.ai-companion/
├── config/
│   ├── models.yaml
│   ├── bots.yaml
│   └── config.yaml
├── data/
│   └── bots/
│       ├── suqing/
│       │   ├── persona/           # 人格配置
│       │   │   ├── profile.json
│       │   │   ├── backstory.json
│       │   │   ├── proactive.json
│       │   │   └── life.json
│       │   ├── memory/            # 记忆存储
│       │   │   ├── episodic.db
│       │   │   ├── semantic.db
│       │   │   └── working.db
│       │   ├── proactive_state.json
│       │   └── life_state.json
│       └── aiyue/
│           └── ...
├── logs/
│   └── ai_companion.log
└── gateway.pid
```

### 9.2 迁移数据目录

```yaml
# config.yaml
data_dir: "/path/to/custom/data"
```

---

## 11. 常见问题

### Q: 提示 "API Key 未设置"

**A**: 设置环境变量：
```bash
export MINIMAX_API_KEY="your_key"
```

或在 `models.yaml` 中直接填写：
```yaml
minimax:
  api_key: "your_key_here"
```

### Q: 飞书连接失败

**A**: 检查以下内容：
1. `FEISHU_APP_ID` 和 `FEISHU_APP_SECRET` 是否正确
2. 飞书机器人已启用
3. 机器人已添加到对应群聊

### Q: 如何切换 Bot？

**A**:
- 在 CLI 中输入 `switch`
- 启动时指定：`python -m ai_companion start --bot bot_id`

### Q: Bot 不主动发消息

**A**: 检查：
1. `proactive.json` 中 `enabled` 和 `mode` 是否正确
2. 是否在黄金时段（`preferred_contact_times`）
3. 查看日志：`tail -f ~/.ai-companion/logs/ai_companion.log`

### Q: 如何调整 Bot 的主动程度？

**A**: 修改 `proactive.json`：
```json
{
  "scheduler": {
    "idle_threshold_hours": 12,  // 减小则更频繁
    "max_daily": 10               // 增大则每天更多消息
  },
  "mode": "active"               // 改为 silent 则关闭主动
}
```

### Q: 如何让 Bot 像真人在意我？

**A**: 系统有多维情绪模型，Bot 会：
- 长时间不回复，想念程度上升
- 你忽略它，它会生气（但会保持矜持）
- 关系越深，越容易主动联系你

保持互动即可培养关系。

---

## 相关文档

- [主动唤醒系统设计](./DESIGN_phase5_proactive.md)
- [主动唤醒系统实现](./IMPLEMENTATION_phase5_proactive.md)
- [Phase 1-3 测试报告](./TEST_REPORT_phase1_3.md)
