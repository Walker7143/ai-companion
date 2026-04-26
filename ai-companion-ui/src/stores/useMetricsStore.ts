import { create } from 'zustand';
import { systemApi } from '../api';
import type { SystemMetrics, BotMetrics } from '../types';

const POLL_INTERVAL = 5000;

interface MetricsState {
  systemMetrics: SystemMetrics | null;
  botMetrics: BotMetrics | null;
  loading: boolean;
  error: string | null;
  intervalId: number | null;
  currentBotId: string | null;
  fetchSystemMetrics: () => Promise<void>;
  fetchBotMetrics: (botId: string) => Promise<void>;
  startPolling: (botId: string) => void;
  stopPolling: () => void;
}

export const useMetricsStore = create<MetricsState>((set, get) => ({
  systemMetrics: null,
  botMetrics: null,
  loading: false,
  error: null,
  intervalId: null,
  currentBotId: null,

  fetchSystemMetrics: async () => {
    try {
      const data = await systemApi.getSystemMetrics();
      set({ systemMetrics: data, error: null });
    } catch (err) {
      set({ error: String(err) });
    }
  },

  fetchBotMetrics: async (botId: string) => {
    set({ loading: true });
    try {
      const data = await systemApi.getBotMetrics(botId);
      set({ botMetrics: data, loading: false, error: null });
    } catch (err) {
      set({ loading: false, error: String(err) });
    }
  },

  startPolling: (botId: string) => {
    const { intervalId, fetchSystemMetrics, fetchBotMetrics } = get();
    if (intervalId) clearInterval(intervalId);

    set({ currentBotId: botId });
    fetchSystemMetrics();
    fetchBotMetrics(botId);

    const id = window.setInterval(() => {
      fetchSystemMetrics();
      fetchBotMetrics(botId);
    }, POLL_INTERVAL);

    set({ intervalId: id });
  },

  stopPolling: () => {
    const { intervalId } = get();
    if (intervalId) {
      clearInterval(intervalId);
      set({ intervalId: null });
    }
  },
}));

// Visibility change handler - stop polling when tab is hidden, resume when visible
if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    const store = useMetricsStore.getState();
    if (document.hidden) {
      store.stopPolling();
    } else if (store.intervalId === null && store.currentBotId) {
      store.startPolling(store.currentBotId);
    }
  });
}
