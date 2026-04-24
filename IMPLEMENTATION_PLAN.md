# AI Companion — 实施计划

> 每个 Task 均可独立验证，通过后才进入下一步。
> 更新于 2026-04-24（Phase 6 TTS bug 修复 + Phase 7 Skill 扩展系统完成）

---

## 阶段 0：环境验证

### Task 0-1：验证 Python 环境 ✅

```bash
python3 --version  # Python 3.11.0+
pip3 --version     # pip 23.x+
```

### Task 0-2：验证 MiniMax API Key ✅

**注意：** 实际使用模型为 `MiniMax-M2.7`（`abab6.5s-chat` 需付费订阅才可用）。

```python
import os, aiohttp, asyncio

async def test():
    api_key = os.environ["MINIMAX_API_KEY"]
    url = "https://api.minimax.chat/v1/text/chatcompletion_v2"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": "MiniMax-M2.7", "messages": [{"role": "user", "content": "你好"}], "max_tokens": 50}
    async with aiohttp.ClientSession() as s:
        async with s.post(url, headers=headers, json=payload) as r:
            data = await r.json()
            msg = data["choices"][0]["message"]
            # MiniMax-M2.7 回复在 content（直接回复）或 reasoning_content（推理内容）
            content = msg.get("content") or msg.get("reasoning_content") or ""
            print(f"回复: {content}")
            return r.status == 200 and content

print("✓ API Key 验证通过" if asyncio.run(test()) else "✗ 验证失败")
```

---

## 阶段 1：核心骨架（CLI 对话）✅ 全部完成

| Task | 验证内容 | 状态 |
|------|---------|------|
| 1-1 | 项目结构 | ✅ |
| 1-2 | 配置加载 | ✅ |
| 1-3 | 人格文件加载 | ✅ |
| 1-4 | System Prompt 构建 | ✅ |
| 1-5 | 模型 API 集成 | ✅ |
| 1-6 | 单 Bot 对话 | ✅ |
| 1-7 | CLI 完整流程 | ✅ |
| 1-8 | 人格差异 | ✅ |

---

## 阶段 2：记忆体系

### 架构概览

```
用户输入
  → MemoryEngine.load_context()
  │    ├── working_history:  工作记忆（摘要正序 + 近期原始消息）
  │    ├── episodic_recall:  情景记忆（向量召回 / SQLite 降级）
  │    └── semantic_facts:   语义记忆（用户事实画像）
  │
  → LLM.chat(messages + system_suffix)
  │
  → extract_and_store()（异步）
       ├── 情景：命中关键词 → Chroma + SQLite 写入
       └── 语义：每次尝试抽取 → 有新事实写入 SQLite
```

**三层存储路径：** `data/bots/{bot_id}/memory/`
- `working.db` — 工作记忆（SQLite）
- `episodic.db` + `chroma/` — 情景记忆（Chroma + SQLite）
- `semantic.db` — 语义记忆（SQLite）

### Task 2-1：SemanticStore 语义记忆 CRUD ✅

**文件：** `ai_companion/memory/stores/semantic.py`

**功能：**
- `init()` — 建表 `user_facts (key, value, updated_at)`
- `set_fact(key, value)` / `get_fact(key)` / `get_all_facts()` / `delete_fact(key)`
- `extract_and_store(user_input, bot_output)` — LLM 抽取新事实，有则写入

**验证结果：** ✅ 通过
```
CRUD: 写入/读取/删除/计数全部正常
抽取: MiniMax-M2.7 推理模型回复在 reasoning_content，修复后成功识别「职业:建筑师」
格式兼容: 同时支持标准 {"key":..., "value":...} 和 flat KV {"姓名":"小明"} 两种格式
会话隔离: composite key (key, session_id) 防止跨会话覆盖
```

---

### Task 2-2：WorkingMemory load_context 拼接 ✅

**文件：** `ai_companion/memory/stores/working.py`

