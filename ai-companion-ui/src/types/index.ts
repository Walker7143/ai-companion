// System types
export interface SystemMetrics {
  cpu_percent: number;
  memory_percent: number;
  memory_used_mb: number;
  disk_percent: number;
  uptime_seconds: number;
}

export interface MemoryStats {
  working_count: number;
  working_size_kb: number;
  episodic_count: number;
  episodic_size_kb: number;
  semantic_count: number;
  semantic_size_kb: number;
  embedding_enabled: boolean;
}

export interface BotMetrics {
  bot_id: string;
  status: string;
  uptime_seconds: number;
  conversations_today: number;
  proactive_messages_today: number;
  input_tokens_today: number;
  output_tokens_today: number;
  memory_stats: MemoryStats;
}

// Session types
export interface SessionInfo {
  session_key: string;
  session_id: string;
  bot_id?: string;
  platform: string;
  user: string;
  created_at: string;
  updated_at: string;
  status: string;
  reset_reason: string | null;
  total_tokens: number;
}

export interface SessionDetail {
  info: SessionInfo;
  input_tokens: number;
  output_tokens: number;
  cache_write_tokens: number;
  cache_read_tokens: number;
  estimated_cost_usd: number;
}

export interface Message {
  id: string;
  role: string;
  content: string;
  created_at: string;
}

export interface EpisodicItem {
  id: string;
  summary: string;
  content: string;
  importance: number;
  created_at: string;
  related_session: string;
}

export interface ContextDetail {
  system_prompt: string;
  working_history: Message[];
  episodic_recall: EpisodicItem[];
  semantic_facts: Record<string, string>;
  system_suffix: string;
  compression_history: CompressionRecord[];
  current_tokens: number;
  hard_limit: number;
  soft_limit: number;
}

export interface CompressionRecord {
  timestamp: string;
  original_chars: number;
  compressed_chars: number;
  savings_percent: number;
}

// Memory types
export interface SemanticMemory {
  facts: Fact[];
  attitude_score: number;
  relationship_level: string;
}

export interface Fact {
  key: string;
  value: string;
  updated_at: string;
}

// Log types
export interface LogParams {
  bot_id: string;
  level?: string;
  log_type?: string;
  date?: string;
  query?: string;
  page: number;
  page_size: number;
}

export interface LogEntry {
  id: string;
  timestamp: string;
  level: string;
  log_type: string;
  platform: string;
  message: string;
  details: string | null;
}

export interface LogPage {
  logs: LogEntry[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface LogStreamEvent {
  id: string;
  timestamp: string;
  level: string;
  log_type: string;
  platform: string;
  message: string;
}

// Config types
export interface BotConfig {
  bot_id: string;
  name: string;
  model: ModelConfig;
  memory: MemoryConfig;
  proactive: ProactiveConfig;
  platforms: PlatformConfig[];
  session_reset: SessionResetConfig;
}

export interface ModelConfig {
  provider: string;
  api_key: string;
  base_url: string;
  model: string;
  temperature: number;
  max_tokens: number;
}

export interface MemoryConfig {
  hard_limit_chars: number;
  soft_limit_chars: number;
  max_working_turns: number;
  embedding: string;
  embedding_model: string;
}

export interface ProactiveConfig {
  enabled: boolean;
  idle_threshold_hours: number;
  min_interval_hours: number;
  max_daily: number;
  emotion_keywords: string[];
}

export interface PlatformConfig {
  name: string;
  enabled: boolean;
  config: Record<string, string>;
}

export interface SessionResetConfig {
  mode: string;
  at_hour: number;
  idle_minutes: number;
  notify: boolean;
}

export interface BotInfo {
  id: string;
  name: string;
  status: string;
}

// Process types
export interface BotStatus {
  bot_id: string;
  running: boolean;
  pid: number | null;
  start_time: string | null;
  cpu_percent: number;
  memory_mb: number;
}

export interface ProcessInfo {
  pid: number;
  name: string;
  cpu_percent: number;
  memory_mb: number;
}