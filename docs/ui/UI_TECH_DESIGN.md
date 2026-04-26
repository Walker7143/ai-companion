# AI Companion 管理后台 - 技术设计方案

> 版本: v1.0
> 日期: 2026-04-26
> 技术栈: Tauri + React + TypeScript

---

## 一、整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                     Tauri 桌面应用                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   WebView (React)                   │   │
│  │                                                      │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐            │   │
│  │  │  监控   │  │  会话   │  │  日志   │   ...      │   │
│  │  │  面板   │  │  管理   │  │  查看   │            │   │
│  │  └────┬────┘  └────┬────┘  └────┬────┘            │   │
│  │       │            │            │                   │   │
│  │       └────────────┼────────────┘                   │   │
│  │                    │                                  │   │
│  │            ┌───────▼───────┐                        │   │
│  │            │   状态管理     │                        │   │
│  │            │   (Zustand)   │                        │   │
│  │            └───────┬───────┘                        │   │
│  └────────────────────┼─────────────────────────────────┘   │
│                       │ Tauri IPC                          │
│  ┌────────────────────▼─────────────────────────────────┐   │
│  │              Rust 后端 (Tauri Commands)                │   │
│  │                                                        │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐          │   │
│  │  │  系统     │  │  文件    │  │  子进程   │          │   │
│  │  │  监控     │  │  操作    │  │  管理     │          │   │
│  │  └──────────┘  └──────────┘  └──────────┘          │   │
│  │                                                        │   │
│  └────────────────────┬─────────────────────────────────┘   │
│                       │                                      │
│  ┌────────────────────▼─────────────────────────────────┐   │
│  │              AI Companion Core (Python)                │   │
│  │                                                        │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐              │   │
│  │  │  Bot    │  │ Memory  │  │ Gateway │              │   │
│  │  │  Instance│  │ Engine  │  │          │              │   │
│  │  └─────────┘  └─────────┘  └─────────┘              │   │
│  │                                                        │   │
│  └────────────────────────────────────────────────────────┘   │
│                       │                                      │
│              ┌────────▼────────┐                           │
│              │  SQLite / Files  │                           │
│              │  ~/.ai-companion/ │                           │
│              └─────────────────┘                            │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、技术选型

### 前端

| 类别 | 技术 | 版本 | 说明 |
|------|------|------|------|
| 框架 | React | 18.x | |
| 语言 | TypeScript | 5.x | 类型安全 |
| 构建 | Vite | 5.x | 快速 HMR |
| 样式 | TailwindCSS | 3.x | 原子化 CSS |
| 状态 | Zustand | 4.x | 轻量状态管理 |
| 图表 | Recharts | 2.x | 简单场景够用 |
| 路由 | React Router | 6.x | SPA 路由 |
| HTTP | axios | 1.x | API 调用 |
| WebSocket | native | - | 浏览器原生 |

### 桌面

| 类别 | 技术 | 版本 | 说明 |
|------|------|------|------|
| 框架 | Tauri | 2.x | 跨平台桌面 |
| 后端语言 | Rust | 1.75+ | Tauri 绑定 |
| IPC | Tauri Commands | 2.x | 前后端通信 |
| 系统 | tauri-plugin-shell | 2.x | 子进程管理 |

### Python Core（现有）

无需修改，复用现有 `ai_companion` 包。

---

## 三、目录结构

```
ai-companion-ui/
├── src/                      # React 前端
│   ├── components/           # 公共组件
│   │   ├── Layout/
│   │   ├── Sidebar.tsx
│   │   ├── Header.tsx
│   │   └── ...
│   ├── pages/               # 页面
│   │   ├── Dashboard/       # 监控仪表盘
│   │   ├── Session/         # 会话管理
│   │   ├── Context/         # 上下文详情
│   │   ├── Memory/         # 记忆管理
│   │   ├── Logs/            # 日志查看
│   │   ├── Settings/        # 设置面板
│   │   └── Skills/          # 技能管理
│   ├── stores/              # Zustand stores
│   │   ├── botStore.ts
│   │   ├── sessionStore.ts
│   │   ├── metricsStore.ts
│   │   └── logStore.ts
│   ├── hooks/               # 自定义 hooks
│   ├── api/                 # API 调用层
│   │   └── tauri.ts         # Tauri IPC 封装
│   ├── types/               # TypeScript 类型
│   ├── utils/               # 工具函数
│   ├── App.tsx
│   ├── main.tsx
│   └── index.css            # Tailwind 入口
├── src-tauri/               # Rust 后端
│   ├── src/
│   │   ├── main.rs          # Tauri 入口
│   │   ├── commands/        # Tauri Commands
│   │   │   ├── mod.rs
│   │   │   ├── system.rs    # 系统监控
│   │   │   ├── file.rs      # 文件操作
│   │   │   ├── process.rs   # 子进程管理
│   │   │   └── config.rs    # 配置读写
│   │   └── lib.rs
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   └── icons/
├── public/
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.js
└── SPEC.md                  # 产品规格
```

