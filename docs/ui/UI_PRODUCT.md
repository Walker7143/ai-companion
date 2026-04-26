# AI Companion 管理后台 - 产品规格

> 版本: v1.0
> 日期: 2026-04-26
> 定位: 内部管理工具（Web 端）

---

## 一、产品定位

**一句话：** 管理后台是 AI Companion 系统的 Web 控制面板，用于配置 Bot 参数、监控运行状态、查看运行时日志。

不是面向普通用户的產品，而是开发者/运维人员调试和维护 AI Companion 的工具。

---

## 二、核心功能

### 2.1 监控面板（Dashboard）

**作用：** 一眼看到 Bot 是否在跑、系统资源是否正常。

| 内容 | 说明 |
|------|------|
| Bot 状态 | 运行中 / 已停止 |
| 今日会话数 | 统计当天对话数量 |
| 运行时长 | 连续运行时间 |
| 记忆总数 | 工作+情景+语义记忆条数 |
| CPU / 内存 | 系统资源占用 |

**数据来源：** `ai_companion` 后端 API `/api/v1/metrics/*`

---

### 2.2 会话管理（Session）

**作用：** 查看 Bot 和用户的对话记录，了解用户说了什么、Bot 回复了什么。

| 内容 | 说明 |
|------|------|
| 会话列表 | 平台、会话 ID、时间、状态 |
| 平台筛选 | 全部 / CLI / 飞书 |
| 会话详情 | 用户消息、Bot 回复、Token 消耗 |
| 操作 | 重置会话（清空上下文） |

**数据来源：** `ai_companion` 后端 API `/api/v1/sessions/*`

---

### 2.3 日志查看（Logs）

**作用：** 排查问题、追踪 Bug、看看 Bot 是不是在乱说话。

| 内容 | 说明 |
|------|------|
| 日志列表 | 时间、级别、类型、消息 |
| 级别筛选 | 全部 / Info / Warning / Error |
| 类型筛选 | 全部 / 对话 / 会话 / API / 主动 |
| 搜索 | 关键词搜索日志内容 |
| 分页 | 每页 20 条 |
| 实时日志 | WebSocket 流式推送新日志 |

**数据来源：** `ai_companion` 后端 API `/api/v1/logs/*` + WebSocket

---

### 2.4 记忆管理（Memory）

**作用：** 看看 Bot 记住了什么、忘了什么，必要时手动清理。

| 内容 | 说明 |
|------|------|
| 统计概览 | 三层记忆数量统计 |
| 工作记忆 | 当前会话的消息列表 |
| 情景记忆 | 重要事件片段，按重要性星级显示 |
| 语义记忆 | 用户画像（关系等级、态度分数、关键事实） |
| 删除 | 删除单条记忆 |
| 清空 | 清空全部记忆 |

**数据来源：** `ai_companion` 后端 API `/api/v1/memory/*`

---

### 2.5 设置（Settings）

**作用：** 配置 Bot 用的模型、调节参数、开关功能。

| 内容 | 说明 |
|------|------|
| 模型配置 | Provider、API Key、Base URL、Model |
| 生成参数 | Temperature、Max Tokens |
| 平台开关 | CLI / 飞书 / Webhook |
| 主动唤醒 | 启用/关闭、唤醒间隔、最大次数 |
| 测试连接 | 验证 API Key 是否可用 |
| 保存/重置 | 持久化配置 |

**数据来源：** `ai_companion` 后端 API `/api/v1/config/*`

---

## 三、非功能需求

| 需求 | 说明 |
|------|------|
| 响应式 | 桌面端为主，平板能用 |
| 主题 | 亮色/暗色切换 |
| 实时性 | Dashboard 5 秒轮询、日志 WebSocket 推送 |
| 独立性 | 纯静态页面，可部署到任意 Web 服务器 |
| 调试友好 | 日志级别颜色区分、操作有 Toast 反馈 |

---

## 四、页面结构

```
┌─────────────────────────────────────────────────┐
│ Header: Logo + Bot 切换 + 主题切换               │
├──────────┬──────────────────────────────────────┤
│          │                                      │
│ Sidebar  │           主内容区                    │
│          │                                      │
│ Dashboard│   监控面板 / 会话 / 日志 / 记忆 / 设置 │
│ Session  │                                      │
│ Logs     │                                      │
│ Memory   │                                      │
│ Settings │                                      │
│          │                                      │
└──────────┴──────────────────────────────────────┘
```

---

## 五、API 对接

前端是纯 Web 页面，通过 HTTP API 与 `ai_companion` Python 后端通信：

```
GET  /api/v1/metrics/system          # 系统指标
GET  /api/v1/metrics/bot/:bot_id     # Bot 指标
GET  /api/v1/sessions?bot_id=xxx     # 会话列表
GET  /api/v1/sessions/:key           # 会话详情
POST /api/v1/sessions/:key/reset     # 重置会话
GET  /api/v1/logs?bot_id=xxx         # 日志分页
WS   /api/v1/logs/stream?bot_id=xxx  # 实时日志
GET  /api/v1/memory/:bot_id/stats    # 记忆统计
GET  /api/v1/memory/:bot_id/working  # 工作记忆
GET  /api/v1/memory/:bot_id/episodic # 情景记忆
GET  /api/v1/memory/:bot_id/semantic  # 语义记忆
DELETE /api/v1/memory/:bot_id/:type/:id  # 删除记忆
GET  /api/v1/config/:bot_id          # 获取配置
PUT  /api/v1/config/:bot_id          # 更新配置
POST /api/v1/config/:bot_id/test     # 测试连接
GET  /api/v1/bots                    # Bot 列表
```

**当前状态：** 前端已实现，Mock Data 可独立运行。需对接真实后端。

---

## 六、技术方案

| 层 | 技术 | 说明 |
|----|------|------|
| 前端框架 | React 18 + TypeScript | 已采用 |
| 构建工具 | Vite | 已采用 |
| 样式 | Inline styles | 已从 Tailwind 改为内联样式 |
| 状态管理 | Zustand | 已采用 |
| 路由 | React Router | 已采用 |
| Toast | Sonner | 已采用 |
| 图标 | Lucide React | 已采用 |
| 后端 | Python ai_companion | 需扩展 REST API |

---

## 七、验收标准

- [ ] 监控面板显示 Bot 状态、CPU、内存、记忆统计
- [ ] 会话列表可筛选，重置会话有效
- [ ] 日志可按级别/类型筛选，支持搜索和实时流
- [ ] 记忆可查看统计，可删除单条或清空全部
- [ ] 设置可修改模型参数，保存后生效
- [ ] 亮色/暗色主题切换正常
- [ ] Bot 切换后刷新对应数据
- [ ] 所有操作有 Toast 反馈
- [ ] 页面加载有骨架屏过渡
