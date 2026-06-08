# AI Companion / AI 知己

开源 AI 陪伴产品，支持 macOS / Linux / Windows。每个 Bot 都有独立人格、长期记忆、关系状态、人生轨迹和可解释的人格演化链路。

## 核心特性

| 特性 | 说明 |
|------|------|
| 多模型支持 | MiniMax / OpenAI / Claude / MiMo / DeepSeek / TeleClaw / Ollama / 自定义兼容接口 |
| 独立人格 | 每个 Bot 拥有独立的 `profile`、`backstory`、`values`、`speaking_style` 和 `conversation_style_rules` |
| 分层记忆系统 | Working / Daily / Episodic / Semantic / Relationship / User Understanding / Conscious Context |
| 长期理解投影 | 将结构化事实、关系状态和近期连续性整理成用户可读、可编辑的长期理解层 |
| Dreaming / 记忆整理 | 对候选记忆做整理、提升、报告和诊断，支持手动运行和后台自动触发 |
| 人格演化 | 日常对话、共同经历、关系转折和人生事件会形成 `signal -> reflection -> promotion -> core patch` 的演化链路 |
| 人生轨迹 | 每个 Bot 有独立时间线，会生成日常事件、人生大事、生日和低概率意外 |
| 主动唤醒 | 支持 idle reminder、deferred reply、topic continuation、emotion followup、life event motive 等主动动机 |
| 多媒体能力 | 内置 `image_generation`、`image_understanding`、`tts` |
| 管理后台 | 提供 Dashboard、Memory、Understanding、StyleLab、Operations、Evolution、Debug、Settings 等页面 |
| 调试可解释性 | 可查看 prompt budget、记忆召回、response style trace、演化时间线和状态诊断 |

---

## 快速开始

### 环境要求

- Python 3.11+
- Git
- 推荐安装 Node.js + npm（用于管理后台 UI）
- 至少一个模型提供方的可用配置

### 安装依赖

```bash
pip install -r requirements.txt
pip install -e .
```

### 首次配置

```bash
ai-companion setup
```

首次配置会引导你：

- 配置默认模型
- 创建或更新 Bot
- 可选配置飞书与微信通道

### 启动本地 CLI

```bash
ai-companion start
ai-companion start --bot <bot_id>
```

### 启动网关

```bash
ai-companion gateway start
ai-companion gateway start --sync
ai-companion gateway status
ai-companion gateway logs
```

默认情况下，CLI 或 Gateway 启动时会同时拉起：

- Admin API: `http://127.0.0.1:8642`
- Web UI: `http://127.0.0.1:14210`

如需关闭自动启动 UI，可设置：

```bash
START_UI=false
# 或
AI_COMPANION_START_UI=false
```

---

## 常用命令

### CLI / 运行

```bash
ai-companion start
ai-companion start --bot <bot_id>
ai-companion status
ai-companion update
ai-companion update --cn
ai-companion update --skip-ui
```

### Gateway

```bash
ai-companion gateway
ai-companion gateway start
ai-companion gateway start --sync
ai-companion gateway stop
ai-companion gateway restart
ai-companion gateway replace
ai-companion gateway status
ai-companion gateway logs -n 100
```

### Bot / Persona / Model / Skill

```bash
ai-companion bot list
ai-companion bot add --name <name>
ai-companion bot remove --name <name>

ai-companion persona --help

ai-companion skill list
ai-companion skill list --json
ai-companion skill run image_generation "一张傍晚街景"
ai-companion skill run tts "今天辛苦了"

ai-companion model test
```

### Memory 维护

```bash
ai-companion memory rebuild-vector
ai-companion memory rebuild-vector --bot <bot_id>
```

### 数据迁移

在旧机器上打包完整运行时数据：

```bash
ai-companion migrate export -o ai-companion-migration.zip
```

在新机器完成安装后恢复：

```bash
ai-companion migrate import ai-companion-migration.zip
```

迁移包默认包含 `~/.ai-companion/config/`、`~/.ai-companion/data/`、`.env` 以及平台配对状态文件；默认排除日志、PID、锁文件、源码缓存和旧迁移备份。恢复时如果目标机器已有同名文件，会先自动备份到 `~/.ai-companion/migration-backups/` 再覆盖。迁移包可能包含 API key、聊天记忆和平台凭据，请按私密备份保存。

### 微信配置

```bash
ai-companion weixin
ai-companion weixin setup
ai-companion weixin setup --no-env
```

---

## 对话内命令

在本地 CLI 对话中可直接使用：

