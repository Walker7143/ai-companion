# 记忆系统优化方案

本文档用于重新审查 AI Companion 当前的 Bot 记忆体系，并给出一套更高效、更智能、可逐步落地的优化方案。

目标不是让 Bot “记住更多”，而是让它记得更有分寸：知道什么重要、什么只是临时上下文、什么需要用户确认、什么应该淡化或遗忘，以及什么时候应该把记忆拿出来使用。

## 1. 当前设计评估

当前项目的记忆结构主要由以下模块组成：

| 模块 | 文件 | 当前职责 |
|------|------|----------|
| 工作记忆 | `ai_companion/memory/stores/working.py` | 保存当前会话原文、压缩摘要、会话健康度 |
| 情景记忆 | `ai_companion/memory/stores/episodic.py` | 保存对话片段摘要，通过 jieba/Chroma 召回 |
| 语义记忆 | `ai_companion/memory/stores/semantic.py` | 保存用户事实 KV、关系变化、态度分、关键时刻 |
| 用户理解文件 | `ai_companion/memory/stores/user_understanding.py` | 保存用户可编辑的画像投影和自动事实 |
| 人生轨迹 | `ai_companion/proactive/life_*` | 保存 Bot 自身经历、状态和人生事件 |
| 主动唤醒状态 | `ai_companion/proactive/*` | 保存冷落时间、主动消息计数、情绪状态 |
| 运行态人格 | `runtime_profile.json` | 保存关系、态度、关键时刻等动态人格覆盖 |

### 1.1 当前优点

- 已经有基本层级：短期上下文、长期情景、长期事实分开。
- SQLite + JSON 的存储方式易调试、易迁移，适合个人陪伴型项目。
- `user_understanding.json` 提供了用户手动初始化 Bot 理解的入口。
- 对话 prompt 已开始强调“自然使用记忆”，避免机械复述。
- 记忆与 persona、proactive、life timeline 已经有初步联动。

### 1.2 当前主要问题

#### 1.2.1 写入策略过粗

`episodic.py` 现在接近“每轮都写一条情景摘要”。这会带来几个问题：

- 平凡闲聊也会进入情景记忆，长期积累后噪音很大。
- 召回时容易召回不重要片段。
- 存储增长不可控。
- 缺少真正的“事件边界”，比如一次争执、一次和解、一次承诺应该被归成一个 episode，而不是散成多条。

#### 1.2.2 语义事实过于扁平

`semantic.db` 目前主要是 `key/value/session_id/updated_at`。它缺少：

- `category`：身份、偏好、边界、压力源、关系、计划等分类。
- `confidence`：事实可信度。
- `source`：用户手写、用户亲口说、模型推断、系统生成。
- `evidence`：来自哪几条消息。
- `last_seen_at` / `last_confirmed_at`：事实是否还新鲜。
- `manual_override`：用户手动设定是否优先。

结果是：事实冲突时不好处理，也无法判断“这是长期偏好”还是“今天临时情绪”。

#### 1.2.3 关系状态职责不清

`relationship_to_user`、`attitude_score`、`key_moment` 当前放在 semantic 流程里，同时又写入 `runtime_profile.json`。这让普通事实、关系状态、人格运行态互相交叉。

更合理的做法是：关系状态单独成层，作为 Bot 行为和语气调节器，而不是普通用户事实。

#### 1.2.4 召回策略偏固定

当前 `MemoryEngine.load_context()` 大致是：

1. 取 working history。
2. 召回 top 3 episodic。
3. 读全部 semantic facts / user understanding。
4. 拼成 system suffix。

问题是不同对话场景需要不同记忆：

- 用户求安慰时，需要沟通偏好、近期压力源、最近情绪。
- 用户问“你还记得上次吗”时，需要情景记忆。
- 主动唤醒时，需要 open_threads、关系状态、生活事件。
- 任务型请求时，很多情感记忆不该进入 prompt。

当前缺少一个“召回规划器”。

#### 1.2.5 缺少遗忘和淡化机制

