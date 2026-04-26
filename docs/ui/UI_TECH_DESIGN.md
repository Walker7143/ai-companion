# AI Companion 管理后台 - 技术设计方案

> 版本: v2.0
> 日期: 2026-04-26
> 变更: 从 Tauri 桌面端改为网页端
> 技术栈: React + TypeScript + Vite + TailwindCSS + Zustand

---

## 一、整体架构

### 1.1 架构概述

网页端作为前端，通过 HTTP API 与后端通信。后端复用现有的 Python AI Companion Core。

```
┌─────────────────────────────────────────────────────────────┐
│                     浏览器 (Web Browser)                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   React 单页应用                       │   │
│  │                                                      │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐            │   │
│  │  │  监控   │  │  会话   │  │  日志   │   ...      │   │
│  │  │  面板   │  │  管理   │  │  查看   │            │   │
│  │  └────┬────┘  └────┬────┘  └────┬────┘            │   │
│  │       │            │            │                   │   │
│  │       └────────────┼────────────┘                   │   │
│  │                    │                              │   │
│  │            ┌───────▼───────┐                      │   │
│  │            │   状态管理     │                      │   │
│  │            │   (Zustand)   │                      │   │
│  │            └───────┬───────┘                      │   │
│  └────────────────────┼──────────────────────────────┘   │
│                       │ Fetch / WebSocket               │
└───────────────────────┼───────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────────┐
│                     后端 API 层                                │
│  ┌────────────────────────────────────────────────────────┐  │
│  │              Python AI Companion Core                   │  │
│  │                                                          │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐              │  │
│  │  │  Bot    │  │ Memory  │  │ Gateway │              │  │
│  │  │  Instance│  │ Engine  │  │          │              │  │
│  │  └─────────┘  └─────────┘  └─────────┘              │  │
│  │                                                          │  │
│  └────────────────────────────────────────────────────────┘  │
│                       │                                        │
│              ┌────────▼────────┐                             │
│              │  SQLite / Files  │                             │
│              │  ~/.ai-companion/ │                             │
│              └─────────────────┘                              │
└───────────────────────────────────────────────────────────────┘
```

### 1.2 前后端分离

- **前端**: 纯静态网页，可部署到任意 Web 服务器或 CDN
- **后端**: 复用现有 Python AI Companion，通过 REST API 暴露功能
- **通信**: HTTP REST API + WebSocket（实时日志）

---

## 二、技术选型

### 前端

| 类别 | 技术 | 版本 | 说明 |
|------|------|------|------|
| 框架 | React | 18.x | UI 框架 |
| 语言 | TypeScript | 5.x | 类型安全 |
| 构建 | Vite | 5.x | 快速 HMR |
| 样式 | TailwindCSS | 3.x | 原子化 CSS |
| 状态 | Zustand | 4.x | 轻量状态管理 |
| 图表 | Recharts | 2.x | 简单场景够用 |
| 路由 | React Router | 6.x | SPA 路由 |
| 图标 | Lucide React | 最新 | 一致的图标 |
| Toast | Sonner | 最新 | 轻量提示 |

### 后端（复用现有）

| 类别 | 技术 | 说明 |
|------|------|------|
| 语言 | Python | 现有 AI Companion Core |
| API | FastAPI / 扩展 | 新增 REST API 端点 |
| WebSocket | fastapi.websockets | 实时日志 |

---

## 三、目录结构

```
ai-companion-ui/
├── src/
│   ├── components/
│   │   ├── Layout/
│   │   │   ├── Layout.tsx
│   │   │   ├── Sidebar.tsx
│   │   │   └── Header.tsx
│   │   ├── ui/
│   │   │   ├── Button.tsx
│   │   │   ├── Input.tsx
│   │   │   ├── Select.tsx
│   │   │   ├── Card.tsx
│   │   │   ├── Badge.tsx
│   │   │   ├── Modal.tsx
│   │   │   ├── Toast.tsx
│   │   │   └── ...
│   │   └── ...
│   ├── pages/
│   │   ├── Dashboard/
│   │   │   └── Dashboard.tsx
│   │   ├── Session/
│   │   │   └── Session.tsx
│   │   ├── Logs/
│   │   │   └── Logs.tsx
│   │   ├── Memory/
│   │   │   └── Memory.tsx
│   │   └── Settings/
│   │       └── Settings.tsx
│   ├── stores/
│   │   ├── botStore.ts
│   │   ├── metricsStore.ts
│   │   ├── sessionStore.ts
│   │   ├── memoryStore.ts
│   │   ├── logStore.ts
│   │   └── configStore.ts
│   ├── api/
│   │   └── index.ts          # API 调用层
│   ├── hooks/
│   │   └── useLogStream.ts   # WebSocket 实时日志
│   ├── types/
│   │   └── index.ts          # TypeScript 类型
│   ├── utils/
│   │   └── ...
│   ├── App.tsx
│   ├── main.tsx
│   └── index.css
├── public/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── tailwind.config.js
```

