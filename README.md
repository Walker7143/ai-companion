# AI Companion / AI 知己

开源 AI 陪伴产品，支持 macOS / Linux / Windows。每个机器人有独立人格和记忆体系，能像真人一样与你互动。

## 核心特性

| 特性 | 说明 |
|------|------|
| **多模型支持** | MiniMax / OpenAI / Claude / MiMo / Ollama / 自定义 API |
| **独立人格** | 每个 Bot 有独特的性格、背景故事和说话风格（傲娇/活泼/温柔/高冷...） |
| **智能记忆体系** | 工作记忆 + 用户模型 + 关系状态 + 情景记忆 + 用户理解文件 + 意识工作区，按意图和预算召回而不是机械堆上下文 |
| **本地向量嵌入** | 支持 sentence-transformers 本地向量语义召回，中文友好 |
| **人生轨迹** | 每个 Bot 有独立时间线，会生成日常小事、人生大事、生日和低概率意外事件 |
| **主动唤醒** | 会主动找你聊天、提醒事情、偶尔撒娇，基于 LLM 推理判断时机，并带着主动来源 metadata 和自我记忆延续同一条话题 |
| **Token 预算控制** | 各层记忆按意图分块进入 prompt，并输出调试诊断，方便观察 token 消耗 |
| **关系进化** | 根据互动深度，Bot 行为会逐渐变化（陌生网友 → 恋人） |
| **性格推断拒绝** | 基于性格判断该不该回答，不是简单的关键词过滤 |
| **多媒体技能** | 支持图片生成、语音合成 |
| **多平台网关** | 本地 CLI / 飞书 / Webhook，多种消息发送方式 |

---

## 快速开始

### 执行命令前需要准备

运行下面的安装命令前，请先确认电脑里有这些环境：

- **Python 3.11+**：后端和命令行工具需要。
- **Git**：安装脚本会拉取项目代码。
- **网络连接**：需要下载 Python 依赖、前端依赖和项目代码。
- **一个模型来源**：MiniMax / OpenAI / Claude / MiMo / Ollama / 自定义 API 任意一种即可。云端模型需要准备 API Key；Ollama 需要本机已启动 Ollama 服务。
- **Node.js + npm（推荐）**：用于启动管理后台 Web UI。如果只想用纯 CLI，可以暂时不装；需要 Web UI 时再安装。

依赖包不需要用户手动逐个安装，安装脚本和 `ai-companion setup` 会尽量自动处理。

### 安装

**macOS / Linux（国内用户）：**
```bash
curl -fsSL https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install-cn.sh | bash
```

**Windows（国内用户）：**
```powershell
irm https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install-cn.ps1 -UseBasicParsing | iex
```

**海外用户**请访问 [Gitee Release](https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/releases) 下载对应脚本。

### 首次配置

```bash
source ~/.ai-companion/.venv/bin/activate  # 如果使用了虚拟环境
ai-companion setup
```

重复运行 `setup` 时会合并更新配置：没有选择重新配置或覆盖的部分会保留旧值，例如只改模型时不会重写已有 Bot、人生轨迹或主动唤醒配置。

### 更新

以后更新代码不需要卸载重装，直接运行：

```bash
ai-companion update
```

国内网络可使用清华 PyPI 镜像同步依赖：

```bash
ai-companion update --cn
```

更新命令会保留 `~/.ai-companion/` 下的 Bot 配置、记忆和日志；如果 Gateway 正在运行，会先停止，更新完成后自动重新启动。

---

## 项目架构