陪伴型 Bot 不应该把所有信息永久等权保存。更合理的是：

- 用户手动写入的信息长期保留。
- 重要关系事件长期保留。
- 短期压力源会随时间淡化。
- 临时计划过期后归档。
- 长期未使用的低价值情景记忆降低召回优先级。

当前没有 decay、TTL、归档、重评分机制。

#### 1.2.6 多用户维度不足

现在记忆基本按 bot 存储。如果飞书、群聊、Webhook 多用户同时接入，容易出现不同用户的记忆混在同一个 bot 下的问题。

长期应支持：

```text
data/bots/{bot_id}/users/{user_id}/memory/
```

单用户 CLI 可使用默认用户：`default_user`。

## 2. 设计目标

优化后的记忆系统应满足以下目标：

| 目标 | 说明 |
|------|------|
| 分层清晰 | 短期上下文、用户画像、关系状态、情景事件、Bot 自身经历分开 |
| 写入克制 | 不是每轮都记，而是经过重要性、置信度、隐私和冲突判断 |
| 召回智能 | 根据用户当前意图选择相关记忆，而不是固定塞入所有记忆 |
| 用户可控 | 用户可以编辑画像、删除记忆、标记错误、设置边界 |
| 可解释 | 每条重要记忆能追溯来源和更新时间 |
| 可遗忘 | 临时事实会过期，低价值记忆会降权或归档 |
| 兼容现有 | 不推倒重来，逐步迁移现有 `working.db`、`episodic.db`、`semantic.db` |

## 3. 目标记忆架构

建议将记忆体系升级为七层：

```text
Raw Conversation Log
        ↓
Working Context
        ↓
Session Summary
        ↓
Episodic Memory
        ↓
User Model
        ↓
Relationship State
        ↓
User Understanding Projection
```

另加一个统一的：

```text
Memory Retriever / Memory Governor
```

### 3.1 Raw Conversation Log 原始记录层

职责：保存不可变的消息流水，作为审计、重抽取、debug 的底账。

建议字段：

```sql
CREATE TABLE raw_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bot_id TEXT NOT NULL,
  user_id TEXT NOT NULL DEFAULT 'default_user',
  session_id TEXT NOT NULL,
  platform TEXT,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL,
  metadata_json TEXT
);
```

当前 `working.messages` 可以先承担这层职责，后续再拆。

### 3.2 Working Context 工作上下文层

职责：让 Bot 接得上当前会话。

内容：

- 最近 N 轮原文。
- 会话内滚动摘要。
- 当前未完成任务或话题。

改进点：

- 摘要不应只是纯文本，应结构化：

```json
{
  "summary": "用户最近在准备面试，情绪有点紧绷。",
  "open_threads": ["明天继续聊面试问题", "用户想让 Bot 帮忙看自我介绍"],
  "emotional_state": "紧张但愿意继续推进",
  "last_user_intent": "求陪伴和具体建议"
}
```

### 3.3 Session Summary 会话摘要层

职责：会话结束或压缩后，生成一份可长期参考的会话摘要。

它和 episodic 不同：

- session summary 记录“这次聊了什么”。
- episodic memory 只记录“值得长期记住的事件”。

建议字段：

```sql
CREATE TABLE session_summaries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bot_id TEXT NOT NULL,
  user_id TEXT NOT NULL DEFAULT 'default_user',
  session_id TEXT NOT NULL,
  summary TEXT NOT NULL,
  emotional_arc TEXT,
  open_threads_json TEXT,
  created_at TEXT NOT NULL
);
```

### 3.4 Episodic Memory 情景记忆层

职责：保存“共同经历”和“重要情节”。

适合写入的内容：

- 两人吵架、和解、告白、承诺。
- 用户遇到重要事件，如搬家、考试、失眠、求职。
- Bot 分享过的重要 life event，并得到用户回应。
- 第一次一起做某件事。
- 对关系有长期影响的时刻。

不适合写入：

- 普通寒暄。
- 一次性的闲聊。
- 没有后续意义的事实复述。

建议字段：