---

## 四、Tauri Commands 设计

### 4.1 系统监控

```rust
// src-tauri/src/commands/system.rs

#[tauri::command]
pub async fn get_system_metrics() -> Result<SystemMetrics, String> {
    // CPU、内存、磁盘使用率
    // AI Companion 进程状态
}

#[tauri::command]
pub async fn get_bot_metrics(bot_id: String) -> Result<BotMetrics, String> {
    // 今日对话数、主动消息数、Token消耗
    // 记忆状态（条数、大小）
    // 运行时间
}

#[derive(Serialize)]
pub struct SystemMetrics {
    pub cpu_percent: f32,
    pub memory_percent: f32,
    pub memory_used_mb: u64,
    pub disk_percent: f32,
    pub uptime_seconds: u64,
}

#[derive(Serialize)]
pub struct BotMetrics {
    pub bot_id: String,
    pub status: String,           // "running" | "stopped"
    pub uptime_seconds: u64,
    pub conversations_today: u32,
    pub proactive_messages_today: u32,
    pub input_tokens_today: u64,
    pub output_tokens_today: u64,
    pub memory_stats: MemoryStats,
}
```

### 4.2 会话管理

```rust
// src-tauri/src/commands/session.rs

#[tauri::command]
pub async fn list_sessions(bot_id: String) -> Result<Vec<SessionInfo>, String> {
    // 读取 SessionStore，获取会话列表
}

#[tauri::command]
pub async fn get_session_detail(session_key: String) -> Result<SessionDetail, String> {
    // 获取单个会话的详细信息
}

#[tauri::command]
pub async fn reset_session(session_key: String) -> Result<(), String> {
    // 重置指定会话
}

#[tauri::command]
pub async fn suspend_session(session_key: String) -> Result<(), String> {
    // 挂起指定会话
}

#[tauri::command]
pub async fn get_session_context(session_key: String) -> Result<ContextDetail, String> {
    // 获取上下文详情（见 4.3）
}

#[derive(Serialize)]
pub struct SessionInfo {
    pub session_key: String,
    pub session_id: String,
    pub platform: String,
    pub user: String,
    pub created_at: String,
    pub updated_at: String,
    pub status: String,           // "active" | "reset" | "expired"
    pub reset_reason: Option<String>,
    pub total_tokens: u64,
}

#[derive(Serialize)]
pub struct SessionDetail {
    pub info: SessionInfo,
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub cache_write_tokens: u64,
    pub cache_read_tokens: u64,
    pub estimated_cost_usd: f64,
}

#[derive(Serialize)]
pub struct ContextDetail {
    pub system_prompt: String,
    pub working_history: Vec<Message>,
    pub episodic_recall: Vec<EpisodicItem>,
    pub semantic_facts: HashMap<String, String>,
    pub system_suffix: String,
    pub compression_history: Vec<CompressionRecord>,
    pub current_tokens: u32,
    pub hard_limit: u32,
    pub soft_limit: u32,
}
```

### 4.3 记忆管理

