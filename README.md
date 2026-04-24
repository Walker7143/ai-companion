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

## ✅ Phase 2 完成情况

| Task | 描述 | 状态 |
|------|------|------|
| 2-1 | 工作记忆：SQLite 存储、context 触发压缩 | ✅ 完成 |
| 2-2 | 情景记忆：Chroma 向量召回 + SQLite 降级 | ✅ 完成 |
| 2-3 | 语义记忆：LLM 提取结构化事实 + CRUD | ✅ 完成 |
| 2-4 | 中文搜索：jieba 分词 + SQLite tokens 列 | ✅ 完成 |
| 2-5 | sentence-transformers 本地向量嵌入 | ⚠️ 可选 |
| 2-6 | setup-embeddings.sh 一键安装脚本 | ⚠️ 可选 |
| 2-7 | 压缩触发逻辑（软限/硬限） | ✅ 完成 |
| 2-8 | load_context 串联（summary + recent） | ✅ 完成 |
| 2-9 | BotInstance 集成记忆引擎 | ✅ 完成 |
| 2-10 | CLI /new /memory /forget 命令 | ✅ 完成 |
| 2-11 | 三层记忆集成日志 | ✅ 完成 |
| 2-12 | 语义记忆会话隔离（composite key） | ✅ 完成 |

> ⚠️ Task 2-5/2-6 为可选：sentence-transformers 可提升向量召回准确性，但 SQLite tokens 降级方案对 v1 已足够。

## ✅ Phase 3 完成情况（Evolution 双向进化系统）

| Task | 描述 | 状态 |
|------|------|------|
| 3-1 | attitude_score 增量模型（±5 变化量叠加） | ✅ 完成 |
| 3-2 | relationship_to_user 状态机更新 | ✅ 完成 |
| 3-3 | key_moment 关键时刻去重记录 | ✅ 完成 |
| 3-4 | profile.json / backstory.json 写回 | ✅ 完成 |
| 3-5 | 真实 CLI 环境完整流程验证 | ✅ 完成 |

> Evolution 系统于 2026-04-23 通过真实 API 完整流程验证：attitude_score 增量叠加、relationship 状态更新、key_moment 去重、profile 写回全部正常。

## ✅ Phase 4 完成（LLM 推理性格拒绝机制）

| Task | 描述 | 状态 |
|------|------|------|
| 4-1 | RefusalEngine 核心实现（LLM 推理） | ✅ 完成 |
| 4-2 | 拒绝分类（NON_NEGOTIABLE/SOFT_BOUNDARY/DEAL_BREAKER） | ✅ 完成 |
| 4-3 | BotInstance 集成 | ✅ 完成 |
| 4-4 | 拒绝开关（refusal_enabled） | ✅ 完成 |
| 4-5 | 人格风格回复模板（傲娇/活泼/高冷/温柔） | ✅ 完成 |
| 4-6 | 真实 CLI 环境完整流程验证 | ✅ 完成 |

> 拒绝机制基于 LLM 性格推理，而非关键词匹配。真实 API 验证通过：硬红线拦截、软边界关系阈值影响放行、人格风格回复正常。

## ✅ Phase 5 完成（主动唤醒系统）

| Task | 描述 | 状态 |
|------|------|------|
| 5-1 | ProactiveConfig 配置加载 | ✅ 完成 |
| 5-2 | ProactiveState 持久化 | ✅ 完成 |
| 5-3 | LLM 推理判断（是否应联系） | ✅ 完成 |
| 5-4 | LLM 生成人格消息 | ✅ 完成 |
| 5-5 | 后台调度器独立运行 | ✅ 完成 |
| 5-6 | 情绪触发检测 | ✅ 完成 |
| 5-7 | 限流（max_daily/min_interval） | ✅ 完成 |
| 5-8 | 生气降级（annoyance_level） | ✅ 完成 |
| 5-9 | 冷却机制 | ✅ 完成 |
| 5-10 | 静默模式（mode=silent） | ✅ 完成 |
| 5-11 | 平台适配器（CLI/飞书/Webhook） | ✅ 完成 |
| 5-12 | 配置项全部可调整 | ✅ 完成 |

> 主动唤醒通过 LLM 推理判断是否应主动联系，LLM 生成符合人格的主动消息。所有参数可配置，状态持久化。

## License

MIT