---

## 四、API 设计

### 4.1 API 基础路径

假设后端运行在 `http://localhost:18888/api/v1`

### 4.2 系统监控

```
GET /api/v1/metrics/system
Response: {
  cpu_percent: number
  memory_percent: number
  memory_used_mb: number
  uptime_seconds: number
}

GET /api/v1/metrics/bot/:bot_id
Response: {
  bot_id: string
  status: "running" | "stopped"
  uptime_seconds: number
  conversations_today: number
  proactive_messages_today: number
  input_tokens_today: number
  output_tokens_today: number
  memory_stats: {
    working_count: number
    episodic_count: number
    semantic_count: number
  }
}
```

### 4.3 会话管理

```
GET /api/v1/sessions?bot_id=xxx
Response: {
  sessions: SessionInfo[]
}

GET /api/v1/sessions/:session_key
Response: SessionDetail

POST /api/v1/sessions/:session_key/reset
POST /api/v1/sessions/:session_key/suspend
```

### 4.4 日志

```
GET /api/v1/logs?bot_id=xxx&level=info&type=dialogue&date=today&page=1&page_size=20
Response: {
  logs: LogEntry[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

WS /api/v1/logs/stream?bot_id=xxx&level=info
# WebSocket 实时日志流
```

### 4.5 记忆管理

```
GET /api/v1/memory/:bot_id/stats
GET /api/v1/memory/:bot_id/working
GET /api/v1/memory/:bot_id/episodic?query=xxx&limit=10
GET /api/v1/memory/:bot_id/semantic
DELETE /api/v1/memory/:bot_id/:type/:id
POST /api/v1/memory/:bot_id/clear
```

### 4.6 配置

```
GET /api/v1/config/:bot_id
PUT /api/v1/config/:bot_id
POST /api/v1/config/:bot_id/test
GET /api/v1/bots
```

---

## 五、Zustand Store 设计

### 5.1 Bot Store

```typescript
// src/stores/botStore.ts
interface BotInfo {
  id: string;
  name: string;
  status: 'running' | 'stopped';
}

interface BotStore {
  bots: BotInfo[];
  currentBotId: string | null;
  setCurrentBot: (id: string) => void;
  fetchBots: () => Promise<void>;
}
```

### 5.2 Metrics Store

```typescript
// src/stores/metricsStore.ts
interface MetricsStore {
  systemMetrics: SystemMetrics | null;
  botMetrics: BotMetrics | null;
  loading: boolean;
  fetchMetrics: () => Promise<void>;
  startPolling: (intervalMs?: number) => void;
  stopPolling: () => void;
}
```

### 5.3 Log Store

```typescript
// src/stores/logStore.ts
interface LogStore {
  logs: LogEntry[];
  total: number;
  page: number;
  pageSize: number;
  isLoading: boolean;
  isStreaming: boolean;
  filters: { level: string; type: string; date: string; query: string };
  fetchLogs: (page?: number) => Promise<void>;
  setFilter: (key: string, value: string) => void;
  startStream: () => void;
  stopStream: () => void;
}
```

---

## 六、响应式设计

### 6.1 断点

| 断点 | 宽度 | 布局 |
|------|------|------|
| 桌面 | ≥1024px | 侧边栏展开 (240px) |
| 平板 | 768-1023px | 侧边栏收起为图标 (64px) |
| 移动 | <768px | 侧边栏隐藏，汉堡菜单 |

### 6.2 CSS 变量主题

```css
/* 亮色主题 (默认) */
:root {
  --bg-primary: #FFFFFF;
  --bg-secondary: #F8FAFC;
  --bg-tertiary: #F1F5F9;
  --border-subtle: #E2E8F0;
  --text-primary: #0F172A;
  --text-secondary: #64748B;
  --accent: #8B5CF6;
}

/* 暗色主题 */
[data-theme="dark"] {
  --bg-primary: #0F172A;
  --bg-secondary: #1E293B;
  --bg-tertiary: #334155;
  --border-subtle: #334155;
  --text-primary: #F1F5F9;
  --text-secondary: #94A3B8;
  --accent: #A855F7;
}
```

---

## 七、开发命令

```bash
cd ai-companion-ui
npm install
npm run dev      # 开发服务器
npm run build    # 生产构建
npm run preview  # 预览构建
```

---

## 八、部署

### 8.1 静态部署

构建产物在 `dist/` 目录，可部署到任意 Web 服务器:

```bash
npm run build
# 部署 dist/ 目录
```

### 8.2 开发调试

开发时前端连接 `http://localhost:18888`，后端需先启动:

```bash
# 终端1: 启动后端
cd /Users/wangxiaowei/projects/own/ai-girl-friend
python -m ai_companion api --port 18888

# 终端2: 启动前端
cd ai-companion-ui
npm run dev
```

---

## 九、文件位置

文档存放位置：`/Users/wangxiaowei/projects/own/ai-girl-friend/docs/ui/UI_TECH_DESIGN.md`
