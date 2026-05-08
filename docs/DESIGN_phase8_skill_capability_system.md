# Skill 能力配置化与自动路由设计（Phase 8）

> 文档目的：把 Skill 从“可安装工具”升级为“配置即能力、自动可用”的统一能力系统  
> 最后更新：2026-05-08  
> 状态：设计评审版（可直接按步骤实施）

---

## 1. 背景与问题

当前仓库已有 Skill 框架，但在“能力发现”和“自动调用”上存在断层，导致用户体验不一致。

### 1.1 现状（基于代码）

1. `BotInstance` 会注册内置技能 `image_generation`、`tts`，并加载已安装技能：  
   [ai_companion/bot/instance.py](/Users/wangxiaowei/projects/own/ai-girl-friend/ai_companion/bot/instance.py:145)

2. `BotInstance` 读取技能配置来源是 `bot_config["skills"]`，即每个 Bot 的配置对象：  
   [ai_companion/bot/instance.py](/Users/wangxiaowei/projects/own/ai-girl-friend/ai_companion/bot/instance.py:44)

3. 启动流程中传给 `BotInstance` 的 `bot_config` 来自 `bots.yaml`（启用 Bot 列表），未自动合并 `models.yaml.skills`：  
   [ai_companion/main.py](/Users/wangxiaowei/projects/own/ai-girl-friend/ai_companion/main.py:101)  
   [ai_companion/config/loader.py](/Users/wangxiaowei/projects/own/ai-girl-friend/ai_companion/config/loader.py:64)

4. 普通对话路径不会自动调用 skill，只有显式 `/skill ...` 才执行：  
   [ai_companion/bot/instance.py](/Users/wangxiaowei/projects/own/ai-girl-friend/ai_companion/bot/instance.py:568)  
   [ai_companion/skill/command.py](/Users/wangxiaowei/projects/own/ai-girl-friend/ai_companion/skill/command.py:127)

5. 网关已支持媒体消息归一化，`MessageEvent` 里有 `media_urls` / `media_types`，可用于图片理解入口：  
   [ai_companion/gateway/platforms/base.py](/Users/wangxiaowei/projects/own/ai-girl-friend/ai_companion/gateway/platforms/base.py:694)

### 1.2 当前痛点

1. 文档和代码对 skill 配置位置不一致，用户难以配置成功。
2. 用户配置了能力也不会自动生效，仍需手动 `/skill` 指令。
3. `/skills` 与 `skill list` 对“已安装 vs 已注册”概念混淆，排障困难。
4. 缺少“能力可用性原因”可视化（未配 key、依赖缺失、provider 不支持）。

---

## 2. 目标与范围

## 2.1 核心目标

1. 图片生成能力：配置后自动支持，未配置则明确不可用。
2. 图片理解能力：配置后自动支持，未配置则明确不可用。
3. 配置驱动：能力是否存在、是否自动调用，由配置和可用性决定。
4. 自动路由：用户自然语言和媒体输入可触发能力，无需 `/skill`。

## 2.2 非目标（本阶段不做）

1. 不做复杂多步 Agent Planner（先规则路由，后续可升级）。
2. 不一次性接入所有第三方平台工具（先打通核心框架）。
3. 不改动三层记忆核心结构（仅补充 skill 结果注入点）。

---

## 3. 设计原则

1. 配置优先：能力启用必须可配置、可追踪、可解释。
2. 默认安全：未配置即禁用，不做隐式外部请求。
3. 可观测：每次自动调用都要有日志和状态。
4. 向后兼容：保留 `/skill` 显式调用，自动调用为增量能力。
5. 分层清晰：配置解析、能力注册、路由决策、执行反馈分开。

---

## 4. 目标架构

```text
Config (models.yaml + bots.yaml)
        ↓
CapabilityResolver（解析有效技能配置）
        ↓
BuiltinSkillManager（按可用性注册内置技能）
        ↓
AutoSkillRouter（文本意图/媒体输入自动路由）
        ↓
SkillDispatcher.execute(...)
        ↓
Bot 响应拼装（文本/图片/语音/结构化结果）
```

