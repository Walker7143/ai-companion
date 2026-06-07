# AI Companion 完整使用指南

> 文档目的：按照当前代码说明安装、配置、运行方式与主要功能
> 最后更新：2026-06-07

---

## 目录

1. [快速开始](#1-快速开始)
2. [命令总览](#2-命令总览)
3. [配置文件](#3-配置文件)
4. [模型与能力](#4-模型与能力)
5. [人格与人生轨迹](#5-人格与人生轨迹)
6. [记忆系统](#6-记忆系统)
7. [人格演化](#7-人格演化)
8. [平台与网关](#8-平台与网关)
9. [管理后台](#9-管理后台)
10. [数据目录](#10-数据目录)
11. [常见问题](#11-常见问题)

---

## 1. 快速开始

### 1.1 环境要求

- Python 3.11+
- Git
- 推荐安装 Node.js + npm，用于管理后台 UI
- 至少一个可用模型配置

当前内置支持的模型 provider：

- `minimax`
- `openai`
- `claude`
- `mimo`
- `deepseek`
- `tele`
- `ollama`
- `custom`

### 1.2 安装

```bash
pip install -r requirements.txt
pip install -e .
```

### 1.3 首次配置

```bash
ai-companion setup
```

`setup` 会引导你：

1. 配置默认模型
2. 创建或更新 Bot
3. 可选配置飞书与微信通道

重复运行 `setup` 时，未重新配置的部分会尽量保留原值，不会粗暴覆盖已有 Bot 数据。

### 1.4 启动

本地 CLI：

```bash
ai-companion start
ai-companion start --bot <bot_id>
```

启动网关：

```bash
ai-companion gateway start
ai-companion gateway start --sync
```

默认情况下，CLI 或 Gateway 启动时会尽量同时拉起：

- Admin API：`http://127.0.0.1:8642`
- Web UI：`http://127.0.0.1:14210`

如果不希望自动启动 UI：

```bash
START_UI=false
# 或
AI_COMPANION_START_UI=false
```

### 1.5 更新

```bash
ai-companion update
ai-companion update --cn
ai-companion update --skip-ui
ai-companion update --no-restart-gateway
```

---

## 2. 命令总览

### 2.1 CLI 主命令

```bash
ai-companion start
ai-companion start --bot <bot_id>

ai-companion setup
ai-companion weixin
ai-companion weixin setup
ai-companion weixin setup --no-env

ai-companion status
ai-companion update
ai-companion update --cn
ai-companion update --skip-ui
```

### 2.2 Gateway 管理

```bash
ai-companion gateway
ai-companion gateway start
ai-companion gateway start --sync
ai-companion gateway stop
ai-companion gateway restart
ai-companion gateway restart --sync
ai-companion gateway replace
ai-companion gateway replace --sync
ai-companion gateway status
ai-companion gateway logs
ai-companion gateway logs -n 100
```

### 2.3 Bot / Persona / Model / Skill

```bash
ai-companion bot list
ai-companion bot add --name <name>
ai-companion bot remove --name <name>

ai-companion persona --help

ai-companion skill list
ai-companion skill list --json
ai-companion skill list --runtime
ai-companion skill run image_generation "一张下雨天咖啡馆"
ai-companion skill run image_understanding '{"media_urls":["/tmp/demo.jpg"],"prompt":"描述这张图"}'
ai-companion skill run tts "今天辛苦了"

ai-companion model test
```

### 2.4 Memory 维护

```bash
ai-companion memory rebuild-vector
ai-companion memory rebuild-vector --bot <bot_id>
```

### 2.5 CLI 对话内命令

本地 CLI 里可直接使用：

- `/new`
- `/memory`
- `/forget <key>`
- `/dream`
- `/dream on`
- `/dream off`
- `/dream run`
- `/dream doctor`
- `/dream report`
- `/dream delete`
- `/skills`
- `/skill <name> ...`
- `switch`
- `quit` / `exit` / `退出`

---

## 3. 配置文件

### 3.1 配置位置

所有用户配置与数据默认存放在：

```text
~/.ai-companion/
```

配置文件目录：

```text
~/.ai-companion/config/
├── config.yaml
├── models.yaml
└── bots.yaml
```

### 3.2 `models.yaml`

示例：

```yaml
model:
  provider: "openai"
  temperature: 0.8
  max_tokens: 1024

openai:
  api_key: "${OPENAI_API_KEY}"
  base_url: "https://api.openai.com/v1"
  model: "gpt-4o"
  max_context_tokens: 20000

deepseek:
  api_key: "${DEEPSEEK_API_KEY}"
  base_url: "https://api.deepseek.com/v1"
  model: "deepseek-v4-pro"
  max_context_tokens: 64000

tele:
  api_key: "${TELE_API_KEY}"
  base_url: "https://agent.teleai.com.cn/superCowork/sapi/api/v1"
  model: "glm-5-turbo"
  timeout: 600

memory:
  embedding: "local"
  embedding_model: "all-MiniLM-L6-v2"
  max_working_turns: 20
  soft_limit_chars: 80000
  hard_limit_chars: 100000
  scene_constraint_enabled: true
  scene_filter_memory_enabled: true
  dreaming:
    enabled: false
    auto_run_enabled: false
    auto_check_interval_seconds: 900
    min_run_interval_minutes: 120
    min_new_messages: 6
    report_retention: 10
    max_candidates: 24
    max_promotions: 6
  evolution:
    enabled: true
    auto_promotion_enabled: true
    auto_fields:
      values: true
      speaking_style: true
      profile_tags: true

skills:
  image_generation:
    enabled: true
    auto: true
    base_url: "https://api.openai.com/v1"
    model: "gpt-image-1"
    api_key: "${OPENAI_API_KEY}"
  image_understanding:
    enabled: true
    auto: true
    base_url: "https://api.openai.com/v1"
    model: "gpt-4o"
    api_key: "${OPENAI_API_KEY}"
```

### 3.3 `bots.yaml`

示例：

```yaml
bots:
  - id: lin_wanqing
    name: 林晚晴
    enabled: true

  - id: ethan_reed
    name: Ethan Reed
    enabled: true
```

### 3.4 `config.yaml`

这里主要存放平台与全局运行配置，例如：

- `platforms.cli`
- `platforms.feishu`
- `platforms.weixin`
- `platforms.webhook`
- `admin.host`
- `admin.port`
- `admin.cors_origins`
- `session_reset`

---

## 4. 模型与能力

### 4.1 ModelFactory

当前 `ai_companion/model/factory.py` 支持：

| Provider | 说明 |
|----------|------|
| `minimax` | MiniMax |
| `openai` | OpenAI |
| `claude` | Anthropic Claude |
| `mimo` | Xiaomi MiMo |
| `deepseek` | DeepSeek |
| `tele` | TeleClaw 风格适配 |
| `ollama` | 本地 Ollama |
| `custom` | 自定义兼容接口 |

### 4.2 内置能力

项目当前只保留与陪伴场景强相关的内置能力：

- `image_generation`
- `image_understanding`
- `tts`

能力有两种触发方式：

1. 自动路由
2. 显式 `/skill` 或 `ai-companion skill run`

通过 `skill list`、`/skills` 可以看到每个能力当前的：

- `enabled`
- `auto`
- `available`
- `reason`
- `provider`
- `model`

---

## 5. 人格与人生轨迹

### 5.1 Persona 文件

每个 Bot 的人格目录位于：

```text
data/bots/{bot_id}/persona/
```

主要文件：

- `profile.json`
- `backstory.json`
- `values.json`
- `speaking_style.json`
- `conversation_style_rules.json`
- `proactive.json`
- `life.json`

### 5.2 `conversation_style_rules.json`

这是当前项目里很重要的一层，专门控制：

- 怎么说话更自然
- 哪些表达要避免
- 不同场景下的口吻策略
- 如何减少 AI 味

它和 `speaking_style.json` 的区别是：

- `speaking_style.json` 更像人物口吻和表达习惯
- `conversation_style_rules.json` 更像“对话调教规则”

### 5.3 人生轨迹

Bot 拥有独立人生时间线，`life.json` 控制：

- `time_ratio`
- `daily_interval_seconds`
- `major_interval_seconds`
- `daily_event_min_gap_days`
- `major_event_fixed_probability`
- `event_policy`

系统会生成：

- 日常事件
- 人生大事
- 低概率意外
- 生日相关事件

这些事件会反过来影响：

- 日常对话
- 主动唤醒
- 记忆系统
- 人格演化

### 5.4 主动唤醒连续性

当前主动系统已经支持多种动机：

- `idle reminder`
- `deferred reply`
- `topic continuation`
- `emotion followup`
- `life event motive`
- `idle ping`

它们会在 Working / Daily 记忆中留下元数据，并形成 Bot 自己的 `self_memory` 连续性。

---

## 6. 记忆系统

### 6.1 分层结构

当前记忆体系核心层包括：

| 层 | 存储 | 用途 |
|----|------|------|
| Working | `working.db` | 原始对话流水和当前会话上下文 |
| Daily | `daily.db` | 近期摘要、开放话题、自我连续性 |
| Episodic | `episodic.db` | 重要共同经历、冲突、和解、承诺、关键节点 |
| Semantic | `semantic.db` | 结构化用户事实 |
| Relationship | `relationship.db` | 关系标签、维度分数、叙事、互动指导 |
| User Understanding | `user_understanding.json` | 用户可读、可编辑的长期理解投影 |
| Vector | `vector/` | 统一向量索引 |

### 6.2 长期理解投影

`user_understanding.json` 不是唯一真相源，而是给系统和用户都可读的投影层。

它至少包括：

- `manual`
- `auto`
- `relationship_memory`
- 有时还会在后台返回 `layered` 与 `meta`

使用原则：

- `manual` 永远优先
- `auto` 会随对话、关系和反思自动更新
- 冲突信息会在 `meta` 中暴露，方便人工校准

### 6.3 Vector 索引

统一向量索引用于把这些来源组织成语义召回层：

- `semantic.db`
- `user_understanding.json`
- `relationship.db`
- `daily.db`
- 人生事件

手动重建命令：

```bash
ai-companion memory rebuild-vector
ai-companion memory rebuild-vector --bot <bot_id>
```

后台也提供按钮和 API。

### 6.4 Dreaming / 记忆整理

Dreaming 是当前系统里面向“长期沉淀”和“可解释整理”的能力。

它支持：

- 状态查看
- 手动运行
- 最近报告查看
- doctor 诊断
- 删除最近一次整理新增项
- 后台自动运行配置

CLI 对话内命令：

- `/dream`
- `/dream on`
- `/dream off`
- `/dream run`
- `/dream doctor`
- `/dream report`
- `/dream delete`

后台 API：

- `GET /api/v1/admin/memory/{bot_id}/dreaming/status`
- `POST /api/v1/admin/memory/{bot_id}/dreaming/run`
- `GET /api/v1/admin/memory/{bot_id}/dreaming/report`
- `POST /api/v1/admin/memory/{bot_id}/dreaming/doctor`
- `DELETE /api/v1/admin/memory/{bot_id}/dreaming/latest`

### 6.5 Debug 与 Prompt Diagnostics

当前系统不只是“记住了什么”，还会记录为什么这么召回、怎么分配 prompt 预算。

调试上下文里可以看到：

- `system_prompt`
- `retrieved_memory`
- `memory_prompt_diagnostics`
- `response_style_trace`
- `working_history`
- `evolution_refs`

这对排查“为什么 Bot 会这样说”非常重要。

---

## 7. 人格演化

### 7.1 当前实现

人格演化现在已经是正式功能，不再只是散落在 runtime 里的临时写入。

演化流程为：

```text
signal -> reflection -> pending promotion -> core patch
```

信号来源包括：

- 日常对话
- 共同经历
- 关系变化
- 人生事件
- Bot 自身连续性

### 7.2 演化状态

当前实现会维护一套正式状态与审计数据，典型包括：

- `evolution_state.json`
- `evolution_audit.jsonl`

在后台页面中可看到：

- 当前阶段
- 活跃 signal 数
- 待晋升候选
- 时间线
- 事件详情
- suppression reason
- before / after diff
- 人类可读诊断

### 7.3 Evolution API

已实现接口：

- `GET /api/v1/admin/evolution/{bot_id}/summary`
- `GET /api/v1/admin/evolution/{bot_id}/timeline`
- `GET /api/v1/admin/evolution/{bot_id}/events/{event_id}`
- `GET /api/v1/admin/evolution/{bot_id}/state`
- `GET /api/v1/admin/evolution/{bot_id}/config`
- `POST /api/v1/admin/evolution/{bot_id}/reflect`
- `POST /api/v1/admin/evolution/{bot_id}/rebuild`
- `POST /api/v1/admin/evolution/{bot_id}/promotion/{candidate_id}/apply`
- `POST /api/v1/admin/evolution/{bot_id}/promotion/{candidate_id}/reject`

### 7.4 Evolution 设置项

在 Settings 页面中，当前可配置至少这些演化相关开关：

- `memory.evolution.enabled`
- `memory.evolution.auto_promotion_enabled`
- `memory.evolution.auto_fields.values`
- `memory.evolution.auto_fields.speaking_style`
- `memory.evolution.auto_fields.profile_tags`

---

## 8. 平台与网关

### 8.1 平台类型

当前主要文档化且在本项目内重点维护的是：

- `cli`
- `feishu`
- `weixin`
- `webhook`

### 8.2 飞书

飞书配置通常位于：

- `config.yaml -> platforms.feishu`

当前后台设置页已支持：

- `app_id`
- `app_secret`
- `connection_mode`
- `group_policy`
- dedicated routing

当前约束：

- 一个飞书 App 绑定一个 Bot
- 一个 Bot 绑定一个飞书 App

### 8.3 微信 iLink

微信当前已接入专门配置流，支持：

- `ai-companion weixin`
- `ai-companion weixin setup`

常见配置项：

- `token`
- `extra.account_id`
- `extra.base_url`
- `extra.cdn_base_url`
- `extra.dm_policy`
- `extra.allow_from`
- `extra.group_policy`
- `extra.group_allow_from`
- `routing.bot_id`
- `home_channel`

运行时账号数据通常位于：

```text
~/.ai-companion/weixin/accounts/
```

### 8.4 Gateway 状态与日志

查看状态：

```bash
ai-companion gateway status
```

查看日志：

```bash
ai-companion gateway logs
ai-companion gateway logs -n 200
```

Gateway PID 默认保存在：

```text
~/.ai-companion/gateway.pid
```

日志默认位于：

```text
~/.ai-companion/logs/gateway.log
```

---

## 9. 管理后台

### 9.1 页面总览

当前 `ai-companion-ui` 包含这些页面：

| 路由 | 页面 | 说明 |
|------|------|------|
| `/` | 监控面板 | 总览核心指标 |
| `/session` | 会话管理 | 查看会话与消息详情 |
| `/logs` | 日志查看 | 查看实时日志 |
| `/memory` | 记忆系统 | 查看分层记忆、Trust View、Dreaming、关系状态、向量索引 |
| `/understanding` | 长期理解投影 | 编辑 `manual`，查看 `auto`、relationship projection 和 layered projection |
| `/style` | 风格调教 | 编辑 `conversation_style_rules.json` |
| `/operations` | 运营台 | 查看主动唤醒、人生轨迹、当前 life snapshot |
| `/evolution` | 人格演化 | 查看时间线、详情、待晋升候选和状态诊断 |
| `/debug` | 调试工具 | 查看 prompt、memory trace、style trace、prompt budget |
| `/settings` | 设置 | 编辑模型、技能、记忆、Dreaming、Evolution、平台、人格等配置 |

### 9.2 Memory 页

Memory 页当前不只看“有哪些记忆”，还会展示：

- Working / Daily / Episodic / Semantic
- Relationship State
- Memory Trust View
- Session State
- Evolution 相关引用入口
- Dreaming 状态与报告

### 9.3 Understanding 页

Understanding 页当前重点展示：

- `manual`
- `auto`
- `relationship_memory`
- `layered`
- `meta`

这是“长期理解投影”，不是另一份独立真相库。

### 9.4 StyleLab 页

StyleLab 页当前直接编辑：

```text
conversation_style_rules.json
```

适合做：

- 反 AI 味规则
- 情绪支持风格
- 任务型说话方式
- 修复关系时的语言策略

### 9.5 Operations 页

Operations 页当前聚焦：

- 主动唤醒状态
- 人生轨迹配置
- 当前日期
- 当前生活状态
- 当前互动态
- `life_status` 快照

### 9.6 Evolution 页

Evolution 页是专门的人格演化可视化页面，当前至少包含：

- 演化总览
- 当前人格快照
- 演化时间线
- 单条变化详情
- 可解释诊断
- 原始状态视图

### 9.7 Debug 页

Debug 页当前可查看：

- Prompt Inspector
- Memory Trace
- Response Style Trace
- Prompt Budget
- Working History
- Evolution Links

---

## 10. 数据目录

### 10.1 总体目录

```text
~/.ai-companion/
├── config/
├── data/
│   └── bots/
├── logs/
├── gateway.pid
└── weixin/
```

### 10.2 单个 Bot

```text
~/.ai-companion/data/bots/{bot_id}/
├── persona/
│   ├── profile.json
│   ├── backstory.json
│   ├── values.json
│   ├── speaking_style.json
│   ├── conversation_style_rules.json
│   ├── proactive.json
│   └── life.json
├── memory/
│   ├── working.db
│   ├── daily.db
│   ├── episodic.db
│   ├── semantic.db
│   ├── relationship.db
│   ├── user_understanding.json
│   ├── vector/
│   ├── evolution_state.json
│   └── evolution_audit.jsonl
├── life_state.json
└── proactive_state.json
```

---

## 11. 常见问题

### Q1：`model test` 为什么看起来很轻？

当前 `ai-companion model test` 主要用于确认命令链路和配置读取入口正常，不是完整联网压测工具。真正的可用性以实际对话启动和后台请求为准。

### Q2：为什么图片没有自动理解或自动出图？

先检查：

1. `skill list` 或 `/skills` 是否显示该能力 `enabled=true`
2. `auto` 是否开启
3. `available` 是否为 `true`
4. `reason` 是否提示缺 `api_key` 或配置错误

### Q3：为什么后台“重建向量索引”报 `Failed to fetch`？

通常不是索引逻辑本身坏了，而是前端没有连上 Admin API。先确认：

```bash
ai-companion gateway status
```

必要时：

```bash
ai-companion gateway restart
```

### Q4：为什么 Bot 说话还是有 AI 味？

优先调这些地方：

1. `conversation_style_rules.json`
2. Settings 页里的 `speaking_style`
3. StyleLab 页的禁用短语和自然表达规则
4. Debug 页里的 `response_style_trace`

### Q5：为什么 Bot 似乎忘了自己刚主动找过我？

新版本里主动消息会写入带 `assistant_initiated`、`proactive`、`proactive_kind` 的记忆元数据，并通过 `self_memory` 参与后续上下文。如果仍表现异常，优先检查：

1. `working.db` / `daily.db`
2. Memory 页的 Daily / Trust View
3. Debug 页的 `retrieved_memory`

### Q6：人格演化会不会黑盒漂移？

当前版本已经尽量避免黑盒：

- 有 Evolution 页
- 有 summary / timeline / detail / state / config API
- 有 suppression reason
- 有 before / after diff
- 有手动 reflect / rebuild / apply / reject

如果你希望更保守，可以在 Settings 里关闭：

- 自动晋升
- `values` 自动演化
- `speaking_style` 自动演化
- `profile_tags` 自动演化

---

## 相关文档

- [README](../README.md)
- [Bot 设计指引](./BOT_DESIGN_GUIDE.md)
- [Bot JSON 字段说明](./BOT_JSON_FIELDS.md)
- [主动唤醒设计](./DESIGN_phase5_proactive.md)
- [UI 设计方案](./ui/UI_DESIGN.md)
- [UI 产品规格](./ui/UI_SPEC.md)
