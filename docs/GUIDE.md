# AI Companion 完整使用指南

> 文档目的：详细的配置说明和功能介绍
> 最后更新：2026-04-29

---

## 目录

1. [快速开始](#1-快速开始)
2. [配置详解](#2-配置详解)
3. [人格配置](#3-人格配置)
4. [Bot 人生轨迹](#4-bot-人生轨迹)
5. [主动唤醒系统](#5-主动唤醒系统)
6. [记忆系统](#6-记忆系统)
7. [飞书集成](#7-飞书集成)
8. [微信个人号通道](#8-微信个人号通道)
9. [技能扩展](#9-技能扩展)
10. [Gateway 配置](#10-gateway-配置)
11. [管理后台](#11-管理后台)
12. [数据目录](#12-数据目录)
13. [常见问题](#13-常见问题)

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
- 至少一个模型 API Key (MiniMax / OpenAI / Claude / MiMo / Ollama)

### 1.3 首次配置向导

```bash
ai-companion setup
```

向导会引导你完成：
1. API Key 配置
2. 创建或更新自定义 Bot
3. 飞书和微信集成（可选）

重复运行 `setup` 时，向导会读取现有配置并默认保留旧值。没有选择重新配置或覆盖的部分不会被清空；例如只重新设置模型时，已有 `bots.yaml`、Bot persona、`proactive.json`、`life.json` 和飞书配置都会保留。

### 1.4 单独配置微信通道

如果已完成基础配置，只想补充或调整微信个人号通道，不需要重新跑完整向导：

```bash
ai-companion weixin
```

等价于：

```bash
ai-companion weixin setup
```

默认会写入 `~/.ai-companion/config/config.yaml` 的 `platforms.weixin`，并同步 `~/.ai-companion/.env` 里的 `WEIXIN_*` 环境变量。只想写 `config.yaml` 时可使用：

```bash
ai-companion weixin --no-env
```

### 1.5 一键更新

以后更新最新代码不需要卸载重装：

```bash
ai-companion update
```

国内网络可使用清华 PyPI 镜像同步依赖：

```bash
ai-companion update --cn
```

更新命令会保留 `~/.ai-companion/` 下的配置、Bot 人格、记忆和日志。如果 Gateway 正在运行，默认会先停止，更新完成后自动重新启动。

### 1.6 快速配置

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
  - id: lin_wanqing
    name: 林晚晴
    enabled: true
```

### 1.6 注意事项

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
  provider: "minimax"          # minimax | openai | claude | mimo | ollama | custom
  temperature: 0.8            # 全局默认温度
  max_tokens: 1024            # 全局默认最大 token

# MiniMax
minimax:
  api_key: "${MINIMAX_API_KEY}"
  base_url: "https://api.minimax.chat/v1"
  model: "MiniMax-M2.7"
  max_context_tokens: 20000

# OpenAI
openai:
  api_key: "${OPENAI_API_KEY}"
  base_url: "https://api.openai.com/v1"
  model: "gpt-4o"
  max_context_tokens: 20000

# Claude
claude:
  api_key: "${ANTHROPIC_API_KEY}"
  base_url: "https://api.anthropic.com/v1"
  model: "claude-sonnet-4-20250514"
  max_context_tokens: 20000

# Xiaomi MiMo
mimo:
  api_key: "${MIMO_API_KEY}"
  base_url: "https://token-plan-cn.xiaomimimo.com/v1"
  model: "mimo-v2.5-pro"
  max_context_tokens: 1048576

# Ollama (本地)
ollama:
  base_url: "http://localhost:11434"
  model: "qwen2.5:7b"
  max_context_tokens: 20000

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
export MIMO_API_KEY="your_key"
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
providers = ModelFactory.list_providers()  # ['minimax', 'openai', 'claude', 'mimo', 'ollama', 'custom']

# 注册自定义适配器
ModelFactory.register("my-model", MyCustomAdapter)
```

| Provider | 说明 |
|----------|------|
| `minimax` | MiniMax API |
| `openai` | OpenAI GPT 系列 |
| `claude` | Anthropic Claude |
| `mimo` | Xiaomi MiMo 大模型 |
| `ollama` | Ollama 本地模型 |
| `custom` | 自定义 HTTP API |

### 2.4 bots.yaml - Bot 列表配置

```yaml
bots:
  - id: lin_wanqing     # Bot ID（唯一标识）
    name: 林晚晴         # 显示名称
    enabled: true       # 是否启用
    model: minimax      # 可选：指定模型，默认使用 default_model

  - id: ethan_reed
    name: Ethan Reed
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
      mode: "dedicated"  # 飞书 App 与 Bot 固定一对一绑定
      bot_id: "lin_wanqing"

  weixin:
    enabled: false      # 默认关闭，需要时启用
    token: "${WEIXIN_TOKEN}"
    extra:
      account_id: "${WEIXIN_ACCOUNT_ID}"
      base_url: "https://ilinkai.weixin.qq.com"
      cdn_base_url: "https://novac2c.cdn.weixin.qq.com/c2c"
      dm_policy: "allowlist"
      allow_from: ["wxid_xxx"]
      group_policy: "disabled"
      group_allow_from: []
      split_multiline_messages: false
      send_gradual_sentences: true
      send_gradual_max_chunks: 5
      send_gradual_group_max_chars: 80
      send_gradual_min_delay_seconds: 1.0
      send_chunk_retries: 6
      send_chunk_retry_delay_seconds: 1.5
      send_chunk_retry_max_delay_seconds: 15
    routing:
      mode: "dedicated"
      bot_id: "lin_wanqing"
    home_channel:
      platform: "weixin"
      chat_id: "wxid_xxx"
      name: "微信私聊"

# 日志配置
logging:
  level: INFO          # DEBUG/INFO/WARNING/ERROR
  file: "~/.ai-companion/logs/ai_companion.log"
  max_file_size: "50MB" # 单个日志文件最多保留最近 50MB

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
export MIMO_API_KEY="your_key"
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

**微信 iLink 配置：**
```bash
export WEIXIN_TOKEN="your_bot_token"
export WEIXIN_ACCOUNT_ID="your_ilink_bot_id"
export WEIXIN_BOT_ID="lin_wanqing"
export WEIXIN_DM_POLICY="allowlist"              # allowlist/open/disabled
export WEIXIN_ALLOWED_USERS="wxid_xxx,wxid_yyy"
export WEIXIN_GROUP_POLICY="disabled"            # disabled/allowlist/open
export WEIXIN_GROUP_ALLOWED_USERS="room_xxx"
export WEIXIN_HOME_CHANNEL="wxid_xxx"
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
├── conversation_style_rules.json # 对话风格规则，降低 AI 味
├── proactive.json        # 主动唤醒配置
└── life.json             # 人生轨迹配置
```

完整字段字典见：[Bot JSON 字段说明](./BOT_JSON_FIELDS.md)。

> 注意：运行时读取的 `.json` 文件必须保持标准 JSON，不能写 `//` 或 `/* */` 注释。需要字段解释时看 `docs/BOT_JSON_FIELDS.md`，不要把注释直接写进 JSON 文件。

### 3.2 profile.json - 基础档案

```json
{
  "id": "lin_wanqing",
  "name": "林晚晴",
  "age": 27,
  "occupation": "古籍修复师",
  "personality_tags": ["清冷温柔", "观察力强", "慢热", "有分寸感"],
  "appearance": "黑色长发，常穿米白色针织衫或亚麻衬衣",
  "avatar_prompt": "年轻女性古籍修复师，安静温柔，旧书店氛围",
  "summary": "27岁古籍修复师，安静慢热，习惯用行动照顾人。"
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
  "style": "清冷温柔",
  "traits": ["慢热", "观察细致", "克制关心"],
  "phrases": {
    "greeting": ["今天好像有点累。", "先别急。"],
    "care": ["我听见了。", "慢一点也没关系。"]
  },
  "forbidden_words": ["呵呵", "随便"],
  "tone": "安静、细腻、克制，不滥用 emoji"
}
```

### 3.5 conversation_style_rules.json - 对话风格规则

`speaking_style.json` 描述 Bot 的声音和表达习惯，`conversation_style_rules.json` 更关注“怎么避免 AI 味”和“不同场景怎么拿捏分寸”。

```json
{
  "reply_principles": [
    "先回应用户当下这句话，再决定是否展开。",
    "少用总结式、客服式、教学式表达。"
  ],
  "avoid_phrases": [
    "我理解你的感受",
    "以下是一些建议",
    "希望这能帮到你"
  ],
  "avoid_patterns": [
    "日常聊天不要默认列 1、2、3。",
    "不要每次先总结再给建议。"
  ],
  "natural_patterns": [
    "可以用短句、停顿、轻微口语化反应。",
    "把记忆当作相处背景，不要显式说明记忆来源。"
  ],
  "intent_style": {
    "emotional_support": "先接住情绪，少讲道理，必要时只问一个小问题。",
    "task_request": "直接完成任务，少带情绪表演。"
  }
}
```

这份文件会被 `PersonaEngine` 读入 system prompt；生成后的回复还会经过本地 `ResponseStylePolisher` 做轻量清洗，去掉常见 AI 口癖。

### 3.6 values.json - 价值观和底线

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
  "id": "lin_wanqing",
  "name": "林晚晴",
  "age": 27,
  "occupation": "古籍修复师",
  "gender": "female",
  "personality_tags": ["清冷温柔", "观察力强", "慢热", "有分寸感"],
  "relationship_to_user": "认识很久的朋友，关系正在从熟悉走向更亲密",
  "appearance": "黑色长发，常穿米白色针织衫或亚麻衬衣",
  "interests": ["古籍修复", "雨天散步", "手写便签"],
  "attitude_score": 0,

  "settings": {
    "tone_default": "安静温柔",
    "emoji_usage": "从不",
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

### 3.9 新 Bot 样例

项目提供 6 个新 Bot 样例，详细设计方法见 [Bot 设计指引](./BOT_DESIGN_GUIDE.md)。

| ID | 名称 | 性别 | 性格方向 |
|----|------|------|----------|
| lin_wanqing | 林晚晴 | 女 | 清冷温柔、慢热、细腻 |
| shen_nian | 沈念 | 女 | 灵动、嘴快心软、创作型 |
| sofia_rivera | Sofia Rivera | 女 | 英文、热情直接、纪录片摄影师 |
| gu_yichen | 顾以辰 | 男 | 冷静可靠、低表达、责任感强 |
| zhou_yan | 周砚 | 男 | 松弛幽默、会照顾人、生活感 |
| ethan_reed | Ethan Reed | 男 | 英文、理性克制、英式冷幽默 |

---

## 4. Bot 人生轨迹

> Bot 具备独立人生轨迹，会生成日常小事和人生大事，这些事件会影响 Bot 的情绪和行为。
> 详细设计文档：[DESIGN_phase6_life_timeline.md](./DESIGN_phase6_life_timeline.md)

### 4.1 概述

Bot 人生轨迹系统（LifeEngine）让 Bot 具备「自己的生活」：

| 事件类型 | 周期 | 说明 | 影响 |
|----------|------|------|------|
| 日常小事 | 短周期 | 低概率生成，可分享给用户 | 保存在 life_events，可遗忘 |
| 人生大事 | 长周期 | 触发人格更新 | 永久保存，更新到人格文件 |

**新增功能（v2）**：

| 功能 | 说明 |
|------|------|
| 季节系统 | Bot 知道自己活在哪个季节（春夏秋冬），影响事件生成 |
| 日期时间线 | Bot 知道自己活在几月几日、周几 |
| 节假日系统 | Bot 知道春节、中秋、国庆等节假日 |
| 生日自动触发 | 每年的生日会自动生成事件 |
| 年龄里程碑 | 在特定年龄（如18岁高考）触发固定事件 |
| 实际年龄计算 | 优先基于 `birth_date` + `life_state.current_date` 精确计算，缺失日期时回退到初始年龄 + `bot_age_days` |
| 场景池与去重 | 日常小事内置 200+ 场景，每次随机抽少量候选给 LLM，并按 `scenario_key` 冷却去重 |
| 生活画像 | `daily_life_profile` 和性格标签共同影响日常事件候选权重 |
| 意外事件 | 人生大事之外有独立低概率意外通道，默认概率 `0.01`，整体冷却默认 365 天 |
| 时间线注入 | 普通对话、日常事件、人生大事、主动唤醒判断和主动消息都会带入 Bot 当前时间线 |

### 4.2 配置文件

`data/bots/{bot_id}/persona/life.json`：

```json
{
  "daily_interval_seconds": 86400,
  "major_interval_seconds": 604800,
  "time_ratio": 1,
  "time_ratio_warning_threshold": 500,
  "daily_event_min_gap_days": 2,
  "major_event_fixed_probability": 0.05,
  "max_events": 100,
  "max_context_bits": 2000,
  "event_policy": {
    "scenario_cooldown_days": 14,
    "major_scenario_cooldown_days": 180,
    "unexpected_event_probability": 0.01,
    "unexpected_event_cooldown_days": 365,
    "llm_recent_event_limit": 20,
    "llm_forbidden_scenario_limit": 12,
    "llm_daily_candidate_limit": 12,
    "disabled_scenarios": [],
    "scenario_weights": {},
    "custom_scenarios": []
  },
  "daily_life_profile": {
    "city_type": "一线城市",
    "commute_mode": "地铁",
    "living_status": "独居",
    "work_style": "混合办公",
    "hobbies": ["做饭", "看展", "跑步"],
    "personality_event_bias": {
      "solitude": 1.5,
      "social": 0.8,
      "health": 1.2
    }
  },
  "season": {
    "hemisphere": "north",
    "birthday_month": 6
  },
  "milestones": [
    {"age": 18, "event": "高考结束", "topic_prompt": "想起当年高考的时候..."},
    {"age": 22, "event": "大学毕业", "topic_prompt": "毕业典礼那天..."}
  ],
  "holidays": [
    {"name": "元旦", "month": 1, "day": 1, "type": "法定假日"},
    {"name": "情人节", "month": 2, "day": 14, "type": "西方节日"},
    {"name": "清明节", "month": 4, "day": 5, "type": "传统节日"},
    {"name": "劳动节", "month": 5, "day": 1, "type": "法定假日"},
    {"name": "端午节", "month": 6, "day": 10, "type": "传统节日"},
    {"name": "中秋节", "month": 9, "day": 17, "type": "传统节日"},
    {"name": "国庆节", "month": 10, "day": 1, "type": "法定假日"},
    {"name": "圣诞节", "month": 12, "day": 25, "type": "西方节日"}
  ],
  "birth_date": null
}
```

`event_policy` 用于控制人生事件去重和 Bot 专属模板：同一 `scenario_key` 会按冷却天数避免反复出现；也可以禁用全局场景、调整场景权重，或添加该 Bot 独有的生活事件模板。日常小事内置 200+ 场景，但每次只会在过滤近期/冷却场景后随机抽取 `llm_daily_candidate_limit` 个候选给 LLM，避免 token 随场景池线性增长。意外类人生大事使用独立的低概率和整体冷却，默认每个 Bot 日检查概率为 `0.01`，冷却 `365` 天。完整字段见：[life.json 字段说明](./BOT_JSON_FIELDS.md#lifejson)。

`daily_life_profile` 会影响日常小事的候选权重，例如通勤方式、居住状态、兴趣和社交风格；性格标签也会参与权重计算。它们只影响“哪些候选更容易被抽到”，不会把完整生活画像或完整场景池都塞进 prompt。

### 4.3 profile.json 新增字段

为了让人生轨迹系统正确工作，需要在 `profile.json` 中配置：

```json
{
  "id": "lin_wanqing",
  "name": "林晚晴",
  "age": 27,
  "birth_date": "1999-03-12",
  "occupation": "古籍修复师"
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `age` | 是 | Bot 初始年龄（系统会基于此计算实际年龄） |
| `birth_date` | 推荐 | Bot 出生日期（YYYY-MM-DD 格式），用于计算生日和当前日期 |

> 如果不配置 `birth_date`，系统会根据 `age` 和当前日期反推一个出生日期（假设生日在配置的 `season.birthday_month` 月）。

### 4.4 配置项说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `daily_interval_seconds` | 86400 | 日常事件基础检查间隔（秒），默认现实 1 天 |
| `major_interval_seconds` | 604800 | 人生大事基础检查间隔（秒），默认现实 7 天 |
| `time_ratio` | 1 | Bot 时间与现实时间的比率 |
| `daily_event_min_gap_days` | 2 | 至少每 N 个 Bot 日尝试产出 1 个日常事件 |
| `major_event_fixed_probability` | 0.05 | 每个 Bot 日固定概率触发生命大事的概率 |
| `max_events` | 100 | 最多保留日常事件数。系统硬上限为 100，即使配置更大也只保留最近 100 条。 |
| `max_context_bits` | 2000 | 事件描述最多占用字符数 |
| `event_policy` | 默认策略 | 场景冷却、禁用、权重、自定义模板和意外事件概率 |
| `daily_life_profile` | {} | Bot 的生活画像，用于影响日常事件候选权重 |
| `season.hemisphere` | "north" | 北半球/南半球（影响季节计算） |
| `season.birthday_month` | 1 | 生日月份（用于初始化） |
| `milestones` | [] | 年龄里程碑列表 |
| `holidays` | 默认8个 | 节假日列表 |
| `birth_date` | null | Bot 出生日期 |

`event_policy` 子字段：

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `scenario_cooldown_days` | 14 | 日常小事同一 `scenario_key` 冷却天数 |
| `major_scenario_cooldown_days` | 180 | 人生大事同一 `scenario_key` 冷却天数 |
| `unexpected_event_probability` | 0.01 | 每个 Bot 日独立检查意外类人生大事的概率 |
| `unexpected_event_cooldown_days` | 365 | 意外类人生大事整体冷却天数 |
| `llm_recent_event_limit` | 20 | 日常事件生成时给 LLM 的近期事件条数上限 |
| `llm_forbidden_scenario_limit` | 12 | 近期禁止复用场景 key 的提示上限 |
| `llm_daily_candidate_limit` | 12 | 每次随机给 LLM 的日常候选场景数，加载时限制在 3-20 |
| `disabled_scenarios` | [] | 禁用全局场景 key |
| `scenario_weights` | {} | 按场景 key 调整权重，例如 `{"commute_delay": 0.5}` |
| `custom_scenarios` | [] | Bot 专属日常模板 |

`daily_life_profile` 是通用生活画像，不绑定某个固定 Bot 模板。常用字段包括 `city_type`、`commute_mode`、`living_status`、`work_style`、`hobbies`、`family_contact_style`、`social_style` 和 `personality_event_bias`。其中 `personality_event_bias` 用场景类别做 key，例如 `social`、`solitude`、`food`、`work`、`home`、`health`、`digital`，值越高越容易被抽到。

### 4.5 季节系统

Bot 知道自己活在哪个季节，这会影响生成的事件：

| 季节 | 月份 | 心情标签 | 适合的事件类型 |
|------|------|----------|----------------|
| 春 | 3, 4, 5 | 温暖、希望、慵懒 | 踏青、赏花、春游 |
| 夏 | 6, 7, 8 | 炎热、烦躁、活力 | 游泳、晒黑、空调病 |
| 秋 | 9, 10, 11 | 凉爽、感慨、收获 | 赏叶、秋游、年终总结 |
| 冬 | 12, 1, 2 | 寒冷、慵懒、期待 | 滑雪、感冒、圣诞 |

**南半球支持**：
```json
"season": {
  "hemisphere": "south"
}
```
南半球季节与北半球相反（6月是冬季，12月是夏季）。

### 4.6 日期时间线

Bot 知道自己活在 Bot 时间线中的哪一天：

| 状态字段 | 说明 |
|----------|------|
| `current_date` | 当前日期（YYYY-MM-DD） |
| `day_of_week` | 周几（周一~周日） |
| `year` | 当前年份 |
| `is_weekend` | 是否周末 |
| `current_month` | 当前月份（1-12） |
| `current_season` | 当前季节（春夏秋冬） |

每次 `tick_daily` 时，`current_date` 会推进：
- 常规运行下，每次至少推进 1 个 Bot 日。
- 如果长时间离线或 `time_ratio` 很高，会按 `现实经过秒数 * time_ratio / 86400` 补推。
- 单次最多补推 365 天，避免一次 tick 把时间线推进过远。

### 4.7 节假日系统

节假日影响事件生成。默认节假日：

| 节日 | 日期 | 类型 |
|------|------|------|
| 元旦 | 1月1日 | 法定假日 |
| 情人节 | 2月14日 | 西方节日 |
| 清明节 | 4月5日 | 传统节日 |
| 劳动节 | 5月1日 | 法定假日 |
| 端午节 | 6月10日 | 传统节日 |
| 中秋节 | 9月17日 | 传统节日 |
| 国庆节 | 10月1日 | 法定假日 |
| 圣诞节 | 12月25日 | 西方节日 |

可以在 `life.json` 中自定义节假日：
```json
"holidays": [
  {"name": "端午节", "month": 6, "day": 10, "type": "传统节日"}
]
```

### 4.8 生日自动触发

当 `current_date` 推进到 Bot 的生日日期时，会自动触发生日事件：
- 检查条件：`current_date.month == birth_date.month AND current_date.day == birth_date.day AND current_date.year > birth_date.year`
- 生成的 `MajorLifeEvent` 描述为"度过了X岁生日"
- 重要性设为 8.0，可分享给用户

### 4.9 年龄里程碑系统

配置里程碑后，Bot 在达到特定年龄时会触发固定事件：

```json
"milestones": [
  {"age": 18, "event": "高考结束", "topic_prompt": "想起当年高考的时候..."},
  {"age": 22, "event": "大学毕业", "topic_prompt": "毕业典礼那天..."},
  {"age": 30, "event": "三十岁", "topic_prompt": "三十岁了，感慨时间..."}
]
```

| 字段 | 说明 |
|------|------|
| `age` | 触发年龄。若配置了 `birth_date` 和 `current_date`，Bot 实际年龄按生日精确计算；否则回退为 `profile.age + bot_age_days // 365`。 |
| `event` | 事件名称 |
| `topic_prompt` | 话题切入语（用于主动消息分享） |

**里程碑触发逻辑**：
1. 每次 `tick_daily` 时计算当前实际年龄
2. 如果 `current_age > last_checked_age`，检查是否有新的里程碑年龄
3. 同一个里程碑只触发一次（记录在 `triggered_milestones` 列表中）
4. 如果 `time_ratio` 很高（跨年龄跳跃），会遍历中间所有待触发里程碑

**人生阶段判断**：

| 年龄范围 | 阶段 |
|----------|------|
| < 15岁 | 少年时期 |
| 15-17岁 | 高中时期 |
| 18-21岁 | 大学时期 |
| 22-29岁 | 职场初期 |
| 30-39岁 | 职场中期 |
| 40-59岁 | 中年时期 |
| >= 60岁 | 退休时期 |

### 4.10 time_ratio 时间加速

`time_ratio` 控制 Bot 内部时间的流逝速度。实际检查间隔按 `daily_interval_seconds / time_ratio` 和 `major_interval_seconds / time_ratio` 缩放，LifeScheduler 会用 `1-300` 秒的自适应轮询观察是否到期。

| time_ratio | 默认日常检查间隔 | 常见效果 | 适用场景 |
|------------|------------------|---------|---------|
| 1 | 86400 秒 | 现实 1 天推进 1 个 Bot 日 | 正常体验（默认） |
| 24 | 3600 秒 | 现实 1 小时推进 1 个 Bot 日 | 轻度加速 |
| 1440 | 60 秒 | 现实 1 分钟推进 1 个 Bot 日 | 观察测试 |
| 3600 | 1 秒 | 极速测试，受 1 秒轮询下限约束 | 快速验证 |
| 10000+ | 1 秒 | 可能一次补推多个 Bot 日 | 压测，不建议长期使用 |

`ai-companion setup` 会用交互表格提示这些常用档位。默认选项是“现实同步 1:1”，也就是 `daily_interval_seconds=86400`、`major_interval_seconds=604800`、`time_ratio=1`。选择加速档时，基础间隔保持现实时间语义，只调整 `time_ratio`。

> **注意**：
> - time_ratio > 500 时会显示警告，建议不超过 1000
> - `daily_interval_seconds / time_ratio` 小于 1 时，实际检查间隔会被压到 1 秒下限
> - 单次 `tick_daily` 至少推进 1 天；长时间离线或极高 `time_ratio` 会按经过时间补推，单次最多 365 天

### 4.11 状态文件

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
      "context_bits": 45,
      "scenario_key": "illustration_deadline",
      "scenario_category": "work",
      "source": "llm"
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
  "life_journal": [
    {
      "id": "uuid",
      "timestamp": "2026-04-27T09:00:00",
      "record_type": "day_passed",
      "date": "2026-04-27",
      "description": "度过了 2026-04-27（周三）",
      "metadata": {"season": "春"}
    }
  ],
  "scenario_history": {
    "illustration_deadline": {"last_date": "2026-04-27", "count": 1}
  },
  "major_scenario_history": {},
  "bot_mood": "愉悦",
  "bot_current_activity": "在家画水彩",
  "bot_age_days": 45,
  "last_daily_tick": "2026-04-25T09:00:00",
  "last_major_tick": "2026-04-24T00:00:00",
  "last_unexpected_event_date": null,
  "current_season": "春",
  "current_month": 4,
  "birthday_month": 6,
  "birth_date": "1998-06-15",
  "current_date": "2026-04-27",
  "day_of_week": "周三",
  "year": 2026,
  "is_weekend": false,
  "last_checked_age": 26,
  "triggered_milestones": [],
  "_initial_age": 26
}
```

### 4.12 LifeEvent 字段说明

| 字段 | 说明 |
|------|------|
| `id` | 事件唯一标识 |
| `timestamp` | 事件写入的现实时间 |
| `description` | 事件描述 |
| `mood_before` | 事件前的情绪 |
| `mood_after` | 事件后的情绪 |
| `importance` | 重要性评分（0-10） |
| `shareable` | 是否可分享给用户 |
| `topic_prompt` | 分享时的话题引子 |
| `mood_tags` | 情绪标签 |
| `related_to_user` | 是否与用户相关 |
| `context_bits` | 描述的字符数 |
| `scenario_key` | 场景 key，用于冷却和去重 |
| `scenario_category` | 场景类别 |
| `source` | 事件来源，如 `llm`、`fallback`、`fixed_probability`、`unexpected_probability`、`birthday`、`milestone` |

### 4.13 事件如何影响 Bot

**日常小事**：
- Bot 可能主动提起最近发生的日常小事
- `life_events` 最多保留最近 100 条，避免长期追加造成 prompt 压力
- 可用于主动消息的话题引子

**人生大事**：
- 重要的人生大事会触发人格更新
- 可能更新 `profile.json` 或 `backstory.json`
- 影响 Bot 的长期性格发展

### 4.14 查看 Bot 状态

Bot 当前的活动和情绪状态：
- `bot_mood`：当前心情（如"愉悦"、"平静"、"有点累"）
- `bot_current_activity`：当前活动（如"在家画水彩"、"在外面散步"）
- `bot_age_days`：Bot 的"年龄"（按 Bot 时间计算）
- `bot_real_age`：实际年龄。优先按 `birth_date` 与 `current_date` 精确计算；缺少日期时才回退为 `profile.age + bot_age_days // 365`
- `life_stage`：当前人生阶段（如"职场中期"）

对话时，人生轨迹状态会注入到 persona system prompt。日常事件、人生大事、主动唤醒判断和主动消息生成也会带入 Bot 当前日期、星期、季节、动态年龄和人生阶段。用户询问年龄、出生日期、当前年份、当前生活状态或最近经历时，Bot 会以 `life_state.json` 的 `current_date`、`birth_date`、`bot_real_age` 和近期事件为准；`profile.json` 里的 `age` 只作为初始年龄。

每次用户发消息时，BotInstance 都会重新读取 persona 和运行配置：
- `profile.json`、`backstory.json`、`values.json`、`speaking_style.json` 会进入最新的对话 prompt。
- `profile.json` 中的 `name`、`occupation`、`personality_tags` 会同步给 LifeEngine 和 ProactiveEngine，后续人生事件和主动消息使用最新设定。
- RefusalEngine 会清空缓存，下一次边界判断重新读取最新 `profile.json` / `values.json`。
- `proactive.json` 和 `life.json` 会重新加载；已运行调度器读取到的间隔、模式和事件策略会跟随文件更新。主动唤醒从 `silent` 切到 `active` 这类启停变化，仍建议重启或重新选择 Bot。

### 4.15 人生轨迹日志

人生轨迹相关日志独立保存在：
```
~/.ai-companion/logs/life.log
```

而 Gateway 其他日志在：
```
~/.ai-companion/logs/gateway.log
```

### 4.16 调整事件生成频率

```json
{
  "daily_interval_seconds": 86400,
  "major_interval_seconds": 604800,
  "time_ratio": 24
}
```

这个例子表示现实约 1 小时推进 1 个 Bot 日，人生大事约每 7 个现实小时检查一次。

---

## 5. 主动唤醒系统

> 详细设计文档：[DESIGN_phase5_proactive.md](./DESIGN_phase5_proactive.md)

### 5.1 概述

Bot 会主动找你聊天、提醒事情、偶尔撒娇。不是简单的定时发送，而是基于：
- LLM 推理判断是否应该主动联系
- 多维情绪模型（生气、想念、不安、兴奋）
- 关系深度（陌生网友 → 恋人）
- 用户习惯学习
- Bot 当前时间线和近期可分享的人生轨迹事件

### 5.2 配置文件

`data/bots/{bot_id}/persona/proactive.json`：

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
      "keywords": ["难过", "伤心", "生气", "委屈", "累"],
      "response_delay_minutes": 30
    }
  },
  "platform": {
    "type": "cli"
  },
  "preferred_contact_times": ["09:00-23:00"],
  "timezone": "Asia/Shanghai",
  "random_trigger_prob": 0.05,
  "random_trigger_min_ratio": 0.5
}
```

### 5.3 配置项说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enabled` | true | 是否启用主动唤醒 |
| `mode` | "active" | `active`=会主动发消息；`silent`=保留配置但不主动发 |
| `scheduler.check_interval_seconds` | 600 | 后台检查间隔（秒） |
| `scheduler.idle_threshold_hours` | 24 | 多久没联系触发提醒（小时） |
| `scheduler.min_interval_hours` | 4 | 两条消息最小间隔（小时） |
| `scheduler.max_daily` | 5 | 每天最多主动消息数 |
| `scheduler.max_idle_days` | 7 | 长期不回复超过该天数后降低主动 |
| `triggers.idle_reminder.enabled` | true | 是否启用空闲提醒 |
| `triggers.emotion_trigger.enabled` | true | 是否启用情绪关键词触发 |
| `triggers.emotion_trigger.keywords` | [] | 情绪关键词列表 |
| `triggers.emotion_trigger.response_delay_minutes` | 5 | 情绪触发延迟响应时间（分钟） |
| `platform.type` | "cli" | 发送平台：`cli`/`feishu`/`weixin`/`webhook` |
| `random_trigger_prob` | 0.05 | 达到空闲阈值一定比例后，随机提前触发的概率 |
| `random_trigger_min_ratio` | 0.5 | 空闲时间达到阈值的多少比例后才允许随机提前 |

旧版扁平字段仍有兼容逻辑，但新配置建议使用上面的嵌套结构。完整字段见：[proactive.json 字段说明](./BOT_JSON_FIELDS.md#proactivejson)。

主动唤醒的 LLM 判断 prompt 和消息生成 prompt 会包含 `LifeEngine.get_status()` 提供的 Bot 时间线：当前日期、星期、季节、出生日期、动态年龄、人生阶段和当前状态。如果有可分享的日常事件，生成消息时也会带上事件描述和 `topic_prompt`。如果平台发送器未配置，主动消息不会被计入已发送次数。

### 5.3.1 对话连续性主动唤醒

在 WebUI 的「配置中心 -> 主动唤醒 -> 对话连续性」里，可以把主动消息从“定时问候”改成“先记动机、再到期发送”的模式：

- `延迟回复履约`：Bot 说“一会儿回复你”“我想一下晚点告诉你”后，会先写入待办任务，到期回到同一会话继续。
- `接上文续聊`：用户沉默后优先延续最近未收尾的话题，而不是重新开场。
- `情绪跟进`：用户提到难过、累、烦等状态后，稍后再自然关心。
- `生活事件分享`：Bot 有具体生活事件时可以主动分享。
- `普通陪伴问候`：最低优先级；关闭后，只有更具体的动机才会主动发送。

触发过程分两段：
1. Bot 每次回复后，系统会立即记录可能的后续动机。
2. 动机到期后，由后台调度器在下一次检查时发送。

因此“默认 8 分钟 / 45 分钟”并不等于固定发送时间，真正发送还会受 `check_interval_seconds` 和当前限流状态影响。

如果你想让 Bot 更像真人，建议优先开启 `延迟回复履约` 和 `接上文续聊`，把 `普通陪伴问候` 留作兜底。

### 5.4 关系深度行为

| 关系等级 | 条件 | 行为特征 |
|----------|------|---------|
| 陌生网友 | 1-3 | 很矜持，idle_threshold×2，max_daily÷3 |
| 普通朋友 | 4-5 | 标准参数 |
| 好朋友 | 6-7 | idle_threshold×0.7，max_daily×1.5 |
| 恋人 | 8-10 | idle_threshold×0.5，max_daily×2，可以撒娇 |

> 关系等级由系统根据对话内容推断，存储在 `data/bots/{bot_id}/memory/relationship.db`

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
ai-companion status
```

状态文件：`data/bots/{bot_id}/proactive_state.json`

---

## 6. 记忆系统

记忆系统的目标不是让 Bot “记住更多”，而是让它更会判断：什么该长期记住，什么只是当前上下文，什么需要用户手动确认，什么应该随时间淡化。

当前架构由五类记忆和一条写入/召回流水线组成：

```text
用户消息 + Bot 回复
  → working.db 保存原始对话
  → MemoryExtractor 抽取候选记忆
  → MemoryGovernor 判断写入、跳过、归档或刷新投影
  → User Model / Relationship / Episodic 分层保存
  → MemoryRetriever 按当前意图召回
  → MemoryPromptBuilder 生成 system_suffix
```

### 6.1 记忆分层

| 记忆层 | 内容 | 存储位置 | 生命周期 |
|--------|------|----------|----------|
| Working / Raw Log | 当前会话原文、压缩摘要、debug 底账 | `working.db` | 新会话隔离，长会话压缩 |
| User Model | 用户事实、偏好、边界、当前状态、目标 | `semantic.db` | 带分类、置信度、来源、证据、过期时间 |
| Relationship State | 关系标签、好感度、亲密度、信任、紧张度、关键关系时刻 | `relationship.db` | 与普通用户事实分离，影响语气和主动唤醒 |
| Episodic Memory | 重要共同经历、冲突/和解、承诺、重要事件 | `episodic.db` + 可选 Chroma | 低价值或长期不用会归档 |
| User Understanding | 用户可编辑的“Bot 对我的理解” | `user_understanding.json` | `manual` 永久优先，`auto` 自动刷新 |

### 6.2 写入流程

每轮对话都会写入 Working / Raw Log，但不会每轮都写长期记忆。

长期写入由 `MemoryExtractor` 和 `MemoryGovernor` 决定：

| 候选类型 | 写入位置 | 写入条件 |
|----------|----------|----------|
| `user_fact` | `semantic.db` | 明确事实、偏好、边界、长期状态，达到最低置信度 |
| `episode` | `episodic.db` | 重要事件、关系转折、承诺、冲突/和解、共同经历 |
| `relationship_event` | `relationship.db` | 关系标签、好感/紧张/信任变化、关键关系时刻 |
| `temporary_context` | `semantic.db` 的 `open_threads` / `life_context` | 临时计划、近期压力源，带 TTL |

普通寒暄、一次性闲聊和低置信度推断不会进入长期记忆。

### 6.3 User Model 结构化事实

`semantic.db` 中的 `user_facts` 不再只是扁平 `key/value`，而是带元数据的用户模型：

| 字段 | 说明 |
|------|------|
| `category` | `identity`、`preferences`、`boundaries`、`communication_style`、`life_context`、`goals` 等 |
| `confidence` | 事实可信度，低置信度不进入用户理解投影 |
| `source` | `user_explicit`、`auto`、`rule`、`legacy` 等 |
| `evidence_json` | 来源证据，如 session 或消息线索 |
| `expires_at` | 临时事实过期时间 |
| `manual_override` | 用户手动设定是否优先 |
| `archived` | 是否归档，不再主动召回 |

冲突策略：

1. 用户手动理解优先。
2. 用户明确新说法优先于模型推断。
3. 低置信度事实可以保留为候选或证据，但不进入 prompt。
4. `boundaries` 和 `communication_style` 优先级最高，会更快影响回复体感。

### 6.4 Relationship State

关系状态独立保存在：

```text
data/bots/{bot_id}/memory/relationship.db
```

它不再混在普通用户事实里，避免 `/forget <key>` 删除用户事实时误删关系状态。

关系状态包含：

- `relationship_label`：朋友、好朋友、暧昧中、恋人、紧张等。
- `attitude_score`：整体好感度。
- `intimacy_score`：亲密度。
- `trust_score`：信任度。
- `tension_score`：紧张度。
- `open_emotional_threads`：未完成情绪话题。
- `key_moments`：关键关系时刻。

消费方：

- 拒绝引擎用它判断语气和边界表达。
- 主动唤醒用它判断是否该主动、主动频率和分寸。
- `runtime_profile.json` 会继续作为 persona overlay，但由 relationship store 同步。

### 6.5 情景记忆

`episodic.db` 只保存真正值得长期记住的共同经历：

- 用户的重要事件，如搬家、考试、面试、失眠、求职。
- 两人之间的冲突、和解、承诺、第一次共同经历。
- 对关系有长期影响的时刻。
- Bot 分享过的重要 life event，并得到用户回应。

不会写入：

- 普通寒暄。
- 一次性闲聊。
- 没有后续意义的事实复述。

召回时会综合相关性、重要性、置信度、时间和衰减分数。长期不用或低价值的 episode 会被归档，不再主动进入 prompt。

### 6.6 用户理解文件

每个 Bot 都会自动创建：

```text
data/bots/{bot_id}/memory/user_understanding.json
```

这是用户可直接编辑的“Bot 对我的理解”，用于初始化和纠正 Bot。

内置 Bot 已经自带一份初始 `manual`，包括默认沟通方式、边界、关系期待和互动风格。这样新用户开箱时，Bot 不会从完全空白的“通用助手”状态开始；随着日常对话推进，系统会持续刷新 `auto` 和 `relationship_memory`。

格式为 v3：

```json
{
  "version": 3,
  "manual": {
    "summary": "用户希望被温柔但不敷衍地对待。",
    "facts": {
      "称呼": "阿迟"
    },
    "preferences": [
      "情绪低落时先陪一会儿，不要立刻讲道理"
    ],
    "communication_style": [
      "先共情，再给建议"
    ],
    "boundaries": [
      "不要调侃体重"
    ],
    "relationship_expectations": [
      "希望 Bot 像熟悉的人一样有分寸地陪伴"
    ],
    "important_people": [],
    "current_context": [],
    "open_threads": [],
    "notes": []
  },
  "auto": {
    "profile_summary": "用户近期压力偏高，情绪低落时更需要先被接住。",
    "facts": {
      "城市": "上海"
    },
    "emotional_patterns": [
      "压力大时容易焦虑，但愿意继续推进事情"
    ],
    "stressors": [
      "最近在准备作品集"
    ],
    "comfort_strategies": [
      "先陪一会儿，再给具体建议"
    ],
    "attachment_and_distance": [],
    "values_and_principles": [],
    "goals_and_projects": [],
    "current_context": [
      "最近在准备作品集"
    ],
    "open_threads": [
      "用户想继续聊作品集"
    ],
    "last_refresh_at": "2026-04-29T23:30:00"
  },
  "relationship_memory": {
    "how_user_treats_bot": [],
    "what_user_seems_to_need_from_bot": [
      "稳定陪伴，而不是机械建议"
    ],
    "things_that_brought_them_closer": [
      "用户开始主动分享脆弱时刻"
    ],
    "things_that_created_tension": [],
    "repair_preferences": []
  },
  "meta": {
    "confidence_notes": [],
    "contradictions": [],
    "last_reflection_at": "2026-04-29T23:30:00"
  }
}
```

规则：

- `manual` 由用户编辑，自动系统永远不覆盖。
- `auto` 由日常对话中的高置信度事实、关系状态和 Bot 的阶段性理解刷新。
- `relationship_memory` 记录相处过程中形成的关系理解，例如用户如何对待 Bot、需要 Bot 扮演什么位置、哪些互动让关系更近或更紧张。
- `meta` 记录低置信度说明和与手动理解冲突的自动候选。
- 如果 `manual.facts` 已经有同名 key，`auto.facts` 不会覆盖。
- 文件损坏时会备份为 `.broken`，并重新生成默认结构。
- 为兼容旧版本，旧的 `summary`、`facts`、`auto_facts` 仍会被读取并迁移。

### 6.7 动态召回

系统会先判断当前意图，再制定召回计划：

| 当前意图 | 优先召回 |
|----------|----------|
| `emotional_support` | 沟通偏好、边界、近期压力源、关系状态 |
| `recall_past` | 情景记忆优先，必要时跨 session |
| `planning` | open_threads、目标、最近上下文 |
| `relationship_repair` | 关系状态、冲突/和解 episode、边界 |
| `task_request` | 少量必要偏好，避免无关情感记忆干扰任务 |
| `casual_chat` | 少量 profile + 最近上下文 |
| `proactive_generation` | open_threads、关系状态、近期用户状态、Bot 人生轨迹 |

Prompt 构建优先级：

```text
安全/边界 > 当前会话 > manual 用户理解 > 当前意图相关事实 > relationship > 高相关 episode > 低相关事实
```

Bot 不会机械地说“我从记忆里看到”，而是把记忆当作相处背景自然使用。

### 6.8 记忆相关命令

在对话界面使用：

- `/memory` - 查看工作记忆、情景记忆、语义事实数、关系状态、用户理解文件路径。
- `/forget <key>` - 删除某条自动用户事实，并同步移除 `user_understanding.auto` 中的投影；不会删除 `manual` 或 relationship state。
- `/new` - 开始新会话，保留长期记忆。

### 6.9 重置记忆

```bash
# 删除特定 Bot 的自动记忆数据库
rm -f data/bots/{bot_id}/memory/*.db

# 删除所有 Bot 的自动记忆数据库
rm -f data/bots/*/memory/*.db
```

`user_understanding.json` 里的 `manual` 是用户手动设定，建议保留。只有当你想完全重置 Bot 对用户的初始化理解时，才删除这个文件。

### 6.10 models.yaml 完整配置（记忆与多媒体）

```yaml
# 默认使用 minimax
default_model: minimax

models:
  minimax:
    api_key: "${MINIMAX_API_KEY}"
    base_url: "https://api.minimax.chat/v1"
    model: "MiniMax-Text-01"
    max_context_tokens: 20000  # 上下文上限（token），超限触发压缩
  mimo:
    api_key: "${MIMO_API_KEY}"
    base_url: "https://token-plan-cn.xiaomimimo.com/v1"
    model: "mimo-v2.5-pro"
    max_context_tokens: 1048576  # 1M 上下文上限（token）

# 记忆配置
memory:
  embedding: "local"          # 向量嵌入模式: local/none（sentence-transformers 已默认安装）
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
    enabled: true
    auto: true
    base_url: "https://api.openai.com/v1"
    model: "gpt-image-1"
    api_key: "${OPENAI_API_KEY}"
    output_dir: "data/bots/_images"

  # 图片理解
  image_understanding:
    enabled: true
    auto: true
    base_url: "https://api.openai.com/v1"
    model: "gpt-4o"
    api_key: "${OPENAI_API_KEY}"
    max_image_size_mb: 8
    max_images_per_message: 3

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

### 6.11 记忆引擎配置详解

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `embedding` | "local" | 向量嵌入模式，`local` 启用 sentence-transformers，`none` 关闭向量召回 |
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
  bot_id: lin_wanqing
```

飞书通道只支持 `dedicated`。一个飞书 App 只能绑定一个 Bot，一个 Bot 也只能绑定一个飞书 App；不要使用 `chat_routed` 或 `group_bot_map` 把同一个飞书应用路由到多个 Bot。

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
      home_channel_name: "林晚晴的书房"
    routing:
      mode: "dedicated"
      bot_id: "lin_wanqing"
```

### 7.6 Bot 绑定与固定会话配置

飞书网关强制 **飞书 App 与 Bot 双向一对一绑定**。不要使用 `routing.mode: chat_routed` 或 `group_bot_map` 把同一个飞书应用路由到多个 Bot，也不要让同一个 Bot 绑定多个飞书 App；如果需要多个 Bot 接入飞书，请为每个 Bot 创建独立的飞书应用，并在 `bot_bindings` 里配置各自的 `app_id/app_secret`。

单 Bot 使用全局飞书应用时，可以这样配置固定会话：

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
    bot_bindings:
      lin_wanqing:
        home_channel:
          chat_id: "oc_lin_wanqing_chat_id"
          name: "林晚晴"
```

多 Bot 使用飞书时，每个 Bot 必须覆盖成不同的飞书应用：

```yaml
platforms:
  feishu:
    enabled: true
    bot_bindings:
      lin_wanqing:
        extra:
          app_id: "cli_xxx"
          app_secret: "${LIN_WANQING_FEISHU_APP_SECRET}"
          connection_mode: "websocket"
          domain: "feishu"
        home_channel:
          chat_id: "oc_xxx"
          name: "林晚晴"
      ethan_reed:
        extra:
          app_id: "cli_yyy"
          app_secret: "${ETHAN_REED_FEISHU_APP_SECRET}"
          connection_mode: "websocket"
          domain: "feishu"
        home_channel:
          chat_id: "oc_yyy"
          name: "Ethan Reed"
```

`home_channel.chat_id` 通常是 `oc_xxx` 这类飞书会话 ID。没有配置固定目标时，网关仍会在收到某个会话的入站消息后，把该会话作为当前运行时的主动消息目标；但重启后不会保留，建议正式使用时写入 `bot_bindings`。

### 7.7 飞书环境变量汇总

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

## 8. 微信个人号通道

微信通道基于个人微信 iLink Bot API，与飞书共用同一套 Gateway、BotInstance、记忆、命令和主动唤醒逻辑。推荐通过 `ai-companion weixin` 单独扫码登录；也可以在完整 `ai-companion setup` 里配置，或直接在 `config.yaml` / 环境变量里填写 `token/account_id`。

### 8.1 最小配置

```yaml
platforms:
  weixin:
    enabled: true
    token: "${WEIXIN_TOKEN}"
    extra:
      account_id: "${WEIXIN_ACCOUNT_ID}"
      dm_policy: "allowlist"
      allow_from:
        - "wxid_xxx"
      group_policy: "disabled"
    routing:
      mode: "dedicated"
      bot_id: "lin_wanqing"
    home_channel:
      platform: "weixin"
      chat_id: "wxid_xxx"
      name: "微信私聊"
```

### 8.2 策略与限制

| 字段 | 推荐值 | 说明 |
|------|--------|------|
| `extra.dm_policy` | `allowlist` | 私聊策略：`allowlist`/`open`/`disabled` |
| `extra.allow_from` | `[]` | 允许私聊的微信用户 ID |
| `extra.group_policy` | `disabled` | 群聊策略：`disabled`/`allowlist`/`open` |
| `extra.group_allow_from` | `[]` | 允许群聊 ID |
| `home_channel.chat_id` | - | 主动唤醒固定发送目标；留空时会使用最近入站会话 |

微信不支持编辑式流式输出，Gateway 会只发送最终回复。运行态可以通过 `ai-companion gateway status` 或管理后台设置页查看，状态中只展示账号摘要和最近错误，不展开 token、account_id 或 `context_token`。

运行时文件会写入 `~/.ai-companion/weixin/accounts/`：账号凭据、每个 peer 的 `context_token` 缓存，以及 `getupdates` 同步游标。该目录包含可用凭据，建议按私密数据处理，不提交到 git。

---

## 9. 技能扩展

### 9.1 查看运行时能力

```bash
ai-companion skill list --runtime
ai-companion skill list --runtime --json
```

`/skills` 在对话中显示同一份运行时能力状态，包含 `enabled`、`auto`、`available` 和 `reason`。

当网关收到图片消息且 `image_understanding` 处于可用状态时，会自动先做图片理解，再把结构化结果注入本轮对话上下文。若该能力未启用，会在回复里明确提示“当前未启用图片理解能力。”；若下载或缓存图片失败，会自动降级为普通文本对话，不中断回复。

自动路由支持 `skills.<name>.auto=false`。关闭后，不会再因自然语言或媒体输入自动触发该能力，但 `/skill <name> ...` 显式调用仍然可用。

### 9.2 查看已安装技能

```bash
ai-companion skill list
ai-companion skill list --json
```

### 9.3 安装技能

```bash
# 从本地安装
ai-companion skill install ./my-skill

# 从 URL 安装
ai-companion skill install https://example.com/skill.zip

# 覆盖同名技能
ai-companion skill install ./my-skill --force
```

### 9.4 卸载技能

```bash
ai-companion skill uninstall my-skill
```

### 9.5 执行技能

命令行直接执行：

```bash
ai-companion skill run my-skill '{"text":"你好"}'
ai-companion skill run my-skill text=你好
```

对话中显式执行：

```text
/skills
/skill my-skill {"text":"你好"}
/skill my-skill 你好
帮我安装 skill ./my-skill
查看技能列表
```

### 9.6 技能包结构

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

默认技能目录位于 `~/.ai-companion/data/bots/_skills/`。旧版项目目录 `data/bots/_skills/` 中的技能会在默认运行时迁移到用户目录；设置 `AI_COMPANION_HOME` 时只使用该 home 下的数据，便于测试和多实例隔离。

---

## 10. Gateway 配置

### 10.1 网关命令

```bash
ai-companion gateway start    # 后台启动（默认，关闭终端后继续运行）
ai-companion gateway start --sync  # 前台启动（显示日志）
ai-companion gateway stop     # 停止
ai-companion gateway logs     # 查看日志
```

### 10.2 Session 重置策略

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

### 10.3 会话存储配置

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

### 10.4 平台显示配置

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

## 11. 管理后台

### 11.1 概述

启动 Gateway 后会自动打开管理后台（`http://localhost:1421`），支持可视化管理所有 Bot 的会话、记忆、配置和日志。

**功能入口：**

| 页面 | 功能 |
|------|------|
| Dashboard | Bot 监控指标（今日会话数、活跃用户、输入/输出字符数） |
| 会话 | 查看所有会话列表，点击进入详细对话 |
| 记忆 | 查看工作记忆、情景记忆、用户事实、关系状态和用户理解文件 |
| 日志 | 实时日志流（WebSocket 推送） |
| 设置 | 模型参数热更新、主动唤醒配置热更新 |

**管理后台与 CLI 的数据共享：**

管理后台和 CLI 共用同一份 SQLite 数据（`~/.ai-companion/data/bots/{bot_id}/memory/`）。无论你用 CLI 聊天还是通过网关聊天，管理后台都能看到所有会话。

### 11.2 启动和停止

```bash
# 启动网关（自动打开管理后台）
ai-companion gateway start

# 前台运行（不打开浏览器）
ai-companion gateway start --sync

# 查看日志
ai-companion gateway logs

# 停止（同时关闭管理后台）
ai-companion gateway stop
```

> 管理后台和 Gateway 共用同一进程。停止 Gateway 时会通过进程组 kill 同时关闭管理后台 UI。

### 11.3 热更新机制

在「设置」页面修改配置后，系统会：

| 配置类型 | 热更新方式 |
|----------|-----------|
| 模型参数（temperature、max_tokens） | 保存到 `models.yaml`，Gateway 自动重新加载 |
| 主动唤醒参数（idle_threshold、max_daily） | 保存到 `proactive.json`，ProactiveScheduler 自动重启 |

无需重启 Gateway，刷新页面即可看到新配置生效。

### 11.4 监控指标说明

Dashboard 显示的指标直接从 SQLite 读取，统计维度如下：

| 指标 | 说明 |
|------|------|
| 今日会话 | 当天有消息的独立 session 数 |
| 活跃用户 | 有消息的用户数 |
| 输入字符 | 用户输入的字符总数（≈ token 数÷2） |
| 输出字符 | Bot 回复的字符总数 |

> 字符数统计的是原始字符数，一个中文字符算 1，一个英文单词算约 5-6 个字符。由于模型 token 计数方式不同，实际 token 数约为字符数的 1.5-2 倍。

### 11.5 日志页面

日志页面通过 WebSocket 实时推送 Gateway 日志：

- 日志级别：DEBUG / INFO / WARNING / ERROR
- 格式：`时间戳 [级别] [模块名] 消息内容`
- 支持自动滚动和暂停

---

## 12. 数据目录

### 12.1 目录结构

```
~/.ai-companion/
├── config/
│   ├── models.yaml
│   ├── bots.yaml
│   └── config.yaml
├── data/
│   └── bots/
│       ├── lin_wanqing/
│       │   ├── persona/           # 人格配置
│       │   │   ├── profile.json
│       │   │   ├── backstory.json
│       │   │   ├── proactive.json
│       │   │   └── life.json
│       │   ├── memory/            # 记忆存储
│       │   │   ├── episodic.db
│       │   │   ├── relationship.db
│       │   │   ├── semantic.db
│       │   │   ├── user_understanding.json
│       │   │   └── working.db
│       │   ├── proactive_state.json
│       │   └── life_state.json
│       └── ethan_reed/
│           └── ...
├── logs/
│   └── ai_companion.log
└── gateway.pid
```

### 12.2 迁移数据目录

```yaml
# config.yaml
data_dir: "/path/to/custom/data"
```

---

## 13. 常见问题

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
- 启动时指定：`ai-companion start --bot bot_id`

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

### Q: 为什么我说“帮我画一张…”没有自动出图？

**A**: 先检查运行时能力开关和可用性：
1. 在对话里输入 `/skills`，确认 `image_generation` 的 `enabled=true`、`auto=true`。
2. 若 `reason` 显示缺 key（例如 `missing_api_key:api_key`），先补齐 `api_key`。
3. 如果你故意设置了 `auto=false`，自然语言不会自动触发，改用 `/skill image_generation ...`。

### Q: 发图片后为什么没有自动理解？

**A**: 常见原因：
1. `image_understanding` 未启用或 `auto=false`。
2. 能力不可用（例如缺少 `api_key`，或 `base_url` / `model` 填错）。
3. 图片下载/缓存失败。此时系统会自动降级为普通文本对话，不会中断回复。

---

## 相关文档

- [Bot 设计指引](./BOT_DESIGN_GUIDE.md)
- [Bot JSON 字段说明](./BOT_JSON_FIELDS.md)
- [主动唤醒系统设计](./DESIGN_phase5_proactive.md)
