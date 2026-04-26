import { create } from 'zustand';
import { logsApi } from '../api';
import type { LogEntry } from '../types';

interface LogParams {
  botId: string;
  level?: string;
  type?: string;
  date?: string;
  query?: string;
  page: number;
  pageSize: number;
}

interface LogState {
  logs: LogEntry[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
  loading: boolean;
  streaming: boolean;
  error: string | null;
  ws: WebSocket | null;
  fetchLogs: (params: Partial<LogParams>) => Promise<void>;
  setPage: (page: number) => void;
  setFilters: (filters: Partial<LogParams>) => void;
  startStreaming: (botId: string, level?: string) => void;
  stopStreaming: () => void;
  exportLogs: (botId: string, format: 'json' | 'csv') => Promise<string>;
}

const defaultParams: LogParams = {
  botId: '',
  level: undefined,
  type: undefined,
  date: undefined,
  query: undefined,
  page: 1,
  pageSize: 20,
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
  ws: null,

  fetchLogs: async (params: Partial<LogParams>) => {
    set({ loading: true, error: null });
    try {
      const { pageSize } = get();
      const fullParams: LogParams = {
        ...defaultParams,
        pageSize,
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

  startStreaming: (botId: string, level?: string) => {
    const { ws, streaming } = get();
    if (streaming || ws) return;

    set({ streaming: true });

    try {
      const { wsUrl } = logsApi.streamLogs(botId, level);
      const socket = new WebSocket(wsUrl);

      socket.onmessage = (event) => {
        try {
          const newLog: LogEntry = JSON.parse(event.data);
          set((state) => ({
            logs: [newLog, ...state.logs].slice(0, 100),
            total: state.total + 1,
          }));
        } catch {
          // Ignore parse errors
        }
      };

      socket.onclose = () => {
        set({ streaming: false, ws: null });
      };

      socket.onerror = () => {
        set({ streaming: false, ws: null, error: 'WebSocket error' });
      };

      set({ ws: socket });
    } catch (err) {
      set({ streaming: false, error: String(err) });
    }
  },

  stopStreaming: () => {
    const { ws } = get();
    if (ws) {
      ws.close();
      set({ ws: null, streaming: false });
    }
  },

  exportLogs: async (botId: string, format: 'json' | 'csv') => {
    return logsApi.exportLogs(botId, format);
  },
}));
