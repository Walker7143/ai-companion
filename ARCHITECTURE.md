# AI Companion — 系统设计文档（修订版）

## 核心决策

| 项目 | 决策 |
|------|------|
| 进程模型 | 单进程 + asyncio 多协程 |
| 向量数据库 | Chroma（单文件，零依赖部署） |
| 初始渠道 | 飞书机器人（多 Bot 并行） |
| 模型 | MiniMax m2.7 |
| 部署 | Docker 单文件，一键启动 |

---

## 一、系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    Single Process                       │
│                      (asyncio)                          │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │ Bot A    │  │ Bot B    │  │ Bot N    │   ← 协程     │
│  │ (苏晴)    │  │ (阿月)    │  │          │             │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘             │
│       │             │             │                    │
│       └─────────────┼─────────────┘                    │
│                     │                                  │
│            ┌────────▼────────┐                        │
│            │   Shared Layer  │                        │
│            │  Model Pool      │                        │
│            │  Chroma Store     │                        │
│            │  Redis (可选)     │                        │
│            └──────────────────┘                        │
└───────────────────────┬─────────────────────────────────┘
                        │
              ┌─────────▼─────────┐
              │   Feishu Gateway  │
              │  (多 App 并行)     │
              └───────────────────┘
```

**关键改变：**
- 单进程内用 asyncio 协程运行多个 Bot 实例
- 每个 Bot 是独立协程/Task，有独立的人格和记忆
- 共享 Model Adapter 连接池（降低 API 调用成本）
- Chroma 作为向量数据库（单文件，无需额外部署）

---

## 二、数据目录结构

```
ai-companion/
├── config/
│   ├── bots.yaml          # Bot 列表配置
│   ├── models.yaml         # 模型配置
│   ├── feishu.yaml         # 飞书多 App 配置
│   ├── skills.yaml         # Skill 配置
│   └── proactive.yaml     # 主动消息策略
├── data/
│   └── bots/
│       ├── suqing/         # Bot A 数据目录
│       │   ├── persona/
│       │   │   ├── profile.json
│       │   │   ├── backstory.json
│       │   │   ├── values.json
│       │   │   ├── speaking_style.json
│       │   │   └── emotional_rules.json
│       │   ├── memory/
│       │   │   ├── semantic.db      # SQLite
│       │   │   └── chromatic/        # Chroma 向量
│       │   └── cache/
│       │       └── working_memory.json
│       ├── aiyue/            # Bot B 数据目录
│       │   └── ...
│       └── _template/        # 新建 Bot 模板
│           └── persona/
└── src/
    ├── main.py
    ├── bot/
    │   ├── manager.py        # Bot 管理器（协程调度）
    │   ├── instance.py       # 单个 Bot 实例
    │   ├── feishu_adapter.py # 飞书适配器
    │   └── cli_adapter.py    # CLI 适配器
    ├── engine/
    │   ├── model_adapter.py
    │   ├── persona_engine.py
    │   ├── memory_engine.py
    │   ├── proactive_engine.py
    │   ├── refusal_engine.py
    │   └── evolution_engine.py
    ├── skill/
    │   ├── dispatcher.py
    │   ├── draw_image.py
    │   └── generate_voice.py
    ├── storage/
    │   ├── sqlite_store.py
    │   └── chroma_store.py
    └── utils/
        └── logger.py
```

---

## 三、核心模块说明

### 3.1 Bot Manager（协程调度）

```python
class BotManager:
    """单进程内管理所有 Bot 协程"""
    
    def __init__(self):
        self.bots: dict[str, BotInstance] = {}
        self.tasks: list[asyncio.Task] = []
        
    async def start_all(self):
        """加载配置，启动所有 Bot 协程"""
        for bot_config in load_bots_config():
            bot = BotInstance(bot_config)
            self.bots[bot.id] = bot
            task = asyncio.create_task(bot.run())
            self.tasks.append(task)
            
    async def stop_all(self):
        """优雅关闭所有 Bot"""
        for bot in self.bots.values():
            await bot.stop()