```
ai_companion/
├── bot/              # Bot 核心实例
│   ├── instance.py   # BotInstance - 核心运行时
│   └── manager.py    # BotManager - 多 Bot 管理
├── memory/           # 记忆系统
│   ├── engine.py     # MemoryEngine - 记忆写入、召回、维护协调
│   ├── extractor.py  # MemoryExtractor - 从对话抽取候选记忆
│   ├── governor.py   # MemoryGovernor - 判断候选是否值得长期写入
│   ├── retriever.py  # MemoryRetriever - 按当前意图制定召回计划
│   ├── conscious.py  # ConsciousContext - 当轮意识工作区
│   ├── prompt_builder.py  # MemoryPromptBuilder - 构建记忆上下文
│   ├── maintenance.py     # MemoryMaintenance - 过期、归档、投影刷新
│   └── stores/
│       ├── working.py    # 工作记忆 / 原始消息流水
│       ├── episodic.py   # 情景记忆 - 重要共同经历
│       ├── semantic.py   # 用户模型 - 结构化用户事实
│       ├── relationship.py       # 关系状态 - 好感、亲密、紧张、关键时刻
│       └── user_understanding.py # 用户可编辑理解文件
├── persona/          # 人格系统
│   ├── loader.py     # PersonaLoader - 人格加载
│   ├── engine.py     # PersonaEngine - System Prompt 构建
│   └── refusal_engine.py  # 拒绝引擎 - 性格推断拒绝
├── proactive/        # 主动唤醒系统
│   ├── engine.py     # ProactiveEngine - LLM 判断 + 消息生成
│   ├── scheduler.py   # ProactiveScheduler - 主动唤醒定时检查
│   ├── platform.py   # 发送平台适配器 (CLI/飞书/Webhook)
│   ├── life_engine.py     # LifeEngine - 人生轨迹事件生成
│   ├── life_scheduler.py  # LifeScheduler - 独立人生轨迹调度
│   ├── life_config.py     # life.json 配置加载
│   └── life_state.py      # life_state.json 状态持久化
├── context/          # 上下文管理
│   ├── compressor.py  # ContextCompressor - 上下文压缩
│   └── tokenizer.py   # TokenEstimator - Token 估算
├── skill/            # 技能系统
│   ├── dispatcher.py  # SkillDispatcher - 技能调度
│   ├── registry.py    # SkillRegistry - 技能注册
│   ├── image_gen.py   # 图片生成技能
│   └── tts.py         # 语音合成技能
├── model/            # 模型系统
│   ├── factory.py    # ModelFactory - 模型工厂
│   └── adapters/     # 模型适配器
│       ├── base.py        # ModelAdapter 抽象基类
│       ├── minimax_adapter.py  # MiniMax
│       ├── openai_adapter.py   # OpenAI GPT
│       ├── claude_adapter.py   # Anthropic Claude
│       ├── mimo_adapter.py     # Xiaomi MiMo
│       ├── ollama_adapter.py   # Ollama 本地
│       └── custom_adapter.py   # 自定义 HTTP API
├── gateway/          # 消息网关
│   ├── cmd.py        # Admin API + 网关入口
│   ├── control.py    # 网关进程管理（启动/停止）
│   └── platforms/    # 平台适配
└── _vendor/          # 第三方库（vendored）
    └── gw_cli/       # Gateway CLI 工具

ai-companion-ui/      # 管理后台 Web UI
├── src/
│   ├── pages/        # 页面（Dashboard/Session/Memory/Settings）
│   ├── stores/       # Zustand 状态管理
│   └── api/          # 前端 API 调用层
└── vite.config.ts   # Vite 构建配置
```

---

## 智能记忆系统

AI Companion 的记忆系统不是简单“多存一点”，而是先判断什么值得记，再按当前对话意图选择相关记忆，并把结果压成当轮真正能进入意识的少量线索。完整记忆会被保存，但主模型每轮只看到相关且有预算的那一小块。

```text
当前对话
  → Working/Raw Log 保存原文和 metadata
  → Extractor 抽取候选记忆
  → Governor 判断写入/跳过/归档/刷新投影
  → User Model / Episodic / Relationship 分层存储
  → Retriever 按意图召回
  → ConsciousContextBuilder 生成意识工作区
  → PromptBuilder 按预算生成记忆上下文与 diagnostics
```