```rust
// src-tauri/src/commands/memory.rs

#[tauri::command]
pub async fn get_memory_stats(bot_id: String) -> Result<MemoryStats, String> {
    // 获取三层记忆统计
}

#[tauri::command]
pub async fn get_working_memory(bot_id: String) -> Result<Vec<Message>, String> {
    // 获取工作记忆详情
}

#[tauri::command]
pub async fn get_episodic_memory(
    bot_id: String,
    query: Option<String>,
    limit: Option<u32>,
) -> Result<Vec<EpisodicItem>, String> {
    // 获取情景记忆（支持搜索）
}

#[tauri::command]
pub async fn get_semantic_memory(bot_id: String) -> Result<SemanticMemory, String> {
    // 获取语义记忆（用户画像）
}

#[tauri::command]
pub async fn delete_memory(
    bot_id: String,
    memory_type: String,     // "working" | "episodic" | "semantic"
    memory_id: String,
) -> Result<(), String> {
    // 删除单条记忆
}

#[tauri::command]
pub async fn clear_all_memory(bot_id: String) -> Result<(), String> {
    // 清空所有记忆（危险操作，需确认）
}

#[derive(Serialize)]
pub struct MemoryStats {
    pub working_count: u32,
    pub working_size_kb: u64,
    pub episodic_count: u32,
    pub episodic_size_kb: u64,
    pub semantic_count: u32,
    pub semantic_size_kb: u64,
    pub embedding_enabled: bool,
}

#[derive(Serialize)]
pub struct Message {
    pub id: String,
    pub role: String,          // "user" | "assistant"
    pub content: String,
    pub created_at: String,
}

#[derive(Serialize)]
pub struct EpisodicItem {
    pub id: String,
    pub summary: String,
    pub content: String,
    pub importance: f32,
    pub created_at: String,
    pub related_session: String,
}

#[derive(Serialize)]
pub struct SemanticMemory {
    pub facts: Vec<Fact>,
    pub attitude_score: f32,
    pub relationship_level: String,
}

#[derive(Serialize)]
pub struct Fact {
    pub key: String,
    pub value: String,
    pub updated_at: String,
}
```

### 4.4 日志

```rust
// src-tauri/src/commands/logs.rs

#[tauri::command]
pub async fn get_logs(
    bot_id: String,
    level: Option<String>,        // "all" | "info" | "warn" | "error"
    log_type: Option<String>,     // "all" | "dialogue" | "memory" | "session" | "proactive" | "api"
    date: Option<String>,        // "today" | "yesterday" | "2026-04-26"
    query: Option<String>,       // 搜索关键词
    page: u32,
    page_size: u32,
) -> Result<LogPage, String> {
    // 分页获取日志
}

#[tauri::command]
pub async fn stream_logs(
    bot_id: String,
    level: Option<String>,
) -> Result<LogStream, String> {
    // 返回 WebSocket URL 用于实时日志
}

#[tauri::command]
pub async fn export_logs(
    bot_id: String,
    start_date: String,
    end_date: String,
    log_types: Vec<String>,
) -> Result<String, String> {
    // 导出日志到文件，返回文件路径
}

#[derive(Serialize)]
pub struct LogPage {
    pub logs: Vec<LogEntry>,
    pub total: u32,
    pub page: u32,
    pub page_size: u32,
    pub total_pages: u32,
}

#[derive(Serialize)]
pub struct LogEntry {
    pub id: String,
    pub timestamp: String,
    pub level: String,           // "info" | "warn" | "error" | "debug"
    pub log_type: String,        // "dialogue" | "memory" | "session" | "proactive" | "api"
    pub platform: String,
    pub message: String,
    pub details: Option<String>,  // JSON 格式的额外信息
}

#[derive(Serialize)]
pub struct LogStream {
    pub ws_url: String,          // WebSocket URL
    pub token: String,           // 认证 token
}
```

### 4.5 配置管理