---

## 5. 配置方案（统一与兼容）

## 5.1 配置来源与优先级

为减少破坏，采用“双来源 + 明确优先级”：

1. `bots.yaml` 中每个 bot 的 `skills`（最高优先级，bot 级覆盖）
2. `models.yaml` 中 `skills`（全局默认）
3. 未出现则视为未配置

合并策略：按 skill 名深度合并，bot 级覆盖同名字段。

## 5.2 推荐配置结构

```yaml
skills:
  image_generation:
    enabled: true
    auto: true
    provider: minimax
    model: image-01
    api_key: "${MINIMAX_API_KEY}"
    output_dir: "data/bots/_images"

  image_understanding:
    enabled: true
    auto: true
    provider: openai
    model: gpt-4o
    api_key: "${OPENAI_API_KEY}"
    max_image_size_mb: 8
    max_images_per_message: 3
```

## 5.3 兼容旧配置

已有 `skills.image_generation.model: minimax` 风格配置继续支持，规范化为新字段：

1. `provider` 缺省时从旧 `model` 推断。
2. `enabled` 缺省默认为 `true`（仅对已配置 skill 生效）。
3. `auto` 缺省：
   `image_generation`、`image_understanding` 默认为 `true`；其他 skill 默认为 `false`。

---

## 6. 能力模型与状态

新增统一能力状态对象（供 prompt、UI、日志、命令复用）：

```python
CapabilityStatus = {
  "name": "image_understanding",
  "enabled": True,         # 配置开关
  "auto": True,            # 是否可自动路由
  "registered": True,      # 是否已注册到 dispatcher
  "available": True,       # runtime 可用性（依赖/API/配置完整）
  "reason": "",            # 不可用时原因（缺 key、依赖缺失、provider 不支持）
  "provider": "openai",
  "model": "gpt-4o"
}
```

用途：

1. `/skills` 输出增强。
2. system prompt 注入可用能力摘要。
3. 管理后台展示能力健康度。

---

## 7. 关键模块设计

## 7.1 `CapabilityResolver`

新文件建议：`ai_companion/skill/capability_resolver.py`

职责：

1. 读取全局与 bot 级技能配置并合并。
2. 兼容旧字段并规范化。
3. 生成 `CapabilityStatus` 初始对象（不做执行）。

输入：

1. `config.models["skills"]`（全局）
2. `bot_config["skills"]`（bot 级）
3. 环境变量（只做存在性判断）

输出：

1. `resolved_skill_config: dict`
2. `capability_statuses: dict[str, CapabilityStatus]`

## 7.2 `BuiltinSkillManager`

新文件建议：`ai_companion/skill/builtin_manager.py`

职责：

1. 按解析后的配置实例化并注册内置 skill。
2. 对每个内置 skill 做 `is_available` 检查，填充状态原因。
3. 只注册 `enabled=true` 的技能。

首批内置：

1. `image_generation`（已有，配置化改造）
2. `image_understanding`（新增）
3. `tts`（已有，纳入统一状态）

## 7.3 `ImageUnderstandingSkill`

新文件：`ai_companion/skill/image_understanding.py`

能力：

1. 输入：`image_paths`/`image_urls` + 可选 `prompt`
2. 输出：`SkillResult(content_type="text")`，内容为结构化理解结果

推荐统一输出结构：

```json
{
  "summary": "...",
  "objects": ["..."],
  "text_ocr": "...",
  "safety_notes": [],
  "confidence": 0.0
}
```

provider 支持（Phase 1）：

1. `openai`（视觉模型）
2. `minimax`（若支持视觉接口）
3. `custom`（OpenAI-compatible / 自定义模板）

## 7.4 `AutoSkillRouter`

新文件建议：`ai_companion/skill/auto_router.py`

职责：

