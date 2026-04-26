# AI Companion 管理后台 - UI 设计方案

> 版本: v1.0
> 日期: 2026-04-26

---

## 一、产品概述

### 1.1 产品定位

AI Companion 管理后台 — 面向开发者/运维人员的控制面板，用于监控 Bot 状态、管理会话和上下文、查看日志、配置参数。

### 1.2 核心用户

- 开发者：调试 Bot 行为、查看日志
- 运维：监控运行状态、管理配置
- 技术用户：理解记忆和上下文机制

### 1.3 使用场景

- 桌面端为主（Windows/macOS）
- 移动端可查看（响应式）

---

## 二、设计原则

### 2.1 视觉定位

**类比产品：** Datadog / Grafana / Vercel Dashboard

- 专业、高效、数据密集
- 暗色主题优先（长时间盯屏不累眼）
- 亮色主题可选

### 2.2 设计原则

| 原则 | 说明 |
|------|------|
| **信息密度优先** | 充分利用屏幕空间展示关键数据 |
| **层次分明** | 重要信息突出，次要信息收敛 |
| **操作明确** | 危险操作需二次确认 |
| **实时感知** | 监控数据定时刷新，日志实时推送 |
| **一致体验** | 全局统一的交互模式 |

---

## 三、设计规范

### 3.1 色彩系统

#### 暗色主题（默认）

```css
:root {
  /* 背景层 */
  --bg-primary: #0f1419;      /* 主背景 */
  --bg-secondary: #1a1f26;    /* 卡片/面板背景 */
  --bg-tertiary: #242b35;    /* 悬浮/选中背景 */
  --bg-elevated: #2d3640;    /* 弹窗/下拉背景 */

  /* 边框 */
  --border-subtle: #2d3640;   /* 细分隔线 */
  --border-default: #3d4654;  /* 默认边框 */
  --border-strong: #4d5664;   /* 强调边框 */

  /* 文本 */
  --text-primary: #e7e9ea;    /* 主要文本 */
  --text-secondary: #8b98a5;  /* 次要文本 */
  --text-muted: #5c6b7a;     /* 禁用/提示文本 */

  /* 功能色 */
  --accent: #3b82f6;          /* 主操作/链接 */
  --accent-hover: #2563eb;    /* 主操作悬浮 */

  /* 状态色 */
  --success: #22c55e;         /* 成功/运行中 */
  --warning: #f59e0b;         /* 警告 */
  --error: #ef4444;           /* 错误/危险 */
  --info: #06b6d4;            /* 信息 */

  /* 标签色 */
  --tag-dialogue: #22c55e;    /* 对话日志 */
  --tag-memory: #a855f7;      /* 记忆日志 */
  --tag-session: #f59e0b;     /* 会话日志 */
  --tag-proactive: #ec4899;   /* 主动唤醒日志 */
  --tag-api: #06b6d4;         /* API调用日志 */
  --tag-error: #ef4444;       /* 错误日志 */
}
```

#### 亮色主题

```css
:root[data-theme="light"] {
  --bg-primary: #ffffff;
  --bg-secondary: #f7f9f9;
  --bg-tertiary: #eff3f4;
  --border-subtle: #cfd9de;
  --border-default: #b9c3cc;
  --text-primary: #0f1419;
  --text-secondary: #536471;
  --text-muted: #8b98a5;
  --accent: #1d9bf0;
  --accent-hover: #1a8cd8;
}
```

### 3.2 字体系统

```css
/* 字体栈 */
--font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
--font-mono: 'JetBrains Mono', 'Fira Code', 'SF Mono', monospace;

/* 字号 */
--text-xs: 0.75rem;    /* 12px - 标签/徽章 */
--text-sm: 0.8125rem; /* 13px - 次要文本 */
--text-base: 0.875rem; /* 14px - 正文 */
--text-lg: 1rem;       /* 16px - 标题 */
--text-xl: 1.25rem;    /* 20px - 页面标题 */
--text-2xl: 1.5rem;    /* 24px - 大标题 */

/* 行高 */
--leading-tight: 1.25;
--leading-normal: 1.5;
--leading-relaxed: 1.75;

/* 字重 */
--font-normal: 400;
--font-medium: 500;
--font-semibold: 600;
--font-bold: 700;
```

### 3.3 间距系统

基于 4px 网格：

