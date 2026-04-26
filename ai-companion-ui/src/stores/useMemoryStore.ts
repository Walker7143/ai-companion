import { create } from 'zustand';
import { memoryApi } from '../api/tauri';
import type { MemoryStats, Message, EpisodicItem, SemanticMemory } from '../types';

interface MemoryState {
  stats: MemoryStats | null;
  workingMemory: Message[];
  episodicMemory: EpisodicItem[];
  semanticMemory: SemanticMemory | null;
  loading: boolean;
  error: string | null;
  fetchStats: (botId: string) => Promise<void>;
  fetchWorkingMemory: (botId: string) => Promise<void>;
  fetchEpisodicMemory: (botId: string, query?: string) => Promise<void>;
  fetchSemanticMemory: (botId: string) => Promise<void>;
  deleteMemory: (botId: string, memoryType: string, memoryId: string) => Promise<void>;
  clearAllMemory: (botId: string) => Promise<void>;
}

export const useMemoryStore = create<MemoryState>((set) => ({
  stats: null,
  workingMemory: [],
  episodicMemory: [],
  semanticMemory: null,
  loading: false,
  error: null,

  fetchStats: async (botId: string) => {
    try {
      const data = await memoryApi.getMemoryStats(botId);
      set({ stats: data, error: null });
    } catch (err) {
      set({ error: String(err) });
    }
  },

  fetchWorkingMemory: async (botId: string) => {
    set({ loading: true, error: null });
    try {
      const data = await memoryApi.getWorkingMemory(botId);
      set({ workingMemory: data, loading: false });
    } catch (err) {
      set({ loading: false, error: String(err) });
    }
  },

  fetchEpisodicMemory: async (botId: string, query?: string) => {
    set({ loading: true, error: null });
    try {
      const data = await memoryApi.getEpisodicMemory(botId, query);
      set({ episodicMemory: data, loading: false });
    } catch (err) {
      set({ loading: false, error: String(err) });
    }
  },

  fetchSemanticMemory: async (botId: string) => {
    set({ loading: true, error: null });
    try {
      const data = await memoryApi.getSemanticMemory(botId);
      set({ semanticMemory: data, loading: false });
    } catch (err) {
      set({ loading: false, error: String(err) });
    }
  },

  deleteMemory: async (botId: string, memoryType: string, memoryId: string) => {
    try {
      await memoryApi.deleteMemory(botId, memoryType, memoryId);
      // Refresh the appropriate memory list
      if (memoryType === 'working') {
        get().fetchWorkingMemory(botId);
      } else if (memoryType === 'episodic') {
        get().fetchEpisodicMemory(botId);
      } else if (memoryType === 'semantic') {
        get().fetchSemanticMemory(botId);
      }
      // Also refresh stats
      get().fetchStats(botId);
    } catch (err) {
      set({ error: String(err) });
      throw err;
    }
  },

  clearAllMemory: async (botId: string) => {
    try {
      await memoryApi.clearAllMemory(botId);
      set({
        stats: null,
        workingMemory: [],
        episodicMemory: [],
        semanticMemory: null,
      });
    } catch (err) {
      set({ error: String(err) });
      throw err;
    }
  },
}));

// Helper to get store actions outside of React
function get() {
  return useMemoryStore.getState();
}
