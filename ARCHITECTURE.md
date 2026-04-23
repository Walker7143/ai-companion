# AI Companion / AI 知己 — 系统设计文档

## 产品定位

**开源 AI 陪伴产品。** 支持 macOS / Windows 双平台，一键安装启动。每个机器人有独立人格和记忆体系。

---

## 一、跨平台支持策略

### 平台差异处理

| 层面 | macOS | Windows | 解决方案 |
|------|-------|---------|---------|
| 路径 | `/Users/xxx` | `C:\Users\xxx` | 全部使用 `pathlib.Path` |
| 换行 | `\n` | `\r\n` | Python `os.linesep` 或始终用 `\n` |
| 环境变量 | `$VAR` | `%VAR%` | `os.environ.get()` |
| Shell | bash/zsh | cmd/PowerShell | 用 Python 脚本封装，不直接调用 shell |
| 服务管理 | launchd | NSSM/计划任务 | 提供双平台服务脚本 |
| 用户目录 | `~/.ai-companion` | `%USERPROFILE%\.ai-companion` | `Path.home() / ".ai-companion"` |

**核心原则：所有路径操作使用 `pathlib`，所有环境变量用 `os.environ.get()`，不硬编码路径分隔符。**

---

## 二、安装与启动设计

### 2.1 一键安装命令

**macOS / Linux：**

```bash
curl -fsSL https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/install.sh | bash
```

**Windows（PowerShell）：**

```powershell
irm https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/install.ps1 | iex
```

### 2.2 安装脚本功能

安装脚本自动完成：

```
install.sh / install.ps1
    │
    ├── 1. 检测 Python 3.11+
    │       └── 不存在 → 提示安装 Python
    │
    ├── 2. 检测 pip
    │       └── 不存在 → 自动安装 pip
    │
    ├── 3. 创建虚拟环境（可选）
    │       └── macOS: ~/ai-companion/venv
    │       └── Windows: %USERPROFILE%\ai-companion\venv
    │
    ├── 4. 安装依赖
    │       └── pip install -r requirements.txt
    │
    ├── 5. 创建数据目录
    │       └── ~/.ai-companion/data/
    │
    ├── 6. 复制配置文件
    │       └── config/bots.yaml
    │       └── config/models.yaml（从模板）
    │
    ├── 7. 设置权限（macOS/Linux）
    │
    └── 8. 启动配置向导
            └── python -m ai_companion setup
```

### 2.3 配置向导

运行 `python -m ai_companion setup` 启动交互式配置：

```
╔══════════════════════════════════════════════╗
║        AI Companion 配置向导                  ║
╚══════════════════════════════════════════════╝

[1/4] 模型配置
  请选择模型来源:
    1. MiniMax（默认）
    2. OpenAI
    3. Claude
    4. 本地模型（Ollama）
    5. 自定义 API

  > 选择: 1
  请输入 API Key: ████████████
  ✓ API Key 已保存

[2/4] 创建第一个 Bot
  请选择人格模板:
    1. 苏晴（傲娇插画师）
    2. 阿月（活泼音乐生）
    3. 导入自定义人格
    4. 稍后创建

  > 选择: 1
  ✓ 苏晴 已创建

[3/4] 飞书配置（可选）
  是否配置飞书机器人? (y/N): y
  请输入 App ID: cli_xxxxx
  请输入 App Secret: ████████████
  请输入 Bot 名称: 苏晴
  ✓ 飞书配置已保存

[4/4] 完成
  ✓ 配置完成！

  启动命令: python -m ai_companion start
  配置目录: ~/.ai-companion/
```

### 2.4 启动命令

**通用启动：**

```bash
# 默认启动（加载所有已配置的 Bot）
python -m ai_companion start

# 指定启动某个 Bot
python -m ai_companion start --bot suqing

# 查看帮助
python -m ai_companion --help
```

**平台特定快捷方式：**

```
macOS:
  ./ai-companion start          # 可双击运行
  open ~/.ai-companion/         # 打开配置目录

Windows:
  ai-companion.exe start        # 双击运行
  explorer %USERPROFILE%\.ai-companion\  # 打开配置目录
```

### 2.5 常用命令

```bash
# 配置向导（重新配置）
python -m ai_companion setup

# 查看状态
python -m ai_companion status

# 管理 Bot
python -m ai_companion bot list      # 列出所有 Bot
python -m ai_companion bot add       # 添加新 Bot
python -m ai_companion bot remove    # 删除 Bot
python -m ai_companion bot configure # 配置已有 Bot

# 模型管理
python -m ai_companion model test    # 测试模型连接
python -m ai_companion model switch  # 切换模型

# 更新
python -m ai_companion update

# 卸载
python -m ai_companion uninstall
```

### 2.6 配置文件位置

```
~/.ai-companion/
├── config.yaml              # 主配置（API Key 等）
├── bots.yaml               # Bot 列表
├── models.yaml             # 模型配置
├── feishu.yaml             # 飞书配置
├── data/
│   └── bots/
│       └── suqing/         # 各 Bot 数据
│           └── persona/    # 人格文件
└── logs/                   # 日志
```

---

## 三、项目结构

