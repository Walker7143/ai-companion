# 修复进度（2026-04-28）

说明：每修复一项立即更新状态和验证结果，避免上下文丢失。

## 总体状态

- 当前阶段：已完成本轮系统级修复
- 基线测试：`.artifacts/system-test-rebuilt-2026-04-28-103028/`（PASS 10 / FAIL 7）
- 修复后全量回归：`.artifacts/system-test-rebuilt-2026-04-28-105232/`（PASS 17 / FAIL 0 / ERROR 0）
- 最终确认回归：`.artifacts/system-test-rebuilt-2026-04-28-105643/`（PASS 17 / FAIL 0 / ERROR 0）
- 本轮新增修复回归：`.artifacts/system-test-rebuilt-2026-04-28-174342/`（PASS 21 / FAIL 0 / ERROR 0）
- 人生轨迹 prompt 修复回归：`.artifacts/system-test-rebuilt-2026-04-28-191830/`（PASS 22 / FAIL 0 / ERROR 0）
- 运行时设置刷新修复回归：`.artifacts/system-test-rebuilt-2026-04-28-192333/`（PASS 23 / FAIL 0 / ERROR 0）
- 主动发送与日常事件 JSON 容错回归：`.artifacts/system-test-rebuilt-2026-04-28-194144/`（PASS 25 / FAIL 0 / ERROR 0）
- 日常小事保留上限回归：`.artifacts/system-test-rebuilt-2026-04-28-205319/`（PASS 26 / FAIL 0 / ERROR 0）
- 人生大事具体化回归：`.artifacts/system-test-rebuilt-2026-04-28-210257/`（PASS 27 / FAIL 0 / ERROR 0）

## 修复项状态