```rust
// src-tauri/src/commands/config.rs

#[tauri::command]
pub async fn get_config(bot_id: String) -> Result<BotConfig, String> {
    // 获取 Bot 配置
}

#[tauri::command]
pub async fn update_config(
    bot_id: String,
    config: BotConfigUpdate,
) -> Result<(), String> {
    // 更新配置
}

#[tauri::command]
pub async fn get_available_bots() -> Result<Vec<BotInfo>, String> {
    // 获取所有可用的 Bot
}

#[tauri::command]
pub async fn test_api_connection(
    provider: String,
    api_key: String,
    base_url: String,
) -> Result<bool, String> {
    // 测试 API 连接
}

#[derive(Serialize, Deserialize)]
pub struct BotConfig {
    pub bot_id: String,
    pub name: String,
    pub model: ModelConfig,
    pub memory: MemoryConfig,
    pub proactive: ProactiveConfig,
    pub platforms: Vec<PlatformConfig>,
    pub session_reset: SessionResetConfig,
}

#[derive(Serialize, Deserialize)]
pub struct ModelConfig {
    pub provider: String,
    pub api_key: String,
    pub base_url: String,
    pub model: String,
    pub temperature: f32,
    pub max_tokens: u32,
}

#[derive(Serialize, Deserialize)]
pub struct MemoryConfig {
    pub hard_limit_chars: u32,
    pub soft_limit_chars: u32,
    pub max_working_turns: u32,
    pub embedding: String,        // "none" | "local"
    pub embedding_model: String,
}

#[derive(Serialize, Deserialize)]
pub struct ProactiveConfig {
    pub enabled: bool,
    pub idle_threshold_hours: u32,
    pub min_interval_hours: u32,
    pub max_daily: u32,
    pub emotion_keywords: Vec<String>,
}

#[derive(Serialize, Deserialize)]
pub struct SessionResetConfig {
    pub mode: String,             // "daily" | "idle" | "both" | "none"
    pub at_hour: u32,
    pub idle_minutes: u32,
    pub notify: bool,
}
```

### 4.6 子进程管理（启动/停止 AI Companion）

```rust
// src-tauri/src/commands/process.rs

#[tauri::command]
pub async fn start_bot(bot_id: String) -> Result<(), String> {
    // 启动 Bot 实例
}

#[tauri::command]
pub async fn stop_bot(bot_id: String) -> Result<(), String> {
    // 停止 Bot 实例
}

#[tauri::command]
pub async fn restart_bot(bot_id: String) -> Result<(), String> {
    // 重启 Bot 实例
}

#[tauri::command]
pub async fn get_bot_status(bot_id: String) -> Result<BotStatus, String> {
    // 获取 Bot 运行状态
}

#[tauri::command]
pub async fn list_processes() -> Result<Vec<ProcessInfo>, String> {
    // 列出所有 AI Companion 相关进程
}

#[derive(Serialize)]
pub struct BotStatus {
    pub bot_id: String,
    pub running: bool,
    pub pid: Option<u32>,
    pub start_time: Option<String>,
    pub cpu_percent: f32,
    pub memory_mb: u64,
}
```

---

## 五、前端状态管理 (Zustand)

### 5.1 Bot Store

```typescript
// src/stores/botStore.ts
import { create } from 'zustand';

interface BotInfo {
  id: string;
  name: string;
  status: 'running' | 'stopped';
}

interface BotStore {
  bots: BotInfo[];
  currentBot: string;
  setCurrentBot: (id: string) => void;
  fetchBots: () => Promise<void>;
  startBot: (id: string) => Promise<void>;
  stopBot: (id: string) => Promise<void>;
}

export const useBotStore = create<BotStore>((set, get) => ({
  bots: [],
  currentBot: '',

  setCurrentBot: (id) => set({ currentBot: id }),

  fetchBots: async () => {
    const bots = await invoke<BotInfo[]>('get_available_bots');
    set({ bots });
    if (bots.length > 0 && !get().currentBot) {
      set({ currentBot: bots[0].id });
    }
  },

  startBot: async (id) => {
    await invoke('start_bot', { botId: id });
    await get().fetchBots();
  },

  stopBot: async (id) => {
    await invoke('stop_bot', { botId: id });
    await get().fetchBots();
  },
}));
```

### 5.2 Metrics Store

