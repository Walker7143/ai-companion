# AI Companion / AI 知己

开源 AI 陪伴产品，支持 macOS / Windows 双平台。

## 功能特性

- 多 Bot 并行（协程）
- 独立人格体系（profile + backstory + values + speaking_style）
- 三层记忆引擎（工作记忆 / 情景记忆 / 语义记忆）
- 主动唤醒（想念提醒 / 生气机制 / 随机戳戳）
- 性格推断拒绝（非词表过滤，基于性格推理）
- 渐进式性格进化
- Skill / MCP 扩展（图片 / 语音 / 视频）
- 支持飞书机器人接入
- 支持自定义模型（MiniMax / OpenAI / Claude / Ollama）

## 安装

### macOS / Linux

```bash
curl -fsSL https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install.sh | bash
```

或手动安装：

```bash
git clone git@gitee.com:wang_xiao_wei_7143/ai-girl-friend.git
cd ai-girl-friend
pip install -r requirements.txt
```

### Windows

```powershell
irm https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install.ps1 | iex
```

## 配置

```bash
python -m ai_companion setup
```

按向导提示配置 API Key、选择人格模板、配置飞书机器人。

## 启动

```bash
python -m ai_companion start
```

## 命令行工具

```bash
python -m ai_companion start              # 启动
python -m ai_companion setup             # 配置向导
python -m ai_companion status             # 查看状态
python -m ai_companion bot list           # 列出所有 Bot
python -m ai_companion bot add --name xxx # 添加 Bot
python -m ai_companion model test         # 测试模型连接
```

## 默认人格

| ID | 名称 | 性格 | 简介 |
|----|------|------|------|
| suqing | 苏晴 | 外冷内热/傲娇 | 26岁自由插画师，嘴硬心软 |
| aiyue | 阿月 | 活泼开朗/直接 | 22岁音乐学院学生，有点粘人 |

## 自定义人格

参考 `data/bots/_template/persona/` 目录下的模板创建新人格。

## 项目结构

```
ai-companion/
├── ai_companion/           # 主包
│   ├── __main__.py         # CLI 入口
│   ├── main.py             # 启动逻辑
│   ├── setup.py            # 配置向导
│   ├── config/             # 配置加载
│   ├── model/              # 模型适配
│   ├── persona/            # 人格引擎
│   ├── bot/                # Bot 管理
│   ├── memory/             # 记忆引擎
│   ├── engine/             # 核心引擎
│   ├── skill/              # Skill 调度
│   ├── cli/                # CLI 适配器
│   └── platform/           # 平台适配
├── config/                 # 配置文件
├── data/bots/              # 人格和数据
├── scripts/                # 安装脚本
├── tests/                  # 测试
└── requirements.txt
```

## License

MIT
