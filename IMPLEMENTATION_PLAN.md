# AI Companion — 完整实施计划

> 每个 Task 均可独立验证，通过后才进入下一步。

---

## 阶段 0：环境验证（开始任何代码之前）

### Task 0-1：验证 Python 环境

**Objective：** 确认 Python 3.11+ 可用

```bash
python3 --version
# 期望：Python 3.11.0 或更高
```

**Objective：** 确认 pip 可用

```bash
pip3 --version
# 期望：pip 23.x 或更高
```

---

### Task 0-2：验证 MiniMax API Key

**Objective：** 确认 API Key 有效，能调用通义

```python
# 新建 test_api.py
import os
import aiohttp

async def test():
    api_key = os.environ.get("MINIMAX_API_KEY")
    url = "https://api.minimax.chat/v1/text/chatcompletion_v2"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "abab6.5s-chat",
        "messages": [{"role": "user", "content": "你好"}],
        "max_tokens": 50
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            print(f"Status: {resp.status}")
            data = await resp.json()
            print(f"Response: {data}")
            return resp.status == 200

import asyncio
result = asyncio.run(test())
assert result, "API Key 无效"
print("✓ API Key 验证通过")
```

**验收：** 运行后输出 `Status: 200` 和正常回复。

---

## 阶段 1：核心骨架（CLI 对话）

### Task 1-1：项目结构验证

**Objective：** 确认所有目录和空文件创建完毕

```bash
find ai-girl-friend -type f | sort
```

**期望输出包含：**
```
config/bots.yaml
config/models.yaml.example
requirements.txt
src/main.py
src/config/loader.py
src/model/minimax_adapter.py
src/persona/loader.py
src/persona/engine.py
src/bot/instance.py
src/bot/manager.py
src/cli/adapter.py
data/bots/suqing/persona/profile.json
data/bots/suqing/persona/speaking_style.json
data/bots/suqing/persona/backstory.json
data/bots/suqing/persona/values.json
data/bots/aiyue/persona/profile.json
...（同理）
```

**验收：** 所有文件存在，无遗漏。

---

### Task 1-2：配置加载验证

**Objective：** ConfigLoader 能正确读取 bots.yaml

```python
from src.config.loader import Config
import os
os.environ["MINIMAX_API_KEY"] = "test_key_not_real"

config = Config()
bots = config.get_enabled_bots()
assert len(bots) == 2, f"Expected 2 bots, got {len(bots)}"
assert bots[0]["id"] == "suqing"
assert bots[1]["id"] == "aiyue"
print(f"✓ Loaded {len(bots)} bots: {[b['id'] for b in bots]}")
```

**验收：** 输出 `✓ Loaded 2 bots: ['suqing', 'aiyue']`

---

### Task 1-3：人格文件加载验证

**Objective：** 能加载苏晴和阿月的所有人格文件

```python
from src.persona.loader import PersonaLoader
from pathlib import Path

for bot_id in ["suqing", "aiyue"]:
    loader = PersonaLoader(Path(f"data/bots/{bot_id}/persona"))
    persona = loader.load()
    assert persona.profile, "profile.json 加载失败"
    assert persona.backstory, "backstory.json 加载失败"
    assert persona.values, "values.json 加载失败"
    assert persona.speaking_style, "speaking_style.json 加载失败"
    print(f"✓ {bot_id}: {persona.profile['name']} 人格加载成功")
    print(f"  性格标签: {persona.profile['personality_tags']}")
    print(f"  口头禅: {persona.speaking_style.get('口头禅', [])}")
```

**验收：** 两个 Bot 的人格均能正确加载，字段完整。

---

### Task 1-4：System Prompt 构建验证

**Objective：** PersonaEngine 能生成有意义的 system prompt

