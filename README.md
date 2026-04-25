# AI Companion / AI 知己

开源 AI 陪伴产品，支持 macOS / Linux / Windows。每个机器人有独立人格和记忆体系，能像真人一样与你互动。

## 核心特性

| 特性 | 说明 |
|------|------|
| **多模型支持** | MiniMax / OpenAI / Claude / Ollama / 自定义 API |
| **独立人格** | 每个 Bot 有独特的性格、背景故事和说话风格（傲娇/活泼/温柔/高冷...） |
| **三层记忆** | 工作记忆 + 情景记忆 + 语义记忆，像真人一样记住你们的故事 |
| **本地向量嵌入** | 支持 sentence-transformers 本地向量语义召回，中文友好 |
| **主动唤醒** | 会主动找你聊天、提醒事情、偶尔撒娇，基于 LLM 推理判断时机 |
| **关系进化** | 根据互动深度，Bot 行为会逐渐变化（陌生网友 → 恋人） |
| **性格推断拒绝** | 基于性格判断该不该回答，不是简单的关键词过滤 |
| **多媒体技能** | 支持图片生成、语音合成 |
| **多平台网关** | 本地 CLI / 飞书 / Webhook，多种消息发送方式 |

---

## 快速开始

### 环境要求

- Python 3.10+
- 至少一个模型 API Key (MiniMax / OpenAI / Claude / Ollama)

### 安装

```bash
# 一键安装（自动选择 Docker 或本地）
curl -fsSL https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install.sh | bash

# 强制 Docker 模式
curl -fsSL https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install.sh | bash -s -- --docker

# 强制本地安装
curl -fsSL https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install.sh | bash -s -- --local

# 或克隆后本地安装
git clone git@gitee.com:wang_xiao_wei_7143/ai-girl-friend.git
cd ai-girl-friend
./scripts/install.sh
./scripts/install.sh --docker    # Docker 模式
./scripts/install.sh --local     # 本地模式
```

### 首次配置

```bash
source ~/.ai-companion/.venv/bin/activate  # 如果使用了虚拟环境
ai-companion setup
```

---

## 项目架构

```
ai_companion/
├── bot/              # Bot 核心实例
│   ├── instance.py   # BotInstance - 核心运行时
│   └── manager.py    # BotManager - 多 Bot 管理
├── memory/           # 记忆系统
│   ├── engine.py     # MemoryEngine - 三层记忆协调
│   └── stores/
│       ├── working.py    # 工作记忆 - SQLite + jieba 分词
│       ├── episodic.py   # 情景记忆 - SQLite + Chroma 向量
│       └── semantic.py   # 语义记忆 - 关键事实提取
├── persona/          # 人格系统
│   ├── loader.py     # PersonaLoader - 人格加载
│   ├── engine.py     # PersonaEngine - System Prompt 构建
│   └── refusal_engine.py  # 拒绝引擎 - 性格推断拒绝
├── proactive/        # 主动唤醒系统
│   ├── engine.py     # ProactiveEngine - LLM 判断 + 消息生成
│   ├── scheduler.py   # ProactiveScheduler - 定时检查调度
│   ├── platform.py   # 发送平台适配器 (CLI/飞书/Webhook)
│   └── life_engine.py  # 生活事件引擎
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
│       ├── ollama_adapter.py   # Ollama 本地
│       └── custom_adapter.py   # 自定义 HTTP API
├── gateway/          # 消息网关
│   ├── session.py    # SessionStore - 会话管理
│   ├── delivery.py   # DeliveryRouter - 消息投递
│   └── platforms/    # 平台适配
└── _vendor/          # 第三方库（vendored）
    └── gw_cli/       # Gateway CLI 工具
```

---

## 三层记忆系统

### 工作记忆 (Working Memory)

- **存储**: SQLite
- **搜索**: jieba 中文分词 + LIKE 匹配
- **用途**: 当前会话的原始消息记录
- **特点**: 高精度关键词匹配，适合精确回忆

### 情景记忆 (Episodic Memory)

- **存储**: SQLite + Chroma 向量数据库
- **搜索**: sentence-transformers 本地向量嵌入
- **用途**: 重要情景片段，跨会话语义召回
- **特点**: 语义相近但非精确的内容也能召回

```yaml
# 启用本地向量嵌入
memory:
  embedding: "local"              # "local" | "none"
  embedding_model: "all-MiniLM-L6-v2"
```

### 语义记忆 (Semantic Memory)

- **存储**: SQLite
- **用途**: 提取和存储关键事实（用户的喜好、习惯、重要纪念日...）

---

## 主动唤醒系统

### 触发机制

- **空闲触发**: 用户超过一定时间未互动，Bot 会主动联系
- **情绪触发**: 用户消息包含特定情绪关键词时延迟关心
- **梯度沉默**: 根据未联系时长调整频率（7天/14天/30天阈值）

### 发送平台

| 平台 | 配置 | 消息去向 |
|------|------|---------|
| CLI | 默认 | 终端 stdout |
| 飞书 | `platform_type: "feishu"` | 飞书用户/群 |
| Webhook | `platform_type: "webhook"` | 自定义 HTTP endpoint |

### 限流保护

