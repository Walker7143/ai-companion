import { create } from 'zustand';
import { evolutionApi } from '../api';
import type {
  EvolutionEventDetail,
  EvolutionSummary,
  EvolutionTimelineItem,
} from '../types';

type TimelineStatusFilter = 'all' | 'promoted' | 'suppressed' | 'runtime';
type TimelineDimensionFilter = 'all' | 'backstory' | 'personality' | 'speaking_style' | 'values' | 'relationship';

interface EvolutionStateView {
  state: Record<string, unknown>;
  human_readable_diagnostics: string[];
}

interface EvolutionStoreState {
  summary: EvolutionSummary | null;
  timeline: EvolutionTimelineItem[];
  selectedEvent: EvolutionEventDetail | null;
  stateView: EvolutionStateView | null;
  loading: boolean;
  refreshing: boolean;
  loadingDetail: boolean;
  loadingState: boolean;
  acting: boolean;
  error: string | null;
  timelineError: string | null;
  detailError: string | null;
  nextCursor: string | null;
  hasMore: boolean;
  filters: {
    dimension: TimelineDimensionFilter;
    status: TimelineStatusFilter;
  };
  setFilters: (filters: Partial<EvolutionStoreState['filters']>) => void;
  fetchOverview: (botId: string) => Promise<void>;
  fetchTimeline: (botId: string, options?: { append?: boolean }) => Promise<void>;
  fetchEventDetail: (botId: string, eventId: string) => Promise<void>;
  fetchStateView: (botId: string) => Promise<void>;
  reflect: (botId: string) => Promise<void>;
  rebuild: (botId: string) => Promise<void>;
  applyPromotion: (botId: string, candidateId: string) => Promise<void>;
  rejectPromotion: (botId: string, candidateId: string, reason: string) => Promise<void>;
  clearSelection: () => void;
}

export const useEvolutionStore = create<EvolutionStoreState>((set, get) => ({
  summary: null,
  timeline: [],
  selectedEvent: null,
  stateView: null,
  loading: false,
  refreshing: false,
  loadingDetail: false,
  loadingState: false,
  acting: false,
  error: null,
  timelineError: null,
  detailError: null,
  nextCursor: null,
  hasMore: false,
  filters: {
    dimension: 'all',
    status: 'all',
  },

  setFilters: (filters) =>
    set((state) => ({
      filters: {
        ...state.filters,
        ...filters,
      },
    })),

  fetchOverview: async (botId) => {
    if (!botId) return;
    const hasSummary = Boolean(get().summary);
    set({
      loading: !hasSummary,
      refreshing: hasSummary,
      error: null,
    });
    try {
      const summary = await evolutionApi.getSummary(botId);
      set({
        summary,
        loading: false,
        refreshing: false,
      });
    } catch (err) {
      set({
        loading: false,
        refreshing: false,
        error: String(err),
      });
      throw err;
    }
  },

  fetchTimeline: async (botId, options) => {
    if (!botId) return;
    const append = options?.append === true;
    const { filters, nextCursor } = get();
    set({
      loading: !append && get().timeline.length === 0,
      refreshing: !append && get().timeline.length > 0,
      timelineError: null,
    });
    try {
      const response = await evolutionApi.getTimeline(botId, {
        cursor: append ? (nextCursor || undefined) : undefined,
        limit: 50,
        dimension: filters.dimension,
        status: filters.status,
      });
      set((state) => ({
        timeline: append ? [...state.timeline, ...response.items] : response.items,
        nextCursor: response.next_cursor || null,
        hasMore: response.has_more,
        loading: false,
        refreshing: false,
      }));
    } catch (err) {
      set({
        loading: false,
        refreshing: false,
        timelineError: String(err),
      });
      throw err;
    }
  },

  fetchEventDetail: async (botId, eventId) => {
    if (!botId || !eventId) return;
    set({
      loadingDetail: true,
      detailError: null,
    });
    try {
      const selectedEvent = await evolutionApi.getEventDetail(botId, eventId);
      set({
        selectedEvent,
        loadingDetail: false,
      });
    } catch (err) {
      set({
        loadingDetail: false,
        detailError: String(err),
      });
      throw err;
    }
  },

  fetchStateView: async (botId) => {
    if (!botId) return;
    set({
      loadingState: true,
      error: null,
    });
    try {
      const stateView = await evolutionApi.getState(botId);
      set({
        stateView,
        loadingState: false,
      });
    } catch (err) {
      set({
        loadingState: false,
        error: String(err),
      });
      throw err;
    }
  },

  reflect: async (botId) => {
    set({ acting: true });
    try {
      await evolutionApi.reflect(botId);
      await Promise.all([
        get().fetchOverview(botId),
        get().fetchTimeline(botId),
        get().fetchStateView(botId),
      ]);
    } finally {
      set({ acting: false });
    }
  },

  rebuild: async (botId) => {
    set({ acting: true });
    try {
      await evolutionApi.rebuild(botId);
      await Promise.all([
        get().fetchOverview(botId),
        get().fetchTimeline(botId),
        get().fetchStateView(botId),
      ]);
    } finally {
      set({ acting: false });
    }
  },

  applyPromotion: async (botId, candidateId) => {
    set({ acting: true });
    try {
      await evolutionApi.applyPromotion(botId, candidateId);
      await Promise.all([
        get().fetchOverview(botId),
        get().fetchTimeline(botId),
        get().fetchStateView(botId),
      ]);
      if (get().selectedEvent?.candidate_patch) {
        set({ selectedEvent: null });
      }
    } finally {
      set({ acting: false });
    }
  },

  rejectPromotion: async (botId, candidateId, reason) => {
    set({ acting: true });
    try {
      await evolutionApi.rejectPromotion(botId, candidateId, reason);
      await Promise.all([
        get().fetchOverview(botId),
        get().fetchTimeline(botId),
        get().fetchStateView(botId),
      ]);
      if (get().selectedEvent?.candidate_patch) {
        set({ selectedEvent: null });
      }
    } finally {
      set({ acting: false });
    }
  },

  clearSelection: () =>
    set({
      selectedEvent: null,
      detailError: null,
    }),
}));