### 记忆分层

| 层 | 存储 | 说明 |
|----|------|------|
| Working / Raw Log | `working.db` | 当前会话原文、压缩摘要、debug 底账 |
| Conscious / 意识工作区 | 由 `conscious.py` 生成，不直接落库 | 把召回结果压成当前焦点、情绪读取、关系姿态和少量 active memories，只让此刻真正需要的线索进入 prompt |
| User Model | `semantic.db` | 结构化用户事实，包含分类、置信度、来源、证据、过期时间 |
| Relationship State | `relationship.db` | Bot 与用户的关系标签、好感度、亲密度、紧张度、关键关系时刻 |
| Episodic Memory | `episodic.db` + 可选 Chroma | 重要共同经历、冲突/和解、承诺、人生事件，不记录普通寒暄 |
| Self / Autobiographical | `daily.db` 中带 `assistant_initiated` 的 assistant 消息 | Bot 自己最近主动发过什么、为什么发、要怎么接住用户回复 |
| User Understanding | `user_understanding.json` | 用户可编辑的“Bot 对我的理解”，分 `manual` 和 `auto` 两区 |

长期记忆完整保存，但每轮进入主模型的只是 `ConsciousContext` 压缩后的短片段。`MemoryPromptBuilder` 会再按意图分配预算，把 `understanding`、`relationship`、`daily`、`self_memory`、`semantic` 和 `episodic` 分块注入，并在 `memory_prompt_diagnostics` 里记录各块字符数、token 估算、截断情况和总预算，方便直接排查 token 为什么变多。

### 用户理解文件

每个 Bot 都有一份可直接编辑的用户理解文件：

```text
~/.ai-companion/data/bots/{bot_id}/memory/user_understanding.json
```

它用于初始化和纠正 Bot 对用户的了解：

- `manual`：用户手动填写，永远优先，自动记忆不会覆盖。
- `auto`：系统从日常对话、关系状态和 Bot 反思中形成的理解，会自动刷新。
- Prompt 优先使用 `manual`，再使用相关的 `auto`。
- 内置 Bot 已带初始 `manual`，开箱就有基础相处分寸；后续会随日常对话刷新 `auto`。

示例：

```json
{
  "version": 3,
  "manual": {
    "summary": "用户希望被温柔但不敷衍地对待。",
    "facts": {"称呼": "阿迟"},
    "communication_style": ["先共情，再给建议"],
    "boundaries": ["不要调侃体重"],
    "relationship_expectations": ["希望 Bot 像熟悉的人一样有分寸地陪伴"]
  },
  "auto": {
    "profile_summary": "用户近期压力偏高，情绪低落时更需要先被接住。",
    "facts": {"城市": "上海"},
    "emotional_patterns": ["压力大时容易焦虑，但愿意继续推进事情"],
    "comfort_strategies": ["先陪一会儿，再给具体建议"],
    "current_context": ["最近在准备作品集"],
    "open_threads": ["用户想继续聊作品集"]
  },
  "relationship_memory": {
    "what_user_seems_to_need_from_bot": ["稳定陪伴，而不是机械建议"],
    "things_that_brought_them_closer": ["用户开始主动分享脆弱时刻"]
  }
}
```

### 动态召回

系统会先判断当前意图，再选择不同记忆：

| 意图 | 优先召回 |
|------|----------|
| 情绪支持 | 沟通偏好、边界、近期压力源、关系状态 |
| 回忆旧事 | 情景记忆优先，必要时跨会话 |
| 计划推进 | open_threads、目标、最近上下文 |
| 关系修复 | 关系状态、冲突/和解片段、边界 |
| 任务请求 | 少量必要偏好，避免无关情感记忆干扰 |
| 主动唤醒 | open_threads、关系状态、近期用户状态、Bot 人生轨迹 |

