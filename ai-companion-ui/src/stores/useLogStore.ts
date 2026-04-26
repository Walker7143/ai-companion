import { create } from 'zustand';
import { listen } from '@tauri-apps/api/event';
import { logsApi } from '../api/tauri';
import type { LogParams, LogEntry, LogStreamEvent } from '../types';

interface LogState {
  logs: LogEntry[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
  loading: boolean;
  streaming: boolean;
  error: string | null;
  unlistenFn: (() => void) | null;
  fetchLogs: (params: Partial<LogParams>) => Promise<void>;
  setPage: (page: number) => void;
  setFilters: (filters: Partial<LogParams>) => void;
  startStreaming: (botId: string) => Promise<void>;
  stopStreaming: () => void;
  exportLogs: (botId: string, format: 'json' | 'csv') => Promise<string>;
}

const defaultParams: LogParams = {
  bot_id: '',
  level: undefined,
  log_type: undefined,
  date: undefined,
  query: undefined,
  page: 1,
  page_size: 20,
};

export const useLogStore = create<LogState>((set, get) => ({
  logs: [],
  total: 0,
  page: 1,
  pageSize: 20,
  totalPages: 0,
  loading: false,
  streaming: false,
  error: null,
  unlistenFn: null,

  fetchLogs: async (params: Partial<LogParams>) => {
    set({ loading: true, error: null });
    try {
      const { pageSize } = get();
      const fullParams: LogParams = {
        ...defaultParams,
        page_size: pageSize,
        ...params,
      };
      const data = await logsApi.getLogs(fullParams);
      set({
        logs: data.logs,
        total: data.total,
        page: data.page,
        pageSize: data.page_size,
        totalPages: data.total_pages,
        loading: false,
      });
    } catch (err) {
      set({ loading: false, error: String(err) });
    }
  },

  setPage: (page: number) => {
    set({ page });
    get().fetchLogs({ page });
  },

  setFilters: (filters: Partial<LogParams>) => {
    set({ page: 1, ...filters });
    get().fetchLogs({ page: 1, ...filters });
  },

  startStreaming: async (botId: string) => {
    const { unlistenFn, streaming } = get();
    if (streaming || unlistenFn) return;

    set({ streaming: true });

    try {
      // Start streaming on backend
      await logsApi.streamLogs(botId);

      // Listen for log events
      const unlisten = await listen<LogStreamEvent>('log-event', (event) => {
        const newLog: LogEntry = {
          id: event.payload.id,
          timestamp: event.payload.timestamp,
          level: event.payload.level,
          log_type: event.payload.log_type,
          platform: event.payload.platform,
          message: event.payload.message,
          details: null,
        };
        set((state) => ({
          logs: [newLog, ...state.logs].slice(0, 100), // Keep last 100
          total: state.total + 1,
        }));
      });

      set({ unlistenFn: unlisten });
    } catch (err) {
      set({ streaming: false, error: String(err) });
    }
  },

  stopStreaming: () => {
    const { unlistenFn } = get();
    if (unlistenFn) {
      unlistenFn();
      set({ unlistenFn: null, streaming: false });
    }
  },

  exportLogs: async (botId: string, format: 'json' | 'csv') => {
    return logsApi.exportLogs(botId, format, '');
  },
}));
