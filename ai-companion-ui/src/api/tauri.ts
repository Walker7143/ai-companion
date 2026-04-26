import { invoke } from '@tauri-apps/api/core';
import type {
  SystemMetrics,
  BotMetrics,
  SessionInfo,
  SessionDetail,
  ContextDetail,
  MemoryStats,
  Message,
  EpisodicItem,
  SemanticMemory,
  LogParams,
  LogPage,
  BotConfig,
  BotInfo,
  BotStatus,
  ProcessInfo,
} from '../types';

// System API
export const systemApi = {
  getSystemMetrics: () => invoke<SystemMetrics>('get_system_metrics'),
  getBotMetrics: (botId: string) => invoke<BotMetrics>('get_bot_metrics', { botId }),
};

// Session API
export const sessionApi = {
  listSessions: (botId: string) => invoke<SessionInfo[]>('list_sessions', { botId }),
  getSessionDetail: (sessionKey: string) => invoke<SessionDetail>('get_session_detail', { sessionKey }),
  resetSession: (sessionKey: string) => invoke<void>('reset_session', { sessionKey }),
  suspendSession: (sessionKey: string) => invoke<void>('suspend_session', { sessionKey }),
  getSessionContext: (sessionKey: string) => invoke<ContextDetail>('get_session_context', { sessionKey }),
};

// Memory API
export const memoryApi = {
  getMemoryStats: (botId: string) => invoke<MemoryStats>('get_memory_stats', { botId }),
  getWorkingMemory: (botId: string) => invoke<Message[]>('get_working_memory', { botId }),
  getEpisodicMemory: (botId: string, query?: string, limit?: number) =>
    invoke<EpisodicItem[]>('get_episodic_memory', { botId, query, limit }),
  getSemanticMemory: (botId: string) => invoke<SemanticMemory>('get_semantic_memory', { botId }),
  deleteMemory: (botId: string, memoryType: string, memoryId: string) =>
    invoke<void>('delete_memory', { botId, memoryType, memoryId }),
  clearAllMemory: (botId: string) => invoke<void>('clear_all_memory', { botId }),
};

// Logs API
export const logsApi = {
  getLogs: (params: LogParams) => invoke<LogPage>('get_logs', { params }),
  streamLogs: (botId: string) => invoke<void>('stream_logs', { botId }),
  exportLogs: (botId: string, format: string, path: string) =>
    invoke<string>('export_logs', { botId, format, path }),
};

// Config API
export const configApi = {
  getConfig: (botId: string) => invoke<BotConfig>('get_config', { botId }),
  updateConfig: (botId: string, config: BotConfig) =>
    invoke<void>('update_config', { botId, config }),
  getAvailableBots: () => invoke<BotInfo[]>('get_available_bots'),
  testApiConnection: (provider: string, apiKey: string, baseUrl: string) =>
    invoke<boolean>('test_api_connection', { provider, apiKey, baseUrl }),
};

// Process API
export const processApi = {
  startBot: (botId: string) => invoke<void>('start_bot', { botId }),
  stopBot: (botId: string) => invoke<void>('stop_bot', { botId }),
  restartBot: (botId: string) => invoke<void>('restart_bot', { botId }),
  getBotStatus: (botId: string) => invoke<BotStatus>('get_bot_status', { botId }),
  listProcesses: () => invoke<ProcessInfo[]>('list_processes'),
};
