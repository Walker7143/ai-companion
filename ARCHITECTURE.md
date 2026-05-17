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
curl -fsSL https://raw.githubusercontent.com/Walker7143/ai-companion/master/install.sh | bash
```

**Windows（PowerShell）：**

```powershell
irm https://raw.githubusercontent.com/Walker7143/ai-companion/master/install.ps1 | iex
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
            └── ai-companion setup
```

### 2.3 配置向导

运行 `ai-companion setup` 启动交互式配置：

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
  请输入 Bot ID (英文唯一标识): lin_wanqing
  请输入 Bot 名称: 林晚晴

  ✓ 林晚晴 已创建

[3/4] 飞书配置（可选）
  是否配置飞书机器人? (y/N): y
  请输入 App ID: cli_xxxxx
  请输入 App Secret: ████████████
  请选择这个飞书 App 绑定的 Bot: 林晚晴
  ✓ 飞书配置已保存

[4/4] 完成
  ✓ 配置完成！

  启动命令: ai-companion start
  配置目录: ~/.ai-companion/
```

### 2.4 启动命令

**通用启动：**

```bash
# 默认启动（加载所有已配置的 Bot）
ai-companion start

# 指定启动某个 Bot
ai-companion start --bot lin_wanqing

# 查看帮助
ai-companion --help
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
ai-companion setup

# 查看状态
ai-companion status

# 管理 Bot
ai-companion bot list      # 列出所有 Bot
ai-companion bot add       # 添加新 Bot
ai-companion bot remove    # 删除 Bot
ai-companion bot configure # 配置已有 Bot

# 模型管理
ai-companion model test    # 测试模型连接
ai-companion model switch  # 切换模型

# 更新
ai-companion update

# 卸载
ai-companion uninstall
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
│       └── lin_wanqing/    # 各 Bot 数据
│           └── persona/    # 人格文件
└── logs/                   # 日志
```

---

## 三、项目结构

```
ai-companion/              # 项目根目录
├── ai_companion/          # 主包（pip install -e . 安装）
│   ├── __init__.py
│   ├── __main__.py         # 入口：ai-companion
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
│   ├── lin_wanqing/
│   │   └── persona/         # 林晚晴人格文件
│   └── ethan_reed/
│       └── persona/         # Ethan Reed 人格文件
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
│  - 支持 MiniMax / OpenAI / Claude / MiMo / Ollama│
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
git clone git@github.com:Walker7143/ai-companion.git
cd ai-companion
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows
pip install -r requirements.txt
cp config/models.yaml.example config/models.yaml
# 编辑 config/models.yaml 填入 API Key
ai-companion start
```

### Docker 部署

```bash
docker-compose up
```

### Windows 一键安装

```powershell
# 下载并运行安装脚本
irm https://raw.githubusercontent.com/Walker7143/ai-companion/master/scripts/install.ps1 | iex
```

---

## 八、飞书集成配置

### 8.1 连接模式

飞书支持两种连接模式：

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `websocket` | WebSocket 长连接（默认） | 生产环境，推荐 |
| `webhook` | HTTP Webhook | 需要公网回调地址 |

### 8.2 环境变量配置

```bash
# 必需
export FEISHU_APP_ID="your_app_id"           # 飞书应用 ID
export FEISHU_APP_SECRET="your_app_secret"   # 飞书应用 Secret

# 可选
export FEISHU_DOMAIN="feishu"                 # feishu 或 lark
export FEISHU_CONNECTION_MODE="websocket"    # websocket 或 webhook
export FEISHU_BOT_OPEN_ID="ou_xxx"           # 机器人 Open ID（用于 @mention 匹配）
export FEISHU_BOT_USER_ID="u_xxx"            # 机器人 User ID（可选）
export FEISHU_BOT_NAME="AICompanion"          # 机器人名称

# Webhook 模式专用
export FEISHU_WEBHOOK_HOST="0.0.0.0"         # 监听地址
export FEISHU_WEBHOOK_PORT="8765"            # 监听端口
export FEISHU_WEBHOOK_PATH="/feishu/webhook" # Webhook 路径

# 安全配置
export FEISHU_ENCRYPT_KEY="your_encrypt_key"  # 事件订阅加密密钥
export FEISHU_VERIFICATION_TOKEN="your_token" # 事件订阅验证 Token

# 群组策略
export FEISHU_GROUP_POLICY="allowlist"        # open/allowlist/blacklist/admin_only/disabled
export FEISHU_ALLOWED_USERS="user1,user2"    # 允许的用户列表（逗号分隔）
```

### 8.3 config.yaml 配置方式

```yaml
platforms:
  feishu:
    enabled: true
    extra:
      app_id: "your_app_id"
      app_secret: "your_app_secret"
      domain: "feishu"
      connection_mode: "websocket"
      encrypt_key: "your_encrypt_key"
      verification_token: "your_verification_token"
      group_policy: "allowlist"
      allowed_users:
        - "user_open_id_1"
        - "user_open_id_2"
      admins:
        - "admin_open_id"
      group_rules:
        "chat_id_1":
          policy: "open"
        "chat_id_2":
          policy: "allowlist"
          allowlist:
            - "allowed_user_id"
```

### 8.4 群组策略说明

| 策略 | 说明 |
|------|------|
| `open` | 完全开放，所有人可用 |
| `allowlist` | 仅白名单用户可用 |
| `blacklist` | 除黑名单外所有人都可用 |
| `admin_only` | 仅管理员可用 |
| `disabled` | 机器人禁用 |

### 8.5 Hermes 适配器特性

迁移自 Hermes 的企业级飞书适配器，提供：

- **消息去重**：24 小时去重窗口，重启后持久化
- **发送方名称缓存**：10 分钟 TTL，减少 API 调用
- **应用锁**：防止多实例使用相同凭证
- **速率限制**：Webhook 模式下滑动窗口限流
- **异常追踪**：连续错误时记录 WARNING 日志
- **Per-chat 串行处理**：保证同一聊天内消息有序
- **打字状态指示**：处理中显示 "Typing"，失败显示 CrossMark
- **表情反应路由**：作为合成文本事件处理
- **卡片按钮事件**：作为 COMMAND 事件路由

### 8.6 消息类型支持

| 类型 | 接收 | 发送 |
|------|------|------|
| 文本 | ✅ | ✅ |
| 富文本 (post) | ✅ | ✅ |
| 图片 | ✅ | ✅ |
| 语音 | ✅ | ✅ |
| 视频/媒体 | ✅ | ✅ |
| 文件 | ✅ | ✅ |
| 卡片消息 | ✅ | ✅ |
| @提及 | ✅ | ✅ |

---

## 九、设计原则

1. **零配置启动：** 安装后无需手动编辑任何文件，`setup` 向导覆盖所有必要配置
2. **路径无关：** 所有路径使用 `pathlib`，用户数据放在 `~/.ai-companion/`
3. **逐步引导：** 每个步骤都有清晰的验证和反馈
4. **容错设计：** 缺少配置时给出友好提示，不直接崩溃
5. **跨平台优先：** 所有代码在写之前先确认跨平台兼容性