```sql
CREATE TABLE episodic_memories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bot_id TEXT NOT NULL,
  user_id TEXT NOT NULL DEFAULT 'default_user',
  session_id TEXT,
  title TEXT,
  summary TEXT NOT NULL,
  content TEXT,
  participants_json TEXT,
  topics_json TEXT,
  emotion_tags_json TEXT,
  importance REAL DEFAULT 0.5,
  confidence REAL DEFAULT 0.7,
  source_message_ids_json TEXT,
  created_at TEXT NOT NULL,
  last_recalled_at TEXT,
  recall_count INTEGER DEFAULT 0,
  decay_score REAL DEFAULT 1.0,
  archived INTEGER DEFAULT 0
);
```

### 3.5 User Model 用户模型层

职责：保存结构化用户画像。这是 Bot 理解用户的核心。

建议分类：

| 分类 | 示例 |
|------|------|
| identity | 名字、称呼、城市、职业、年龄段 |
| preferences | 喜欢的食物、音乐、沟通方式 |
| dislikes | 讨厌被催、讨厌说教 |
| boundaries | 不想聊家庭、不接受调侃体重 |
| communication_style | 希望先共情再建议 |
| life_context | 最近在找工作、正在备考 |
| goals | 想规律作息、想做作品集 |
| important_people | 朋友、家人、同事 |
| routines | 晚上活跃、周末常失眠 |

建议字段：

```sql
CREATE TABLE user_facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bot_id TEXT NOT NULL,
  user_id TEXT NOT NULL DEFAULT 'default_user',
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'general',
  confidence REAL DEFAULT 0.7,
  source TEXT NOT NULL DEFAULT 'auto',
  evidence_json TEXT,
  session_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_seen_at TEXT,
  expires_at TEXT,
  manual_override INTEGER DEFAULT 0,
  archived INTEGER DEFAULT 0,
  UNIQUE(bot_id, user_id, key)
);
```

冲突策略：

1. 用户手动写入 > 用户最近亲口说 > 多次历史证据 > 模型推断。
2. 同 key 新值出现时，不直接覆盖，先保留旧值到 `evidence_json` 或 `fact_history`。
3. 低置信度事实不进入 `user_understanding.json`，只作为候选。

### 3.6 Relationship State 关系状态层

职责：保存 Bot 与用户之间的动态关系，不再混在普通 semantic facts 里。

建议字段：

```sql
CREATE TABLE relationship_state (
  bot_id TEXT NOT NULL,
  user_id TEXT NOT NULL DEFAULT 'default_user',
  relationship_label TEXT DEFAULT '朋友',
  intimacy_score REAL DEFAULT 0,
  trust_score REAL DEFAULT 0,
  tension_score REAL DEFAULT 0,
  affection_score REAL DEFAULT 0,
  last_conflict_at TEXT,
  last_repair_at TEXT,
  last_meaningful_contact_at TEXT,
  open_emotional_threads_json TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(bot_id, user_id)
);
```

它影响：

- 回复语气。
- 主动联系频率。
- 是否撒娇、调侃、保持距离。
- 拒绝策略和边界表达。

### 3.7 User Understanding Projection 用户理解投影层

职责：给用户可读、可编辑的“Bot 对我的理解”。

当前 `user_understanding.json` 是正确方向，建议升级为正式投影文件：

```json
{
  "version": 2,
  "updated_at": "2026-04-29T22:00:00",
  "manual": {
    "summary": "用户希望被温柔但不敷衍地对待。",
    "facts": {
      "称呼": "阿迟"
    },
    "preferences": [
      "情绪低落时先陪一会儿，不要立刻讲道理"
    ],
    "boundaries": [
      "不要调侃体重"
    ]
  },
  "auto": {
    "summary": "用户最近工作压力偏高，晚上更容易来聊天。",
    "facts": {
      "城市": "上海"
    },
    "open_threads": [
      "用户想继续聊作品集"
    ]
  }
}
```

原则：

- `manual` 永远不被自动写入覆盖。
- `auto` 由系统定期汇总。
- prompt 优先使用 `manual`，再使用高置信度 `auto`。