- 每日最大主动消息数
- 最小发送间隔
- 冷却机制
- 生气降级（用户多次不回复后减少打扰）

---

## 配置说明

### 配置文件位置

```
~/.ai-companion/
├── config.yaml      # 主配置
├── models.yaml      # AI 模型配置
├── bots.yaml        # Bot 列表
└── proactive_states/  # 主动唤醒状态
```

### models.yaml 示例

```yaml
# 默认 provider
model:
  provider: "minimax"          # minimax | openai | claude | ollama | custom
  temperature: 0.8
  max_tokens: 1024

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

memory:
  embedding: "local"              # 启用本地向量嵌入
  embedding_model: "all-MiniLM-L6-v2"
  max_working_turns: 20
  hard_limit_chars: 5000
  soft_limit_chars: 3000
```

### 环境变量

```bash
export MINIMAX_API_KEY="your_key"
export FEISHU_APP_ID="your_feishu_app_id"
export FEISHU_APP_SECRET="your_feishu_app_secret"
```

---

## 启动方式

### 本地 CLI

```bash
python -m ai_companion start              # 默认 Bot
python -m ai_companion start --bot suqing  # 指定 Bot
```

### 飞书网关服务

```bash
python -m ai_companion gateway start    # 后台启动
python -m ai_companion gateway start --sync  # 前台启动
python -m ai_companion gateway stop     # 停止
python -m ai_companion gateway logs     # 查看日志
```

### 内置命令

在对话界面使用：

| 命令 | 说明 |
|------|------|
| `/new` | 开始新会话 |
| `/memory` | 查看记忆状态 |
| `/forget <key>` | 删除某条记忆 |
| `quit` | 退出 |

---

## 内置人格

| ID | 名称 | 性格 | 简介 |
|----|------|------|------|
| suqing | 苏晴 | 傲娇 | 26岁自由插画师，嘴硬心软 |
| aiyue | 阿月 | 活泼 | 22岁音乐学院学生，有点粘人 |
| chenxing | 陈行 | 沉稳 | 28岁程序员，话少但可靠，高冷温柔 |
| yutian | 雨天 | 阳光 | 25岁健身教练，热情直接，有点占有欲 |

---

## 自定义人格

```
data/bots/mybot/persona/
├── profile.json        # 基础档案（名字、年龄、职业等）
├── backstory.json      # 人生经历
├── values.json        # 价值观和底线
├── speaking_style.json # 说话风格
└── proactive.json      # 主动唤醒配置
```

复制模板：

```bash
cp -r data/bots/_template data/bots/mybot
```

---

## 测试

项目包含全面的测试套件：

```bash
# 单元/集成测试（181 个测试用例）
python test_comprehensive.py

# 真实使用场景测试（10 项核心功能验证）
python test_real_usage.py
```

测试覆盖：配置加载、模型对话、人格系统、记忆系统、BotInstance、主动唤醒、上下文压缩、会话管理、技能系统、Gateway

---

## 安装方式

### macOS / Linux

```bash
# 一键安装（自动检测 Docker 或本地）
curl -fsSL https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install.sh | bash

# 指定安装模式
curl -fsSL https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install.sh | bash -s -- --docker
curl -fsSL https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install.sh | bash -s -- --local

# 或克隆后本地运行
git clone git@gitee.com:wang_xiao_wei_7143/ai-girl-friend.git
cd ai-girl-friend
./scripts/install.sh
```

### Windows

```powershell
# 在线安装（自动下载并执行）
irm https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install.ps1 -UseBasicParsing | iex

# 本地安装
.\scripts\install.ps1

# Docker 模式
.\scripts\install.ps1 -Docker
```

### Docker

```bash
curl -fsSL https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install.sh | bash -s -- --docker
# 或克隆后
./scripts/install.sh --docker
```

---

## 注意事项

- **Python 版本**：本地安装需要 Python 3.11+
- **虚拟环境**：如果系统 Python 受保护（externally-managed-environment），脚本会自动创建虚拟环境 `~/.ai-companion/.venv`
- **数据目录**：所有数据存储在 `~/.ai-companion/`
- **API Key**：安装后需要配置 API Key，参考[配置说明](#配置说明)

---

## 常见问题

**Q: 提示 "API Key 未设置"**
A: `export MINIMAX_API_KEY="your_key"`

**Q: Bot 不主动发消息**
A: 检查 `data/bots/{bot_id}/persona/proactive.json` 中 `enabled` 和 `mode`

**Q: 向量嵌入不生效**
A: 确认 `models.yaml` 中 `memory.embedding: "local"`（sentence-transformers 已默认安装）

**Q: 如何重置记忆？**
A: `rm -rf ~/.ai-companion/data/bots/{bot_id}/memory/*.db`

---

## 详细文档

| 文档 | 说明 |
|------|------|
| [使用指南](./docs/GUIDE.md) | 详细的配置说明和功能介绍 |
| [主动唤醒设计](./docs/DESIGN_phase5_proactive.md) | 主动唤醒架构和算法设计 |
| [主动唤醒实现](./docs/IMPLEMENTATION_phase5_proactive.md) | 主动唤醒实现细节 |

---

## License

MIT