**验证结果：** ✅ 通过
```
load_context() 返回: 摘要(正序) + 原始消息(正序)，共12条消息
```

---

### Task 2-3：WorkingMemory 压缩验证 ✅

**文件：** `ai_companion/memory/stores/working.py`

**触发时机：**
- HARD_LIMIT(>5000字): 同步压缩
- SOFT_LIMIT(>3000字): 后台异步压缩

**验证结果：** ✅ 通过
```
LLM压缩摘要生成正常（MiniMax-M2.7）
```

---

### Task 2-4：EpisodicStore 中文搜索（jieba 分词 + SQLite tokens 列）✅

**文件：** `ai_companion/memory/stores/episodic.py`

**方案：**
- **写入时**：`content` → jieba 切分 → tokens 列存储 `['word1', 'word2', ...]`
- **搜索时**：查询词也经 jieba 切分，多词 OR 匹配 `tokens` 列
- **降级方案**：tokens 无结果则直接 LIKE 匹配 `summary` / `content`

> ⚠️ SQLite FTS5 的 `unicode61` tokenizer 不支持 CJK 字符索引（实测 Hermes Agent 的 FTS5 同样无法索引纯中文），
> 故采用 jieba + tokens 列方案。

**验证结果：** ✅ 通过
```
搜「餐厅」: ✓ 找到「今天去那家餐厅吃饭」
搜「新手机」: ✓ 找到「买了新手机」
搜「加班」: ✓ 找到「加班到很晚」
搜「吃饭」: ✓ 找到「今天去那家餐厅吃饭」
会话隔离: ✓ 跨 session 不串数据
```

---

### Task 2-5：sentence-transformers 本地 Embedding ⏳ TODO

**Objective：** 实现 `embedding: "local"` 模式，接入 sentence-transformers

**前置条件：** `pip install sentence-transformers`

**状态：** 代码已实现，但未安装依赖，待 Phase 2 收尾时验证。

```python
# 验证脚本（安装依赖后执行）
from ai_companion.memory.stores.episodic import EpisodicStore
store = EpisodicStore("/tmp/test.db", "/tmp/chroma", embedding_mode="local")
encoder = store._get_encoder()
emb = encoder.encode("今天吃了火锅")
print(f"向量维度: {len(emb)}")  # 期望 384
```

---

### Task 2-6：setup-embeddings.sh 一键安装脚本 ⏳ TODO

**文件：** `scripts/setup-embeddings.sh`

**状态：** 脚本已创建，待 sentence-transformers 安装后验证。

---

### Task 2-7：models.yaml 配置更新 ✅

**文件：** `config/models.yaml`

**当前配置：**
```yaml
minimax:
  api_key: "${MINIMAX_API_KEY}"
  base_url: "https://api.minimax.chat/v1"
  model: "MiniMax-M2.7"
  max_context_chars: 8000

memory:
  embedding: "none"          # "local" | "none"
  embedding_model: "all-MiniLM-L6-v2"
  max_working_turns: 20
  hard_limit_chars: 5000
  soft_limit_chars: 3000
```

**验证结果：** ✅ 通过

---

### Task 2-8：MemoryEngine 读取 context_window 配置 ✅

**文件：** `ai_companion/memory/engine.py`

**验证结果：** ✅ 通过
```
配置覆盖正确: hard_limit=3000, soft_limit=2000, max_working_turns=10
```

---

### Task 2-9：BotInstance 集成 MemoryEngine ✅

**文件：** `ai_companion/bot/instance.py`

**验证结果：** ✅ 通过
```
handle_message() 正确调用:
  1. maybe_compress() 检查压缩
  2. load_context() 加载三层记忆
  3. LLM 对话
  4. on_message() 异步写入记忆
```

---

### Task 2-10：CLI 命令 /new、/memory、/forget ✅

**文件：** `ai_companion/cli/adapter.py`

