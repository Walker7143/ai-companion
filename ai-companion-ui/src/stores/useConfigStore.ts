import { create } from 'zustand';
import { configApi } from '../api/tauri';
import type { BotConfig, BotInfo } from '../types';

interface ConfigState {
  config: BotConfig | null;
  availableBots: BotInfo[];
  loading: boolean;
  saving: boolean;
  error: string | null;
  fetchConfig: (botId: string) => Promise<void>;
  updateConfig: (botId: string, config: BotConfig) => Promise<void>;
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

  updateConfig: async (botId: string, config: BotConfig) => {
    set({ saving: true, error: null });
    try {
      await configApi.updateConfig(botId, config);
      set({ config, saving: false });
    } catch (err) {
      set({ saving: false, error: String(err) });
      throw err;
    }
  },

  fetchAvailableBots: async () => {
    try {
      const data = await configApi.getAvailableBots();
      set({ availableBots: data, error: null });
    } catch (err) {
      set({ error: String(err) });
    }
  },

  testApiConnection: async (provider: string, apiKey: string, baseUrl: string) => {
    try {
      return await configApi.testApiConnection(provider, apiKey, baseUrl);
    } catch (err) {
      set({ error: String(err) });
      throw err;
    }
  },
}));
