# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt

# 本地开发安装
pip install -e .

# 运行测试（181个测试用例）
python tests/test_comprehensive.py

# 真实使用场景测试（10项核心功能验证）
python tests/test_real_usage.py

# CLI 启动
ai-companion start
ai-companion start --bot suqing  # 指定Bot

# 配置向导
ai-companion setup

# 飞书网关
ai-companion gateway start
ai-companion gateway stop
ai-companion gateway logs

# 内置命令（在对话界面）
/new          # 开始新会话
/memory       # 查看记忆状态
/forget <key> # 删除某条记忆
quit          # 退出
```

## 项目架构

### 核心模块层级

```
Platform Adapter（飞书/CLI/Webhook）
         ↓
Skill / MCP Dispatcher
         ↓
Model Adapter（统一接口，支持 MiniMax/OpenAI/Claude/Ollama/自定义）
         ↓
Agent Engine（Persona/Memory/Refusal/Proactive/Evolution）
         ↓
Storage Layer（SQLite + Chroma 向量）
```

### 关键目录

| 目录 | 说明 |
|------|------|
| `ai_companion/bot/` | Bot 核心实例（BotInstance, BotManager） |
| `ai_companion/memory/` | 三层记忆引擎（Working/Episodic/Semantic） |
| `ai_companion/persona/` | 人格系统（Loader, Engine, RefusalEngine） |
| `ai_companion/proactive/` | 主动唤醒系统（Engine, Scheduler, LifeEngine） |
| `ai_companion/model/` | 模型适配器工厂（支持多模型热插拔） |
| `ai_companion/gateway/` | 消息网关（Session, Delivery, Platform） |
| `ai_companion/skill/` | 技能系统（Dispatcher, Registry） |
| `ai_companion/context/` | 上下文管理（Compressor, TokenEstimator） |
| `data/bots/` | 各 Bot 的 persona 配置和运行时数据 |

### 三层记忆系统

1. **Working Memory** - SQLite + jieba 分词，当前会话原始消息
2. **Episodic Memory** - SQLite + Chroma 向量，情景片段语义召回
3. **Semantic Memory** - SQLite，关键事实（用户画像）提取

向量嵌入默认关闭（`embedding: "none"`），启用需安装 sentence-transformers。

### 人格配置

每个 Bot 的 persona 位于 `data/bots/{bot_id}/persona/`：
- `profile.json` - 基础档案
- `backstory.json` - 人生经历
- `values.json` - 价值观和底线
- `speaking_style.json` - 说话风格
- `proactive.json` - 主动唤醒配置
- `life.json` - Bot 人生轨迹配置

### 运行时数据

运行时数据（数据库、缓存）位于 `data/bots/{bot_id}/memory/` 和 `data/suqing/memory/`，通常不需要提交到 git。

## 设计原则

- **路径无关**：所有路径使用 `pathlib.Path`，数据存储在 `~/.ai-companion/`
- **零配置启动**：安装后 `ai-companion setup` 向导覆盖所有必要配置
- **跨平台优先**：使用 Python 3.11+，所有代码兼容 macOS/Linux/Windows
- **性格推断拒绝**：基于人格判断该不该回答，不是简单的关键词过滤

## 配置位置

用户配置和数据存储在 `~/.ai-companion/`：
- `config/models.yaml` - 模型配置
- `config/bots.yaml` - Bot 列表
- `config/config.yaml` - 主配置
- `data/bots/{bot_id}/` - 各 Bot 的人格和记忆

## 管理后台 UI

管理后台项目位于 `ai-companion-ui/`，技术栈：

| 层 | 技术 |
|----|------|
| 桌面框架 | Tauri 2.x |
| 前端框架 | React 18 + TypeScript |
| 构建工具 | Vite 5 |
| 样式 | TailwindCSS 3 |
| 状态管理 | Zustand 4 |
| 图表 | Recharts 2 |

详细文档：
- `docs/ui/UI_DESIGN.md` - UI 设计方案（设计规范、页面布局、组件规范）
- `docs/ui/UI_SPEC.md` - 产品规格（功能清单、交互细节、验收标准）
- `docs/ui/UI_TECH_DESIGN.md` - 技术设计方案（架构、API、目录结构）

开发命令（TODO，待初始化）：
```bash
cd ai-companion-ui
npm install
npm run tauri dev
```
