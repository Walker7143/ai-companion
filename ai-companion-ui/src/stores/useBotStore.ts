import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { botsApi } from '../api';
import type { BotInfo } from '../types';

interface BotState {
  bots: BotInfo[];
  currentBotId: string | null;
  setBots: (bots: BotInfo[]) => void;
  setCurrentBot: (botId: string) => void;
  fetchBots: () => Promise<void>;
}

export const useBotStore = create<BotState>()(
  persist(
    (set, get) => ({
      bots: [],
      currentBotId: null,

      setBots: (bots) => set({ bots }),

      setCurrentBot: (botId) => set({ currentBotId: botId }),

      fetchBots: async () => {
        try {
          const bots = await botsApi.getBots();
          set({ bots });
          // Auto-select first bot if none selected
          if (bots.length > 0 && !get().currentBotId) {
            set({ currentBotId: bots[0].id });
          }
        } catch (error) {
          console.error('Failed to fetch bots:', error);
        }
      },
    }),
    {
      name: 'bot-storage',
      partialize: (state) => ({ currentBotId: state.currentBotId }),
    }
  )
);