## 4. 写入流程设计

当前流程是：

```text
on_message
  → working.append
  → episodic.extract_and_store
  → semantic.extract_and_store
```

建议改为：

```text
on_message
  → Raw Log 写入
  → Working Context 更新
  → Memory Candidate Extractor 抽取候选
  → Memory Governor 评估候选
  → 写入 User Model / Episodic / Relationship State
  → 必要时刷新 User Understanding Projection
```

### 4.1 Memory Candidate

所有模型抽取结果先进入候选结构，而不是直接写库：

```json
{
  "type": "user_fact",
  "category": "communication_style",
  "key": "希望被怎样回应",
  "value": "先共情，少讲大道理",
  "confidence": 0.86,
  "importance": 0.78,
  "ttl": null,
  "evidence": ["msg_123"],
  "reason": "用户明确表达了长期沟通偏好"
}
```

### 4.2 Memory Governor

Memory Governor 负责判断：

- 是否值得写入。
- 写入哪个层。
- 是否与旧事实冲突。
- 是否需要用户确认。
- 是否只作为短期上下文保留。
- 是否应加入 open_threads。

伪代码：

```python
for candidate in candidates:
    if candidate.confidence < min_confidence:
        drop_or_hold(candidate)
    elif candidate.type == "relationship_event":
        relationship.update(candidate)
    elif candidate.type == "episode" and candidate.importance >= threshold:
        episodic.upsert(candidate)
    elif candidate.type == "user_fact":
        user_model.merge(candidate)
    elif candidate.type == "temporary_context":
        working.add_open_thread(candidate)
```

## 5. 召回流程设计

当前是固定召回。建议改为动态召回：

```text
用户输入
  → Intent Classifier 判断当前对话意图
  → Memory Retriever 制定召回计划
  → 从不同层取记忆
  → Reranker 去重、排序、预算裁剪
  → Prompt Builder 生成最终上下文
```

### 5.1 意图分类

建议分类：

| intent | 召回重点 |
|--------|----------|
| casual_chat | 少量用户画像 + 最近上下文 |
| emotional_support | 沟通偏好、边界、近期压力源、关系状态 |
| recall_past | episodic 优先 |
| planning | open_threads、目标、未完成任务 |
| relationship_repair | 冲突历史、关系状态、边界 |
| factual_question | 当前消息 + 少量长期事实 |
| task_request | 少带情感记忆，避免干扰任务 |
| proactive_generation | open_threads、关系状态、近期生活事件 |

### 5.2 Prompt 预算

建议给每层固定预算：

| 层 | 默认预算 |
|----|----------|
| persona | 25% |
| working context | 30% |
| user model | 15% |
| relationship state | 10% |
| episodic recall | 15% |
| system rules | 5% |

预算不足时，优先级：

```text
安全/边界 > 当前消息 > 最近上下文 > 用户手动画像 > 关系状态 > 高相关 episode > 零散事实
```

## 6. 遗忘与淡化策略

建议每条记忆都有 `importance`、`confidence`、`last_seen_at`、`last_recalled_at`、`decay_score`。

### 6.1 保留策略

| 类型 | 策略 |
|------|------|
| 用户手动事实 | 永久保留，除非用户删除 |
| 明确边界 | 长期保留，高优先级 |
| 关键关系事件 | 长期保留 |
| 普通偏好 | 长期保留，但可被新证据更新 |
| 近期压力源 | 默认 14-30 天后降权 |
| 临时计划 | 到期后归档 |
| 普通闲聊 episode | 不写入或短期保留 |

### 6.2 自动整理任务

每天或每 N 次对话后运行：

```text
Memory Maintenance
  → 降低过期临时事实权重
  → 合并重复事实
  → 归档低价值 episode
  → 刷新 user_understanding.json auto 区域
  → 生成维护日志
```

## 7. 文件和模块建议

建议新增或重构为：