| ID | 问题 | 优先级 | 状态 | 修复点 | 验证 |
|---|---|---|---|---|---|
| F1 | 前端构建失败（TS 报错） | P0 | done | `ai-companion-ui/src/pages/Logs/Logs.tsx`、`ai-companion-ui/src/pages/Memory/Memory.tsx` | `T15=PASS`，`npm run build` 通过 |
| F2 | Proactive `mode=silent` 失效 | P1 | done | `ai_companion/proactive/config.py`（`is_active` 按 `enabled && mode=="active"` 计算） | `T09=PASS` |
| F3 | Proactive 重复发送 | P1 | done | `ai_companion/proactive/scheduler.py`（去除重复通知发送） | `T10=PASS` |
| F4 | LifeEngine 未注入 persona_loader | P1 | done | `ai_companion/bot/instance.py`（注入 `self.persona_loader`） | `T08=PASS` |
| F5 | Main/Gateway 未走 ModelFactory | P1 | done | `ai_companion/model/factory.py`、`ai_companion/main.py`、`ai_companion/gateway/cmd.py` | `T11=PASS` |
| F6 | UI provider 枚举不一致 | P2 | done | `ai-companion-ui/src/pages/Settings/Settings.tsx`（`anthropic` -> `claude`） | `T13=PASS` |
| F7 | UI 清空记忆 no-op | P2 | done | `ai-companion-ui/src/api/index.ts` + `ai_companion/gateway/cmd.py` 新增删除接口 | `T14=PASS` |
| F8 | `silent` 模式误伤人生轨迹调度器 | P1 | done | `ai_companion/bot/instance.py`（LifeScheduler 改为独立启动，不依赖 proactive active） | 定向验证：`silent` 下 `proactive_running=False` 且 `life_scheduler.running=True`，并发生 tick |
| F9 | 旧版扁平 proactive 配置参数被忽略 | P1 | done | `ai_companion/proactive/config.py`（新增旧配置归一化逻辑） | 定向验证：`check_interval/idle/max_daily/platform/emotion` 等扁平参数均可生效 |
| F10 | 观察用三类测试 Bot 缺失 | P2 | done | `~/.ai-companion/data/bots/` 新建 3 个测试 Bot，`~/.ai-companion/config/bots.yaml` 注册启用 | `ai-companion bot list` 可见 3 个新 Bot，离线初始化验证通过 |
| F11 | CLI 启动即全量推进人生轨迹，不符合按需启动 | P1 | done | `ai_companion/bot/instance.py`（`init(start_schedulers=False)` + 首次对话按需启动调度器）、`ai_companion/main.py`（CLI 改为延迟调度器启动） | 定向验证：首次发消息前 `life_scheduler/proactive_scheduler` 不启动，发消息后仅当前 Bot 启动；全量回归 PASS 17 |
| F12 | CLI 选中 Bot 后仍需首条消息才启动轮询，不符合交互预期 | P1 | done | `ai_companion/cli/adapter.py`（选中/切换时立即调用 `ensure_schedulers_started()`）、`ai_companion/bot/instance.py`（新增公开方法） | 全量回归 PASS 17；行为改为“选中即启动” |
| F13 | 网关启动轮询策略不匹配飞书投递策略 | P1 | done | `ai_companion/gateway/cmd.py`（按 `active + platform=feishu + 有飞书配置目标` 选择性启动轮询，其他 Bot 跳过并打印原因）、`ai_companion/bot/instance.py`（飞书目标读取稳健化） | 全量回归 PASS 17；网关启动日志可见每个 Bot 的 start/skip 原因 |
| F14 | 多窗口 CLI 日志混写，无法按 Bot 观察 | P1 | done | 新增 `ai_companion/logging_utils.py`，并在 `main.py` / `cli/adapter.py` 切换为按 Bot 名称分文件 | 生成 `cli.<bot名>.log / life.<bot名>.log / proactive.<bot名>.log`；全量回归 PASS 17 |
| F15 | 观察测试速度不够快，压测周期过长 | P1 | done | `~/.ai-companion/data/bots/obs_*/persona/proactive.json` + `life.json`：统一拉满活跃度与时间流速 | 三个 Bot 生效值校验通过（proactive `check_interval=1`、life `daily/major_interval=1`、`time_ratio=10000`） |
| F16 | 人生轨迹轮询存在固定 10s 上限，限制极速测试 | P1 | done | `ai_companion/proactive/life_scheduler.py`：轮询改为自适应 `max(1, min(10, daily_interval, major_interval))` | 定向验证可在 1s 间隔推进；全量回归 PASS 17 |
| F17 | `life.<bot名>.log` 缺少人生轨迹轮询内容 | P1 | done | `ai_companion/logging_utils.py`：为 `ai_companion.proactive` 增加 life/proactive 前缀过滤分流（`life_*` 写入 life 文件，其余写入 proactive 文件） | 定向复验：`life.<bot名>.log` 出现 `LifeScheduler` 连续 tick；全量回归 PASS 17 |
| F18 | 人生轨迹缺少“每日必记”与“新事件必记”的持久化流水 | P1 | done | `ai_companion/proactive/life_state.py`（新增 `life_journal` 流水、每日记录与事件记录写入）、`ai_companion/proactive/life_engine.py`（按推进天数逐日写记录，事件缺省也写“今日无新增事件”日志，且加固日常/大事 JSON 解析支持嵌套结构） | 新增 `T17` 用例验证每日记录+事件记录；全量回归 PASS 18 |
| F19 | CLI 空闲等待输入时阻塞事件循环，导致轮询不推进 | P1 | done | `ai_companion/cli/adapter.py`：`input/Prompt.ask` 改为 `asyncio.to_thread` 异步读取，不再阻塞后台任务 | 实机验证：选中 Bot 后静置 4s，`life/proactive` 日志持续增长并出现 tick；全量回归 PASS 18 |
| F20 | 日常事件长期空窗、人生大事长期不触发 | P1 | done | `ai_companion/proactive/life_config.py`（新增 `daily_event_min_gap_days`、`major_event_fixed_probability`）、`ai_companion/proactive/life_state.py`（新增事件日期状态字段）、`ai_companion/proactive/life_engine.py`（两天保底日常事件、人生大事按 Bot 日固定概率兜底、同日仅检查一次） | 新增 `T18` 用例验证保底日常+固定概率大事；全量回归 PASS 19 |
| F21 | 保底日常事件描述过于抽象、观测速度过快导致 529 拥塞 | P1 | done | `ai_companion/proactive/life_engine.py`（保底事件模板改为具体生活场景：美食/堵车/同事八卦/外卖等，并强化 LLM 提示词“禁止抽象空话”）；`~/.ai-companion/data/bots/obs_*/persona/life.json`（调速至日常 2s、人生日志 10s） | `T18` 增强校验 `specific_detail=yes`；全量回归 PASS 19 |
| F22 | PersonaUpdater 报 `PersonaLoader.reload` 不存在；日常事件出现重复描述 | P1 | done | `ai_companion/proactive/life_engine.py`：Persona 更新后改为 `load()`（兼容当前 Loader 接口，不再抛属性错误）；新增近期重复事件检测与替换为非重复具体场景 | 定向脚本验证 `update_ok=True`；全量回归 PASS 19 |
| F23 | 人生轨迹事件高频压测下场景重复、PersonaUpdater 大 JSON 易解析失败 | P1 | done | `ai_companion/proactive/life_state.py`（事件新增 `scenario_key/category/source`，按 Bot 持久化日常/人生大事场景历史）；`ai_companion/proactive/life_config.py`（新增 `event_policy`：场景冷却、禁用、权重、自定义场景）；`ai_companion/proactive/life_engine.py`（LLM prompt 带禁用场景，保底模板池扩充，保底无可用场景时跳过，修正场景识别，`bot_current_activity` 改为抽象状态，人生大事也加场景冷却，PersonaUpdater 改为小补丁合并） | 新增 `T19` 验证场景冷却阻止重复；新增 `T20` 验证 persona patch；全量回归 PASS 21 |
| F24 | 人生轨迹推进到未来年份后，对话仍使用静态年龄/出生年份 | P1 | done | `ai_companion/proactive/life_engine.py`（实际年龄优先按 `birth_date/current_date` 精确计算，状态输出补充生日、初始年龄和近期事件）；`ai_companion/persona/engine.py`（persona prompt 注入当前人生轨迹状态，年龄/出生日期/当前年份以 life_state 为准）；`ai_companion/bot/instance.py`（对话统一传入 life context）；`tests/system_test_suite.py`（固定从仓库源码导入，新增 prompt 年龄用例） | 新增 `T21` 验证 2030-05-08 + 2002-11-03 => 27 岁并进入 prompt；全量回归 PASS 22 |
| F25 | 人格/配置文件更新后，运行时对象仍可能使用旧缓存 | P1 | done | `ai_companion/bot/instance.py`（每次对话前重新读取 persona、清空 RefusalEngine 缓存、重载 proactive/life 配置，并同步 LifeEngine/ProactiveEngine 的名字、职业、性格）；`ai_companion/persona/refusal_engine.py`（新增 `reload()` 清缓存）；`ai_companion/proactive/life_engine.py`（PersonaUpdater 写完后同步最新 profile 到 LifeEngine） | 新增 `T22` 验证运行中修改 persona 后，下一轮对话 prompt、LifeEngine、ProactiveEngine 都使用新设定；全量回归 PASS 23 |
| F26 | 主动消息未绑定发送通道仍计数；日常事件 JSON 少逗号时报 ERROR | P1 | done | `ai_companion/bot/instance.py`（CLI 主动唤醒自动绑定发送通道，Feishu/Webhook 缺配置时明确告警）；`ai_companion/proactive/engine.py`（没有 sender 或发送失败时不计入已发送、不设置冷却）；`ai_companion/proactive/life_engine.py`（日常事件 JSON 增加轻量修复和字段级兜底解析，解析失败降级为跳过/保底，不再打 ERROR） | 新增 `T23` 验证少逗号 JSON 可解析；新增 `T24` 验证缺 sender 不计数；全量回归 PASS 25 |
| F27 | 日常小事记录需要最多只保留 100 条 | P1 | done | `ai_companion/proactive/life_config.py`（`max_events` 默认 100 且配置上限 100）；`ai_companion/proactive/life_state.py`（加载、赋值、追加、裁剪时均强制 `life_events` 只保留最近 100 条）；文档同步默认值和硬上限 | 新增 `T25` 验证直接追加 150 条、配置 1000 条、重载状态后均只保留最近 100 条；全量回归 PASS 26 |
| F28 | 人生大事过于笼统、缺少具体经历意义 | P1 | done | `ai_companion/proactive/life_engine.py`（人生大事 prompt 增加具体性要求；LLM 返回抽象描述时改走兜底；固定概率人生大事模板替换为 10 类具体场景：转岗确认、项目上线、职责升级、项目失败复盘、搬家、健康转折、家庭责任、公开认可、财务独立、关系谈清）；`docs/BOT_JSON_FIELDS.md` 更新内置 key | 新增 `T26` 验证兜底人生大事目录均为具体事件且不再使用旧抽象 key；全量回归 PASS 27 |
| F29 | 人生大事需要支持低概率意外事件 | P1 | done | `ai_companion/proactive/life_config.py`（新增 `unexpected_event_probability=0.01`、`unexpected_event_cooldown_days=365`）；`ai_companion/proactive/life_state.py`（新增 `last_unexpected_event_date`）；`ai_companion/proactive/life_engine.py`（新增意外类人生大事独立概率通道和 8 类非图形化具体场景：自己意外、家人意外、天灾、公共突发、证件遗失、居住突发、出行中断、诈骗未遂）；文档同步字段和 key | 新增 `T27` 验证普通人生大事概率关闭时意外通道仍可触发，且触发后按整体冷却阻止连续意外；全量回归 PASS 28 |