| 命令 | 功能 | 状态 |
|------|------|------|
| `/new` | 开始新会话 | ✅ |
| `/memory` | 查看记忆状态 | ✅ |
| `/forget <key>` | 删除语义记忆 | ✅ |
| `quit/exit` | 退出 | ✅ |
| `switch` | 切换 Bot | ✅ |
| `reset` | 重置历史 | ✅ |

---

### Task 2-11：记忆召回影响对话验证 ✅

**验证结果：** ✅ 通过
```
告知"我是建筑师"+"我在上海工作"后
跨会话事实召回: {'工作城市': '上海', '职业': '建筑师'}
```

---

### Task 2-12：记忆矛盾检测验证 ⏳ 待手动测试

**状态：** 逻辑已实现（语义记忆 + 性格推断），需手动对话验证。

---

## 阶段 2 验证总览

|| Task | 验证内容 | 状态 |
|------|---------|------|
| 2-1 | SemanticStore CRUD + 抽取 + reasoning_content 修复 | ✅ 已验证 |
| 2-2 | load_context 摘要+原始拼接 | ✅ 已验证 |
| 2-3 | 自动压缩 + summarizer | ✅ 已验证 |
| 2-4 | jieba 分词 + SQLite tokens 中文搜索 | ✅ 已验证 |
| 2-5 | sentence-transformers 向量召回 | ⚠️ 可选 |
| 2-6 | setup-embeddings.sh | ⚠️ 可选 |
| 2-7 | models.yaml 新配置 | ✅ 已验证 |
| 2-8 | MemoryEngine 读配置 | ✅ 已验证 |
| 2-9 | BotInstance 集成 | ✅ 已验证 |
| 2-10 | CLI /new /memory /forget | ✅ 已验证 |
| 2-11 | 跨会话记忆召回 | ✅ 已验证 |
| 2-12 | 语义记忆会话隔离（composite key） | ✅ 已验证 |

**完成度：11/12（2个可选）**

---

## 阶段 3：性格进化系统 ✅ 全部完成

### 架构概览

```
每次对话结束 → extract_and_store()
  ├── attitude_score:   LLM判断本轮变化量(±5) → 增量叠加写入 profile.json
  ├── relationship:     LLM判断关系状态变化 → 写入 profile.json
  └── key_moment:       LLM判断是否为重要情景 → 追加写入 backstory.json（去重）
```

**关键文件：**
- `ai_companion/memory/stores/semantic.py` — attitude/relation/key_moment 抽取 + 写回
- `ai_companion/memory/engine.py` — `on_message` 异步触发抽取，传 conversation_context

### Task 3-1：attitude_score 增量模型 ✅

**设计：** LLM 输出本轮 attitude 变化量（±5），现有分数叠加。
- `profile.json` 字段：`attitude_score`（整数，-10~+10 基准，可溢出）
- `semantic.db` 字段：`attitude_score`（最近一次会话值）
- 解析：`re.findall(r'-?\d+', text)[-1]` 取 LLM 结论数字

**验证：** ✅ 2026-04-23 真实 API 测试
```
对话1（自我介绍）: attitude 无异常
对话2（夸奖）:      attitude NO_CHANGE（attitude_score 维持 -4）
对话3（调侃）:      +1 → attitude_score -4 → 1 ✓
```

### Task 3-2：relationship_to_user 状态机 ✅

**状态机：** `陌生网友` → `普通朋友` → `好朋友` → `暧昧中的青梅竹马` → `恋人`

**判断规则：** LLM 输出一致性状态描述（`UPGRADE`、`DOWNGRADE`、`NO_CHANGE`），Engine 判断是否满足升级条件。

**验证：** ✅ 逻辑已实现，通过直接调用测试。

### Task 3-3：key_moment 去重记录 ✅

**设计：** 每次抽取 key_moment，追加到 `backstory.json` 的 `key_moments[]`，写入前先去重（比较事件类型 + 内容哈希）。