### 本地向量召回

```yaml
# 启用本地向量嵌入
memory:
  embedding: "local"              # "local" | "none"
  embedding_model: "all-MiniLM-L6-v2"
```

---

## 主动唤醒系统

### 触发机制

- **空闲触发**: 用户超过一定时间未互动，Bot 会主动联系
- **情绪触发**: 用户消息包含特定情绪关键词时延迟关心
- **梯度沉默**: 根据未联系时长调整频率（7天/14天/30天阈值）
- **生活话题**: 主动唤醒判断和消息生成会读取 Bot 当前日期、动态年龄、人生阶段和近期可分享事件

### 发送平台

| 平台 | 配置 | 消息去向 |
|------|------|---------|
| CLI | `platform.type: "cli"` | 终端 stdout |
| 飞书 | `platform.type: "feishu"` | 飞书用户/群 |
| Webhook | `platform.type: "webhook"` | 自定义 HTTP endpoint |

### 限流保护

- 每日最大主动消息数
- 最小发送间隔
- 冷却机制
- 生气降级（用户多次不回复后减少打扰）

### 主动连续性

主动消息现在会写入 Working / Daily 记忆并保留 `metadata.proactive=true`、`metadata.assistant_initiated=true` 和 `proactive_kind`。这样用户一回复，Bot 能知道上一条是自己先发起的，不会像没发过那句话一样重新开场。`proactive_kind` 会区分 `idle_reminder`、`deferred_reply`、`topic_continuation`、`emotion_followup`、`life_event` 等来源，后续会以 `self_memory` 进入意识工作区，让 Bot 记得“我刚才为什么主动找你”。兜底文案也改得更自然，不再只吐一个裸 `在吗`。

---

## 人生轨迹系统

Bot 具备独立人生轨迹，独立于主动消息调度器运行。人生轨迹状态会进入普通对话、日常事件、人生大事和主动唤醒 prompt，避免 Bot 时间线推进后仍按静态年龄回答。

### 事件类型

| 类型 | 周期 | 说明 |
|------|------|------|
| 日常小事 | 按 `life.json` 的 `daily_interval_seconds / time_ratio` | 从 200+ 场景池中随机抽少量候选给 LLM；最多保留最近 100 条 |
| 人生大事 | 按 `life.json` 的 `major_interval_seconds / time_ratio` | 具体化的长期事件，触发人格文件更新 |
| 意外事件 | 独立低概率通道 | 默认每个 Bot 日 `0.01` 概率，整体冷却默认 365 天 |

### 事件去重与生活画像

- `event_policy.scenario_cooldown_days` 和 `major_scenario_cooldown_days` 控制同类事件冷却。
- `event_policy.llm_daily_candidate_limit` 控制每次给 LLM 的日常候选数，默认 12，不会把完整 200+ 场景池塞进 prompt。
- `daily_life_profile` 描述 Bot 的城市、通勤、居住、工作、兴趣和事件偏好；性格标签也会影响候选权重。

### 时间加速

`time_ratio` 控制 Bot 内部时间的流逝速度：

| time_ratio | 默认日常检查间隔 | 常见效果 | 适用场景 |
|------------|------------------|---------|---------|
| 1 | 86400 秒 | 现实 1 天推进 1 个 Bot 日 | 正常体验（默认） |
| 24 | 3600 秒 | 现实 1 小时推进 1 个 Bot 日 | 轻度加速 |
| 1440 | 60 秒 | 现实 1 分钟推进 1 个 Bot 日 | 观察测试 |
| 3600 | 1 秒 | 极速测试，受 1 秒轮询下限约束 | 快速验证 |

LifeScheduler 会自适应轮询，间隔为 `1-10` 秒之间；单次 `tick_daily` 至少推进 1 天，长时间离线或极高 `time_ratio` 会按经过时间补推，单次最多推进 365 天。

---

## 配置说明

