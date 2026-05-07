// System types
export interface SystemMetrics {
  cpu_percent: number;
  memory_percent: number;
  memory_used_mb: number;
  disk_percent: number;
  disk_used_mb?: number;
  uptime_seconds: number;
}

export interface MemoryStats {
  working_count: number;
  working_size_kb: number;
  daily_count?: number;
  daily_summary_count?: number;
  daily_size_kb?: number;
  episodic_count: number;
  episodic_size_kb: number;
  semantic_count: number;
  semantic_size_kb: number;
  user_understanding_path?: string | null;
  user_understanding_auto_facts?: number;
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

export interface DailyMessage {
  id: string;
  bot_id?: string;
  user_id?: string;
  local_date: string;
  created_at: string;
  platform?: string | null;
  session_id?: string | null;
  channel_type?: string | null;
  role: string;
  content: string;
  summarized?: number;
}

export interface DailySummary {
  id: string;
  bot_id?: string;
  user_id?: string;
  local_date: string;
  summary: string;
  topics_json?: string | null;
  open_threads_json?: string | null;
  mood_json?: string | null;
  commitments_json?: string | null;
  message_count?: number;
  updated_at: string;
}

export interface DailyMemoryPayload {
  messages: DailyMessage[];
  summaries: DailySummary[];
}

export interface EpisodicItem {
  id: string;
  summary: string;
  content: string;
  importance: number;
  confidence?: number;
  created_at: string;
  session_id?: string;
  related_session?: string;
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
  user_understanding?: Record<string, unknown>;
  user_understanding_path?: string | null;
}

export interface UnderstandingPayload {
  data: Record<string, unknown>;
  path?: string | null;
}

export interface DebugContextPayload {
  bot_id: string;
  last_context: {
    system_prompt: string;
    memory_suffix: Record<string, unknown>;
    working_history: Message[];
    retrieved_memory: Record<string, unknown>;
    response_style_trace: Record<string, unknown>;
  };
}

export interface Fact {
  key: string;
  value: string;
  updated_at: string;
  category?: string;
  confidence?: number;
  source?: string;
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
  schema?: WebConfigSchema;
  model: ModelConfig;
  memory: MemoryConfig;
  proactive: ProactiveConfig;
  life: LifeConfig;
  platforms: PlatformConfig[];
  session_reset: SessionResetConfig;
  persona_summary: PersonaSummaryConfig;
  diagnostics?: ConfigDiagnostics;
}

export interface WebConfigSchema {
  sections: Array<{
    id: string;
    title: string;
    scope: string;
    description: string;
    restart: string;
    fields: Record<string, string>;
  }>;
  sensitive_fields: string[];
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
  max_summaries: number;
  semantic_char_limit: number;
  embedding: string;
  embedding_model: string;
  daily: DailyMemoryConfig;
}

export interface DailyMemoryConfig {
  enabled: boolean;
  retention_days: number;
  recent_message_limit: number;
  summary_days: number;
  max_prompt_chars: number;
  summarize_after_messages: number;
  summarize_after_chars: number;
}

export interface ProactiveConfig {
  enabled: boolean;
  mode: string;
  check_interval_seconds: number;
  idle_threshold_hours: number;
  min_interval_hours: number;
  max_daily: number;
  max_idle_days: number;
  idle_reminder_enabled: boolean;
  idle_reminder_hours: number;
  emotion_trigger_enabled: boolean;
  emotion_keywords: string[];
  emotion_response_delay_minutes: number;
  preferred_contact_times: string[];
  timezone: string;
  random_trigger_prob: number;
  random_trigger_min_ratio: number;
  platform_type: string;
  webhook_url: string;
  home_channel: string;
}

export interface LifeConfig {
  preset: string;
  presets: Array<{
    id: string;
    label: string;
    time_ratio: number;
    description: string;
  }>;
  daily_interval_seconds: number;
  major_interval_seconds: number;
  time_ratio: number;
  time_ratio_warning_threshold: number;
  daily_event_min_gap_days: number;
  major_event_fixed_probability: number;
  max_events: number;
  max_context_bits: number;
  birth_date: string;
  season: {
    hemisphere: string;
    birthday_month: number;
  };
  event_policy: {
    scenario_cooldown_days: number;
    major_scenario_cooldown_days: number;
    unexpected_event_probability: number;
    unexpected_event_cooldown_days: number;
    llm_daily_candidate_limit: number;
  };
  milestones: Array<Record<string, unknown>>;
  holidays: Array<Record<string, unknown>>;
}

export interface PlatformConfig {
  name: string;
  enabled: boolean;
  config: Record<string, unknown>;
}

export interface SessionResetConfig {
  mode: string;
  at_hour: number;
  idle_minutes: number;
  notify: boolean;
}

export interface PersonaSummaryConfig {
  profile: {
    name: string;
    age: number | string;
    birth_date: string;
    occupation: string;
    gender: string;
    personality_tags: string[];
    relationship_to_user: string;
    interests: string[];
    appearance: string;
    summary: string;
  };
  backstory: {
    summary: string;
    key_moments: string[];
    meeting_user: string;
    now: string;
  };
  values: {
    non_negotiable: string[];
    soft_boundaries: Array<Record<string, unknown>>;
  };
  speaking_style: {
    tone: string;
    catchphrases: string[];
    greeting_style: string;
    farewell_style: string;
  };
}

export interface ConfigDiagnostics {
  requires_restart: string[];
  life_status: Record<string, unknown>;
  gateway_status?: Record<string, unknown>;
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
