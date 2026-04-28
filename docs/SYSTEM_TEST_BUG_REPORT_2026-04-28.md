# AI Companion 系统级测试缺陷报告（重装 + 重建测试套件）

日期：2026-04-28
范围：先卸载 `~/.ai-companion`，按最新代码重装；删除旧测试脚本；从零重写并执行系统级全量测试；记录缺陷与修复闭环。

---

## 1. 测试前操作（已完成）

### 1.1 卸载旧运行目录

- 已完整删除 `~/.ai-companion`。

### 1.2 按最新代码重装

由于系统 Python 为 PEP668 管理，使用独立虚拟环境安装：

- `python3 -m venv ~/.ai-companion/.venv`
- `~/.ai-companion/.venv/bin/python -m pip install -e <repo>`

补装当前代码路径实际依赖：

- `jieba`
- `httpx`
- `lark-oapi`
- `python-dotenv`

### 1.3 重建配置文件

重建：

- `~/.ai-companion/config/bots.yaml`
- `~/.ai-companion/config/models.yaml`

验证：

- `~/.ai-companion/.venv/bin/ai-companion --help` 可用
- `~/.ai-companion/.venv/bin/ai-companion status` 可用

---

## 2. 旧测试脚本处理（已完成）

- 按要求删除全部旧脚本 `tests/test_*.py`。
- 新测试套件不复用旧逻辑，统一严格 PASS/FAIL 统计。

---

## 3. 新系统测试套件

测试脚本：

- `tests/system_test_suite.py`

执行命令：

- `~/.ai-companion/.venv/bin/python tests/system_test_suite.py`

关键产物：

- 基线（修复前）：`.artifacts/system-test-rebuilt-2026-04-28-103028/`
- 回归（修复后）：`.artifacts/system-test-rebuilt-2026-04-28-105232/`
- 最终确认回归：`.artifacts/system-test-rebuilt-2026-04-28-105643/`

---

## 4. 覆盖清单与结果

| Case | 领域 | 基线结果 | 修复后结果 |
|---|---|---|---|
| T00 | 旧脚本清理校验 | PASS | PASS |
| T01 | CLI help | PASS | PASS |
| T02 | CLI status | PASS | PASS |
| T03 | CLI bot list | PASS | PASS |
| T04 | 配置加载 | PASS | PASS |
| T05 | ModelFactory 注册表 | PASS | PASS |
| T06 | 上下文压缩器行为 | PASS | PASS |
| T07 | 记忆引擎离线读写 | PASS | PASS |
| T08 | BotInstance 离线全流程 | FAIL | PASS |
| T09 | Proactive silent 语义 | FAIL | PASS |
| T10 | Proactive 重复发送保护 | FAIL | PASS |
| T11 | 运行入口统一走工厂 | FAIL | PASS |
| T12 | Gateway 生命周期 + 管理 API | PASS | PASS |
| T13 | UI/后端 provider 契约一致性 | FAIL | PASS |
| T14 | UI 清空全部记忆实现 | FAIL | PASS |
| T15 | 前端生产构建 | FAIL | PASS |
| T16 | 飞书凭据硬编码扫描 | PASS | PASS |

汇总：

- 基线：PASS 10 / FAIL 7 / ERROR 0
- 修复后：PASS 17 / FAIL 0 / ERROR 0

---

## 5. 缺陷闭环（已修复）

### BUG-01（P0）前端构建失败

- 现象：`Logs.tsx` 未使用状态 setter；`Memory.tsx` 存在 `string | null` 到 `string` 类型错误。
- 修复：
  - `ai-companion-ui/src/pages/Logs/Logs.tsx`
  - `ai-companion-ui/src/pages/Memory/Memory.tsx`
- 验证：`T15=PASS`，`npm run build` 通过。

### BUG-02（P1）`mode=silent` 未禁用 active 行为

- 现象：`enabled=True` 且 `mode=silent` 时仍被判定 active。
- 修复：
  - `ai_companion/proactive/config.py`：`is_active` 改为 `enabled && mode=="active"`。
- 验证：`T09=PASS`。

### BUG-03（P1）Proactive 单次 tick 重复发送

- 现象：引擎层发送后，调度层再次发送，导致重复消息。
- 修复：
  - `ai_companion/proactive/scheduler.py`：移除重复通知发送。
- 验证：`T10=PASS`（发送次数为 1）。

### BUG-04（P1）LifeEngine 未注入 persona_loader

- 现象：实例化链路中注入检查对象错误，导致 life 轨迹刷新人格时加载器不可用。
- 修复：
  - `ai_companion/bot/instance.py`：改为注入 `self.persona_loader`。
- 验证：`T08=PASS`（`life_loader_ok=True`）。

### BUG-05（P1）Main/Gateway 入口绕过 ModelFactory

- 现象：入口直接使用 `MiniMaxAdapter`，与多 provider 设计不一致。
- 修复：
  - `ai_companion/model/factory.py`：新增 `create_from_runtime_config(...)` 与运行时参数白名单。
  - `ai_companion/main.py`：切到 `ModelFactory.create_from_runtime_config(...)`，按 provider 获取 key。
  - `ai_companion/gateway/cmd.py`：同上。
- 验证：`T11=PASS`。

### BUG-06（P2）UI provider 枚举与后端不一致

- 现象：UI 使用 `anthropic`，后端工厂使用 `claude`。
- 修复：
  - `ai-companion-ui/src/pages/Settings/Settings.tsx`：`anthropic` 调整为 `claude`。
- 验证：`T13=PASS`。

### BUG-07（P2）UI“清空全部记忆”是 no-op

- 现象：前端接口 `clearAll` 只返回 `Promise.resolve()`，未调用后端。
- 修复：
  - `ai-companion-ui/src/api/index.ts`：改为调用 `DELETE /api/v1/admin/memory/{botId}/all`。
  - `ai_companion/gateway/cmd.py`：新增对应管理 API 删除路由。
- 验证：`T14=PASS`。

---

## 6. 当前状态

- 结论：本轮系统级主功能测试全部通过，未发现剩余阻断缺陷。
- 当前报告状态：已闭环（如后续有新增改动，需再次执行同一套全量回归）。
- 观察项：离线回归时会看到 `[PersonaUpdater] 无法找到 JSON 边界` 告警，来源是测试用离线模型返回非 JSON 文本；该告警不影响本轮 17 项主功能通过。
