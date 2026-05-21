# Proactive Style Alignment Design

## Goal

让主动唤醒消息与日常对话在风格、记忆承接方式和输出质感上保持一致，同时保留主动唤醒自身的触发时机、动机表达和短消息特征。

## Current Problem

当前系统里，日常对话与主动唤醒分别走两条不同的生成链：

- 日常对话通过 `PersonaEngine.build_system_prompt()` 组装完整人格提示，并叠加 `MemoryPromptBuilder` 产出的记忆 suffix，再经过 `ResponseStylePolisher` 做输出清洗与自然化。
- 主动唤醒通过 `ProactiveEngine` 内部的专用 prompt 模板直接向模型发起请求，只拼接主动消息需要的少量人格片段和上下文。

这会导致两个体感问题：

1. 主动唤醒“像这个 bot”，但不像它平时真实聊天时的完整说话方式。
2. 主动唤醒对用户记忆的引用更像“资料拼接”，而不是日常对话那种自然承接。

## Design Principles

- 不重写主动唤醒的触发逻辑、动机模型和发送流程。
- 只对齐“说话像不像同一个人”的关键层：共享风格规则、共享记忆承接方式、共享输出后处理。
- 主动唤醒仍然保持“短、顺手、像熟人突然发来一句”的产品特征，不直接变成完整聊天回复。

## Proposed Architecture

### 1. Shared prompt style block

在 `PersonaEngine` 中抽出一段可复用的“共享风格规则”文本，供日常对话和主动唤醒共同使用。

这一块应包含：

- 真实人设与非 AI 约束
- 日常聊天先接情绪和重点
- 不要说明文、不要总总结/列点
- 不要机械复述用户画像
- 保持人格中的情绪、边界和分寸
- 基于 `speaking_style.json`、`conversation_style_rules.json` 的自然表达要求

日常对话继续保留完整 `build_system_prompt()`；主动唤醒新增对共享风格规则的调用，把它显式拼进主动消息 prompt。

### 2. Shared memory carry style

主动唤醒不再优先使用整份 `user_understanding.format_for_prompt()` 作为主上下文，而是尽量改为类似日常对话的“分层短承接”。

具体策略：

- 优先保留主动唤醒现有的：
  - 最近对话
  - 动机上下文
  - 今日连续性
  - 关系状态
  - 长期用户理解摘要
- 增加一个更接近日常对话的共享记忆 suffix：
  - 使用 `MemoryPromptBuilder` 对 `RetrievedMemory(intent="proactive_generation")` 生成压缩版 suffix
  - 主动唤醒 prompt 明确说明：这些内容只影响语气、承接方式和分寸，不要像翻档案或复述资料

这样主动唤醒仍然是“主动消息专用 prompt”，但其记忆组织方式更接近日常对话。

### 3. Shared output polishing

主动唤醒生成结果在结构化解析与占位符清洗之后，接入与日常对话一致的 `ResponseStylePolisher` 能力：

- 去掉 AI/助手腔
- 去掉记忆解释腔
- 在合适场景下压掉过长、过像说明文的回复
- 保留口语感

主动唤醒的后处理参数建议固定为：

- `intent="proactive_generation"`
- `relationship_state` 使用当前关系状态
- `user_understanding` 使用当前用户理解摘要

## File-Level Changes

### `ai_companion/persona/engine.py`

- 新增一个可复用的共享风格构建方法，例如：
  - `build_shared_style_prompt(...)`
- 保持现有 `build_system_prompt()` 输出不变，改为在内部复用共享风格块，避免重复规则漂移。

### `ai_companion/proactive/engine.py`

- 接入共享风格 prompt 块
- 接入共享记忆 suffix / 更自然的主动记忆承接
- 在 `generate_message()` / `generate_contextual_message()` / `_regenerate_proactive_message()` 成功生成后统一走共享后处理
- 保留主动消息现有的：
  - 动机 prompt
  - 时间线约束
  - 生活锚点约束
  - 结构化消息解析与占位兜底

### `ai_companion/bot/response_style.py`

- 视需要为 `proactive_generation` 加轻量节奏约束，确保主动消息更短、更像随手发来的一句。
- 不引入会改变日常对话现有行为的激进规则。

### Tests

- 扩充 `tests/proactive_engine_test.py`
- 验证主动唤醒 prompt 已包含共享风格规则
- 验证主动唤醒 prompt 包含共享记忆 suffix 或等价的共享记忆承接文本
- 验证主动消息生成结果会经过 `ResponseStylePolisher` 风格清洗

## Error Handling

- 如果主动唤醒无法读取共享记忆 suffix，降级为当前已有的主动记忆上下文，不影响消息发送。
- 如果共享风格块读取失败，降级为当前主动唤醒已有的 `persona_style_context`。
- 后处理必须保持保守，不能凭空改写语义，只做去 AI 味和节奏收束。

## Testing Strategy

- 现有主动唤醒测试继续保留，确保不回退已有占位符修复和时间线约束。
- 新增定向测试覆盖：
  - prompt 中共享风格规则注入
  - prompt 中共享记忆承接注入
  - 主动输出经过风格清洗
- 至少运行：
  - `PYTHONPATH=. python tests/proactive_engine_test.py`
  - `python -m compileall -q ai_companion`

## Scope Boundaries

本次不做：

- 重写 `ProactiveOrchestrator` / scheduler / motive 触发逻辑
- 把主动唤醒改造成完整聊天式多轮回复
- 重构整套 memory retrieval pipeline
- 修改 bot persona 配置文件格式

## Expected Outcome

修改后，主动唤醒与日常聊天应当：

- 更像同一个人在说话
- 更少出现“模板味”“资料味”“说明文味”
- 在关系承接和记忆带入上更自然
- 同时保留主动消息短、轻、顺手的特点