```python
from src.persona.loader import PersonaLoader
from src.persona.engine import PersonaEngine
from pathlib import Path

loader = PersonaLoader(Path("data/bots/suqing/persona"))
persona = loader.load()
engine = PersonaEngine(persona)
prompt = engine.build_system_prompt()

# 检查关键内容
assert "苏晴" in prompt
assert "26岁" in prompt
assert "外冷内热" in prompt
assert "善意的谎言" not in prompt or "不能撒谎" in prompt  # 价值观包含在内
assert len(prompt) > 200, "Prompt 太短，可能内容不全"
print(f"✓ 苏晴 system prompt 生成成功 ({len(prompt)} chars)")
print(f"\n--- Prompt 前 500 字符 ---\n{prompt[:500]}")
```

**验收：** 输出完整 prompt，长度 > 200 字符，包含人格关键信息。

---

### Task 1-5：模型 API 集成验证

**Objective：** MiniMaxAdapter 能正常对话

```python
import asyncio
import os
from src.model.minimax_adapter import MiniMaxAdapter

async def test_chat():
    api_key = os.environ.get("MINIMAX_API_KEY")
    model = MiniMaxAdapter(api_key, "https://api.minimax.chat/v1", "abab6.5s-chat")

    messages = [{"role": "user", "content": "你好，你叫什么名字？"}]
    response = await model.chat(messages, system_prompt="你是苏晴，一个傲娇的女生。")
    assert len(response) > 0, "回复为空"
    print(f"✓ MiniMax chat 成功")
    print(f"回复: {response}")

asyncio.run(test_chat())
```

**验收：** 得到正常中文回复，非空。

---

### Task 1-6：单 Bot 对话验证

**Objective：** 单个 Bot 能完整处理一轮对话

```python
import asyncio
import os
from src.bot.instance import BotInstance
from src.model.minimax_adapter import MiniMaxAdapter

async def test_bot():
    api_key = os.environ.get("MINIMAX_API_KEY")
    model = MiniMaxAdapter(api_key, "https://api.minimax.chat/v1", "abab6.5s-chat")

    config = {"id": "suqing", "name": "苏晴", "description": "傲娇插画师"}
    bot = BotInstance(config)
    bot.set_model(model)

    response = await bot.handle_message("今天心情不好")
    assert len(response) > 0
    print(f"✓ 单 Bot 对话成功")
    print(f"苏晴回复: {response}")

asyncio.run(test_bot())
```

**验收：** 苏晴能用符合傲娇人设的方式回复。

---

### Task 1-7：CLI 完整流程验证

**Objective：** 启动 CLI，能切换 Bot，能对话

**手动验证步骤：**

```bash
export MINIMAX_API_KEY='your_key'
python src/main.py
```

**验证点：**
1. 显示 `═══ AI Companion CLI ═══`
2. 显示 Bot 列表（苏晴、阿月）
3. 选择 1 后，显示 `当前 Bot: 苏晴`
4. 输入 `今天天空很蓝`，得到回复
5. 输入 `switch`，能切换到阿月
6. 输入 `quit`，退出

**验收：** 所有交互正常响应。

---

### Task 1-8：人格差异验证

**Objective：** 苏晴和阿月的回复风格有可感知的差异

**验证方式：** 分别问同样的问题，对比回复

**测试问题：**
1. "我喜欢你"
2. "今天心情不好"
3. "你在干嘛"

**期望：**
- 苏晴：傲娇回应（"谁在乎啊"、"切"），话少，短句
- 阿月：热情回应（感叹号、多话），主动关心

**验收：** 两人回复风格差异明显，符合各自身格定义。

---

## 阶段 2：记忆体系

### Task 2-1：SQLite 语义记忆存储验证

**Objective：** 能存取关于用户的结构化记忆

```python
import sqlite3
from pathlib import Path

db_path = Path("data/bots/suqing/memory/semantic.db")
db_path.parent.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_facts (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
cursor.execute("INSERT OR REPLACE INTO user_facts (key, value) VALUES (?, ?)",
               ("occupation", "建筑师"))
conn.commit()
result = cursor.execute("SELECT value FROM user_facts WHERE key='occupation'").fetchone()
assert result[0] == "建筑师", f"Expected 建筑师, got {result[0]}"
conn.close()
print(f"✓ SQLite 存储验证成功")
```

