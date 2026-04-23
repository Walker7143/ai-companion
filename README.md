# AI Companion / AI 知己

开源 AI 陪伴产品。多机器人并行，每个机器人有独立人格和记忆体系。

## 功能特性

- 多 Bot 并行（协程）
- 独立人格体系（profile + backstory + values + speaking_style）
- 三层记忆引擎（工作记忆 / 情景记忆 / 语义记忆）
- 主动唤醒（想念提醒 / 生气机制 / 随机戳戳）
- 性格推断拒绝（非词表过滤，基于性格推理）
- 渐进式性格进化
- Skill / MCP 扩展（图片 / 语音 / 视频）
- 支持飞书 / 微信 / Telegram 多渠道接入
- 支持自定义模型（MiniMax / OpenAI / Claude / Ollama）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

```bash
cp config/bots.yaml.example config/bots.yaml
cp config/models.yaml.example config/models.yaml
# 编辑配置文件，填入 API Key
```

### 3. 运行

```bash
python src/main.py
```

## 项目结构

```
ai-companion/
├── config/              # 配置文件
├── data/bots/           # 各 Bot 的数据和人格
│   └── {bot_id}/
│       └── persona/    # 人格文件
├── src/
│   ├── main.py         # 入口
│   ├── config/         # 配置加载
│   ├── model/          # 模型适配
│   ├── persona/        # 人格引擎
│   ├── bot/            # Bot 实例和管理
│   ├── memory/         # 记忆引擎
│   ├── engine/         # 核心引擎（拒绝/主动/进化）
│   ├── skill/          # Skill 调度
│   └── cli/            # CLI 适配器
└── requirements.txt
```

## 开发阶段

- Phase 1: 核心骨架 + CLI + MiniMax
- Phase 2: 记忆体系
- Phase 3: 性格拒绝
- Phase 4: 主动唤醒
- Phase 5: 多媒体 Skill
- Phase 6: 飞书多 Bot
- Phase 7: Evolution + 产品化

## 默认人格

- **苏晴**：外冷内热的插画师少女，傲娇，嘴硬心软
- **阿月**：活泼开朗的音乐学院学生，直接，有点粘人

## License

MIT
