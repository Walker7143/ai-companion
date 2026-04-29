import { useCallback, useEffect, useMemo, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { BookOpen, Bot, Brain, Clock, Globe, HeartPulse, Moon, RotateCcw, Save, ShieldAlert, Sparkles, Sun, TestTube, Zap } from 'lucide-react';
import { Button, Card, CardContent, CardHeader, CardTitle, Input, Select, Toggle, useToast } from '../../components/ui';
import { useBotStore, useThemeStore } from '../../stores';
import { configApi } from '../../api';
import type { BotConfig, LifeConfig, PlatformConfig, ProactiveConfig } from '../../types';

type SectionId = 'model' | 'memory' | 'proactive' | 'life' | 'platforms' | 'persona' | 'session_reset';

const sectionIcon: Record<string, ReactNode> = {
  model: <Sparkles style={{ width: 18, height: 18, color: 'var(--accent)' }} />,
  memory: <Brain style={{ width: 18, height: 18, color: 'var(--accent)' }} />,
  proactive: <Zap style={{ width: 18, height: 18, color: 'var(--warning)' }} />,
  life: <Clock style={{ width: 18, height: 18, color: 'var(--success)' }} />,
  platforms: <Globe style={{ width: 18, height: 18, color: 'var(--accent)' }} />,
  persona: <Bot style={{ width: 18, height: 18, color: 'var(--accent)' }} />,
  session_reset: <HeartPulse style={{ width: 18, height: 18, color: 'var(--warning)' }} />,
};

const gridStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
  gap: 16,
};

const providerOptions = [
  { value: 'minimax', label: 'MiniMax' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'claude', label: 'Claude' },
  { value: 'ollama', label: 'Ollama' },
  { value: 'custom', label: '自定义' },
];

function FieldHint({ text }: { text?: string }) {
  if (!text) return null;
  return <div style={{ marginTop: 4, fontSize: 12, lineHeight: 1.5, color: 'var(--text-muted)' }}>{text}</div>;
}