```css
--space-1: 0.25rem;   /* 4px */
--space-2: 0.5rem;    /* 8px */
--space-3: 0.75rem;   /* 12px */
--space-4: 1rem;      /* 16px */
--space-5: 1.25rem;  /* 20px */
--space-6: 1.5rem;    /* 24px */
--space-8: 2rem;      /* 32px */
--space-10: 2.5rem;   /* 40px */
--space-12: 3rem;     /* 48px */
```

### 3.4 圆角

```css
--radius-sm: 4px;     /* 输入框、小按钮 */
--radius-md: 6px;     /* 卡片、面板 */
--radius-lg: 8px;     /* 模态框、大卡片 */
--radius-full: 9999px; /* 标签、徽章 */
```

### 3.5 阴影

```css
--shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
--shadow-md: 0 4px 6px rgba(0, 0, 0, 0.4);
--shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.5);
--shadow-glow: 0 0 20px rgba(59, 130, 246, 0.3); /* Accent glow */
```

### 3.6 动效

```css
/* 过渡 */
--transition-fast: 150ms ease;
--transition-base: 200ms ease;
--transition-slow: 300ms ease;

/* 动画 */
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideIn {
  from { transform: translateY(10px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 使用 */
.animate-fade-in { animation: fadeIn var(--transition-base); }
.animate-slide-in { animation: slideIn var(--transition-slow); }
.animate-pulse { animation: pulse 2s infinite; }
.animate-spin { animation: spin 1s linear infinite; }
```

---

## 四、页面设计

### 4.1 整体布局

```
┌─────────────────────────────────────────────────────────────┐
│ Header (48px)                                              │
│ [Logo] AI Companion          [Bot ▼]  [Theme] [Settings]  │
├──────────┬──────────────────────────────────────────────────┤
│ Sidebar  │                                                  │
│ (200px)  │               Main Content                      │
│          │                                                  │
│ 📊 监控  │                                                  │
│ ⚙️ 设置  │                                                  │
│ 💬 会话  │                                                  │
│ 📝 日志  │                                                  │
│ 🤖 技能  │                                                  │
│ ───────  │                                                  │
│ 💾 记忆  │                                                  │
│ 💾 数据  │                                                  │
│          │                                                  │
│ [展开▼]  │                                                  │
└──────────┴──────────────────────────────────────────────────┘
```

**响应式断点：**

| 断点 | 宽度 | 行为 |
|------|------|------|
| Desktop | ≥1024px | 完整侧边栏 + 内容 |
| Tablet | 768-1023px | 收起侧边栏，汉堡菜单 |
| Mobile | <768px | 底部 Tab 导航 |

### 4.2 监控仪表盘