```typescript
// src/stores/metricsStore.ts
import { create } from 'zustand';

interface SystemMetrics {
  cpuPercent: number;
  memoryPercent: number;
  memoryUsedMb: number;
  diskPercent: number;
  uptimeSeconds: number;
}

interface BotMetrics {
  conversationsToday: number;
  proactiveMessagesToday: number;
  inputTokensToday: number;
  outputTokensToday: number;
  currentContextChars: number;
  hardLimitChars: number;
}

interface MetricsStore {
  system: SystemMetrics | null;
  bot: BotMetrics | null;
  isLoading: boolean;
  fetchMetrics: () => Promise<void>;
  startPolling: (intervalMs?: number) => void;
  stopPolling: () => void;
}

let pollingTimer: number | null = null;

export const useMetricsStore = create<MetricsStore>((set, get) => ({
  system: null,
  bot: null,
  isLoading: false,

  fetchMetrics: async () => {
    set({ isLoading: true });
    try {
      const [system, bot] = await Promise.all([
        invoke<SystemMetrics>('get_system_metrics'),
        invoke<BotMetrics>('get_bot_metrics', { botId: useBotStore.getState().currentBot }),
      ]);
      set({ system, bot });
    } finally {
      set({ isLoading: false });
    }
  },

  startPolling: (intervalMs = 5000) => {
    get().fetchMetrics();
    pollingTimer = window.setInterval(() => get().fetchMetrics(), intervalMs);
  },

  stopPolling: () => {
    if (pollingTimer) {
      clearInterval(pollingTimer);
      pollingTimer = null;
    }
  },
}));
```

### 5.3 Log Store

```typescript
// src/stores/logStore.ts
import { create } from 'zustand';

interface LogEntry {
  id: string;
  timestamp: string;
  level: 'info' | 'warn' | 'error';
  logType: string;
  platform: string;
  message: string;
  details?: string;
}

interface LogStore {
  logs: LogEntry[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
  isLoading: boolean;
  isStreaming: boolean;
  level: string;
  logType: string;
  date: string;
  query: string;
  fetchLogs: (page?: number) => Promise<void>;
  setFilter: (key: string, value: string) => void;
  startStream: () => void;
  stopStream: () => void;
  exportLogs: () => Promise<string>;
}

let ws: WebSocket | null = null;

export const useLogStore = create<LogStore>((set, get) => ({
  logs: [],
  total: 0,
  page: 1,
  pageSize: 50,
  totalPages: 0,
  isLoading: false,
  isStreaming: false,
  level: 'all',
  logType: 'all',
  date: 'today',
  query: '',

  fetchLogs: async (page = 1) => {
    const { level, logType, date, query, pageSize } = get();
    set({ isLoading: true });

    try {
      const result = await invoke<LogPage>('get_logs', {
        botId: useBotStore.getState().currentBot,
        level: level === 'all' ? null : level,
        logType: logType === 'all' ? null : logType,
        date,
        query: query || null,
        page,
        pageSize,
      });

      set({
        logs: result.logs,
        total: result.total,
        page: result.page,
        totalPages: result.totalPages,
      });
    } finally {
      set({ isLoading: false });
    }
  },

  setFilter: (key, value) => {
    set({ [key]: value, page: 1 });
    get().fetchLogs(1);
  },

  startStream: () => {
    const { level } = get();
    const stream = invoke<LogStream>('stream_logs', {
      botId: useBotStore.getState().currentBot,
      level: level === 'all' ? null : level,
    }).then(({ wsUrl, token }) => {
      ws = new WebSocket(`${wsUrl}?token=${token}`);

      ws.onmessage = (event) => {
        const log = JSON.parse(event.data) as LogEntry;
        set((state) => ({
          logs: [log, ...state.logs].slice(0, 500), // 保留最新500条
        }));
      };

      ws.onclose = () => set({ isStreaming: false });
      set({ isStreaming: true });
    });
  },

  stopStream: () => {
    if (ws) {
      ws.close();
      ws = null;
    }
    set({ isStreaming: false });
  },

  exportLogs: async () => {
    const { startDate, endDate, logTypes } = get();
    return invoke<string>('export_logs', {
      botId: useBotStore.getState().currentBot,
      startDate,
      endDate,
      logTypes,
    });
  },
}));
```

---

## 六、API 调用封装

