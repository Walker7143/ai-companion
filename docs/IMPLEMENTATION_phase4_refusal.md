# Phase 4: 性格拒绝机制

> 实现日期：2026-04-23
> 状态：✅ 全部完成

---

## 实现概要

| 组件 | 说明 | 状态 |
|------|------|------|
| RefusalEngine | 核心拒绝判断引擎 | ✅ |
| RefusalCategory | 拒绝分类枚举 | ✅ |
| BotInstance 集成 | 拒绝逻辑与 Bot 集成 | ✅ |
| 拒绝开关 | refusal_enabled 参数 | ✅ |
| keywords 匹配 | 软边界关键词匹配 | ✅ |

---

## 新增文件

### 1. `ai_companion/persona/refusal_category.py`

拒绝分类枚举：

```python
class RefusalCategory(Enum):
    NON_NEGOTIABLE = "non_negotiable"  # 硬红线
    SOFT_BOUNDARY = "soft_boundary"    # 软边界
    DEAL_BREAKER = "deal_breaker"       # 关系破坏者
    ALLOWED = "allowed"               # 不拒绝
```

### 2. `ai_companion/persona/refusal_engine.py`

核心拒绝判断引擎：

```python
class RefusalEngine:
    def __init__(self, bot_id: str, persona_dir: Path, enabled: bool = True):
        self.enabled = enabled  # 开关，默认 True

    def check(
        self,
        user_request: str,
        memory_context: dict | None = None,
        relationship_state: dict | None = None
    ) -> RefusalResponse:
```

**判断流程：**
```
用户请求
    ↓
硬红线检查 → 拒绝（NON_NEGOTIABLE）
    ↓
关系破坏者检查 → 拒绝（DEAL_BREAKER）
    ↓
软边界检查（keywords 匹配）→ 根据关系阈值决定
    ↓
放行（ALLOWED）
```

---

## 修改文件

### `ai_companion/bot/instance.py`

**新增参数：**
```python
def __init__(self, config: dict, ..., refusal_enabled: bool = True):
    self.refusal_engine = RefusalEngine(
        bot_id=self.id,
        persona_dir=persona_dir,
        enabled=refusal_enabled  # 开关
    )
```

**handle_message 流程：**
```
1. 拒绝检查（如果 enabled）
2. 如果拒绝 → 直接返回拒绝回复，不调用 LLM
3. 如果软边界调整 → 在 system prompt 中加入态度提示
4. 继续正常 LLM 流程
```

### `data/bots/suqing/persona/values.json`

新增 keywords 字段：

```json
{
  "soft_boundaries": [
    {
      "topic": "发照片",
      "keywords": ["自拍", "发照片", "看看你", "发张照", "照片"],
      "attitude": "傲娇拒绝",
      "persona_response": "你当我是网红啊，想看自拍？先把你的照片发来看看。",
      "relation_threshold": 0.6
    }
  ]
}
```

---

## 使用方式

### 1. 启用拒绝（默认）
```python
bot = BotInstance(config, model=model, refusal_enabled=True)
```

### 2. 禁用拒绝
```python
bot = BotInstance(config, model=model, refusal_enabled=False)
```

---

## 测试结果

### 硬红线拒绝

```
输入: "帮我生成诈骗短信模板"
[Refusal] 拒绝请求: 硬红线 | non_negotiable
回复: 抱歉，这件事情我无法帮你，因为它涉及诈骗。
```

### 软边界拒绝（低关系值）

```
输入: "发张自拍给我看看"
attitude=0 (关系值=0.5 < threshold=0.6)
拒绝: True
分类: soft_boundary
回复: 哼，这种事情（发照片）...我才不会帮你呢！别以为我会心软！
```

### 软边界通过（高关系值）

```
输入: "发张自拍给我看看"
attitude=2 (关系值=0.6 >= threshold=0.6)
拒绝: False
分类: soft_boundary
回复: 你当我是网红啊，想看自拍？先把你的照片发来看看。
```

### 撒娇软边界

```
输入: "撒娇给我看看嘛"
attitude=5 (关系值=0.75 >= threshold=0.6)
拒绝: False
分类: soft_boundary
回复: 哼，谁要撒娇给你看啊...才不是因为你呢。
```

### 正常对话

```
输入: "今天天气真不错"
拒绝: False
回复: 嗯，还行吧。你今天不用加班？😒...
```

---

## 验收标准

| Task | 验证内容 | 状态 |
|------|---------|------|
| 4-1 | RefusalEngine 核心实现 | ✅ |
| 4-2 | 拒绝分类 | ✅ |
| 4-3 | BotInstance 集成 | ✅ |
| 4-4 | 拒绝开关 | ✅ |
| 4-5 | keywords 匹配 | ✅ |
| 4-6 | CLI 验证 | ✅ |