```
┌─────────────────────────────────────────────────────────────┐
│ 📊 监控                                           [刷新 🔄]  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ ┌─ 状态卡片 (4列) ───────────────────────────────────────┐  │
│ │                                                        │  │
│ │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │  │
│ │ │ 🟢 运行中  │ │ ⏱️ 3d    │ │ 💬 23    │ │ 📤 5    │ │  │
│ │ │          │ │ 14h 22m  │ │ 今日对话  │ │ 主动消息 │ │  │
│ │ │ 状态     │ │ 运行时长  │ │          │ │          │ │  │
│ │ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │  │
│ │                                                        │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                              │
│ ┌─ 上下文状态 ──────────┐  ┌─ Token 消耗 ──────────────┐  │
│ │                          │  │                              │  │
│ │  ████████░░░  68%      │  │  今日: 12,450 / 100,000     │  │
│ │  2,450 / 3,600 chars   │  │  ████░░░░░░░░░░░░░░░░ 12%  │  │
│ │                          │  │  延迟: 230ms              │  │
│ │  压缩: 3 次             │  │  模型: MiniMax-M2.7         │  │
│ └──────────────────────────┘  └────────────────────────────┘  │
│                                                              │
│ ┌─ 主动唤醒 ─────────────────────────────────────────────┐  │
│ │  🔔 已启用    ⏰ 24h阈值   📊 今日 3/5   💭 2次情绪触发 │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                              │
│ ┌─ 记忆状态 ─────────────────────────────────────────────┐  │
│ │  ┌─────────┬─────────┬─────────┐                        │  │
│ │  │ 工作记忆 │ 情景记忆 │ 语义记忆 │                        │  │
│ │  │  23条   │  156条  │   42条  │                        │  │
│ │  │  ████░ │  █████░ │  ███░░ │                        │  │
│ │  └─────────┴─────────┴─────────┘                        │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**设计要点：**
- 状态卡片网格布局（CSS Grid: repeat(4, 1fr)）
- 进度条用渐变色（绿色→黄色→红色表示占比）
- 数字用等宽字体（JetBrains Mono）
- 实时数据每 5 秒轮询刷新

### 4.3 会话管理

```
┌─────────────────────────────────────────────────────────────┐
│ 💬 会话管理                                      [导出 📤]   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ Bot: [苏晴 ▼]   平台: [全部 ▼]   状态: [全部 ▼]           │
│                                                              │
│ ┌─ 当前会话 ─────────────────────────────────────────────┐  │
│ │                                                            │  │
│ │  Session ID: 20260426_143215_a1b2c3d4                    │  │
│ │  平台: 🖥️ CLI  用户: localhost                          │  │
│ │  创建: 2026-04-26 14:32:15  活跃: 2小时前               │  │
│ │                                                            │  │
│ │  Token: Input 1,234 | Output 2,456 | Cache 690 | 总计 4,380 │  │
│ │  费用: $0.0123 USD                                       │  │
│ │                                                            │  │
│ │  [查看上下文]  [查看记忆]  [重置会话]  [挂起会话]         │  │
│ │                                                            │  │
│ └────────────────────────────────────────────────────────────┘  │
│                                                              │
│ ┌─ 会话历史 ─────────────────────────────────────────────┐  │
│ │                                                            │  │
│ │  📅 今天                                                  │  │
│ │  ├── 14:32:15  cli://localhost        🟢 活跃           │  │
│ │  └── 09:15:00  feishu://oc_xxx       🔴 已重置 (idle)   │  │
│ │                                                            │  │
│ │  📅 昨天                                                  │  │
│ │  ├── 22:30:00  cli://localhost       🔴 已重置 (daily)   │  │
│ │  └── 18:45:00  feishu://oc_xxx       🔴 已重置 (idle)   │  │
│ │                                                            │  │
│ └────────────────────────────────────────────────────────────┘  │
│                                                              │
│ ┌─ 重置策略 ─────────────────────────────────────────────┐  │
│ │                                                            │  │
│ │  模式: [每日+空闲 ▼]                                      │  │
│ │  每日重置: 04:00    空闲超时: 1440分钟                    │  │
│ │  重置通知: [启用]                                         │  │
│ │                                                            │  │
│ └────────────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**设计要点：**
- 表格使用斑马纹（zebra striping）
- 状态用彩色标签（绿色活跃、红色已重置）
- 操作按钮组右对齐
- 分页器固定在底部

### 4.4 上下文详情

