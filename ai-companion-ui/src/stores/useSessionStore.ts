import { create } from 'zustand';
import { sessionApi } from '../api';
import type { SessionInfo, SessionDetail } from '../types';

interface SessionState {
  sessions: SessionInfo[];
  selectedSession: SessionDetail | null;
  loading: boolean;
  error: string | null;
  fetchSessions: (botId: string) => Promise<void>;
  fetchSessionDetail: (sessionKey: string) => Promise<void>;
  resetSession: (sessionKey: string) => Promise<void>;
  suspendSession: (sessionKey: string) => Promise<void>;
  clearSelectedSession: () => void;
}

export const useSessionStore = create<SessionState>((set, get) => ({
  sessions: [],
  selectedSession: null,
  loading: false,
  error: null,

  fetchSessions: async (botId: string) => {
    set({ loading: true, error: null });
    try {
      const data = await sessionApi.listSessions(botId);
      set({ sessions: data, loading: false });
    } catch (err) {
      set({ loading: false, error: String(err) });
    }
  },

  fetchSessionDetail: async (sessionKey: string) => {
    set({ loading: true, error: null });
    try {
      const data = await sessionApi.getSessionDetail(sessionKey);
      set({ selectedSession: data, loading: false });
    } catch (err) {
      set({ loading: false, error: String(err) });
    }
  },

  resetSession: async (sessionKey: string) => {
    try {
      await sessionApi.resetSession(sessionKey);
      // Refresh sessions list
      const { sessions } = get();
      set({
        sessions: sessions.map((s) =>
          s.session_key === sessionKey ? { ...s, status: 'reset' } : s
        ),
      });
    } catch (err) {
      set({ error: String(err) });
      throw err;
    }
  },

  suspendSession: async (sessionKey: string) => {
    try {
      await sessionApi.suspendSession(sessionKey);
      const { sessions } = get();
      set({
        sessions: sessions.map((s) =>
          s.session_key === sessionKey ? { ...s, status: 'suspended' } : s
        ),
      });
    } catch (err) {
      set({ error: String(err) });
      throw err;
    }
  },

  clearSelectedSession: () => {
    set({ selectedSession: null });
  },
}));