### 配置文件位置

```
~/.ai-companion/
├── config/
│   ├── config.yaml  # 主配置
│   ├── models.yaml  # AI 模型配置
│   └── bots.yaml    # Bot 列表
└── data/
    └── bots/        # Bot 配置、记忆、life_state/proactive_state
```

### models.yaml 示例

```yaml
# 默认 provider
model:
  provider: "minimax"          # minimax | openai | claude | mimo | ollama | custom
  temperature: 0.8
  max_tokens: 1024

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

memory:
  embedding: "local"              # 启用本地向量嵌入
  embedding_model: "all-MiniLM-L6-v2"
  max_working_turns: 20
  hard_limit_chars: 5000
  soft_limit_chars: 3000

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

### 环境变量

```bash
export MINIMAX_API_KEY="your_key"
export MIMO_API_KEY="your_key"
export FEISHU_APP_ID="your_feishu_app_id"
export FEISHU_APP_SECRET="your_feishu_app_secret"
```

---

## 启动方式

### 本地 CLI

```bash
ai-companion start              # 默认 Bot
ai-companion start --bot mybot   # 指定 Bot
```

### 飞书网关服务

```bash
ai-companion gateway start    # 后台启动（默认，关闭终端后继续运行）
ai-companion gateway start --sync  # 前台启动（显示日志）
ai-companion gateway stop     # 停止
ai-companion gateway logs     # 查看日志
```

**管理后台**: 启动本地 CLI 或 Gateway 时会自动拉起本地 Admin API（http://127.0.0.1:8642）和 Web UI（http://localhost:1421）。如果 CLI 和 Gateway 同时启动，会复用同一个 UI 进程，不会重复启动。

```bash
ai-companion start
ai-companion gateway start
```

如需禁用自动 UI，可设置 `START_UI=false` 或 `AI_COMPANION_START_UI=false`。

### 一键更新

```bash
ai-companion update       # 更新代码和依赖，保留本地数据
ai-companion update --cn  # 使用清华 PyPI 镜像
```

### 内置命令

在对话界面使用：

| 命令 | 说明 |
|------|------|
| `/new` | 开始新会话 |
| `/memory` | 查看工作记忆、情景记忆、用户事实、关系状态和用户理解文件路径 |
| `/forget <key>` | 删除某条自动用户事实，并同步移除用户理解文件里的 `auto` 投影 |
| `quit` | 退出 |

---

## Bot 初始化

仓库提供了三男三女的新 Bot 人设样例，可参考 `docs/BOT_DESIGN_GUIDE.md`。你也可以通过 `ai-companion setup` 创建自己的 Bot，并在 `data/bots/{bot_id}/persona/` 中完成设定。

---

## 自定义人格

```
data/bots/mybot/persona/
├── profile.json        # 基础档案（名字、年龄、职业等）
├── backstory.json      # 人生经历
├── values.json        # 价值观和底线
├── speaking_style.json # 说话风格
├── conversation_style_rules.json # 对话风格规则，降低 AI 味
├── proactive.json      # 主动唤醒配置
└── life.json           # 人生轨迹配置
```

复制模板：

```bash
cp -r data/bots/_template data/bots/mybot
```

---

## 测试

项目包含系统级离线测试套件：

```bash
# 端到端系统测试（配置、模型工厂、记忆、BotInstance、主动唤醒、人生轨迹、Gateway、前端构建）
python tests/system_test_suite.py
```

测试报告会写入 `.artifacts/system-test-rebuilt-*/`，当前套件覆盖 40+ 项核心行为。

---

## 安装方式

详细安装说明请参考上方 [快速开始](#快速开始) 部分。

---

## 卸载

### 本地安装卸载

```bash
# 1. 停止网关服务（如有运行）
ai-companion gateway stop

# 2. 删除 Python 包
pip uninstall ai-companion -y