```typescript
// src/api/tauri.ts
import { invoke } from '@tauri-apps/api/core';

// 封装所有 Tauri IPC 调用
// 提供类型安全的调用方式

export const tauriApi = {
  // 系统
  getSystemMetrics: () => invoke<SystemMetrics>('get_system_metrics'),
  getBotMetrics: (botId: string) => invoke<BotMetrics>('get_bot_metrics', { botId }),

  // 会话
  listSessions: (botId: string) => invoke<SessionInfo[]>('list_sessions', { botId }),
  getSessionDetail: (sessionKey: string) => invoke<SessionDetail>('get_session_detail', { sessionKey }),
  getSessionContext: (sessionKey: string) => invoke<ContextDetail>('get_session_context', { sessionKey }),
  resetSession: (sessionKey: string) => invoke<void>('reset_session', { sessionKey }),
  suspendSession: (sessionKey: string) => invoke<void>('suspend_session', { sessionKey }),

  // 记忆
  getMemoryStats: (botId: string) => invoke<MemoryStats>('get_memory_stats', { botId }),
  getWorkingMemory: (botId: string) => invoke<Message[]>('get_working_memory', { botId }),
  getEpisodicMemory: (botId: string, query?: string, limit?: number) =>
    invoke<EpisodicItem[]>('get_episodic_memory', { botId, query, limit }),
  getSemanticMemory: (botId: string) => invoke<SemanticMemory>('get_semantic_memory', { botId }),
  deleteMemory: (botId: string, memoryType: string, memoryId: string) =>
    invoke<void>('delete_memory', { botId, memoryType, memoryId }),
  clearAllMemory: (botId: string) => invoke<void>('clear_all_memory', { botId }),

  // 日志
  getLogs: (params: LogParams) => invoke<LogPage>('get_logs', params),
  streamLogs: (botId: string, level?: string) =>
    invoke<LogStream>('stream_logs', { botId, level }),
  exportLogs: (params: ExportParams) => invoke<string>('export_logs', params),

  // 配置
  getConfig: (botId: string) => invoke<BotConfig>('get_config', { botId }),
  updateConfig: (botId: string, config: Partial<BotConfig>) =>
    invoke<void>('update_config', { botId, config }),
  getAvailableBots: () => invoke<BotInfo[]>('get_available_bots'),
  testApiConnection: (provider: string, apiKey: string, baseUrl: string) =>
    invoke<boolean>('test_api_connection', { provider, apiKey, baseUrl }),

  // 进程
  startBot: (botId: string) => invoke<void>('start_bot', { botId }),
  stopBot: (botId: string) => invoke<void>('stop_bot', { botId }),
  restartBot: (botId: string) => invoke<void>('restart_bot', { botId }),
  getBotStatus: (botId: string) => invoke<BotStatus>('get_bot_status', { botId }),
  listProcesses: () => invoke<ProcessInfo[]>('list_processes'),
};
```

---

## 七、核心页面路由

```typescript
// src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout/Layout';
import Dashboard from './pages/Dashboard/Dashboard';
import Session from './pages/Session/Session';
import SessionContext from './pages/Session/Context';
import Memory from './pages/Memory/Memory';
import Logs from './pages/Logs/Logs';
import Settings from './pages/Settings/Settings';
import Skills from './pages/Skills/Skills';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="session" element={<Session />} />
          <Route path="session/:sessionKey/context" element={<SessionContext />} />
          <Route path="memory" element={<Memory />} />
          <Route path="logs" element={<Logs />} />
          <Route path="settings" element={<Settings />} />
          <Route path="skills" element={<Skills />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
```

---

## 八、实时通信

### 8.1 日志实时流 (WebSocket)

Rust 后端启动一个本地 WebSocket 服务器（或复用现有的 Tauri WebView）：

```rust
// 日志 WebSocket 路径: ws://localhost:18888/logs/{bot_id}
// 前端通过 tauri://localhost:18888 访问

// 或使用 Tauri 的事件系统
#[tauri::command]
pub async fn start_log_stream(app: AppHandle, bot_id: String) -> Result<(), String> {
    // 使用 tauri::emit 推送日志事件
    // 前端通过 listen() 订阅
}

// src-tauri/src/main.rs
use tauri::{Manager, Emitter};

loop {
    // 读取日志文件或从管道
    let log_entry = read_log().await;

    // 发送到前端
    app.emit("log-entry", log_entry).unwrap();
}
```

### 8.2 前端订阅

```typescript
// src/hooks/useLogStream.ts
import { listen } from '@tauri-apps/api/event';
import { useEffect } from 'react';
import { useLogStore } from '../stores/logStore';

export function useLogStream() {
  const addLog = useLogStore((s) => s.logs.unshift);

  useEffect(() => {
    const unlisten = listen<LogEntry>('log-entry', (event) => {
      addLog(event.payload);
    });

    return () => {
      unlisten.then((fn) => fn());
    };
  }, []);
}
```