1. 文本意图路由：画图请求 -> `image_generation`
2. 媒体路由：消息含图片 -> `image_understanding`
3. 执行后返回统一结果给 `BotInstance`

Phase 1 路由规则：

1. 图片消息优先：先走 `image_understanding`
2. 文本关键词命中画图意图：走 `image_generation`
3. 否则不拦截，走原聊天路径

## 7.5 `BotInstance` 接入点

改造文件：`ai_companion/bot/instance.py`

改动点：

1. 初始化时引入 `CapabilityResolver` + `BuiltinSkillManager`。
2. 在 `handle_message` 普通对话前执行 `AutoSkillRouter.try_handle(...)`。
3. `_build_system_prompt` 附加能力摘要（仅可用能力）。
4. `get_skill_capabilities()` 改为返回 `CapabilityStatus`，不再只读 dispatcher。

---

## 8. 消息与上下文设计

## 8.1 统一输入模型（不破坏现有 `MessageEvent`）

保留 `event.text`，并把媒体信息通过可选上下文透传：

```python
runtime_input = {
  "text": "...",
  "media_urls": [...],   # 来自 MessageEvent.media_urls
  "media_types": [...],  # 来自 MessageEvent.media_types
}
```

CLI 场景无媒体则为空数组。

## 8.2 图片理解结果注入策略

当 `image_understanding` 成功时，路由器返回：

1. `bot_visible_context`：供本轮对话补充理解结果
2. `user_facing_hint`：可选（如“我看到了这张图里的...”）

注入形式示例：

```text
[图片理解结果]
图片摘要: ...
识别到元素: ...
OCR文本: ...
```

然后继续走原 `memory.load_context` + `chat` 流程，确保人格和记忆保持一致。

---

## 9. 命令与可观测性

## 9.1 `/skills` 与 `skill list`

目标：区分“安装状态”和“运行时能力状态”。

新增建议：

1. `/skills`：显示运行时能力（内置 + 安装）
2. `python -m ai_companion skill list --json` 增加 `--runtime` 视图

展示字段：

1. `name`
2. `source`（builtin/installed）
3. `enabled`
4. `auto`
5. `available`
6. `reason`
7. `provider`/`model`

## 9.2 日志规范

新增日志标签：

1. `[CapabilityResolver]`
2. `[BuiltinSkillManager]`
3. `[AutoSkillRouter]`
4. `[ImageUnderstandingSkill]`

关键日志点：

1. 配置解析结果
2. 自动路由命中/未命中
3. skill 执行耗时
4. 失败原因与降级路径

---

## 10. 分阶段实施计划（可直接执行）

## Phase 8.1 配置与能力状态打通（P0）

目标：让能力由配置决定，并且可观测。

步骤：

1. 新增 `capability_resolver.py` 和 `builtin_manager.py`。
2. 改 `BotInstance` 初始化：通过 resolver + manager 注册内置技能。
3. 把 `get_skill_capabilities()` 改为返回完整能力状态。
4. 增强 `/skills` 输出，显示内置技能状态和原因。
5. 更新 `config/*.example` 和 `docs/GUIDE.md` 的技能配置说明。

验收标准：

1. 未配置 `image_generation` 时，能力状态为 disabled 且不会被注册。
2. 配置不完整时，状态为 enabled 但 unavailable，且有明确 reason。
3. `hello` 这类安装技能与内置技能能同时展示。

## Phase 8.2 图片理解能力接入（P0）

目标：用户发图片可自动被理解。

步骤：

1. 新增 `image_understanding.py`。
2. 在 `BuiltinSkillManager` 中注册该技能。
3. 路由入口接入 `MessageEvent.media_urls/media_types`。
4. 图片理解结果注入对话上下文再调用主聊天模型。

验收标准：

1. 发图片消息时，若能力可用，bot 能结合图片内容回复。
2. 未配置能力时，bot 清楚提示“当前未启用图片理解能力”。
3. 图片下载/缓存异常时，不阻断文本对话。