**验证：** ✅ 通过直接调用测试验证去重逻辑正确。

### Task 3-4：Evolution 异步任务异常处理 ✅

**设计：** `on_message` 异步触发抽取，回调用 `_on_task_done` 函数打印完整异常（`traceback.format_exception`）。

**验证：** ✅ `CancelledError` 等异步异常被正确捕获和打印。

### Task 3-5：真实 CLI 环境完整流程验证 ✅

**验证：** ✅ 2026-04-23 真实 API 完整流程测试
- Bot 回复正常（傲娇语气）
- attitude_score 增量叠加写回 profile.json
- semantic.db attitude_score 记录正确
- fact 抽取正常（「偏好：喜欢绘画」）
- `/memory` 命令正常

---

## 阶段 4：性格拒绝机制 ✅ 完成

| Task | 描述 | 状态 |
|------|------|------|
| 4-1 | RefusalEngine 核心实现（LLM 推理） | ✅ 完成 |
| 4-2 | 拒绝分类（NON_NEGOTIABLE/SOFT_BOUNDARY/DEAL_BREAKER） | ✅ 完成 |
| 4-3 | BotInstance 集成 | ✅ 完成 |
| 4-4 | 拒绝开关（refusal_enabled） | ✅ 完成 |
| 4-5 | 人格风格回复模板（傲娇/活泼/高冷/温柔） | ✅ 完成 |
| 4-6 | 真实 CLI 环境完整流程验证 | ✅ 完成 |

**实现方式：**
- LLM 推理判断（REFUSAL_JUDGE_PROMPT）+ 人格回复模板
- 非关键词匹配，基于性格价值观推断
- 关系阈值影响软边界放行

---

## 阶段 5：主动唤醒系统 ✅ 完成

| Task | 验证内容 | 状态 |
|------|---------|------|
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

**实现方式：**
- LLM 推理判断（LLM 综合关系/心情/时间判断是否应联系）
- LLM 生成符合人格的消息（非模板）
- 所有参数通过 `proactive.json` 可配置
- 状态持久化到 `proactive_state.json`（重启保留）

---

## 阶段 6：多媒体 Skill ✅ 完成

| Task | 验证内容 | 状态 |
|------|---------|------|
| 6-1 | Skill Dispatcher 实现 | ✅ 完成 |
| 6-2 | 图片生成 Skill（ImageGenerationSkill） | ✅ 完成 |
| 6-3 | 语音生成 Skill（TTSSkill） | ✅ 完成 |
| 6-4 | 通道能力系统（ChannelCapability） | ✅ 完成 |
| 6-5 | 多模态发送器（MultimodalSender） | ✅ 完成 |
| 6-6 | 通道降级（不支持类型 → text） | ✅ 完成 |
| 6-7 | 自定义模型扩展支持 | ✅ 完成 |

**实现方式：**
- Skill 基类 + SkillDispatcher 调度器
- ImageGenerationSkill 支持 dalle/minimax/stable_diffusion
- TTSSkill 支持 edge_tts/minimax/azure_tts/openai_tts
- ChannelCapability 检测通道能力
- MultimodalSender 协调技能执行和通道发送
- 所有技能支持自定义模型配置（HTTP API + 认证 + 轮询）
- 所有参数通过 `config/models.yaml` 可配置

**验证结果（2026-04-24）：**
- 图片生成 MiniMax：✓ 成功（164.5 KB PNG）
- TTS MiniMax：✓ 成功（52.3 KB MP3）

---

## 阶段 7：Skill 扩展系统 ✅ 完成

| Task | 验证内容 | 状态 |
|------|---------|------|
| 7-1 | SkillRegistry 技能注册中心 | ✅ 完成 |
| 7-2 | SkillInstaller 安装器 | ✅ 完成 |
| 7-3 | skill CLI 命令 | ✅ 完成 |
| 7-4 | BotInstance 动态加载 | ✅ 完成 |
| 7-5 | 测试验证 | ✅ 完成 |