# 3. 删除数据目录（可选，会删除所有 Bot 配置和记忆）
rm -rf ~/.ai-companion

# 4. 如果使用了虚拟环境
rm -rf ~/.ai-companion/.venv

# 5. 删除克隆到本地的项目代码（如有）
rm -rf ~/AICompanion  # 或者你克隆到的目录
```

### Windows

```powershell
# 1. 停止网关服务
ai-companion gateway stop

# 2. 卸载 Python 包
pip uninstall ai-companion -y

# 3. 删除数据目录
Remove-Item -Recurse -Force ~/.ai-companion

# 4. 如使用虚拟环境
Remove-Item -Recurse -Force ~/.ai-companion/.venv

# 5. 删除克隆到本地的项目代码（如有）
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\AICompanion"  # 或者你克隆到的目录
```

### Docker 卸载

```bash
# 停止并删除容器
docker-compose -f ~/.ai-companion/docker-compose.yml down

# 删除数据卷
docker volume rm ai-companion-data 2>/dev/null

# 删除安装目录
rm -rf ~/.ai-companion
```

---

## 注意事项

- **Python 版本**：本地安装需要 Python 3.11+
- **虚拟环境**：如果系统 Python 受保护（externally-managed-environment），脚本会自动创建虚拟环境 `~/.ai-companion/.venv`
- **数据目录**：所有数据存储在 `~/.ai-companion/`
- **API Key**：安装后需要配置 API Key，参考[配置说明](#配置说明)
- **重复 setup**：配置向导默认保留旧值，只合并写入本次修改的模型、Bot 或平台配置

---

## 常见问题

**Q: 提示 "API Key 未设置"**
A: `export MINIMAX_API_KEY="your_key"`

**Q: Bot 不主动发消息**
A: 检查 `data/bots/{bot_id}/persona/proactive.json` 中 `enabled`、`mode`、`platform.type` 和发送平台配置；平台发送器未配置时不会计入已发送次数。

**Q: Bot 像不知道自己刚发过的主动消息？**
A: 主动消息会带 `assistant_initiated` / `proactive` / `proactive_kind` 元数据写入 Working / Daily 记忆，下一轮回复会自动接上这条主动动机，并通过 `self_memory` 投影成“Bot 自己最近主动做过的事”。如果还看到旧行为，先查 `~/.ai-companion/logs/gateway.log`、`working.db` 和 `daily.db` 里的 `metadata_json`，确认是不是旧数据或旧版本生成的记录。

**Q: 向量嵌入不生效**
A: 确认 `models.yaml` 中 `memory.embedding: "local"`（sentence-transformers 已默认安装）

**Q: 如何重置记忆？**
A: 删除自动记忆可清理 `~/.ai-companion/data/bots/{bot_id}/memory/*.db`。`user_understanding.json` 里的 `manual` 是用户手动理解，建议不要直接删除，除非你想完全重置 Bot 对用户的初始化理解。

---

## 详细文档

| 文档 | 说明 |
|------|------|
| [使用指南](./docs/GUIDE.md) | 详细的配置说明和功能介绍 |
| [Bot 设计指引](./docs/BOT_DESIGN_GUIDE.md) | 新 Bot 样例与自建 Bot 方法论 |
| [Bot JSON 字段说明](./docs/BOT_JSON_FIELDS.md) | `profile.json` / `life.json` / `proactive.json` / 状态文件字段说明 |
| [主动唤醒设计](./docs/DESIGN_phase5_proactive.md) | 主动唤醒架构和算法设计 |
| [类人记忆与 Token 控制设计](./docs/DESIGN_human_like_memory_token_architecture.md) | 本分支的记忆层次、意识工作区和上下文预算方案 |
| [UI 设计方案](./docs/ui/UI_DESIGN.md) | 管理后台设计规范 |
| [UI 产品规格](./docs/ui/UI_SPEC.md) | 管理后台功能清单 |

---

## License

MIT