```
┌─────────────────────────────────────────────────────────────┐
│ ◀ 返回          上下文详情                    Token: 4,380   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ ┌─ System Prompt ────────────────────────────────────────┐  │
│ │ 你叫苏晴，26岁自由插画师，性格傲娇...                      │  │
│ │ 关系状态: 暧昧期 ❤️                                       │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                              │
│ ┌─ 工作记忆 ▼ ───────────────────────────────────────────┐  │
│ │ 摘要[3]: 最近在讨论工作很累的话题                         │  │
│ │ ─────────────────────────────────────────────────────── │  │
│ │ [1] user: 今天加班好累                                   │  │
│ │ [2] bot: 又加班了吗...要注意身体啊                       │  │
│ │ [3] user: 嗯，最近项目赶工期                             │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                              │
│ ┌─ 情景记忆 ▼ ───────────────────────────────────────────┐  │
│ │ 召回 3 条 (相关性降序)                                   │  │
│ │ ─────────────────────────────────────────────────────── │  │
│ │ ★★★★☆ [0.92] 「上次加班到很晚，她说笨蛋...」           │  │
│ │ ★★★★☆ [0.85] 「你喜欢她的画，她很开心」                 │  │
│ │ ★★★☆☆ [0.78] 「上周吵架后和好的那次」                   │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                              │
│ ┌─ 语义记忆 ▼ ───────────────────────────────────────────┐  │
│ │ 💕 关系相关                                             │  │
│ │   · 关系状态: 暧昧期                                    │  │
│ │   · 好感度: +6 ↑                                       │  │
│ │ 👤 基本信息                                             │  │
│ │   · 职业: 程序员（经常加班）                           │  │
│ │ 🎂 重要日期                                             │  │
│ │   · 生日: 5月15日（还有约2周）                         │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                              │
│ ┌─ 压缩历史 ─────────────────────────────────────────────┐  │
│ │ 压缩 3 次 | 最后: 14:20:00 | 节省: 64-72%              │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**设计要点：**
- 手风琴组件（Accordion）展开/收起各层
- 相关性用星级或进度条表示
- 记忆条目可点击查看完整内容
- 代码块（System Prompt）用等宽字体

### 4.5 日志查看

```
┌─────────────────────────────────────────────────────────────┐
│ 📝 日志                           [实时 ●] [导出 📤]       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ [全部 ▼]  [今天 ▼]  🔍 [搜索: agent|error         ]        │
│                                                              │
│ ┌─ 级别 ────────────────────────────────────────────────┐  │
│ │  [全部]  [对话]  [记忆]  [会话]  [主动]  [API]  [错误] │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                              │
│ ─────────────────────────────────────────────────────────── │
│                                                              │
│ 14:32:15.234  [对话]  🟢 user → bot                       │
│               「今天工作好累啊」                               │
│                                                              │
│ 14:32:15.456  [会话]  💾 加载上下文                        │
│               working: 4 | episodic: 3 | semantic: 42       │
│                                                              │
│ 14:32:15.678  [记忆]  💾 存储工作记忆                      │
│               session: 20260426_xxx  tokens: +45          │
│                                                              │
│ 14:32:16.100  [API]  📤 MiniMax.chat                      │
│               tokens: 1234/2345  延迟: 215ms  $0.003       │
│                                                              │
│ 14:32:17.123  [对话]  🟢 bot → user                       │
│               「又加班了吗...要注意身体啊笨蛋」                 │
│                                                              │
│ 14:31:45.000  [主动]  🔔 空闲触发                          │
│               24h30m > 阈值24h                              │
│                                                              │
│ ─────────────────────────────────────────────────────────── │
│                                                              │
│ ◀ 上一页  [1] [2] [3] ... [42]  下一页 ▶   实时: ON ●    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**设计要点：**
- 日志级别用颜色标签区分
- 时间戳用等宽字体
- 搜索框支持正则表达式
- 实时开关用 Toggle Switch
- 虚拟滚动（Virtual Scroll）处理大量日志

### 4.6 记忆管理

