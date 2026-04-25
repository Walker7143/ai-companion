# AI Companion / AI 知己

开源 AI 陪伴产品，支持 macOS / Windows 双平台。每个机器人有独立人格和记忆体系，能像真人一样与你互动。

## 快速开始

### 5分钟启动

```bash
# 1. 克隆项目
git clone git@gitee.com:wang_xiao_wei_7143/ai-girl-friend.git
cd ai-girl-friend

# 2. 安装依赖
pip install -r requirements.txt

# 3. 设置 API Key（只需一个 MiniMax Key）
export MINIMAX_API_KEY="your_api_key_here"

# 4. 启动
python -m ai_companion start
```

> **最低要求**：Python 3.10+ 和一个 MiniMax API Key

### 首次配置向导

```bash
python -m ai_companion setup
```

按提示完成 API Key 配置、人格选择等。

---

## 功能特性

- **独立人格**：每个 Bot 有独特的性格、背景故事和说话风格（傲娇/活泼/温柔/高冷...）
- **三层记忆**：工作记忆 + 情景记忆 + 语义记忆，像真人一样记住你们的故事
- **主动唤醒**：会主动找你聊天、提醒事情、偶尔撒娇，基于 LLM 推理判断时机
- **关系进化**：根据互动深度，Bot 行为会逐渐变化（陌生网友 → 恋人）
- **性格推断拒绝**：基于性格判断该不该回答，不是简单的关键词过滤
- **多维情绪**：想念程度、不安感、兴奋度、偶尔生气，情绪更真实
- **多媒体技能**：支持图片生成、语音合成
- **飞书集成**：连接飞书机器人，通过飞书与 AI 对话
- **多模型支持**：MiniMax / OpenAI / Claude / Ollama

---

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

---

## 配置

### 配置文件位置

```
~/.ai-companion/config/
├── models.yaml      # AI 模型配置
├── bots.yaml         # Bot 列表
└── config.yaml       # 主配置
```

### models.yaml - 模型配置

```yaml
minimax:
  api_key: "${MINIMAX_API_KEY}"  # 或直接填写 API Key
  base_url: "https://api.minimax.chat/v1"
  model: "MiniMax-Text-01"
```

### 环境变量配置

```bash
export MINIMAX_API_KEY="your_api_key"
export FEISHU_APP_ID="your_feishu_app_id"
export FEISHU_APP_SECRET="your_feishu_app_secret"
```

---

## 启动

### 本地对话
```bash
python -m ai_companion start              # 启动（选择默认 Bot）
python -m ai_companion start --bot suqing  # 指定 Bot
```

### 飞书网关服务
```bash
python -m ai_companion gateway start        # 后台启动
python -m ai_companion gateway start --sync  # 前台启动
python -m ai_companion gateway stop         # 停止
python -m ai_companion gateway logs         # 查看日志
```

### 内置命令

在对话界面使用：
- `/new` - 开始新会话
- `/memory` - 查看记忆状态
- `/forget <key>` - 删除某条记忆
- `quit` - 退出

---

## 内置人格

| ID | 名称 | 性格 | 简介 |
|----|------|------|------|
| suqing | 苏晴 | 傲娇 | 26岁自由插画师，嘴硬心软 |
| aiyue | 阿月 | 活泼 | 22岁音乐学院学生，有点粘人 |

---

## 自定义人格

```
data/bots/mybot/persona/
├── profile.json        # 基础档案（名字、年龄、职业等）
├── backstory.json      # 人生经历
├── values.json         # 价值观和底线
├── speaking_style.json # 说话风格
└── emotional_rules.json # 情绪规则
```

复制模板并修改：
```bash
cp -r data/bots/_template data/bots/mybot
```

---

## Skill 扩展

```bash
python -m ai_companion skill list           # 查看已安装技能
python -m ai_companion skill install ./my-skill  # 从本地安装
python -m ai_companion skill uninstall my-skill  # 卸载
```

---

## 详细文档

| 文档 | 说明 |
|------|------|
| [完整使用指南](./docs/GUIDE.md) | 详细的配置说明和功能介绍 |
| [主动唤醒系统设计](./docs/DESIGN_phase5_proactive.md) | 主动唤醒架构和算法设计 |
| [主动唤醒系统实现](./docs/IMPLEMENTATION_phase5_proactive.md) | 主动唤醒实现细节 |

---

## 常见问题

**Q: 提示 "API Key 未设置"**
A: `export MINIMAX_API_KEY="your_key"`

**Q: 飞书连接失败**
A: 检查 `FEISHU_APP_ID` 和 `FEISHU_APP_SECRET` 是否正确

**Q: Bot 不主动发消息**
A: 检查 `data/bots/{bot_id}/persona/proactive.json` 中 `enabled` 和 `mode`

**Q: 如何重置记忆？**
A: `rm -rf ~/.ai-companion/data/bots/{bot_id}/memory/*.db`

---

## License

MIT