## Phase 8.3 自动路由（P0）

目标：无需 `/skill` 也能触发图片能力。

步骤：

1. 新增 `auto_router.py`。
2. 在 `BotInstance.handle_message` 中加入 `try_handle`。
3. 先实现规则路由（图片优先、画图关键词命中）。
4. 支持 `skills.<name>.auto=false` 强制关闭自动路由。

验收标准：

1. “帮我画一张…” 自动调用 `image_generation`。
2. 用户发图并提问，自动调用 `image_understanding`。
3. `auto=false` 时仅 `/skill` 显式调用可触发。

## Phase 8.4 回归与文档收口（P0）

目标：保证升级不破坏现有能力。

步骤：

1. 增加单测和集成测试（见第 11 节）。
2. 补管理后台能力状态接口字段（可选）。
3. 更新用户文档和 FAQ。

验收标准：

1. 旧 `/skill` 行为保持可用。
2. 无媒体场景对话路径无回归。
3. Gateway/CLI 两种入口行为一致。

---

## 11. 测试计划

## 11.1 单元测试

建议新增：

1. `tests/skill/test_capability_resolver.py`
2. `tests/skill/test_builtin_manager.py`
3. `tests/skill/test_auto_router.py`
4. `tests/skill/test_image_understanding.py`

覆盖点：

1. 配置合并优先级。
2. enabled/available 判定。
3. 自动路由命中与关闭。
4. provider 错配与缺 key 错误提示。

## 11.2 集成测试

1. CLI 文本触发画图：验证自动路由。
2. Gateway 图片消息：验证图片理解注入。
3. `/skills` 输出：验证状态可观测。

## 11.3 回归命令

```bash
python -m compileall -q ai_companion
python tests/system_test_suite.py
python -m ai_companion skill list --json
```

---

## 12. 迁移与兼容策略

1. 不删除旧配置字段，先做兼容映射。
2. 现有安装技能目录不变：`~/.ai-companion/data/bots/_skills/`
3. `ai-companion skill ...` 和 `python -m ai_companion skill ...` 都保留。
4. 先增加能力状态输出，再逐步引导新配置格式。

---

## 13. 风险与对策

1. 风险：自动路由误触发，影响闲聊体验。  
   对策：`auto` 开关 + 置信度阈值 + 可回退 `/skill`。

2. 风险：图片理解延迟增加首字节时间。  
   对策：限制图片数/大小，增加超时和降级文本路径。

3. 风险：配置来源混乱导致“看起来配置了但不生效”。  
   对策：统一 `CapabilityStatus.reason`，启动时打印解析来源。

4. 风险：provider 行为差异导致结果格式不稳定。  
   对策：skill 内统一输出 schema，适配层做 provider 归一化。

---

## 14. 本阶段推荐内置 Skill 优先级

## P0（本设计必须完成）

1. `image_generation`
2. `image_understanding`
3. `memory_update`
4. `reminder`
5. `web_search`
6. `url_reader`
7. `file_reader`

## P1（完成 P0 后）

1. `tts`
2. `asr`
3. `weather`
4. `current_time`
5. `diary_daily_review`

## P2（后续扩展）

1. `browser_automation`
2. `gmail/notion/calendar` 第三方深度集成
3. `shell/code_interpreter` 高权限工具

---

## 15. 执行清单（一步步照做）

1. 新增 resolver/manager/router/图片理解四个模块骨架。
2. 改造 `BotInstance` 初始化和 `handle_message` 接入新链路。
3. 改造 `/skills` 输出能力状态。
4. 补 `models.yaml.example` 与 `bots.yaml.example` 的新配置示例。
5. 写单测与两条集成路径（文本画图、图片理解）。
6. 跑 `compileall` + `system_test_suite`。
7. 更新 `docs/GUIDE.md` 与 FAQ，标注迁移说明。

完成上述 7 步后，即可实现“用户不配置就不支持，配置后自动支持”的目标。

