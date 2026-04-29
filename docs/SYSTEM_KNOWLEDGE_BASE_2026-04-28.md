# AI Companion 系统认知沉淀（2026-04-28）

## 1. 文档目的

- 固化当前对系统结构、关键路径、配置优先级、主要风险的理解
- 作为后续测试与修复的共同基线，避免上下文丢失
- 时间基准：2026-04-28（北京时间）

---

## 2. 系统边界与组成

### 2.1 后端核心目录（`ai_companion/`）

- `main.py`：CLI 启动主入口（本地交互模式）
- `bot/instance.py`：单 Bot 运行时（人格、记忆、主动唤醒、人生轨迹、技能）
- `bot/manager.py`：多 Bot 管理
- `config/loader.py`：配置加载与解析
- `model/`：模型适配层（`factory.py` + adapters）
- `memory/`：三层记忆引擎（working / episodic / semantic）
- `persona/`：人格加载与系统提示词构建，拒绝策略
- `proactive/`：主动唤醒 + 人生轨迹（scheduler/engine/state/config）
- `gateway/cmd.py`：Gateway 进程管理 + 管理 API（端口 8642）+ 共享 UI 子进程
- `ui_server.py`：CLI/Gateway 共用的 UI 启动去重逻辑（端口 1421）
- `skill/`：技能分发与注册

### 2.2 前端目录（`ai-companion-ui/`）

- 基于 Vite + TypeScript
- `src/pages`：Dashboard / Memory / Logs / Settings 等页面
- `src/api/index.ts`：调用 `http://localhost:8642/api/v1` 的 API 封装

### 2.3 数据与配置

- 项目内默认数据：`data/bots/...`
- 用户目录优先数据：`~/.ai-companion/data/bots/...`
- 配置目录（按文档设计）：`~/.ai-companion/` 下 `config.yaml/models.yaml/bots.yaml` 等

---

## 3. 关键运行链路

### 3.1 CLI 链路

1. `python -m ai_companion` 进入 `main.py`
2. 加载配置（模型 + bot 列表）
3. 初始化模型适配器
4. 创建并初始化每个 `BotInstance`
5. 启动 `CLIAdapter` 处理会话交互

### 3.2 Gateway 链路

1. `python -m ai_companion gateway start`
2. 启动 Gateway 进程，记录 PID
3. 初始化模型与 BotManager
4. 启动管理 API（8642）
5. CLI/Gateway 默认启动或复用前端 dev server（`START_UI=false` 可关闭）
6. 可选接入飞书消息路由

### 3.3 BotInstance 内部依赖顺序

1. PersonaLoader -> PersonaEngine
2. RefusalEngine
3. MemoryEngine（可选，依赖配置）
4. ProactiveConfig/State/Engine/Scheduler
5. LifeConfig/State/Engine/Scheduler
6. SkillDispatcher + 已安装技能

---

## 4. 关键设计约束（当前版本）

1. 外部模型调用依赖 API key（至少 MiniMax/OpenAI/Claude/Ollama/custom 之一）。
2. 记忆系统依赖 SQLite，部分功能依赖本地 embedding 配置。
3. Gateway 管理 API 与前端页面耦合较强，接口字段不一致会直接影响 UI 功能。
4. 人生轨迹与主动唤醒是并行调度系统，状态一致性对行为影响大。

---

## 5. 历史风险与当前状态

以下风险均在 2026-04-28 基线测试中暴露，已在同日修复并通过全量回归（详细见 `SYSTEM_TEST_BUG_REPORT_2026-04-28.md`）：

1. 前端构建阻断（TypeScript 报错）-> 已修复，`T15=PASS`。
2. 主动消息重复发送 -> 已修复，`T10=PASS`。
3. `mode=silent` 语义失效 -> 已修复，`T09=PASS`。
4. LifeEngine PersonaLoader 注入链断点 -> 已修复，`T08=PASS`。
5. Main/Gateway 绕过 ModelFactory -> 已修复，`T11=PASS`。
6. UI provider 枚举与后端不一致 -> 已修复，`T13=PASS`。
7. UI 清空全部记忆为 no-op -> 已修复，`T14=PASS`。

当前系统级主流程状态：PASS 17 / FAIL 0 / ERROR 0。

---

## 6. 新测试体系设计原则（从本次起）

1. 不复用旧测试脚本逻辑，脚本从零重建。
2. 每个检查项必须返回结构化 PASS/FAIL，不允许“只打印不计入结果”。
3. 覆盖分层：
   - 启动与进程：CLI/Gateway 生命周期
   - 核心能力：配置、人格、记忆、主动唤醒、人生轨迹
   - 接口一致性：管理 API 与前端契约
   - 可交付性：前端 build
4. 输出物标准化：
   - 统一日志目录（`.artifacts/<date>/`）
   - 统一机器可读摘要（JSON）
   - 人可读报告（Markdown）

---

## 7. 后续执行准则（持续）

1. 先验证（测试）再修复，修复后必须回归同一套脚本。
2. 任何“跳过”项都要明确原因（缺钥匙/环境能力缺失/外部依赖不可用）。
3. 优先级顺序：
   - P0：安全与构建阻断
   - P1：核心链路逻辑正确性
   - P2：一致性和体验问题

---

## 8. 关联文档

- `docs/SYSTEM_TEST_BUG_REPORT_2026-04-28.md`
- `README.md`
- `ARCHITECTURE.md`