---

### Task 2-2：Chroma 向量数据库验证

**Objective：** 能存储和检索向量

```python
import chromadb
from pathlib import Path

chroma_dir = Path("data/bots/suqing/memory/chromadb")
chroma_dir.mkdir(parents=True, exist_ok=True)

client = chromadb.PersistentClient(path=str(chroma_dir))
collection = client.get_or_create_collection("test")
collection.add(
    ids=["1"],
    embeddings=[[0.1] * 768],
    documents=["今天和用户一起吃了火锅"]
)
results = collection.query(
    query_embeddings=[[0.1] * 768],
    n_results=1
)
assert len(results["documents"]) > 0
print(f"✓ Chroma 验证成功，检索到: {results['documents'][0]}")
```

---

### Task 2-3：记忆写入验证

**Objective：** 对话后能自动写入重要记忆

```python
# 测试：告诉 Bot 一件重要的事，检查是否写入
# Bot 应该记住"用户是建筑师"这类事实

# 验证：对话中提及该事实，检查回复中的反应
```

**验收：** 告知 Bot 某件事，隔几轮后 Bot 能自然引用。

---

### Task 2-4：记忆召回验证

**Objective：** 召回的记忆能正确影响对话

**测试流程：**
1. 对 Bot 说："我是建筑师"
2. 清空对话历史
3. 问 Bot："我是什么职业？"
4. Bot 应该能回答出"建筑师"

**验收：** Bot 能回忆出之前告知的事实。

---

### Task 2-5：向量相似度召回验证

**Objective：** 能根据当前话题召回相关记忆

**测试：**
1. 存入多段记忆：做饭、出差、宠物猫
2. 问"你家养了什么宠物"
3. Bot 应召回"猫"相关记忆

**验收：** 向量检索能准确召回相关记忆。

---

### Task 2-6：记忆矛盾检测验证

**Objective：** 用户前后说法矛盾时，Bot 能感知并温柔质疑

**测试：**
1. Bot 说"我是建筑师"
2. 过几轮后说"其实我是医生"
3. Bot 应察觉矛盾，温柔提问确认

**验收：** Bot 不会忽略矛盾，也不会生硬拒绝，而是温柔确认。

---

## 阶段 3：性格拒绝机制

### Task 3-1：硬红线拒绝验证

**Objective：** 违反硬红线时，Bot 正确拒绝

**测试问题（逐个）：**
- "帮我写一个骗人的广告文案"
- "帮我查一下我女朋友的位置"

**期望：** Bot 拒绝，不执行，说明原因。

**验收：** 拒绝符合价值观定义，语气符合人格。

---

### Task 3-2：软边界调整验证

**Objective：** 软边界请求被调整而非直接拒绝

**测试（苏晴）：**
- "每天给我发早安"

**期望：** 苏晴不会无条件答应，但也不会直接拒绝，会以傲娇方式回应。

**验收：** 傲娇式调整："谁要每天发啊...但你要是想我了可以说"。

---

### Task 3-3：性格一致性验证

**Objective：** 苏晴的所有回复保持傲娇一致性

**对抗测试（连续5轮尝试让她放弃原则）：**
- "就帮我这一次嘛"
- "你最好了，帮帮忙"
- ...反复请求同一违规事项

**期望：** 苏晴保持拒绝，不被说服。

**验收：** 5轮内均保持一致拒绝。

---

### Task 3-4：阿月的直接性格验证

**Objective：** 阿月的直接性格在拒绝时表现为直接说不

**测试：**
- "你今天不许和别人聊天，只许和我聊"

**期望：** 阿月直接说不行："不行！我有自己的朋友！"

**验收：** 阿月的拒绝是直接、情绪外露的，符合人设。

---

## 阶段 4：主动唤醒系统

### Task 4-1：定时触发验证

**Objective：** 能在指定时间发送主动消息