## 变更记录

- 2026-04-28：创建修复进度文档，建立 F1~F7 问题清单。
- 2026-04-28：F1 完成并验证通过，前端构建恢复。
- 2026-04-28：F2/F3/F4 完成并通过全量回归用例验证（T08/T09/T10）。
- 2026-04-28：F5/F6/F7 完成并通过全量回归用例验证（T11/T13/T14）。
- 2026-04-28：执行全量系统测试，结果 PASS 17 / FAIL 0 / ERROR 0。
- 2026-04-28：再次执行最终确认回归，结果保持 PASS 17 / FAIL 0 / ERROR 0。
- 2026-04-28：记录非阻断观察：离线测试中出现 `[PersonaUpdater] 无法找到 JSON 边界` 告警，原因为 mock 回复非 JSON，不影响本轮主功能通过结论。
- 2026-04-28：F8 完成，修复 `silent` 模式下 LifeScheduler 未启动问题。
- 2026-04-28：F9 完成，兼容旧版扁平 proactive 配置结构（setup 生成格式）。
- 2026-04-28：修复 F8/F9 后再次全量回归，结果 PASS 17 / FAIL 0 / ERROR 0（`.artifacts/system-test-rebuilt-2026-04-28-111620/`）。
- 2026-04-28：F10 完成，创建 `obs_proactive_lab` / `obs_life_lab` / `obs_combo_lab` 三个正式观察 Bot，并补充观察文档 `docs/TEST_BOT_OBSERVATION_PLAN_2026-04-28.md`。
- 2026-04-28：F11 完成，CLI 切到“首次对话才启动人生轨迹/主动唤醒”的按需模式。
- 2026-04-28：F11 后全量回归通过，PASS 17 / FAIL 0 / ERROR 0（`.artifacts/system-test-rebuilt-2026-04-28-112734/`）。
- 2026-04-28：F12 完成，CLI 调整为“选中 Bot（含 switch 切换）即启动人生轨迹/主动唤醒轮询”。
- 2026-04-28：F12 后全量回归通过，PASS 17 / FAIL 0 / ERROR 0（`.artifacts/system-test-rebuilt-2026-04-28-113200/`）。
- 2026-04-28：F13 完成，网关改为按 Feishu 配置选择性拉起 Bot 轮询，避免全量误启动。
- 2026-04-28：F13 后全量回归通过，PASS 17 / FAIL 0 / ERROR 0（`.artifacts/system-test-rebuilt-2026-04-28-113614/`）。
- 2026-04-28：F14 完成，CLI 日志改为按 Bot 名称分文件，支持多窗口并行观察。
- 2026-04-28：F14 后全量回归通过，PASS 17 / FAIL 0 / ERROR 0（`.artifacts/system-test-rebuilt-2026-04-28-114529/`）。
- 2026-04-28：F15 完成，三个观察 Bot 压测参数拉满并完成生效校验。
- 2026-04-28：F16 完成，人生轨迹轮询改为自适应最小 1s，拉满参数下可实现真正高速推进。
- 2026-04-28：F16 后全量回归通过，PASS 17 / FAIL 0 / ERROR 0（`.artifacts/system-test-rebuilt-2026-04-28-140347/`）。
- 2026-04-28：F17 完成，修复按 Bot 分文件后的人生日志分流问题，`life.<bot名>.log` 可直接观察到轮询推进。
- 2026-04-28：F17 后全量回归通过，PASS 17 / FAIL 0 / ERROR 0（`.artifacts/system-test-rebuilt-2026-04-28-142105/`）。
- 2026-04-28：F18 完成，人生轨迹新增 `life_journal` 持久化流水：每推进一天必落一条 `day_passed`，每次新增事件必落 `daily_event/major_event` 记录。
- 2026-04-28：F18 补充修复：加固 LifeEngine JSON 解析（支持 `mood_tags` 等嵌套数组/对象），避免新事件被误解析丢失。
- 2026-04-28：F19 完成，修复 CLI 在等待用户输入时阻塞事件循环的问题；选中 Bot 后无需发消息，人生轨迹/主动唤醒轮询可持续推进。
- 2026-04-28：新增系统用例 `T17`（Life daily progression + event journal）验证“每日必记+新事件必记”，并完成 F19 后全量回归 PASS 18 / FAIL 0 / ERROR 0（`.artifacts/system-test-rebuilt-2026-04-28-143151/`）。
- 2026-04-28：F20 完成，新增“每两天最少 1 条日常事件”保底机制，并为人生大事增加按 Bot 日固定概率兜底触发（同一天仅检查一次，避免高频轮询下过度触发）。
- 2026-04-28：新增系统用例 `T18`（Life fallback daily + fixed major probability）验证 F20；全量回归 PASS 19 / FAIL 0 / ERROR 0（`.artifacts/system-test-rebuilt-2026-04-28-145332/`）。
- 2026-04-28：F21 完成，保底日常事件模板改为“可感知细节”场景（通勤堵车/牛肉面/同事吃瓜/外卖乌龙/排队甜品/晚间快走），避免“状态更稳定了”这类抽象描述。
- 2026-04-28：F21 同步调速观察 Bot：`~/.ai-companion/data/bots/obs_*/persona/life.json` 调整为 `daily_interval_seconds=20000`、`major_interval_seconds=100000`（在 `time_ratio=10000` 下对应日常约 2s、人生日志约 10s），并设置 `major_event_fixed_probability=0.15`。
- 2026-04-28：F21 后全量回归 PASS 19 / FAIL 0 / ERROR 0（`.artifacts/system-test-rebuilt-2026-04-28-150707/`），`T18` 校验项增强为 `specific_detail=yes`。
- 2026-04-28：F22 完成，修复 PersonaUpdater 对 `PersonaLoader.reload()` 的错误调用，改为 `load()` 兼容路径；同时新增“最近 30 条重复描述拦截”，重复时自动替换为非重复具体场景事件。
- 2026-04-28：F22 后全量回归 PASS 19 / FAIL 0 / ERROR 0（`.artifacts/system-test-rebuilt-2026-04-28-154831/`）。
- 2026-04-28：F23 完成，人生轨迹事件改为结构化场景驱动：日常和人生大事均持久化 `scenario_key`，按 Bot 做场景冷却；保底事件模板池扩展并支持 `life.json.event_policy` 做禁用、权重和自定义场景；重复场景无可用替代时不再强行补事件；PersonaUpdater 改为补丁式 JSON，降低大 JSON 解析失败和误覆盖风险。
- 2026-04-28：F23 后全量回归 PASS 21 / FAIL 0 / ERROR 0（`.artifacts/system-test-rebuilt-2026-04-28-174342/`）。
- 2026-04-28：F24 完成，Bot 对话 prompt 注入人生轨迹当前日期、出生日期、动态年龄和近期事件；实际年龄改为优先按生日和 `current_date` 精确计算，避免时间线到 2030 后仍回答静态 24 岁。
- 2026-04-28：F24 后全量回归 PASS 22 / FAIL 0 / ERROR 0（`.artifacts/system-test-rebuilt-2026-04-28-191830/`）。
- 2026-04-28：F25 完成，BotInstance 在每次用户消息前刷新 persona/config，并把最新 profile 同步到对话 prompt、拒绝判断、LifeEngine 和 ProactiveEngine。
- 2026-04-28：F25 后全量回归 PASS 23 / FAIL 0 / ERROR 0（`.artifacts/system-test-rebuilt-2026-04-28-192333/`）。
- 2026-04-28：F26 完成，CLI 模式主动唤醒自动绑定发送通道；未绑定 sender 时不再把主动消息记为已发送；日常事件 LLM JSON 少逗号时增加宽松解析。
- 2026-04-28：F26 后全量回归 PASS 25 / FAIL 0 / ERROR 0（`.artifacts/system-test-rebuilt-2026-04-28-194144/`）。
- 2026-04-28：F27 完成，日常小事 `life_events` 加硬上限，加载、追加、赋值和裁剪路径都只保留最近 100 条。
- 2026-04-28：F27 后全量回归 PASS 26 / FAIL 0 / ERROR 0（`.artifacts/system-test-rebuilt-2026-04-28-205319/`）。
- 2026-04-28：F28 完成，人生大事固定概率兜底从抽象“方向/转折/成长”改为可感知、可追溯的具体事件，并让 LLM 抽象输出自动降级到具体兜底。
- 2026-04-28：F28 后全量回归 PASS 27 / FAIL 0 / ERROR 0（`.artifacts/system-test-rebuilt-2026-04-28-210257/`）。
- 2026-04-28：F29 完成，人生大事新增独立低概率意外通道，默认每个 Bot 日检查概率 `0.01`、整体冷却 `365` 天，并补充系统用例 `T27`；全量回归 PASS 28 / FAIL 0 / ERROR 0（`.artifacts/system-test-rebuilt-2026-04-28-212913/`）。