```
┌─────────────────────────────────────────────────────────────┐
│ 💾 记忆管理                                    [搜索 🔍]    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ Bot: [苏晴 ▼]                                              │
│                                                              │
│ ┌─ 记忆总览 ─────────────────────────────────────────────┐  │
│ │  ┌─────────┬─────────┬─────────┐                        │  │
│ │  │ 工作记忆  │ 情景记忆  │ 语义记忆  │                        │  │
│ │  │  23条   │  156条  │   42条  │                        │  │
│ │  │  12 KB  │  89 KB  │   8 KB  │                        │  │
│ │  │  [展开] │  [展开]  │  [展开]  │                        │  │
│ │  └─────────┴─────────┴─────────┘                        │  │
│ │  向量嵌入: ● 启用  模型: all-MiniLM-L6-v2              │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                              │
│ ┌─ 情景记忆 ─────────────────────────────────────────────┐  │
│ │ [搜索情景记忆...]                                        │  │
│ │ ───────────────────────────────────────────────────── │  │
│ │ ★★★★☆ 「上次加班到很晚，她发了关心消息」               │  │
│ │         相关: 20260424_xxx  创建: 04-24  feishu       │  │
│ │ ───────────────────────────────────────────────────── │  │
│ │ ★★★★★ 「你说喜欢她的画，她很开心」                     │  │
│ │         相关: 20260420_xxx  创建: 04-20  cli          │  │
│ │ ───────────────────────────────────────────────────── │  │
│ │                                      [删除] [标记重要] │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                              │
│ ┌─ 语义记忆 ─────────────────────────────────────────────┐  │
│ │ 💕 关系: 暧昧期 (+6 ↑)                                 │  │
│ │ 👤 职业: 程序员 | 城市: 上海                           │  │
│ │ ❤️ 喜欢: 简洁直接 | 讨厌: 太啰嗦                       │  │
│ │ 🎂 生日: 5月15日（还有约2周）                         │  │
│ │ ───────────────────────────────────────────────────── │  │
│ │                              [编辑] [删除] [添加事实]   │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**设计要点：**
- 三栏卡片布局展示三层记忆
- 重要性用星级表示
- 语义记忆以结构化方式展示（分类）
- 危险操作（删除）需二次确认

### 4.7 设置面板

```
┌─────────────────────────────────────────────────────────────┐
│ ⚙️ 设置                                                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ ┌─ 模型配置 ─────────────────────────────────────────────┐  │
│ │                                                            │  │
│ │  Provider   [MiniMax              ▼]                     │  │
│ │  API Key    [••••••••••••••••••••••••]  [测试]        │  │
│ │  Base URL   [https://api.minimax.chat/v1      ]         │  │
│ │  Model      [MiniMax-M2.7                         ]         │  │
│ │                                                            │  │
│ │  Temperature  [0.8  ]    Max Tokens  [1024    ]          │  │
│ │                                                            │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                              │
│ ┌─ 平台配置 ─────────────────────────────────────────────┐  │
│ │                                                            │  │
│ │  ┌─────────┬─────────┬─────────┐                        │  │
│ │  │ 🖥️ CLI  │ 📱 飞书 │ 🔗 Webhook │                     │  │
│ │  │  [●]    │  [●]    │   [○]    │                        │  │
│ │  │ ● 连接中 │ ● 连接中 │          │                        │  │
│ │  └─────────┴─────────┴─────────┘                        │  │
│ │                                                            │  │
│ │  飞书配置:                                                 │  │
│ │  App ID    [cli_xxxxxxxxxxxxx                   ]        │  │
│ │  Secret    [•••••••••••••••••••••••            ]        │  │
│ │                                                            │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                              │
│ ┌─ 上下文配置 ──────────────────────────────────────────┐  │
│ │                                                            │  │
│ │  工作记忆上限    [20 ] 轮                               │  │
│ │  上下文硬上限    [5000] 字符                           │  │
│ │  上下文软上限    [3000] 字符                           │  │
│ │                                                            │  │
│ │  结构化压缩: [●] 启用                                    │  │
│ │  触发阈值: [0.75]  尾部保留: [4000] tokens           │  │
│ │                                                            │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                              │
│                          [保存配置]  [重置默认]               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**设计要点：**
- 表单分组用卡片分隔
- 密码字段用 dots 隐藏 + 显示切换
- 测试按钮在输入框同一行
- 保存按钮固定在底部

---

## 五、组件规范

### 5.1 按钮

```tsx
// 类型
type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
type ButtonSize = 'sm' | 'md' | 'lg';

// 样式
.primary {
  bg: var(--accent);
  color: white;
  hover: var(--accent-hover);
}

.secondary {
  bg: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
}

.ghost {
  bg: transparent;
  color: var(--text-secondary);
  hover: bg var(--bg-tertiary);
}

.danger {
  bg: var(--error);
  color: white;
}

// 尺寸
.sm { h: 28px; px: 12px; font-size: var(--text-xs); }
.md { h: 36px; px: 16px; font-size: var(--text-sm); }
.lg { h: 44px; px: 20px; font-size: var(--text-base); }
```

### 5.2 输入框

```tsx
.input {
  h: 36px;
  px: 12px;
  bg: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.input:focus {
  border-color: var(--accent);
  outline: none;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
}

.input::placeholder {
  color: var(--text-muted);
}

.input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
```

### 5.3 卡片

```tsx
.card {
  bg: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  p: var(--space-4);
}

.card-header {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  mb: var(--space-3);
}
```

### 5.4 标签/徽章

```tsx
.badge {
  display: inline-flex;
  align-items: center;
  h: 22px;
  px: 8px;
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  border-radius: var(--radius-full);
}

.badge-success { bg: rgba(34, 197, 94, 0.15); color: var(--success); }
.badge-warning { bg: rgba(245, 158, 11, 0.15); color: var(--warning); }
.badge-error { bg: rgba(239, 68, 68, 0.15); color: var(--error); }
.badge-info { bg: rgba(6, 182, 212, 0.15); color: var(--info); }
```

### 5.5 表格

```tsx
.table {
  width: 100%;
  border-collapse: collapse;
}

.table th {
  text-align: left;
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  py: var(--space-2);
  px: var(--space-3);
  border-bottom: 1px solid var(--border-subtle);
}

.table td {
  py: var(--space-3);
  px: var(--space-3);
  border-bottom: 1px solid var(--border-subtle);
  font-size: var(--text-sm);
}

.table tr:hover {
  bg: var(--bg-tertiary);
}
```

### 5.6 折叠面板 (Accordion)

```tsx
.accordion {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.accordion-item {
  border-bottom: 1px solid var(--border-subtle);
}

.accordion-item:last-child {
  border-bottom: none;
}

.accordion-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  w: 100%;
  p: var(--space-3) var(--space-4);
  bg: var(--bg-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  text-align: left;
}

.accordion-trigger:hover {
  bg: var(--bg-tertiary);
}

.accordion-content {
  p: var(--space-4);
  bg: var(--bg-primary);
  font-size: var(--text-sm);
}
```

### 5.7 进度条

```tsx
.progress {
  h: 8px;
  bg: var(--bg-tertiary);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.progress-bar {
  h: 100%;
  border-radius: var(--radius-full);
  transition: width var(--transition-base);
}

.progress-low { bg: var(--success); }     /* 0-60% */
.progress-medium { bg: var(--warning); }  /* 60-85% */
.progress-high { bg: var(--error); }     /* 85-100% */
```

### 5.8 Toggle Switch

```tsx
.toggle {
  position: relative;
  w: 40px;
  h: 22px;
  bg: var(--bg-tertiary);
  border-radius: var(--radius-full);
  cursor: pointer;
  transition: bg var(--transition-fast);
}

.toggle[data-checked="true"] {
  bg: var(--accent);
}

.toggle::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  w: 18px;
  h: 18px;
  bg: white;
  border-radius: 50%;
  transition: transform var(--transition-fast);
}

.toggle[data-checked="true"]::after {
  transform: translateX(18px);
}
```

---

## 六、图标

使用 **Lucide Icons**（MIT 许可）：

```bash
npm install lucide-react
```

常用图标：

| 功能 | 图标名 |
|------|--------|
| 监控 | `Activity` |
| 设置 | `Settings` |
| 会话 | `MessageSquare` |
| 日志 | `FileText` |
| 技能 | `Wand2` |
| 记忆 | `Brain` |
| 数据 | `Database` |
| 刷新 | `RefreshCw` |
| 搜索 | `Search` |
| 导出 | `Download` |
| 删除 | `Trash2` |
| 编辑 | `Pencil` |
| 发送 | `Send` |
| 连接 | `Plug` |
| 断开 | `Unplug` |

---

## 七、主题切换

```tsx
// ThemeProvider.tsx
import { createContext, useContext, useEffect, useState } from 'react';

type Theme = 'dark' | 'light';

const ThemeContext = createContext<{
  theme: Theme;
  toggleTheme: () => void;
}>({ theme: 'dark', toggleTheme: () => {} });

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState<Theme>(() => {
    const stored = localStorage.getItem('theme');
    return (stored as Theme) || 'dark';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((t) => (t === 'dark' ? 'light' : 'dark'));
  };

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
```

---

## 八、技术实现

### 8.1 组件库

基于 Headless UI + TailwindCSS：

```bash
npm install @headlessui/react
```

### 8.2 状态管理

使用 Zustand 管理全局状态：

```typescript
// stores/
export { useBotStore } from './botStore';
export { useMetricsStore } from './metricsStore';
export { useLogStore } from './logStore';
export { useSessionStore } from './sessionStore';
export { useMemoryStore } from './memoryStore';
```

### 8.3 样式

TailwindCSS 配置扩展：

```js
// tailwind.config.js
module.exports = {
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg: {
          primary: 'var(--bg-primary)',
          secondary: 'var(--bg-secondary)',
          tertiary: 'var(--bg-tertiary)',
        },
        border: {
          subtle: 'var(--border-subtle)',
          default: 'var(--border-default)',
        },
        text: {
          primary: 'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          muted: 'var(--text-muted)',
        },
      },
      fontFamily: {
        sans: ['Inter', '...'],
        mono: ['JetBrains Mono', '...'],
      },
    },
  },
};
```