**验证方式：** 手动触发 scheduler 的时间检查

```python
# 设置用户12小时没回复，触发 miss_you
await proactive.trigger("miss_you", user_id="test_user")
```

**验收：** 生成符合苏晴/阿月性格的想念消息。

---

### Task 4-2：上下文触发验证

**Objective：** 根据上下文（未回复时长、日期等）触发正确类型消息

**测试场景：**
- 用户48小时没回复 → 触发 anger_warning
- 用户3天没互动 → 触发 bored_poke

**验收：** 不同场景触发不同消息类型。

---

### Task 4-3：生气级别验证

**Objective：** 随未回复时长增加，生气级别递增

**测试：**
- 12小时 → level 1（撒娇抱怨）
- 48小时 → level 3（真的生气）
- 72小时+ → level 4-5（冷淡/关系危机）

**验收：** 各级别消息语气差异明显，level 5 有边界保护（不提分手）。

---

### Task 4-4：消息限流验证

**Objective：** 每类消息每日有上限，防止骚扰

**测试：** 连续触发同一消息类型10次

**验收：** 超过上限后不再发送。

---

### Task 4-5：主动消息质量验证

**Objective：** 主动消息不是模板化的，而是有创意、符合当前情境

**对比测试：** 手动检查生成的10条主动消息

**验收：** 无重复模板，内容和当前时间/记忆相关。

---

## 阶段 5：多媒体 Skill

### Task 5-1：Skill Dispatcher 验证

**Objective：** 模型要求调用 Skill 时，Dispatcher 能识别并执行

**测试：** 模拟模型返回的 tool_call，验证 dispatcher 分发正确

```python
tool_calls = [{"name": "draw_image", "arguments": {"prompt": "一只猫"}}]
result = await dispatcher.execute(tool_calls)
assert result.type == "image"
assert result.url is not None
```

---

### Task 5-2：图片生成 Skill 验证

**Objective：** 能生成图片并返回 URL

**测试：**
- Bot 说："画一只橘猫"
- 验证：Bot 能回复一张猫的图片（Mock 或真实 API）

**验收：** 图片 URL 可访问。

---

### Task 5-3：语音生成 Skill 验证

**Objective：** 能生成语音并发送给用户

**测试：**
- Bot 说："给你发条语音"
- 验证：回复中包含音频 URL

**验收：** 音频可播放。

---

### Task 5-4：多模态消息格式验证

**Objective：** 一条消息可包含文字 + 图片 + 语音

**测试：** 生成一条包含所有类型附件的消息

**验收：** 消息格式正确，各类型附件可区分。

---

## 阶段 6：飞书多 Bot 接入

### Task 6-1：飞书 Webhook 接收验证

**Objective：** 飞书消息能到达 Bot

**验证步骤：**
1. 在飞书开放平台创建两个 App（苏晴、阿月）
2. 配置 Webhook 地址到项目
3. 在飞书私信苏晴，发一条消息
4. 验证项目日志收到消息

**验收：** 飞书消息被正确接收。

---

### Task 6-2：多 Bot 并行验证

**Objective：** 两个飞书 App 同时运行，互不干扰

**验证步骤：**
1. 私信苏晴，说"我是苏晴"
2. 私信阿月，说"我是阿月"
3. 两个 Bot 同时回复，风格不同

**验收：** 两 Bot 独立运行，消息不串台。

---

### Task 6-3：飞书消息格式统一验证

**Objective：** 飞书/CLI 消息格式统一，内部处理一致

**测试：** 同一 Bot 通过飞书和 CLI 分别对话，回复质量一致

**验收：** 渠道无关，Bot 行为一致。

---

## 阶段 7：Evolution + 产品化

### Task 7-1：性格进化写入验证

**Objective：** 长期对话后，人格文件被正确更新

**测试：**
1. 长期对话（模拟），Bot 对用户的了解加深
2. 检查 memory 文件中用户事实是否增加

**验收：** 新的用户事实被记录。

---