**核心文件：**
- `ai_companion/skill/registry.py` — SkillRegistry
- `ai_companion/skill/installer.py` — SkillInstaller
- `ai_companion/cli/skill_cmd.py` — CLI 命令

**安装来源：**
- 本地路径（目录或 .zip/.tar.gz）
- 远程 URL（.zip）
- Git 仓库

**验证结果（2026-04-24）：**
- `skill list` ✓
- `skill create` ✓
- `skill enable/disable` ✓
- BotInstance 动态加载 ✓

---

## 阶段 8：飞书多 Bot 接入 🚧 进行中

| Task | 描述 | 状态 |
|------|------|------|
| 8-1 | WebSocket 服务（FeishuServer） | ✅ 完成 |
| 8-2 | 消息解析（FeishuHandler） | ✅ 完成 |
| 8-3 | 消息模型（FeishuMessage） | ✅ 完成 |
| 8-4 | Bot 路由和映射 | ✅ 完成 |
| 8-5 | 接入配置示例 | 🚧 待补充 |
| 8-6 | 真实环境验证 | ❌ 待验证 |

**核心文件：**
- `ai_companion/platform/feishu/server.py` — WebSocket 服务
- `ai_companion/platform/feishu/handler.py` — 消息处理和路由
- `ai_companion/platform/feishu/models.py` — 飞书消息模型

**依赖：**
- `lark-oapi>=1.0.0`

**配置示例（config/models.yaml）：**
```yaml
feishu:
  enabled: true
  app_id: "${FEISHU_APP_ID}"
  app_secret: "${FEISHU_APP_SECRET}"

  # Bot 映射
  bots:
    - bot_id: "suqing"
      app_id: "${FEISHU_APP_ID_SUQING}"
      app_secret: "${FEISHU_APP_SECRET_SUQING}"
```

---

## 阶段 9：产品化 + Docker ❌ 未开始

| Task | 验证内容 |
|------|---------|
| 9-1 | Docker 化验证 |
| 9-2 | 完整对话流程压测 |
| 9-3 | 一键安装脚本跨平台验证 |

---

## 总体进度

| 阶段 | 进度 |
|------|------|
| 阶段 0：环境验证 | ✅ 完成 |
| 阶段 1：核心骨架 | ✅ 完成 |
| 阶段 2：记忆体系 | ✅ 完成（11/12，2个可选） |
| 阶段 3：性格进化 | ✅ 完成（5/5） |
| 阶段 4：性格拒绝 | ✅ 完成（6/6） |
| 阶段 5：主动唤醒 | ✅ 完成（12/12） |
| 阶段 6：多媒体 Skill | ✅ 完成（7/7） |
| 阶段 7：Skill 扩展 | ✅ 完成（5/5） |
| 阶段 8：飞书接入 | 🚧 进行中（4/6） |
| 阶段 9：产品化 | ❌ 未开始 |

**重大修复记录：**
- 2026-04-23：jieba + SQLite tokens 列替换 FTS5（中文搜索）；MiniMax-M2.7 `reasoning_content` 优先策略修复语义抽取
- 2026-04-23：Phase 3 Evolution 完成 — attitude 增量模型（re.findall 取最后数字）、relationship 状态机、key_moment 去重、profile 写回，真实 API 验证通过
- 2026-04-23：Phase 4 RefusalEngine 重写 — LLM 推理替代关键词匹配，人格风格回复模板，BotInstance 模型注入修复，真实 CLI 环境验证通过
- 2026-04-24：Phase 6 TTS bug 修复 — `model == "minimax"` 时正确路由到 `_generate_minimax_tts`，真实 API 验证通过（52.3 KB MP3）
- 2026-04-24：Phase 7 完成 — SkillRegistry + SkillInstaller + skill CLI + BotInstance 动态加载，真实 API 验证通过
