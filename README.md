# AI Companion / AI 知己

开源 AI 陪伴产品，支持 macOS / Windows 双平台。每个机器人有独立人格和记忆体系，能像真人一样与你互动。

## 功能特性

- **独立人格**：每个 Bot 有独特的性格、背景故事和说话风格
- **三层记忆**：工作记忆（当前会话）+ 情景记忆（重要经历）+ 语义记忆（用户画像）
- **主动唤醒**：会主动找你聊天、提醒你事情、偶尔撒撒娇
- **性格进化**：根据你们的互动，关系会逐渐加深
- **性格推断拒绝**：基于性格判断该不该回答，不是简单的关键词过滤
- **多媒体技能**：支持图片生成、语音合成
- **飞书集成**：连接飞书机器人，通过微信/飞书与 AI 对话
- **多模型支持**：MiniMax / OpenAI / Claude / Ollama

## 安装

### 方式一：本地安装（推荐）

**macOS / Linux：**
```bash
curl -fsSL https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install.sh | bash
```

或手动安装：
```bash
git clone git@gitee.com:wang_xiao_wei_7143/ai-girl-friend.git
cd ai-girl-friend
pip install -r requirements.txt
```

**Windows：**
```powershell
irm https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install.ps1 | iex
```

### 方式二：Docker 安装

```bash
# macOS / Linux
curl -fsSL https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install.sh | bash -s -- --docker

# Windows (管理员权限 PowerShell)
irm https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install.ps1 | iex -Docker
```

## 配置

### 首次配置

运行配置向导：
```bash
python -m ai_companion setup
```

按提示设置：
1. API Key（从 MiniMax/OpenAI 等平台获取）
2. 选择人格模板
3. 飞书机器人配置（可选）

### 手动配置

配置文件位于 `~/.ai-companion/config/`：

**models.yaml** - 模型配置：
```yaml
minimax:
  api_key: "${MINIMAX_API_KEY}"  # 或直接填写你的 API Key
  base_url: "https://api.minimax.chat/v1"
  model: "MiniMax-M2.7"
```

**bots.yaml** - Bot 列表：
```yaml
bots:
  - id: suqing
    name: 苏晴
    enabled: true
  - id: aiyue
    name: 阿月
    enabled: true
```

### 环境变量配置

也可以通过环境变量配置敏感信息：
```bash
export MINIMAX_API_KEY="your_api_key"
export FEISHU_APP_ID="your_feishu_app_id"
export FEISHU_APP_SECRET="your_feishu_app_secret"
```

## 启动

### 本地对话
```bash
python -m ai_companion start              # 启动（选择默认 Bot）
python -m ai_companion start --bot suqing  # 指定 Bot
```

### 飞书网关服务
```bash
python -m ai_companion gateway start        # 后台启动
python -m ai_companion gateway start --sync  # 前台启动（显示日志）
python -m ai_companion gateway stop         # 停止
python -m ai_companion gateway logs         # 查看日志
python -m ai_companion gateway status        # 查看状态
```

## 内置命令

在对话界面可以使用以下命令：
- `/new` - 开始新会话
- `/memory` - 查看记忆状态
- `/forget <key>` - 删除某条记忆
- `quit` - 退出

## 飞书机器人配置详解

### 环境变量方式

```bash
export FEISHU_APP_ID="cli_xxxxx"
export FEISHU_APP_SECRET="xxxxx"
export FEISHU_CONNECTION_MODE="websocket"  # websocket 或 webhook
```

### config.yaml 方式

```yaml
platforms:
  feishu:
    enabled: true
    extra:
      app_id: "cli_xxxxx"
      app_secret: "xxxxx"
      connection_mode: "websocket"
    routing:
      mode: "dedicated"  # dedicated（专用）或 chat_routed（群聊路由）
      bot_id: "suqing"
```

### 路由模式

**dedicated 模式**（一对一）：
```yaml
routing:
  mode: dedicated
  bot_id: suqing  # 所有消息发给苏晴
```

**chat_routed 模式**（群聊）：
```yaml
routing:
  mode: chat_routed
  default_bot: suqing  # 默认 Bot
  group_bot_map:
    "oc群ID1": aiyue    # 群1 给阿月
    "oc群ID2": suqing    # 群2 给苏晴
```

### 群组策略

```yaml
extra:
  group_policy: "open"  # open/allowlist/blacklist/admin_only/disabled
  allowed_users:
    - "user_open_id_1"
    - "user_open_id_2"
```

## 内置人格

| ID | 名称 | 性格 | 简介 |
|----|------|------|------|
| suqing | 苏晴 | 傲娇 | 26岁自由插画师，嘴硬心软 |
| aiyue | 阿月 | 活泼 | 22岁音乐学院学生，有点粘人 |

## 自定义人格

在 `data/bots/_template/persona/` 有模板，复制并修改可创建新人格：

```
data/bots/mybot/persona/
├── profile.json        # 基础档案（名字、年龄、职业等）
├── backstory.json      # 人生经历
├── values.json         # 价值观和底线
├── speaking_style.json # 说话风格
└── emotional_rules.json # 情绪规则
```

## Skill 扩展

AI Companion 支持安装额外技能：

```bash
python -m ai_companion skill list           # 查看已安装技能
python -m ai_companion skill install ./my-skill  # 从本地安装
python -m ai_companion skill install https://xxx # 从 URL 安装
python -m ai_companion skill uninstall my-skill  # 卸载
```

技能包格式：
```
skill-my-skill/
├── skill.json   # 元数据
└── my_skill.py  # 入口
```

## 数据目录

所有数据默认保存在 `~/.ai-companion/`：

```
~/.ai-companion/
├── config/           # 配置文件
├── data/bots/       # Bot 数据（人格、记忆）
├── logs/            # 日志
└── gateway.pid      # 网关进程 ID
```

## 常见问题

**Q: 提示 "API Key 未设置"**
A: 设置环境变量 `export MINIMAX_API_KEY="your_key"`，或编辑 `~/.ai-companion/config/models.yaml`

**Q: 飞书连接失败**
A: 检查 `FEISHU_APP_ID` 和 `FEISHU_APP_SECRET` 是否正确，确保机器人已启用

**Q: 如何切换 Bot？**
A: 在 CLI 中输入 `switch`，或启动时指定 `--bot bot_id`

**Q: 如何重置记忆？**
A: 删除 `~/.ai-companion/data/bots/{bot_id}/memory/` 下的 .db 文件

## License

MIT