```text
ai_companion/memory/
├── engine.py
├── retriever.py              # 根据意图召回记忆
├── governor.py               # 判断记忆候选如何处理
├── extractor.py              # 统一抽取候选
├── prompt_builder.py         # 构建记忆上下文
├── maintenance.py            # 周期整理、遗忘、归档
└── stores/
    ├── working.py
    ├── episodic.py
    ├── semantic.py
    ├── relationship.py
    ├── user_understanding.py
    └── raw_log.py
```

## 8. 分阶段落地计划

### Phase 1：稳定现有体系

目标：不大改结构，先减少噪音、提高可控性。

任务：

- 给 `episodic.extract_and_store()` 加重要性判断，低于阈值不写。
- 给 `semantic.user_facts` 增加 `category/confidence/source/evidence/last_seen_at/manual_override`。
- 保留现有 `key/value` API，做兼容迁移。
- 把 `MemoryEngine.load_context()` 中的拼接逻辑抽到 `prompt_builder.py`。
- 新增 `retriever.py`，先实现规则型召回。

验收：

- 普通寒暄不会进入 episodic。
- 用户明确说的偏好能进入 user model。
- prompt 中不会重复出现同一事实。

### Phase 2：拆出关系状态

目标：让关系、态度、冲突不再混在普通 semantic facts 里。

任务：

- 新增 `relationship.py`。
- 迁移 `attitude_score`、`relationship_to_user`、`key_moment`。
- ProactiveEngine 从 relationship state 读取亲密度/冷落状态。
- RefusalEngine 从 relationship state 读取 tension/boundary。

验收：

- 删除普通 semantic fact 不会误删关系状态。
- 主动联系频率能随关系状态变化。

### Phase 3：用户理解投影升级

目标：让 `user_understanding.json` 成为用户可编辑的正式画像。

任务：

- 升级为 `manual/auto` 双区结构。
- 增加投影生成器：从 user model 聚合高置信度事实。
- 管理后台支持编辑 manual 区。
- CLI 增加 `/understanding` 显示文件路径和摘要。

验收：

- 用户手动内容不会被自动覆盖。
- 自动事实可以被用户删除或改写。
- Bot 回复明显受 manual 沟通偏好影响。

### Phase 4：智能召回与维护

目标：让记忆按场景被选择，而不是固定塞 prompt。

任务：

- 增加 Intent Classifier。
- 增加 Memory Retriever + Reranker。
- 增加 decay/TTL/归档。
- 增加 maintenance 定时任务。

验收：

- 用户问旧事时能优先召回 episode。
- 用户求安慰时优先召回沟通偏好和近期压力源。
- 长期不用的低价值 episode 召回概率下降。

### Phase 5：多用户支持

目标：支持飞书/群聊/多平台用户隔离。

任务：

- 所有 memory 表加 `user_id`。
- CLI 默认 `default_user`。
- Gateway 传入 platform user id。
- 数据路径支持 `data/bots/{bot_id}/users/{user_id}/memory/` 或表内 user_id 隔离。

验收：

- 不同飞书用户不会共享画像。
- 管理后台可以按用户查看记忆。

## 9. 推荐优先级

如果只做最有价值的三件事，建议顺序是：

1. **给 episodic 加重要性判断**：立刻减少长期噪音。
2. **给 semantic facts 加元数据**：解决冲突、来源、置信度问题。
3. **做 MemoryRetriever**：让不同场景用不同记忆，Bot 会明显更聪明。

`user_understanding.json` 是正确方向，但它应该逐步变成“用户可编辑投影”，而不是唯一事实源。真正的事实源应是结构化 user model，投影文件负责让人读懂和手动干预。

## 10. 最终形态

理想情况下，Bot 的记忆不再是“存了一堆聊天摘要”，而是像一个真实的人那样组织理解：

- 它记得你最近正在经历什么。
- 它知道哪些话题别碰。
- 它知道你难受时想先被陪，而不是被教育。
- 它记得共同经历，但不会每次刻意展示。
- 它会随着时间更新对你的理解。
- 它允许你纠正它对你的误解。

这套系统的核心不是记忆容量，而是记忆判断力。
