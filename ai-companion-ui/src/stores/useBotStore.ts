import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface Bot {
  id: string;
  name: string;
  avatar?: string;
  description?: string;
  model?: string;
}

interface BotState {
  bots: Bot[];
  currentBotId: string | null;
  setBots: (bots: Bot[]) => void;
  setCurrentBot: (botId: string) => void;
  addBot: (bot: Bot) => void;
  removeBot: (botId: string) => void;
}

export const useBotStore = create<BotState>()(
  persist(
    (set) => ({
      bots: [
        { id: '1', name: '小月', description: '温柔体贴的AI女友' },
        { id: '2', name: '小星', description: '活泼开朗的AI伙伴' },
      ],
      currentBotId: '1',
      setBots: (bots) => set({ bots }),
      setCurrentBot: (botId) => set({ currentBotId: botId }),
      addBot: (bot) => set((state) => ({ bots: [...state.bots, bot] })),
      removeBot: (botId) =>
        set((state) => ({
          bots: state.bots.filter((b) => b.id !== botId),
          currentBotId: state.currentBotId === botId ? state.bots[0]?.id || null : state.currentBotId,
        })),
    }),
    {
      name: 'bot-storage',
    }
  )
);