```
ai-companion/              # 项目根目录
├── ai_companion/          # 主包（pip install -e . 安装）
│   ├── __init__.py
│   ├── __main__.py         # 入口：python -m ai_companion
│   ├── main.py             # 启动逻辑
│   ├── setup.py            # 配置向导（TODO）
│   ├── config/
│   │   └── loader.py       # 配置加载
│   ├── model/
│   │   └── minimax_adapter.py  # MiniMax 模型适配器
│   ├── persona/
│   │   ├── loader.py       # 人格文件加载
│   │   └── engine.py        # System Prompt 构建
│   ├── bot/
│   │   ├── instance.py      # Bot 实例（含记忆引擎集成）
│   │   ├── manager.py       # Bot 管理器
│   │   └── cli.py           # CLI 入口
│   ├── memory/
│   │   ├── engine.py        # 三层记忆引擎
│   │   └── stores/
│   │       ├── working.py   # 工作记忆（SQLite）
│   │       ├── episodic.py   # 情景记忆（SQLite + jieba 分词）
│   │       └── semantic.py   # 语义记忆（SQLite）
│   ├── engine/              # 核心引擎（预留）
│   ├── skill/               # Skill 调度（预留）
│   ├── cli/
│   │   └── adapter.py       # CLI 交互适配器（/new /memory /forget）
│   └── platform/            # 平台适配（预留：飞书/微信）
├── config/
│   ├── bots.yaml            # Bot 列表配置
│   ├── models.yaml          # 模型配置
│   └── models.yaml.example  # 模型配置示例
├── data/bots/               # 人格和数据（per bot）
│   ├── suqing/
│   │   └── persona/         # 傲娇插画师人格文件
│   └── aiyue/
│       └── persona/         # 活泼音乐生人格文件
├── scripts/
│   ├── install.sh           # macOS/Linux 安装脚本
│   ├── install.ps1          # Windows 安装脚本
│   └── setup-embeddings.sh  # sentence-transformers 安装（可选）
├── tests/                   # 测试（TODO）
├── requirements.txt
├── setup.py
└── README.md

---

## 四、模块层级（不变）

```
┌─────────────────────────────────────────┐
│  Platform Adapter（飞书/微信/CLI）        │
│  - 消息格式统一化                         │
│  - 事件：message / callback_query / etc  │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│  Skill / MCP Dispatcher                  │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│  Model Adapter（统一接口）                │
│  - 支持 MiniMax / OpenAI / Claude / Ollama│
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│           Agent Engine                   │
│  Persona / Memory / Refusal / Proactive  │
│  / Evolution                             │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│  Storage Layer                           │
│  SQLite + Chroma                         │
└─────────────────────────────────────────┘
```

---

## 五、核心模块说明

### 5.1 Persona Engine

人格文件体系（per bot）：

```
data/bots/{bot_id}/persona/
├── profile.json           # 基础档案
├── backstory.json         # 人生经历
├── values.json            # 价值观 + 底线
├── speaking_style.json    # 说话风格
└── emotional_rules.json  # 情绪规则
```

### 5.2 Memory Engine

三层记忆（已实现）：

```
L1: Working Memory  — SQLite，当前会话原始消息 + 摘要压缩
L2: Episodic Memory — SQLite + jieba 分词，中文关键词精确召回
L3: Semantic Memory — SQLite，结构化用户事实画像
```

**关键设计：**
- 上下文超限自动压缩（硬上限同步压缩，软上限后台异步压缩）
- `embedding: "none"` 时降级为 SQLite 关键词匹配（无需额外依赖）
- `embedding: "local"` 时启用 sentence-transformers 向量召回（可选）

### 5.3 Model Adapter

支持多种模型，统一接口：

```python
class ModelAdapter(ABC):
    async def chat(messages, system_prompt, tools=None) -> str
    async def embeddings(texts) -> list[vector]
    async def vision(image_url, prompt) -> str
```

### 5.4 Proactive Scheduler

主动消息触发：

```python
TRIGGER_TYPES = {
    "time_based",    # 定时（早安/晚安）
    "context_based",  # 上下文（未回复/重要日期）
    "random",         # 随机戳戳
}
```

### 5.5 Refusal Engine

性格推断拒绝，不是词表过滤：

```python
should_refuse(request, personality, memory, relationship)
→ RefusalResponse(refuse=False, adjustment="...", reply="...")
```

### 5.6 Evolution Engine

渐进式性格更新，Evolution Guard 保护核心价值观不被污染。

---

## 六、跨平台技术栈

| 层次 | 技术 | 跨平台 |
|------|------|--------|
| 语言 | Python 3.11+ | ✓ |
| 异步 | asyncio | ✓ |
| HTTP | aiohttp / httpx | ✓ |
| 数据库 | SQLite + Chroma | ✓ |
| 路径 | pathlib | ✓ |
| 安装脚本 | bash + PowerShell | 双平台 |
| 容器 | Docker + docker-compose | ✓ |
| 飞书 SDK | feishu-sdk | ✓ |

---

## 七、开发和部署

### 开发环境

```bash
git clone git@gitee.com:wang_xiao_wei_7143/ai-girl-friend.git
cd ai-girl-friend
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows
pip install -r requirements.txt
cp config/models.yaml.example config/models.yaml
# 编辑 config/models.yaml 填入 API Key
python -m ai_companion start
```

### Docker 部署

```bash
docker-compose up
```

### Windows 一键安装

```powershell
# 下载并运行安装脚本
irm https://gitee.com/xxx/install.ps1 | iex
```

---

## 八、设计原则

1. **零配置启动：** 安装后无需手动编辑任何文件，`setup` 向导覆盖所有必要配置
2. **路径无关：** 所有路径使用 `pathlib`，用户数据放在 `~/.ai-companion/`
3. **逐步引导：** 每个步骤都有清晰的验证和反馈
4. **容错设计：** 缺少配置时给出友好提示，不直接崩溃
5. **跨平台优先：** 所有代码在写之前先确认跨平台兼容性
