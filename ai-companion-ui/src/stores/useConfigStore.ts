import { create } from 'zustand';
import { configApi, botsApi } from '../api';
import type { BotConfig, BotInfo } from '../types';

interface ConfigState {
  config: BotConfig | null;
  availableBots: BotInfo[];
  loading: boolean;
  saving: boolean;
  error: string | null;
  fetchConfig: (botId: string) => Promise<void>;
  updateConfig: (botId: string, config: Partial<BotConfig>) => Promise<void>;
  fetchAvailableBots: () => Promise<void>;
  testApiConnection: (provider: string, apiKey: string, baseUrl: string) => Promise<boolean>;
}

export const useConfigStore = create<ConfigState>((set) => ({
  config: null,
  availableBots: [],
  loading: false,
  saving: false,
  error: null,

  fetchConfig: async (botId: string) => {
    set({ loading: true, error: null });
    try {
      const data = await configApi.getConfig(botId);
      set({ config: data, loading: false });
    } catch (err) {
      set({ loading: false, error: String(err) });
    }
  },

  updateConfig: async (botId: string, config: Partial<BotConfig>) => {
    set({ saving: true, error: null });
    try {
      await configApi.updateConfig(botId, config);
      set({ saving: false });
    } catch (err) {
      set({ saving: false, error: String(err) });
      throw err;
    }
  },

  fetchAvailableBots: async () => {
    try {
      const data = await botsApi.getBots();
      set({ availableBots: data, error: null });
    } catch (err) {
      set({ error: String(err) });
    }
  },

  testApiConnection: async (provider: string, apiKey: string, baseUrl: string) => {
    try {
      return await configApi.testConnection(provider, apiKey, baseUrl);
    } catch (err) {
      set({ error: String(err) });
      throw err;
    }
  },
}));
