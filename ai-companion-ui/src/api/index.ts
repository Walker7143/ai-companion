import type {
  SystemMetrics,
  BotMetrics,
  SessionInfo,
  SessionDetail,
  MemoryStats,
  Message,
  EpisodicItem,
  SemanticMemory,
  DailyMemoryPayload,
  UnderstandingPayload,
  DebugContextPayload,
  VectorRebuildResult,
  LogPage,
  BotConfig,
  BotInfo,
} from '../types';

const API_BASE = 'http://localhost:8642/api/v1';

// Generic fetch wrapper with error handling
async function fetchApi<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

// System API
export const systemApi = {
  getSystemMetrics: (): Promise<SystemMetrics> =>
    fetchApi<SystemMetrics>('/admin/metrics/system'),

  getBotMetrics: (botId: string): Promise<BotMetrics> =>
    fetchApi<BotMetrics>(`/admin/metrics/bot/${botId}`),
};

// Bots API
export const botsApi = {
  getBots: (): Promise<BotInfo[]> =>
    fetchApi<{bots: BotInfo[]}>('/admin/bots').then(r => r.bots),
};

// Session API
export const sessionApi = {
  listSessions: (botId: string): Promise<SessionInfo[]> =>
    fetchApi<{sessions: SessionInfo[]}>(`/admin/sessions?bot_id=${encodeURIComponent(botId)}`).then(r => r.sessions),

  getSessionDetail: (sessionKey: string): Promise<SessionDetail> =>
    fetchApi<SessionDetail>(`/admin/sessions/${sessionKey}`),

  resetSession: (sessionKey: string): Promise<void> =>
    fetchApi<void>(`/admin/sessions/${sessionKey}/reset`, { method: 'POST' }),

  suspendSession: (sessionKey: string): Promise<void> =>
    fetchApi<void>(`/admin/sessions/${sessionKey}/suspend`, { method: 'POST' }),
};

// Memory API
export const memoryApi = {
  getStats: (botId: string): Promise<MemoryStats> =>
    fetchApi<MemoryStats>(`/admin/memory/${botId}/stats`),

  getWorking: (botId: string): Promise<Message[]> =>
    fetchApi<Message[]>(`/admin/memory/${botId}/working`),

  getDaily: (botId: string): Promise<DailyMemoryPayload> =>
    fetchApi<DailyMemoryPayload>(`/admin/memory/${botId}/daily`),

  getEpisodic: (botId: string, query?: string, limit?: number): Promise<EpisodicItem[]> => {
    const params = new URLSearchParams();
    if (query) params.set('query', query);
    if (limit) params.set('limit', limit.toString());
    const queryStr = params.toString();
    return fetchApi<EpisodicItem[]>(`/admin/memory/${botId}/episodic${queryStr ? `?${queryStr}` : ''}`);
  },

  getSemantic: (botId: string): Promise<SemanticMemory> =>
    fetchApi<SemanticMemory>(`/admin/memory/${botId}/semantic`),

  getUnderstanding: (botId: string): Promise<UnderstandingPayload> =>
    fetchApi<UnderstandingPayload>(`/admin/memory/${botId}/understanding`),

  updateUnderstanding: (botId: string, data: Record<string, unknown>): Promise<UnderstandingPayload & {ok: boolean}> =>
    fetchApi<UnderstandingPayload & {ok: boolean}>(`/admin/memory/${botId}/understanding`, {
      method: 'PUT',
      body: JSON.stringify({ data }),
    }),

  rebuildVector: (botId: string): Promise<VectorRebuildResult> =>
    fetchApi<VectorRebuildResult>(`/admin/memory/${botId}/rebuild-vector`, { method: 'POST' }),

  deleteMemory: (botId: string, type: string, id: string): Promise<void> =>
    fetchApi<void>(
      `/admin/memory/${encodeURIComponent(botId)}/${encodeURIComponent(type)}/${encodeURIComponent(id)}`,
      { method: 'DELETE' }
    ),

  clearAll: (botId: string): Promise<void> =>
    fetchApi<void>(`/admin/memory/${botId}/all`, { method: 'DELETE' }),
};

export const personaApi = {
  getConversationStyle: (botId: string): Promise<UnderstandingPayload> =>
    fetchApi<UnderstandingPayload>(`/admin/persona/${botId}/conversation-style`),

  updateConversationStyle: (botId: string, data: Record<string, unknown>): Promise<UnderstandingPayload & {ok: boolean}> =>
    fetchApi<UnderstandingPayload & {ok: boolean}>(`/admin/persona/${botId}/conversation-style`, {
      method: 'PUT',
      body: JSON.stringify({ data }),
    }),
};

export const debugApi = {
  getLastContext: (botId: string): Promise<DebugContextPayload> =>
    fetchApi<DebugContextPayload>(`/admin/debug/${botId}/last-context`),
};

// Logs API
export const logsApi = {
  getLogs: (params: {
    botId: string;
    level?: string;
    type?: string;
    date?: string;
    query?: string;
    page?: number;
    pageSize?: number;
  }): Promise<LogPage> => {
    const searchParams = new URLSearchParams({
      bot_id: params.botId,
      page: (params.page || 1).toString(),
      page_size: (params.pageSize || 20).toString(),
    });
    if (params.level && params.level !== 'all') searchParams.set('level', params.level);
    if (params.type && params.type !== 'all') searchParams.set('type', params.type);
    if (params.date) searchParams.set('date', params.date);
    if (params.query) searchParams.set('query', params.query);

    return fetchApi<LogPage>(`/admin/logs?${searchParams.toString()}`);
  },

  streamLogs: (botId: string, level?: string): { wsUrl: string } => {
    const wsUrl = `ws://localhost:8642/api/v1/admin/logs/stream?bot_id=${botId}${level ? `&level=${level}` : ''}`;
    return { wsUrl };
  },

  exportLogs: (_botId: string, _format: string): Promise<string> =>
    Promise.reject(new Error('日志导出暂未实现')),
};

// Config API
export const configApi = {
  getConfig: (botId: string): Promise<BotConfig> =>
    fetchApi<BotConfig>(`/admin/config/${botId}`),

  updateConfig: (botId: string, config: Partial<BotConfig> & Record<string, unknown>): Promise<{ok: boolean; warnings?: string[]; changed_files?: string[]; config?: BotConfig}> =>
    fetchApi<{ok: boolean; warnings?: string[]; changed_files?: string[]; config?: BotConfig}>(`/admin/config/${botId}`, {
      method: 'PUT',
      body: JSON.stringify(config),
    }),

  testConnection: (provider: string, apiKey: string, baseUrl: string, model = '', botId = '_default'): Promise<boolean> =>
    fetchApi<{ok: boolean; error?: string}>(`/admin/config/${encodeURIComponent(botId)}/test`, {
      method: 'POST',
      body: JSON.stringify({
        model: {
          provider,
          api_key: apiKey,
          base_url: baseUrl,
          model,
        },
      }),
    }).then(r => r.ok),
};

// Re-export types
export type * from '../types';