| 命令 | 说明 |
|------|------|
| `/new` | 开启新会话 |
| `/memory` | 查看当前记忆状态、关系状态、理解文件和向量索引 |
| `/forget <key>` | 删除一条自动语义事实 |
| `/dream` | 查看 Dreaming 状态 |
| `/dream on` / `/dream off` | 开关记忆整理 |
| `/dream run` | 手动运行一次记忆整理 |
| `/dream doctor` | 查看 Dreaming 诊断 |
| `/dream report` | 查看最近整理报告 |
| `/dream delete` | 删除最近一次整理新增项 |
| `/skills` | 查看当前 Bot 的运行时内置能力状态 |
| `/skill <name> ...` | 显式调用内置能力 |
| `switch` | 切换 Bot |
| `quit` / `exit` / `退出` | 退出 CLI |

---

## 管理后台页面

当前 `ai-companion-ui/` 已包含这些一级页面：

| 路由 | 页面 | 用途 |
|------|------|------|
| `/` | 监控面板 | 查看核心指标和 Bot 总览 |
| `/session` | 会话管理 | 查看会话列表与对话详情 |
| `/logs` | 日志查看 | 实时查看 Gateway / 系统日志 |
| `/memory` | 记忆系统 | 查看 Working / Daily / Episodic / Semantic / Relationship / Trust View / Dreaming |
| `/understanding` | 长期理解投影 | 编辑 `manual` 理解，查看 `auto`、relationship projection 和 layered projection |
| `/style` | 风格调教 | 编辑 `conversation_style_rules.json`，降低 AI 味 |
| `/operations` | 运营台 | 查看主动唤醒配置、人生轨迹状态和 life snapshot |
| `/evolution` | 人格演化 | 查看 signal、reflection、promotion、core patch 的完整演化过程 |
| `/debug` | 调试工具 | 查看 system prompt、retrieved memory、prompt budget、response style trace |
| `/settings` | 设置 | 可视化编辑模型、技能、记忆、Dreaming、Evolution、主动唤醒、人生轨迹、平台与人格配置 |

---

## 人格演化与记忆整理

### 人格演化

系统现在提供正式的人格演化层，而不是只靠运行时临时改写：

- 记录 `signal`
- 定期或即时 `reflection`
- 生成 `pending promotion`
- 满足阈值后写入核心 persona
- 保留抑制原因、证据引用、before/after diff

演化相关后台接口位于：

- `GET /api/v1/admin/evolution/:bot_id/summary`
- `GET /api/v1/admin/evolution/:bot_id/timeline`
- `GET /api/v1/admin/evolution/:bot_id/events/:event_id`
- `GET /api/v1/admin/evolution/:bot_id/state`
- `GET /api/v1/admin/evolution/:bot_id/config`
- `POST /api/v1/admin/evolution/:bot_id/reflect`
- `POST /api/v1/admin/evolution/:bot_id/rebuild`
- `POST /api/v1/admin/evolution/:bot_id/promotion/:candidate_id/apply`
- `POST /api/v1/admin/evolution/:bot_id/promotion/:candidate_id/reject`

### Dreaming / 记忆整理

Dreaming 负责把近期对话中的候选内容整理成更稳定的长期层，并输出人类可读报告。后台接口包括：

- `GET /api/v1/admin/memory/:bot_id/dreaming/status`
- `POST /api/v1/admin/memory/:bot_id/dreaming/run`
- `GET /api/v1/admin/memory/:bot_id/dreaming/report`
- `POST /api/v1/admin/memory/:bot_id/dreaming/doctor`
- `DELETE /api/v1/admin/memory/:bot_id/dreaming/latest`

---

## 人格与数据文件

每个 Bot 的 persona 位于：

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

运行时数据通常位于：

```text
~/.ai-companion/data/bots/{bot_id}/memory/
```

常见文件包括：

- `working.db`
- `episodic.db`
- `semantic.db`
- `relationship.db`
- `daily.db`
- `user_understanding.json`
- `vector/`
- `evolution_state.json`
- `evolution_audit.jsonl`

---

## 模型支持

当前 `ModelFactory` 内置支持：

- `minimax`
- `openai`
- `claude`
- `mimo`
- `deepseek`
- `tele`
- `ollama`
- `custom`

其中 `tele` 对应 TeleClaw 风格适配，`custom` 用于自定义兼容接口。

---

## 测试与健康检查

```bash
python tests/system_test_suite.py
python -m compileall -q ai_companion
```

---

## 相关文档

- [使用指南](./docs/GUIDE.md)
- [Bot 设计指引](./docs/BOT_DESIGN_GUIDE.md)
- [Bot JSON 字段说明](./docs/BOT_JSON_FIELDS.md)
- [主动唤醒设计](./docs/DESIGN_phase5_proactive.md)
- [UI 设计方案](./docs/ui/UI_DESIGN.md)
- [UI 产品规格](./docs/ui/UI_SPEC.md)

---

## 许可证

本项目使用 [BSL 1.1](./LICENSE)。