```

### 3.2 Bot Instance（单 Bot 协程）

```python
class BotInstance:
    """单个 Bot 的完整运行实例"""
    
    def __init__(self, config: BotConfig):
        self.id = config.id
        self.persona = PersonaEngine(config.persona_path)
        self.memory = MemoryEngine(config)
        self.model = ModelAdapter(config.model)
        self.proactive = ProactiveEngine(config, self.memory)
        self.refusal = RefusalEngine(config.persona_path, self.memory)
        self.channel = FeishuAdapter(config.feishu)
        
    async def run(self):
        """协程主循环"""
        await self.channel.start_listening(self.on_message)
        
    async def on_message(self, message: ChannelMessage):
        """处理收到的消息"""
        # 1. 召回记忆，构建上下文
        context = await self.memory.build_context(message.text)
        
        # 2. 注入人格，构造 prompt
        prompt = self.persona.build_prompt(context)
        
        # 3. 检查是否违背性格
        refusal_check = await self.refusal.evaluate(message.text, context)
        
        # 4. 调用模型
        response = await self.model.chat(prompt)
        
        # 5. 触发 Skill（如果模型要求）
        result = await self.skill_dispatcher.execute(response.tool_calls)
        
        # 6. 更新记忆
        await self.memory.write_interaction(message, response)
        
        # 7. 发送回复
        await self.channel.send(result)
```

### 3.3 Model Adapter（MiniMax m2.7）

```python
class MiniMaxAdapter(ModelAdapter):
    def __init__(self, config: ModelConfig):
        self.api_key = config.api_key
        self.model = "MiniMax-m2.7"  # 或具体模型名
        
    async def chat(self, messages: list[dict], tools: list[dict] = None) -> str:
        # 调用 MiniMax API
        response = await self.minimax_chat(messages, tools)
        return response
        
    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        # 调用 MiniMax embeddings API
```

### 3.4 Memory Engine（Chroma）

```python
class MemoryEngine:
    def __init__(self, config: BotConfig):
        self.semantic = SQLiteStore(config.db_path)  # L3 语义
        self.episodic = ChromaStore(config.chroma_path)  # L2 情景
        
    async def build_context(self, query: str) -> str:
        """构建对话上下文"""
        # 向量检索最近情景记忆
        episodic = await self.episodic.search(query, top_k=5)
        # 查语义记忆
        semantic = await self.semantic.get_all()
        return self.organize(episodic, semantic)
```

---

## 四、飞书多 Bot 配置

```yaml
# config/feishu.yaml
feishu:
  apps:
    suqing:
      app_id: "${FEISHU_APP_ID_SUQING}"
      app_secret: "${FEISHU_APP_SECRET_SUQING}"
      bot_name: "苏晴"
      description: "外冷内热的插画师少女"
      
    aiyue:
      app_id: "${FEISHU_APP_ID_AIYUE}"
      app_secret: "${FEISHU_APP_SECRET_AIYUE}"
      bot_name: "阿月"
      description: "活泼开朗的音乐学院学生"
```

**飞书 Bot 如何路由：**
- 每个飞书 App 有独立的 `app_id`
- 用户搜索对应的 Bot 名称添加，消息发给那个 App
- 系统根据 `app_id` 分发到对应 Bot Instance

---

## 五、默认人格（开源版预置）

计划内置 3 个人格：

| ID | 名称 | 性格标签 | 简介 |
|----|------|---------|------|
| suqing | 苏晴 | 外冷内热/傲娇/嘴硬心软 | 26岁自由插画师，缺乏安全感 |
| aiyue | 阿月 | 活泼开朗/直接/有点粘人 | 22岁音乐学院学生，性格直接 |
| template | 人格模板 | 可自定义 | 新用户创建人格的起点 |

---

## 六、技术栈（最终版）

| 层次 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| 异步 | asyncio |
| HTTP | aiohttp / httpx |
| 数据库 | SQLite（语义）+ Chroma（向量） |
| 飞书 | feishu-sdk |
| 调度 | asyncio + 内置定时器 |
| 部署 | Docker + docker-compose |
| 模型 | MiniMax m2.7 |

**零额外依赖：** Chroma 是单文件 Python 库，不需要额外部署 Milvus。

---

## 七、开发阶段（保持不变）

```
Phase1 核心骨架     → 单进程 + 单 Bot + CLI + MiniMax
Phase2 记忆体系     → 三层记忆 + Chroma
Phase3 性格拒绝     → Refusal Engine
Phase4 主动性       → Proactive Scheduler
Phase5 多媒体 Skill → 图片 + 语音
Phase6 飞书多 Bot   → 多协程并行
Phase7 Evolution    → 性格进化 + 产品化
```

---

## 八、下一步

确认以上设计后，我将输出：
1. **Phase 1 详细实施计划**（具体文件、代码量、任务拆分）
2. **人格模板 JSON 结构**（可直接填写的格式）
3. **苏晴完整人格文件**（预置人格）
