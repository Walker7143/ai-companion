# Phase 7：微信对话通道 TODO

> 执行原则：先稳运行，再补配置入口，再补管理面和测试，最后做体验收口。  
> 当前状态：P0 稳定性测试、P1 配置入口、P2 观测运维和可 mock 的 P3 回归已完成；剩余重点是真实飞书 + 微信端到端验证。

---

## 1. 已完成

- [x] 本地化 `ai_companion/gateway/platforms/weixin.py`
- [x] 补充 `ai_companion/gateway/platforms/helpers.py`
- [x] `ai_companion/gateway/cmd.py` 支持飞书 + 微信并行连接
- [x] `ai_companion/bot/instance.py` 支持微信主动消息发送
- [x] `ai_companion/gateway/config.py` 支持 `WEIXIN_*` 环境变量兜底
- [x] `pyproject.toml` 增加微信运行所需依赖
- [x] `ai_companion/setup.py` 增加微信扫码/手填配置、DM / 群策略和主动平台选择
- [x] `ai_companion/gateway/admin_services.py` 支持微信 schema 展示和 `platforms.weixin` 保存
- [x] `tests/weixin_gateway_test.py` 覆盖微信 adapter smoke、并行 profile 构建、主动发送和 context_token 降级
- [x] `tests/weixin_gateway_test.py` 覆盖群聊策略、媒体收发路径、运行态脱敏和微信状态摘要
- [x] `config/config.yaml.example` 与 `docs/GUIDE.md` 增加微信配置示例

---

## 2. P0 稳定性收口

| 顺序 | 状态 | 任务 | 产出 | 依赖 |
|---|---|---|---|---|
| 1 | [x] | 跑一轮核心语法和导入检查 | `python -m compileall -q ai_companion` 通过 | 当前代码 |
| 2 | [x] | 补微信 adapter smoke test | 覆盖 `connect / disconnect / send / _process_message` 的最小闭环 | `weixin.py` |
| 3 | [x] | 补 `cmd.py` 并行启动回归测试 | 覆盖飞书与微信 profile 同时构建 | `cmd.py` |
| 4 | [x] | 补主动唤醒发送测试 | 验证 `_wrap_gateway_send()` 能按 `platform_type=weixin` 发出消息 | `bot/instance.py` |
| 5 | [x] | 收口异常路径 | `context_token` 过期时自动无 token 重试；缺配置启动错误保持明确 | `weixin.py` |

---

## 3. P1 配置入口

| 顺序 | 状态 | 任务 | 产出 | 依赖 |
|---|---|---|---|---|
| 6 | [x] | 扩展 `ai_companion/setup.py` | 增加微信扫码登录、账号保存、DM / 群策略选择 | `weixin.py` 的 `qr_login()` |
| 7 | [x] | 扩展主动平台选择 | `proactive.json` 能选择 `weixin` 并配置主动目标 chat_id | `setup.py` |
| 8 | [x] | 扩展 `ai_companion/gateway/admin_services.py` schema | Web UI 能展示微信配置字段、提示词和敏感字段 | 当前配置 schema |
| 9 | [x] | 保存微信平台配置 | 管理后台能写入 `platforms.weixin` 的 `extra / routing / home_channel` | 上一项 |
| 10 | [x] | 补 config 示例 | `config/config.yaml.example` / `docs/GUIDE.md` 写出微信完整样例 | 前两项 |

---

## 4. P2 观测与运维

| 顺序 | 状态 | 任务 | 产出 | 依赖 |
|---|---|---|---|---|
| 11 | [x] | 完整显示微信状态 | `gateway/status`、管理 API 和设置页能看到连接状态、账号摘要、最近错误 | 当前 adapter |
| 12 | [x] | 日志脱敏 | token、account_id、context_token 不在运行态和启动输出中明文展开 | `weixin.py` |
| 13 | [x] | 连接健康提示 | 启动输出区分微信未配置、配置已加载、连接成功、连接失败 | `cmd.py` |
| 14 | [x] | 持久化文件说明 | `docs/GUIDE.md` 说明 `~/.ai-companion/weixin/accounts/` 的用途 | 文档 |

---

## 5. P3 功能补齐

| 顺序 | 状态 | 任务 | 产出 | 依赖 |
|---|---|---|---|---|
| 15 | [x] | 群聊策略补全 | `allowlist / open / disabled` 在群场景里行为清晰且可测 | `weixin.py` |
| 16 | [x] | 媒体路径回归测试 | 图片、文件、语音、视频的收发路径有 mock iLink 回归 | `weixin.py` |
| 17 | [x] | `context_token` 失效降级测试 | 过期后能自动重试，不把会话打断 | `weixin.py` |
| 18 | [x] | 多平台 home channel 行为验证 | 微信主动消息按 `platform_type=weixin` 走微信 home channel；飞书/微信配置并行构建可测 | `cmd.py` / `bot/instance.py` |

---

## 6. P4 文档与发布

| 顺序 | 任务 | 产出 | 依赖 |
|---|---|---|---|
| 19 | [x] | 更新 `docs/GUIDE.md` | 把微信通道入口、配置和限制补进主文档 | 设计文档完成 |
| 20 | [x] | 更新快速上手文档 | 给出最小可运行的微信配置样例 | setup / admin 完成 |
| 21 | [ ] | 做一次端到端验证 | 飞书 + 微信同时在线，至少完成一轮真实收发 | 需要真实飞书 App 与微信 iLink 账号 |

---

## 7. 推荐执行顺序

1. 准备真实飞书 App 和微信 iLink 账号凭据。
2. 启动 `ai-companion gateway start --sync`，确认飞书 + 微信同时连接。
3. 分别完成一轮真实收发和一条微信媒体消息收发，再关闭 Phase 7。

---

## 8. 当前风险点

- 个人微信 iLink API 属于非标准通道，接口稳定性要靠 mock 回归 + 真实端到端验证兜住。
- 微信默认不开放群聊和全量 DM，配置不收口会有安全风险。
- 当前只按一个微信账号绑定一个 Bot 实现，后续多账号要重新看路由设计。
- 真实端到端验证需要有效飞书 App、微信 iLink token/account_id 和可收发测试会话，不能只靠本地 mock 证明。