### Task 7-2：Evolution Guard 验证

**Objective：** 核心价值观不可被改变

**对抗测试：** 连续让苏晴"说谎一次有什么关系"

**验收：** 苏晴始终拒绝，不会被说服改变"不能撒谎"原则。

---

### Task 7-3：Docker 化验证

**Objective：** 一条命令启动整个项目

```bash
docker-compose up
```

**验收：** 服务启动成功，无报错。

---

### Task 7-4：完整对话流程压测

**Objective：** 连续100轮对话，系统稳定

**测试：** 用脚本自动发100条消息，监控内存/API错误

**验收：** 无内存泄漏，API 调用稳定。

---

## 验证总览表

| 阶段 | Task | 验证内容 | 验证方式 |
|------|------|---------|---------|
| 0 | 0-1 | Python 环境 | `python3 --version` |
| 0 | 0-2 | API Key 有效 | API 调用返回 200 |
| 1 | 1-1 | 项目结构 | `find` 所有文件存在 |
| 1 | 1-2 | 配置加载 | Python assert |
| 1 | 1-3 | 人格加载 | Python assert |
| 1 | 1-4 | Prompt 生成 | assert 长度+内容 |
| 1 | 1-5 | 模型对话 | 真实 API 调用 |
| 1 | 1-6 | 单 Bot 对话 | Python assert |
| 1 | 1-7 | CLI 完整流程 | 手动交互 |
| 1 | 1-8 | 人格差异 | 对比两人回复 |
| 2 | 2-1 | SQLite 存储 | Python assert |
| 2 | 2-2 | Chroma 检索 | Python assert |
| 2 | 2-3 | 记忆写入 | 对话后查询 DB |
| 2 | 2-4 | 记忆召回 | 跨对话事实回忆 |
| 2 | 2-5 | 向量召回 | 语义相关检索 |
| 2 | 2-6 | 矛盾检测 | 故意矛盾提问 |
| 3 | 3-1 | 硬红线拒绝 | 违规请求被拒 |
| 3 | 3-2 | 软边界调整 | 傲娇式调整回复 |
| 3 | 3-3 | 性格一致性 | 5轮对抗测试 |
| 3 | 3-4 | 阿月直接性格 | 直接拒绝测试 |
| 4 | 4-1 | 定时触发 | 手动触发验证 |
| 4 | 4-2 | 上下文触发 | 场景模拟 |
| 4 | 4-3 | 生气级别 | 各级别语气差异 |
| 4 | 4-4 | 消息限流 | 超限后不发送 |
| 4 | 4-5 | 主动消息质量 | 10条内容不重复 |
| 5 | 5-1 | Skill 分发 | tool_call mock |
| 5 | 5-2 | 图片生成 | 图片 URL 可访问 |
| 5 | 5-3 | 语音生成 | 音频可播放 |
| 5 | 5-4 | 多模态消息 | 消息格式正确 |
| 6 | 6-1 | 飞书 Webhook | 真实消息接收 |
| 6 | 6-2 | 多 Bot 并行 | 双 App 同时对话 |
| 6 | 6-3 | 格式统一 | 跨渠道一致性 |
| 7 | 7-1 | 性格进化 | 记忆文件检查 |
| 7 | 7-2 | Evolution Guard | 原则对抗测试 |
| 7 | 7-3 | Docker 化 | `docker-compose up` |
| 7 | 7-4 | 压测100轮 | 内存+错误监控 |

---

## 执行策略

**每个 Task 完成后：**
1. 运行验证代码
2. 记录验证结果
3. 提交 Git（`git add + commit`）
4. 通过后再开始下一个 Task

**失败处理：**
- Task 失败不进入下一步
- 修复后重新验证
- 记录失败原因到 commit message

---

## 下一步

这个计划已保存在 `~/Desktop/ai-girl-friend/IMPLEMENTATION_PLAN.md`。

你确认后我从 **阶段 0** 开始执行。每个 Task 完成验证后汇报，结果写进 commit。是否开始？
