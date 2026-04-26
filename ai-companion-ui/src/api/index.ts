import type {
  SystemMetrics,
  BotMetrics,
  SessionInfo,
  SessionDetail,
  MemoryStats,
  Message,
  EpisodicItem,
  SemanticMemory,
  LogPage,
  BotConfig,
  BotInfo,
} from '../types';

const API_BASE = '/api/v1';

// Mock data for development
const mockBots: BotInfo[] = [
  { id: 'suqing', name: '苏晴', status: 'running' },
  { id: 'xiaoyue', name: '小月', status: 'running' },
];

const mockSystemMetrics: SystemMetrics = {
  cpu_percent: 35.5,
  memory_percent: 62.3,
  memory_used_mb: 8192,
  disk_percent: 45.2,
  uptime_seconds: 864000,
};

const mockBotMetrics: BotMetrics = {
  bot_id: 'suqing',
  status: 'running',
  uptime_seconds: 864000,
  conversations_today: 42,
  proactive_messages_today: 8,
  input_tokens_today: 125000,
  output_tokens_today: 98000,
  memory_stats: {
    working_count: 28,
    working_size_kb: 512,
    episodic_count: 156,
    episodic_size_kb: 2048,
    semantic_count: 89,
    semantic_size_kb: 128,
    embedding_enabled: false,
  },
};

// Generic fetch wrapper with error handling
async function fetchApi<T>(url: string, options?: RequestInit): Promise<T> {
  try {
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
  } catch (error) {
    console.warn('API call failed, using mock data:', error);
    throw error;
  }
}

// System API
export const systemApi = {
  getSystemMetrics: (): Promise<SystemMetrics> =>
    fetchApi<SystemMetrics>('/metrics/system').catch(() => mockSystemMetrics),

  getBotMetrics: (botId: string): Promise<BotMetrics> =>
    fetchApi<BotMetrics>(`/metrics/bot/${botId}`).catch(() => ({
      ...mockBotMetrics,
      bot_id: botId,
    })),
};

// Bots API
export const botsApi = {
  getBots: (): Promise<BotInfo[]> =>
    fetchApi<BotInfo[]>('/bots').catch(() => mockBots),
};

// Session API
export const sessionApi = {
  listSessions: (botId: string): Promise<SessionInfo[]> =>
    fetchApi<SessionInfo[]>(`/sessions?bot_id=${botId}`).catch(() => []),

  getSessionDetail: (sessionKey: string): Promise<SessionDetail> =>
    fetchApi<SessionDetail>(`/sessions/${sessionKey}`).catch(() => ({
      info: {
        session_key: sessionKey,
        session_id: 'session_001',
        platform: 'cli',
        user: 'User',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        status: 'active',
        reset_reason: null,
        total_tokens: 0,
      },
      input_tokens: 0,
      output_tokens: 0,
      cache_write_tokens: 0,
      cache_read_tokens: 0,
      estimated_cost_usd: 0,
    })),

  resetSession: (sessionKey: string): Promise<void> =>
    fetchApi<void>(`/sessions/${sessionKey}/reset`, { method: 'POST' }).catch(() => {}),

  suspendSession: (sessionKey: string): Promise<void> =>
    fetchApi<void>(`/sessions/${sessionKey}/suspend`, { method: 'POST' }).catch(() => {}),
};

// Memory API
export const memoryApi = {
  getStats: (botId: string): Promise<MemoryStats> =>
    fetchApi<MemoryStats>(`/memory/${botId}/stats`).catch(() => mockBotMetrics.memory_stats),

  getWorking: (botId: string): Promise<Message[]> =>
    fetchApi<Message[]>(`/memory/${botId}/working`).catch(() => []),

  getEpisodic: (botId: string, query?: string, limit?: number): Promise<EpisodicItem[]> => {
    const params = new URLSearchParams();
    if (query) params.set('query', query);
    if (limit) params.set('limit', limit.toString());
    const queryStr = params.toString();
    return fetchApi<EpisodicItem[]>(`/memory/${botId}/episodic${queryStr ? `?${queryStr}` : ''}`).catch(() => []);
  },

  getSemantic: (botId: string): Promise<SemanticMemory> =>
    fetchApi<SemanticMemory>(`/memory/${botId}/semantic`).catch(() => ({
      facts: [],
      attitude_score: 0,
      relationship_level: '陌生',
    })),

  deleteMemory: (botId: string, type: string, id: string): Promise<void> =>
    fetchApi<void>(`/memory/${botId}/${type}/${id}`, { method: 'DELETE' }).catch(() => {}),

  clearAll: (botId: string): Promise<void> =>
    fetchApi<void>(`/memory/${botId}/clear`, { method: 'POST' }).catch(() => {}),
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

    return fetchApi<LogPage>(`/logs?${searchParams.toString()}`).catch(() => ({
      logs: [],
      total: 0,
      page: 1,
      page_size: 20,
      total_pages: 0,
    }));
  },

  streamLogs: (botId: string, level?: string): { wsUrl: string } => {
    const wsUrl = `ws://localhost:18888/api/v1/logs/stream?bot_id=${botId}${level ? `&level=${level}` : ''}`;
    return { wsUrl };
  },

  exportLogs: (botId: string, format: string): Promise<string> =>
    fetchApi<string>(`/logs/export?bot_id=${botId}&format=${format}`, { method: 'POST' }).catch(() => ''),
};

// Config API
export const configApi = {
  getConfig: (botId: string): Promise<BotConfig> =>
    fetchApi<BotConfig>(`/config/${botId}`).catch(() => ({
      bot_id: botId,
      name: 'Bot',
      model: {
        provider: 'openai',
        api_key: '',
        base_url: 'https://api.openai.com',
        model: 'gpt-4',
        temperature: 0.7,
        max_tokens: 2000,
      },
      memory: {
        hard_limit_chars: 100000,
        soft_limit_chars: 80000,
        max_working_turns: 20,
        embedding: 'none',
        embedding_model: '',
      },
      proactive: {
        enabled: true,
        idle_threshold_hours: 2,
        min_interval_hours: 0.5,
        max_daily: 10,
        emotion_keywords: [],
      },
      platforms: [],
      session_reset: {
        mode: 'daily',
        at_hour: 0,
        idle_minutes: 30,
        notify: true,
      },
    })),

  updateConfig: (botId: string, config: Partial<BotConfig>): Promise<void> =>
    fetchApi<void>(`/config/${botId}`, {
      method: 'PUT',
      body: JSON.stringify(config),
    }).catch(() => {}),

  testConnection: (provider: string, apiKey: string, baseUrl: string): Promise<boolean> =>
    fetchApi<boolean>('/config/test', {
      method: 'POST',
      body: JSON.stringify({ provider, api_key: apiKey, base_url: baseUrl }),
    }).catch(() => false),
};

// Re-export types
export type * from '../types';
