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
10. [管理后台](#10-管理后台)
11. [数据目录](#11-数据目录)
12. [常见问题](#12-常见问题)

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
ai-companion setup
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
├── proactive.json        # 主动唤醒配置
└── life.json             # 人生轨迹配置
```

完整字段字典见：[Bot JSON 字段说明](./BOT_JSON_FIELDS.md)。

> 注意：运行时读取的 `.json` 文件必须保持标准 JSON，不能写 `//` 或 `/* */` 注释。需要字段解释时看 `docs/BOT_JSON_FIELDS.md`，不要把注释直接写进 JSON 文件。

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
| 实际年龄计算 | 基于 profile.json 的初始年龄 + bot_age_days 计算 |

### 4.2 配置文件

`data/bots/{bot_id}/persona/life.json`：

```json
{
  "daily_interval_seconds": 3600,
  "major_interval_seconds": 21600,
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
    "disabled_scenarios": [],
    "scenario_weights": {},
    "custom_scenarios": []
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

`event_policy` 用于控制人生事件去重和 Bot 专属模板：同一 `scenario_key` 会按冷却天数避免反复出现；也可以禁用全局场景、调整场景权重，或添加该 Bot 独有的生活事件模板。意外类人生大事使用独立的低概率和整体冷却，默认每个 Bot 日检查概率为 `0.01`，冷却 `365` 天。完整字段见：[life.json 字段说明](./BOT_JSON_FIELDS.md#lifejson)。

### 4.3 profile.json 新增字段

为了让人生轨迹系统正确工作，需要在 `profile.json` 中配置：

```json
{
  "id": "suqing",
  "name": "苏晴",
  "age": 26,
  "birth_date": "1998-06-15",
  "occupation": "自由插画师"
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
| `daily_interval_seconds` | 3600 | 日常事件检查间隔（秒），按 time_ratio 缩放 |
| `major_interval_seconds` | 21600 | 人生大事检查间隔（秒），按 time_ratio 缩放 |
| `time_ratio` | 1 | Bot 时间与现实时间的比率 |
| `daily_event_min_gap_days` | 2 | 至少每 N 个 Bot 日尝试产出 1 个日常事件 |
| `major_event_fixed_probability` | 0.05 | 每个 Bot 日固定概率触发生命大事的概率 |
| `max_events` | 100 | 最多保留日常事件数。系统硬上限为 100，即使配置更大也只保留最近 100 条。 |
| `max_context_bits` | 2000 | 事件描述最多占用字符数 |
| `event_policy` | 默认策略 | 场景冷却、禁用、权重、自定义模板和意外事件概率 |
| `season.hemisphere` | "north" | 北半球/南半球（影响季节计算） |
| `season.birthday_month` | 1 | 生日月份（用于初始化） |
| `milestones` | [] | 年龄里程碑列表 |
| `holidays` | 默认8个 | 节假日列表 |
| `birth_date` | null | Bot 出生日期 |

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

Bot 知道自己活在现实中的哪一天：

| 状态字段 | 说明 |
|----------|------|
| `current_date` | 当前日期（YYYY-MM-DD） |
| `day_of_week` | 周几（周一~周日） |
| `year` | 当前年份 |
| `is_weekend` | 是否周末 |
| `current_month` | 当前月份（1-12） |
| `current_season` | 当前季节（春夏秋冬） |

每天 `tick_daily` 时，`current_date` 会推进：
- `time_ratio >= 1440` 时，每天推进 1 天
- `time_ratio < 1440` 时，每次推进 1 天（不受加速影响）

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

time_ratio 控制 Bot 内部时间的流逝速度。实际触发间隔受 LifeScheduler 轮询周期（10秒）限制：

| time_ratio | 实际触发间隔 | Bot 每天老化 | 适用场景 |
|------------|------------|-------------|---------|
| 1 | 1 小时 | 1 天 | 正常体验（默认） |
| 60 | 1 分钟 | 60 天 | 加速体验 |
| 360 | 10 秒 | 360 天 | 快速验证（最大有效值） |
| 500+ | 10 秒 | 500+ 天 | 测试用，显示警告 |

> **注意**：
> - time_ratio > 500 时会显示警告，建议不超过 1000
> - time_ratio 最大有效值为 **360**（因为 LifeScheduler 每 10 秒检查一次）
> - 超过 360 的值效果不会再加快，只是 Bot 年龄增长更快

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
  "bot_mood": "愉悦",
  "bot_current_activity": "在家画水彩",
  "bot_age_days": 45,
  "last_daily_tick": "2026-04-25T09:00:00",
  "last_major_tick": "2026-04-24T00:00:00",
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
| `scenario_key` | 场景 key，用于冷却和去重 |
| `scenario_category` | 场景类别 |
| `source` | 事件来源，如 `llm`、`fallback`、`fixed_probability` |

### 4.13 事件如何影响 Bot

**日常小事**：
- Bot 可能主动提起最近发生的日常小事
- 低重要性事件会被定期清理（遗忘）
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

对话时，人生轨迹状态会注入到 persona system prompt。用户询问年龄、出生日期、当前年份、当前生活状态或最近经历时，Bot 会以 `life_state.json` 的 `current_date`、`birth_date`、`bot_real_age` 和近期事件为准；`profile.json` 里的 `age` 只作为初始年龄。

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
  "daily_interval_seconds": 1800,
  "major_interval_seconds": 10800,
  "time_ratio": 24
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
  "timezone": "Asia/Shanghai"
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
| `platform.type` | "cli" | 发送平台：`cli`/`feishu`/`webhook` |

旧版扁平字段仍有兼容逻辑，但新配置建议使用上面的嵌套结构。完整字段见：[proactive.json 字段说明](./BOT_JSON_FIELDS.md#proactivejson)。

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
ai-companion status
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
ai-companion skill list
```

### 8.2 安装技能

```bash
# 从本地安装
ai-companion skill install ./my-skill

# 从 URL 安装
ai-companion skill install https://example.com/skill.zip
```

### 8.3 卸载技能

```bash
ai-companion skill uninstall my-skill
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

### 9.1 网关命令

```bash
ai-companion gateway start    # 后台启动（默认，关闭终端后继续运行）
ai-companion gateway start --sync  # 前台启动（显示日志）
ai-companion gateway stop     # 停止
ai-companion gateway logs     # 查看日志
```

### 9.2 Session 重置策略

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

### 9.2 会话存储配置

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

### 9.3 平台显示配置

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

## 10. 管理后台

### 10.1 概述

启动 Gateway 后会自动打开管理后台（`http://localhost:1421`），支持可视化管理所有 Bot 的会话、记忆、配置和日志。

**功能入口：**

| 页面 | 功能 |
|------|------|
| Dashboard | Bot 监控指标（今日会话数、活跃用户、输入/输出字符数） |
| 会话 | 查看所有会话列表，点击进入详细对话 |
| 记忆 | 查看工作记忆、情景记忆、语义记忆内容 |
| 日志 | 实时日志流（WebSocket 推送） |
| 设置 | 模型参数热更新、主动唤醒配置热更新 |

**管理后台与 CLI 的数据共享：**

管理后台和 CLI 共用同一份 SQLite 数据（`~/.ai-companion/data/bots/{bot_id}/memory/`）。无论你用 CLI 聊天还是通过网关聊天，管理后台都能看到所有会话。

### 10.2 启动和停止

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

### 10.3 热更新机制

在「设置」页面修改配置后，系统会：

| 配置类型 | 热更新方式 |
|----------|-----------|
| 模型参数（temperature、max_tokens） | 保存到 `models.yaml`，Gateway 自动重新加载 |
| 主动唤醒参数（idle_threshold、max_daily） | 保存到 `proactive.json`，ProactiveScheduler 自动重启 |

无需重启 Gateway，刷新页面即可看到新配置生效。

### 10.4 监控指标说明

Dashboard 显示的指标直接从 SQLite 读取，统计维度如下：

| 指标 | 说明 |
|------|------|
| 今日会话 | 当天有消息的独立 session 数 |
| 活跃用户 | 有消息的用户数 |
| 输入字符 | 用户输入的字符总数（≈ token 数÷2） |
| 输出字符 | Bot 回复的字符总数 |

> 字符数统计的是原始字符数，一个中文字符算 1，一个英文单词算约 5-6 个字符。由于模型 token 计数方式不同，实际 token 数约为字符数的 1.5-2 倍。

### 10.5 日志页面

日志页面通过 WebSocket 实时推送 Gateway 日志：

- 日志级别：DEBUG / INFO / WARNING / ERROR
- 格式：`时间戳 [级别] [模块名] 消息内容`
- 支持自动滚动和暂停

---

## 11. 数据目录

### 11.1 目录结构

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

### 11.2 迁移数据目录

```yaml
# config.yaml
data_dir: "/path/to/custom/data"
```

---

## 12. 常见问题

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

---

## 相关文档

- [主动唤醒系统设计](./DESIGN_phase5_proactive.md)
- [主动唤醒系统实现](./IMPLEMENTATION_phase5_proactive.md)
- [Phase 1-3 测试报告](./TEST_REPORT_phase1_3.md)