### 8.3 监控数据轮询

对于监控仪表盘，使用轮询而非 WebSocket（数据量小，5秒间隔足够）：

```typescript
// Dashboard 页面
useEffect(() => {
  metricsStore.startPolling(5000);
  return () => metricsStore.stopPolling();
}, []);
```

---

## 九、数据流

### 9.1 会话列表 → 上下文详情

```
用户点击「查看上下文」
    ↓
Session 页面调用 getSessionContext(sessionKey)
    ↓
Rust 读取 SessionStore 获取 working_history
    ↓
Rust 调用 MemoryEngine.load_context() 加载三层记忆
    ↓
返回 ContextDetail {
    system_prompt,
    working_history,
    episodic_recall,
    semantic_facts,
    system_suffix,
    compression_history
}
    ↓
Context 页面渲染四层结构
```

### 9.2 日志查看

```
用户打开日志页面
    ↓
调用 getLogs({ page: 1, pageSize: 50 })
    ↓
Rust 读取日志文件 (JSONL 格式)
    ↓
过滤、分页、返回 LogPage
    ↓
用户开启「实时」
    ↓
WebSocket 连接，建立日志流
    ↓
新日志通过事件系统推送
    ↓
前端实时追加到列表
```

---

## 十、安全考虑

### 10.1 配置加密

API Key 等敏感配置不存储明文：

```rust
// 使用系统 Keychain (macOS) / Credential Manager (Windows)
// 或使用 Tauri's secure storage plugin

#[tauri::command]
pub async fn save_api_key(encrypted: String) -> Result<(), String> {
    // 加密存储
}

#[tauri::command]
pub async fn get_api_key() -> Result<String, String> {
    // 解密读取
}
```

### 10.2 权限控制

管理后台仅本地访问，无外部攻击面。

---

## 十一、开发计划

### Phase 1: 基础框架 (1周)
- [ ] Tauri 项目初始化
- [ ] React + Vite + TailwindCSS 搭建
- [ ] 基础 Layout + 路由
- [ ] Zustand 状态管理基础
- [ ] Tauri Commands 骨架

### Phase 2: 监控面板 (2-3天)
- [ ] 系统指标获取 (Rust)
- [ ] Bot 指标获取 (调用 Python)
- [ ] Dashboard UI
- [ ] 轮询机制

### Phase 3: 会话管理 (3-4天)
- [ ] Session 列表
- [ ] Session 详情
- [ ] 上下文结构展示
- [ ] 重置/挂起功能

### Phase 4: 日志查看 (2-3天)
- [ ] 日志读取 (Rust)
- [ ] 日志过滤/搜索/分页
- [ ] WebSocket 实时流
- [ ] 导出功能

### Phase 5: 记忆管理 (2-3天)
- [ ] 三层记忆读取
- [ ] 记忆搜索
- [ ] 删除/清空功能

### Phase 6: 配置管理 (2-3天)
- [ ] 配置读取/修改
- [ ] API 测试连接
- [ ] 持久化

### Phase 7: 打包发布 (1-2天)
- [ ] macOS .dmg
- [ ] Windows .exe (NSIS)
- [ ] Linux .AppImage

**总工期：约 3 周**

---

## 十二、依赖版本

```json
// package.json
{
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.22.0",
    "zustand": "^4.5.0",
    "recharts": "^2.12.0",
    "axios": "^1.6.7",
    "@tauri-apps/api": "^2.0.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.1",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.2.1",
    "autoprefixer": "^10.4.18",
    "postcss": "^8.4.35",
    "tailwindcss": "^3.4.1",
    "typescript": "^5.4.0",
    "vite": "^5.2.0"
  }
}
```

```toml
# src-tauri/Cargo.toml
[package]
name = "ai-companion-ui"
version = "1.0.0"

[dependencies]
tauri = { version = "2", features = ["shell-open"] }
tauri-plugin-shell = "2"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tokio = { version = "1", features = ["full"] }
sysinfo = "0.30"
directories = "5"

[build-dependencies]
tauri-build = "2"
```

---

## 十三、文件位置

文档存放位置：`/Users/wangxiaowei/projects/own/ai-girl-friend/docs/UI_TECH_DESIGN.md`