function SectionCard({
  id,
  title,
  description,
  restart,
  children,
}: {
  id: string;
  title: string;
  description?: string;
  restart?: string;
  children: ReactNode;
}) {
  return (
    <Card id={id}>
      <CardHeader style={{ padding: '16px 20px', marginBottom: 0 }}>
        <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {sectionIcon[id] ?? <BookOpen style={{ width: 18, height: 18 }} />}
          {title}
        </CardTitle>
        {(description || restart) && (
          <div style={{ marginTop: 8, display: 'grid', gap: 6, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            {description && <div>{description}</div>}
            {restart && <div style={{ color: 'var(--text-muted)' }}>生效方式：{restart}</div>}
          </div>
        )}
      </CardHeader>
      <CardContent style={{ padding: '20px' }}>{children}</CardContent>
    </Card>
  );
}

function TextareaField({
  label,
  value,
  onChange,
  hint,
  rows = 4,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  rows?: number;
}) {
  return (
    <div>
      <label style={{ display: 'block', fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 6 }}>
        {label}
      </label>
      <textarea
        value={value}
        rows={rows}
        onChange={(event) => onChange(event.target.value)}
        style={{
          width: '100%',
          resize: 'vertical',
          padding: '8px 12px',
          borderRadius: 6,
          border: '1px solid var(--border-subtle)',
          backgroundColor: 'var(--bg-secondary)',
          color: 'var(--text-primary)',
          fontSize: 14,
          outline: 'none',
        }}
      />
      <FieldHint text={hint} />
    </div>
  );
}

const splitList = (value: string) => value.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean);
const joinList = (value?: unknown[]) => (value || []).map(String).join(', ');

function platformByName(config: BotConfig, name: string): PlatformConfig {
  return config.platforms.find((p) => p.name === name) || { name, enabled: false, config: {} };
}

function configObject(platform: PlatformConfig): Record<string, unknown> {
  return (platform.config || {}) as Record<string, unknown>;
}

function nestedConfig(platform: PlatformConfig, key: string): Record<string, unknown> {
  const cfg = configObject(platform);
  return (cfg[key] && typeof cfg[key] === 'object' ? cfg[key] : {}) as Record<string, unknown>;
}

const defaultModel: BotConfig['model'] = {
  provider: 'minimax',
  api_key: '',
  base_url: '',
  model: '',
  temperature: 0.7,
  max_tokens: 2000,
};

const defaultMemory: BotConfig['memory'] = {
  hard_limit_chars: 100000,
  soft_limit_chars: 80000,
  max_working_turns: 20,
  max_summaries: 5,
  semantic_char_limit: 4400,
  embedding: 'none',
  embedding_model: 'all-MiniLM-L6-v2',
};

const defaultProactive: ProactiveConfig = {
  enabled: false,
  mode: 'active',
  check_interval_seconds: 600,
  idle_threshold_hours: 24,
  min_interval_hours: 4,
  max_daily: 5,
  max_idle_days: 7,
  idle_reminder_enabled: true,
  idle_reminder_hours: 24,
  emotion_trigger_enabled: true,
  emotion_keywords: [],
  emotion_response_delay_minutes: 5,
  preferred_contact_times: ['09:00-23:00'],
  timezone: 'Asia/Shanghai',
  random_trigger_prob: 0.05,
  random_trigger_min_ratio: 0.5,
  platform_type: 'cli',
  webhook_url: '',
  home_channel: '',
};

const defaultLife: LifeConfig = {
  preset: 'realtime',
  presets: [
    { id: 'realtime', label: '现实同步 1:1', time_ratio: 1, description: '现实 1 天 = Bot 1 天' },
    { id: 'hourly', label: '轻度加速 24x', time_ratio: 24, description: '现实 1 小时 = Bot 1 天' },
    { id: 'minute', label: '观察测试 1440x', time_ratio: 1440, description: '现实 1 分钟 = Bot 1 天' },
  ],
  daily_interval_seconds: 86400,
  major_interval_seconds: 604800,
  time_ratio: 1,
  time_ratio_warning_threshold: 500,
  daily_event_min_gap_days: 2,
  major_event_fixed_probability: 0.05,
  max_events: 100,
  max_context_bits: 2000,
  birth_date: '',
  season: { hemisphere: 'north', birthday_month: 1 },
  event_policy: {
    scenario_cooldown_days: 14,
    major_scenario_cooldown_days: 180,
    unexpected_event_probability: 0.01,
    unexpected_event_cooldown_days: 365,
    llm_daily_candidate_limit: 12,
  },
  milestones: [],
  holidays: [],
};

const defaultPersona: BotConfig['persona_summary'] = {
  profile: {
    name: '',
    age: '',
    birth_date: '',
    occupation: '',
    gender: '',
    personality_tags: [],
    relationship_to_user: '',
    interests: [],
    appearance: '',
    summary: '',
  },
  backstory: {
    summary: '',
    key_moments: [],
    meeting_user: '',
    now: '',
  },
  values: {
    non_negotiable: [],
    soft_boundaries: [],
  },
  speaking_style: {
    tone: '',
    catchphrases: [],
    greeting_style: '',
    farewell_style: '',
  },
};

function normalizeConfig(data: BotConfig): BotConfig {
  const raw = data as Partial<BotConfig>;
  const life = { ...defaultLife, ...(raw.life || {}) };
  life.presets = Array.isArray(life.presets) && life.presets.length ? life.presets : defaultLife.presets;
  life.milestones = Array.isArray(life.milestones) ? life.milestones : [];
  life.holidays = Array.isArray(life.holidays) ? life.holidays : [];
  life.season = { ...defaultLife.season, ...(life.season || {}) };
  life.event_policy = { ...defaultLife.event_policy, ...(life.event_policy || {}) };

  const persona = raw.persona_summary || defaultPersona;
  return {
    bot_id: raw.bot_id || '',
    name: raw.name || raw.bot_id || '未命名 Bot',
    schema: raw.schema || { sections: [], sensitive_fields: [] },
    model: { ...defaultModel, ...(raw.model || {}) },
    memory: { ...defaultMemory, ...(raw.memory || {}) },
    proactive: {
      ...defaultProactive,
      ...(raw.proactive || {}),
      emotion_keywords: Array.isArray(raw.proactive?.emotion_keywords) ? raw.proactive.emotion_keywords : [],
      preferred_contact_times: Array.isArray(raw.proactive?.preferred_contact_times) ? raw.proactive.preferred_contact_times : defaultProactive.preferred_contact_times,
    },
    life,
    platforms: Array.isArray(raw.platforms) ? raw.platforms : [],
    session_reset: { mode: 'daily', at_hour: 0, idle_minutes: 30, notify: true, ...(raw.session_reset || {}) },
    persona_summary: {
      profile: { ...defaultPersona.profile, ...(persona.profile || {}) },
      backstory: {
        ...defaultPersona.backstory,
        ...(persona.backstory || {}),
        key_moments: Array.isArray(persona.backstory?.key_moments) ? persona.backstory.key_moments : [],
      },
      values: {
        ...defaultPersona.values,
        ...(persona.values || {}),
        non_negotiable: Array.isArray(persona.values?.non_negotiable) ? persona.values.non_negotiable : [],
        soft_boundaries: Array.isArray(persona.values?.soft_boundaries) ? persona.values.soft_boundaries : [],
      },
      speaking_style: {
        ...defaultPersona.speaking_style,
        ...(persona.speaking_style || {}),
        catchphrases: Array.isArray(persona.speaking_style?.catchphrases) ? persona.speaking_style.catchphrases : [],
      },
    },
    diagnostics: raw.diagnostics,
  };
}

export function Settings() {
  const { theme, toggleTheme } = useThemeStore();
  const { currentBotId } = useBotStore();
  const toast = useToast();

  const [savedConfig, setSavedConfig] = useState<BotConfig | null>(null);
  const [draft, setDraft] = useState<BotConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  const fetchConfig = useCallback(async () => {
    if (!currentBotId) {
      setSavedConfig(null);
      setDraft(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const data = normalizeConfig(await configApi.getConfig(currentBotId));
      setSavedConfig(data);
      setDraft(data);
    } catch (err) {
      toast.error(`获取配置失败: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [currentBotId, toast]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const sectionMeta = useMemo(() => {
    const result: Record<string, { title: string; description: string; restart: string; fields: Record<string, string> }> = {};
    draft?.schema?.sections?.forEach((section) => {
      result[section.id] = {
        title: section.title,
        description: section.description,
        restart: section.restart,
        fields: section.fields,
      };
    });
    return result;
  }, [draft?.schema]);

  const hasChanges = useMemo(() => JSON.stringify(savedConfig) !== JSON.stringify(draft), [savedConfig, draft]);

  const changedSections = useMemo(() => {
    if (!savedConfig || !draft) return [];
    const sections: Array<[SectionId, keyof BotConfig]> = [
      ['model', 'model'],
      ['memory', 'memory'],
      ['proactive', 'proactive'],
      ['life', 'life'],
      ['platforms', 'platforms'],
      ['persona', 'persona_summary'],
      ['session_reset', 'session_reset'],
    ];
    return sections.filter(([, key]) => JSON.stringify(savedConfig[key]) !== JSON.stringify(draft[key])).map(([section]) => section);
  }, [savedConfig, draft]);

  const warnings = useMemo(() => {
    if (!draft) return [];
    const items: string[] = [];
    if (draft.life.time_ratio > draft.life.time_ratio_warning_threshold) {
      items.push('人生轨迹时间倍率较高，适合测试观察，不建议长期生产使用。');
    }
    const feishuExtra = nestedConfig(platformByName(draft, 'feishu'), 'extra');
    if (feishuExtra.group_policy === 'open') {
      items.push('飞书群组策略为 open，所有群成员都可能触发 Bot，生产环境建议使用 allowlist 或 admin_only。');
    }
    if (draft.proactive.enabled && draft.proactive.min_interval_hours < 1) {
      items.push('主动唤醒最小间隔小于 1 小时，可能造成消息过于频繁。');
    }
    return items;
  }, [draft]);

  const fieldHint = (section: string, field: string) => sectionMeta[section]?.fields?.[field];

  const patchSection = <K extends keyof BotConfig>(section: K, patch: Partial<BotConfig[K]>) => {
    setDraft((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        [section]: { ...(prev[section] as object), ...(patch as object) },
      };
    });
  };

  const patchProactive = (patch: Partial<ProactiveConfig>) => patchSection('proactive', patch);
  const patchLife = (patch: Partial<LifeConfig>) => patchSection('life', patch);

  const updatePlatform = (name: string, updater: (platform: PlatformConfig) => PlatformConfig) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const exists = prev.platforms.some((p) => p.name === name);
      const platforms = exists
        ? prev.platforms.map((p) => (p.name === name ? updater(p) : p))
        : [...prev.platforms, updater({ name, enabled: false, config: {} })];
      return { ...prev, platforms };
    });
  };

  const handleLifePreset = (presetId: string) => {
    if (!draft) return;
    const preset = draft.life.presets.find((item) => item.id === presetId);
    patchLife({
      preset: presetId,
      time_ratio: preset ? preset.time_ratio : draft.life.time_ratio,
      daily_interval_seconds: 86400,
      major_interval_seconds: 604800,
    });
  };

  const handleTestConnection = async () => {
    if (!draft || !currentBotId) return;
    setTesting(true);
    try {
      const result = await configApi.testConnection(draft.model.provider, draft.model.api_key, draft.model.base_url, currentBotId);
      if (result) {
        toast.success('API 连接测试成功');
      } else {
        toast.error('API 连接测试失败，请检查 Provider、Key 和 Base URL');
      }
    } catch (err) {
      toast.error(`测试连接失败: ${err}`);
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    if (!draft) return;
    if (warnings.length > 0 && !confirm(`检测到以下风险：\n\n${warnings.join('\n')}\n\n仍然保存吗？`)) return;
    setSaving(true);
    try {
      const feishu = configObject(platformByName(draft, 'feishu'));
      const payload = {
        model: draft.model,
        memory: draft.memory,
        proactive: draft.proactive,
        life: draft.life,
        platforms: draft.platforms,
        feishu,
        session_reset: draft.session_reset,
        persona: draft.persona_summary,
      };
      const response = await configApi.updateConfig(draft.bot_id, payload);
      if (response?.warnings?.length) {
        toast.info(`配置已保存：${response.warnings.join('；')}`);
      } else {
        toast.success('配置已保存');
      }
      await fetchConfig();
    } catch (err) {
      toast.error(`保存配置失败: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  if (!currentBotId && !draft) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)' }}>设置</h1>
        <Card><CardContent style={{ padding: 32, color: 'var(--text-muted)' }}>未选择 Bot，请先在右上角选择一个 Bot。</CardContent></Card>
      </div>
    );
  }

  if (loading || !draft) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)' }}>设置</h1>
        <Card><CardContent style={{ padding: 32, color: 'var(--text-muted)' }}>加载配置中...</CardContent></Card>
      </div>
    );
  }

  const feishu = platformByName(draft, 'feishu');
  const feishuExtra = nestedConfig(feishu, 'extra');
  const feishuRouting = nestedConfig(feishu, 'routing');
  const webhook = platformByName(draft, 'webhook');
  const webhookConfig = configObject(webhook);
  const persona = draft.persona_summary;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
          配置中心
        </h1>
        <p style={{ fontSize: 14, color: 'var(--text-secondary)' }}>
          当前 Bot：{draft.name}。这里的配置会写回 YAML/JSON 文件，保存前可在底部查看变更范围。
        </p>
      </div>

      <Card>
        <CardContent style={{ padding: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            {theme === 'dark' ? <Moon style={{ width: 20, height: 20 }} /> : <Sun style={{ width: 20, height: 20 }} />}
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>外观</div>
              <FieldHint text="深色模式只保存在浏览器本地，不会影响 Bot 配置文件。" />
            </div>
          </div>
          <Toggle checked={theme === 'dark'} onChange={toggleTheme} />
        </CardContent>
      </Card>

      <SectionCard id="model" title={sectionMeta.model?.title || '模型配置'} description={sectionMeta.model?.description} restart={sectionMeta.model?.restart}>
        <div style={gridStyle}>
          <Select
            label="Provider"
            options={providerOptions}
            value={draft.model.provider}
            onChange={(event) => patchSection('model', { provider: event.target.value })}
          />
          <div>
            <Input label="API Key" type="password" value={draft.model.api_key} onChange={(event) => patchSection('model', { api_key: event.target.value })} />
            <FieldHint text={fieldHint('model', 'api_key')} />
          </div>
          <div>
            <Input label="Base URL" value={draft.model.base_url} onChange={(event) => patchSection('model', { base_url: event.target.value })} />
            <FieldHint text={fieldHint('model', 'base_url')} />
          </div>
          <Input label="模型名" value={draft.model.model} onChange={(event) => patchSection('model', { model: event.target.value })} />
          <Input label="Temperature" type="number" min="0" max="2" step="0.1" value={draft.model.temperature} onChange={(event) => patchSection('model', { temperature: Number(event.target.value) })} />
          <Input label="Max Tokens" type="number" min="1" value={draft.model.max_tokens} onChange={(event) => patchSection('model', { max_tokens: Number(event.target.value) })} />
        </div>
        <div style={{ marginTop: 16 }}>
          <Button variant="secondary" onClick={handleTestConnection} loading={testing}>
            <TestTube style={{ width: 14, height: 14, marginRight: 6 }} />
            测试连接
          </Button>
        </div>
      </SectionCard>

      <SectionCard id="memory" title={sectionMeta.memory?.title || '记忆与上下文'} description={sectionMeta.memory?.description} restart={sectionMeta.memory?.restart}>
        <div style={gridStyle}>
          <Input label="软压缩阈值（字符）" type="number" value={draft.memory.soft_limit_chars} onChange={(event) => patchSection('memory', { soft_limit_chars: Number(event.target.value) })} />
          <Input label="硬压缩阈值（字符）" type="number" value={draft.memory.hard_limit_chars} onChange={(event) => patchSection('memory', { hard_limit_chars: Number(event.target.value) })} />
          <Input label="保留工作记忆轮数" type="number" value={draft.memory.max_working_turns} onChange={(event) => patchSection('memory', { max_working_turns: Number(event.target.value) })} />
          <Input label="摘要保留条数" type="number" value={draft.memory.max_summaries} onChange={(event) => patchSection('memory', { max_summaries: Number(event.target.value) })} />
          <Select
            label="向量嵌入"
            options={[{ value: 'none', label: '关闭' }, { value: 'local', label: '本地 sentence-transformers' }]}
            value={draft.memory.embedding}
            onChange={(event) => patchSection('memory', { embedding: event.target.value })}
          />
          <Input label="Embedding 模型" value={draft.memory.embedding_model} onChange={(event) => patchSection('memory', { embedding_model: event.target.value })} />
        </div>
        <FieldHint text="软阈值用于后台压缩，硬阈值会同步压缩。开启本地向量会增加首次加载时间和磁盘占用。" />
      </SectionCard>

      <SectionCard id="proactive" title={sectionMeta.proactive?.title || '主动唤醒'} description={sectionMeta.proactive?.description} restart={sectionMeta.proactive?.restart}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>启用主动唤醒</div>
            <FieldHint text="关闭后 Bot 不会主动发送消息，但仍会保留状态。" />
          </div>
          <Toggle checked={draft.proactive.enabled} onChange={(event) => patchProactive({ enabled: event.target.checked })} />
        </div>
        <div style={gridStyle}>
          <Select label="模式" options={[{ value: 'active', label: '主动' }, { value: 'silent', label: '静默' }]} value={draft.proactive.mode} onChange={(event) => patchProactive({ mode: event.target.value })} />
          <Input label="检查间隔（秒）" type="number" value={draft.proactive.check_interval_seconds} onChange={(event) => patchProactive({ check_interval_seconds: Number(event.target.value) })} />
          <Input label="空闲阈值（小时）" type="number" value={draft.proactive.idle_threshold_hours} onChange={(event) => patchProactive({ idle_threshold_hours: Number(event.target.value) })} />
          <Input label="最小间隔（小时）" type="number" step="0.1" value={draft.proactive.min_interval_hours} onChange={(event) => patchProactive({ min_interval_hours: Number(event.target.value) })} />
          <Input label="每日最大次数" type="number" value={draft.proactive.max_daily} onChange={(event) => patchProactive({ max_daily: Number(event.target.value) })} />
          <Input label="最长沉默天数" type="number" value={draft.proactive.max_idle_days} onChange={(event) => patchProactive({ max_idle_days: Number(event.target.value) })} />
          <Select label="投递平台" options={[{ value: 'cli', label: 'CLI' }, { value: 'feishu', label: '飞书' }, { value: 'webhook', label: 'Webhook' }]} value={draft.proactive.platform_type} onChange={(event) => patchProactive({ platform_type: event.target.value })} />
          <Input label="Webhook URL" value={draft.proactive.webhook_url} onChange={(event) => patchProactive({ webhook_url: event.target.value })} />
          <Input label="主动发送目标频道" value={draft.proactive.home_channel} onChange={(event) => patchProactive({ home_channel: event.target.value })} />
          <Input label="情绪延迟（分钟）" type="number" value={draft.proactive.emotion_response_delay_minutes} onChange={(event) => patchProactive({ emotion_response_delay_minutes: Number(event.target.value) })} />
        </div>
        <div style={{ marginTop: 16 }}>
          <Input label="允许联系时间段" value={joinList(draft.proactive.preferred_contact_times)} onChange={(event) => patchProactive({ preferred_contact_times: splitList(event.target.value) })} />
          <FieldHint text="可填写多个时间段，用逗号分隔，例如 09:00-12:00, 19:00-23:00。" />
        </div>
        <div style={{ marginTop: 16 }}>
          <Input label="情绪关键词" value={joinList(draft.proactive.emotion_keywords)} onChange={(event) => patchProactive({ emotion_keywords: splitList(event.target.value) })} />
          <FieldHint text="用户消息包含这些词时，Bot 会更倾向于延迟关心。" />
        </div>
      </SectionCard>

      <SectionCard id="life" title={sectionMeta.life?.title || '人生轨迹'} description={sectionMeta.life?.description} restart={sectionMeta.life?.restart}>
        <div style={gridStyle}>
          <Select label="时间流速预设" options={[...draft.life.presets.map((p) => ({ value: p.id, label: `${p.label} - ${p.description}` })), { value: 'custom', label: '自定义' }]} value={draft.life.preset} onChange={(event) => handleLifePreset(event.target.value)} />
          <Input label="时间倍率 time_ratio" type="number" value={draft.life.time_ratio} onChange={(event) => patchLife({ preset: 'custom', time_ratio: Number(event.target.value) })} />
          <Input label="日常基础间隔（秒）" type="number" value={draft.life.daily_interval_seconds} onChange={(event) => patchLife({ daily_interval_seconds: Number(event.target.value) })} />
          <Input label="人生大事间隔（秒）" type="number" value={draft.life.major_interval_seconds} onChange={(event) => patchLife({ major_interval_seconds: Number(event.target.value) })} />
          <Input label="大事固定概率" type="number" step="0.01" min="0" max="1" value={draft.life.major_event_fixed_probability} onChange={(event) => patchLife({ major_event_fixed_probability: Number(event.target.value) })} />
          <Input label="日常最小间隔（Bot 天）" type="number" value={draft.life.daily_event_min_gap_days} onChange={(event) => patchLife({ daily_event_min_gap_days: Number(event.target.value) })} />
          <Input label="最大日常事件数" type="number" value={draft.life.max_events} onChange={(event) => patchLife({ max_events: Number(event.target.value) })} />
          <Input label="出生日期" value={draft.life.birth_date} placeholder="YYYY-MM-DD" onChange={(event) => patchLife({ birth_date: event.target.value })} />
        </div>
        <div style={{ marginTop: 16 }}>
          <FieldHint text={`当前设置约等于：现实 ${Math.max(1, Math.round(86400 / Math.max(1, draft.life.time_ratio)))} 秒推进 1 个 Bot 日。`} />
        </div>
      </SectionCard>

      <SectionCard id="platforms" title={sectionMeta.platforms?.title || '平台集成'} description={sectionMeta.platforms?.description} restart={sectionMeta.platforms?.restart}>
        <div style={{ display: 'grid', gap: 16 }}>
          {['cli', 'feishu', 'webhook'].map((name) => {
            const platform = platformByName(draft, name);
            return (
              <div key={name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: 12, borderRadius: 8, background: 'var(--bg-tertiary)' }}>
                <div>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{name === 'cli' ? 'CLI' : name === 'feishu' ? '飞书' : 'Webhook'}</div>
                  <FieldHint text={name === 'cli' ? '本地命令行入口。' : name === 'feishu' ? '飞书机器人接入，凭据保存到 config.yaml。' : '通用 Webhook 投递。'} />
                </div>
                <Toggle checked={platform.enabled} onChange={(event) => updatePlatform(name, (p) => ({ ...p, enabled: event.target.checked }))} />
              </div>
            );
          })}
        </div>

        <div style={{ ...gridStyle, marginTop: 20 }}>
          <Input label="飞书 App ID" value={String(feishuExtra.app_id || '')} onChange={(event) => updatePlatform('feishu', (p) => ({ ...p, config: { ...configObject(p), extra: { ...nestedConfig(p, 'extra'), app_id: event.target.value } } }))} />
          <Input label="飞书 App Secret" type="password" value={String(feishuExtra.app_secret || '')} onChange={(event) => updatePlatform('feishu', (p) => ({ ...p, config: { ...configObject(p), extra: { ...nestedConfig(p, 'extra'), app_secret: event.target.value } } }))} />
          <Select label="连接模式" options={[{ value: 'websocket', label: 'WebSocket' }, { value: 'webhook', label: 'Webhook' }]} value={String(feishuExtra.connection_mode || 'websocket')} onChange={(event) => updatePlatform('feishu', (p) => ({ ...p, config: { ...configObject(p), extra: { ...nestedConfig(p, 'extra'), connection_mode: event.target.value } } }))} />
          <Select label="群组策略" options={[{ value: 'open', label: 'open' }, { value: 'allowlist', label: 'allowlist' }, { value: 'blacklist', label: 'blacklist' }, { value: 'admin_only', label: 'admin_only' }]} value={String(feishuExtra.group_policy || 'allowlist')} onChange={(event) => updatePlatform('feishu', (p) => ({ ...p, config: { ...configObject(p), extra: { ...nestedConfig(p, 'extra'), group_policy: event.target.value } } }))} />
          <Select label="路由模式" options={[{ value: 'dedicated', label: '固定 Bot' }, { value: 'chat_routed', label: '按群聊路由' }]} value={String(feishuRouting.mode || 'dedicated')} onChange={(event) => updatePlatform('feishu', (p) => ({ ...p, config: { ...configObject(p), routing: { ...nestedConfig(p, 'routing'), mode: event.target.value } } }))} />
          <Input label="默认/固定 Bot ID" value={String(feishuRouting.bot_id || feishuRouting.default_bot || '')} onChange={(event) => updatePlatform('feishu', (p) => ({ ...p, config: { ...configObject(p), routing: { ...nestedConfig(p, 'routing'), bot_id: event.target.value, default_bot: event.target.value } } }))} />
          <Input label="Webhook URL" value={String(webhookConfig.webhook_url || '')} onChange={(event) => updatePlatform('webhook', (p) => ({ ...p, config: { ...configObject(p), webhook_url: event.target.value } }))} />
        </div>
      </SectionCard>

      <SectionCard id="persona" title={sectionMeta.persona?.title || 'Bot 人格'} description={sectionMeta.persona?.description} restart={sectionMeta.persona?.restart}>
        <div style={gridStyle}>
          <Input label="名称" value={persona.profile.name} onChange={(event) => patchSection('persona_summary', { profile: { ...persona.profile, name: event.target.value } })} />
          <Input label="年龄" value={persona.profile.age} onChange={(event) => patchSection('persona_summary', { profile: { ...persona.profile, age: event.target.value } })} />
          <Input label="职业/身份" value={persona.profile.occupation} onChange={(event) => patchSection('persona_summary', { profile: { ...persona.profile, occupation: event.target.value } })} />
          <Input label="关系" value={persona.profile.relationship_to_user} onChange={(event) => patchSection('persona_summary', { profile: { ...persona.profile, relationship_to_user: event.target.value } })} />
          <Input label="性格标签" value={joinList(persona.profile.personality_tags)} onChange={(event) => patchSection('persona_summary', { profile: { ...persona.profile, personality_tags: splitList(event.target.value) } })} />
          <Input label="兴趣" value={joinList(persona.profile.interests)} onChange={(event) => patchSection('persona_summary', { profile: { ...persona.profile, interests: splitList(event.target.value) } })} />
        </div>
        <div style={{ display: 'grid', gap: 16, marginTop: 16 }}>
          <TextareaField label="人物摘要" value={persona.profile.summary} onChange={(value) => patchSection('persona_summary', { profile: { ...persona.profile, summary: value } })} />
          <TextareaField label="当前背景" value={persona.backstory.now} onChange={(value) => patchSection('persona_summary', { backstory: { ...persona.backstory, now: value } })} />
          <TextareaField label="关键经历（一行一个）" value={(persona.backstory.key_moments || []).join('\n')} onChange={(value) => patchSection('persona_summary', { backstory: { ...persona.backstory, key_moments: splitList(value) } })} />
          <TextareaField label="不可妥协原则（一行一个）" value={(persona.values.non_negotiable || []).join('\n')} onChange={(value) => patchSection('persona_summary', { values: { ...persona.values, non_negotiable: splitList(value) } })} />
          <Input label="说话语气" value={persona.speaking_style.tone} onChange={(event) => patchSection('persona_summary', { speaking_style: { ...persona.speaking_style, tone: event.target.value } })} />
          <Input label="口头禅" value={joinList(persona.speaking_style.catchphrases)} onChange={(event) => patchSection('persona_summary', { speaking_style: { ...persona.speaking_style, catchphrases: splitList(event.target.value) } })} />
        </div>
      </SectionCard>

      <SectionCard id="session_reset" title="会话策略" description="控制会话自动重置和空闲判断。" restart="保存到 config.yaml，具体生效取决于运行入口读取策略。">
        <div style={gridStyle}>
          <Select label="重置模式" options={[{ value: 'daily', label: '每日' }, { value: 'idle', label: '空闲后' }, { value: 'manual', label: '手动' }]} value={draft.session_reset.mode} onChange={(event) => patchSection('session_reset', { mode: event.target.value })} />
          <Input label="每日重置小时" type="number" min="0" max="23" value={draft.session_reset.at_hour} onChange={(event) => patchSection('session_reset', { at_hour: Number(event.target.value) })} />
          <Input label="空闲分钟" type="number" value={draft.session_reset.idle_minutes} onChange={(event) => patchSection('session_reset', { idle_minutes: Number(event.target.value) })} />
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>重置时通知</div>
              <FieldHint text="开启后会在会话切换或重置时提示用户。" />
            </div>
            <Toggle checked={draft.session_reset.notify} onChange={(event) => patchSection('session_reset', { notify: event.target.checked })} />
          </div>
        </div>
      </SectionCard>

      <Card>
        <CardContent style={{ padding: 20, display: 'grid', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-primary)', fontWeight: 600 }}>
            <ShieldAlert style={{ width: 18, height: 18, color: warnings.length ? 'var(--warning)' : 'var(--text-muted)' }} />
            保存预览
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
            {changedSections.length ? `将更新：${changedSections.join(', ')}` : '暂无未保存改动。'}
          </div>
          {warnings.map((warning) => (
            <div key={warning} style={{ fontSize: 13, color: 'var(--warning)' }}>{warning}</div>
          ))}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
            <Button variant="secondary" disabled={!hasChanges} onClick={() => setDraft(savedConfig)}>
              <RotateCcw style={{ width: 14, height: 14, marginRight: 6 }} />
              恢复上次保存
            </Button>
            <Button variant="primary" disabled={!hasChanges || saving} loading={saving} onClick={handleSave}>
              <Save style={{ width: 14, height: 14, marginRight: 6 }} />
              保存配置
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
