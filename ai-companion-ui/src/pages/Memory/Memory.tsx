import { useCallback, useEffect, useMemo, useState } from 'react';
import { Archive, ArrowRight, Brain, CalendarDays, CheckCircle2, Clock, Database, Filter, Heart, HelpCircle, Layers3, Link2, MapPin, RefreshCw, Search, ShieldCheck, Star, Trash2, User, Wrench } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, Modal, useToast } from '../../components/ui';
import { memoryApi } from '../../api';
import { useBotStore } from '../../stores';
import type {
  ActiveMemoryDetail,
  ContinuityContractFact,
  DailyMemoryPayload,
  DreamingDoctorPayload,
  DreamingStatusPayload,
  EpisodicItem,
  Fact,
  MemoryStats,
  MemoryAuthorityView,
  MemoryTrustItem,
  MemoryTrustPayload,
  Message,
  RelationshipProjectionView,
  SemanticMemory,
  SceneCapsule,
  SessionStateItem,
  EvolutionRefsView,
  EvolutionTimelineItem,
} from '../../types';

type MemoryTab = 'overview' | 'working' | 'daily' | 'episodic' | 'semantic' | 'tools';
type MemoryDeleteType = 'working' | 'daily' | 'episodic' | 'semantic';

interface DeleteTarget {
  type: MemoryDeleteType;
  id: string;
  label: string;
  detail?: string;
}

type ActiveMemoryFocusKey = 'active' | 'recent' | 'stable' | 'pending' | 'changes';

function LayerHint({
  title,
  description,
  badges,
}: {
  title: string;
  description: string;
  badges?: string[];
}) {
  return (
    <Card style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}>
      <CardContent style={{ padding: 14, display: 'grid', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{title}</span>
          {(badges || []).map((item) => (
            <Badge key={item}>{item}</Badge>
          ))}
        </div>
        <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{description}</p>
      </CardContent>
    </Card>
  );
}

function parseList(value?: string | null): string[] {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.map(String).filter(Boolean) : [];
  } catch {
    return [];
  }
}

function scoreValue(value?: number | null) {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function textIncludes(text: string | undefined, query: string) {
  if (!query) return true;
  return (text || '').toLowerCase().includes(query.toLowerCase());
}

function clipText(text: string, maxLength = 120) {
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength).trimEnd()}...`;
}

function trustItems(items?: MemoryTrustItem[]) {
  return Array.isArray(items) ? items.filter(Boolean) : [];
}

function sessionStateItems(items?: SessionStateItem[]) {
  return Array.isArray(items) ? items.filter(Boolean) : [];
}

function trustText(value: unknown) {
  if (value === null || value === undefined || value === '') return '暂无';
  if (typeof value === 'string') return value;
  return JSON.stringify(value);
}

function trustDate(value?: string | null) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN');
}

function humanizePolicy(value: string) {
  const labels: Record<string, string> = {
    short_term_state_overrides_long_term_recall: '短期状态优先于旧长期记忆',
    manual_user_understanding_overrides_auto_fact: '手动理解优先于自动事实',
    committed_relationship_overrides_single_turn_tone: '稳定关系不被单轮语气推翻',
    vector_and_rollup_are_retrieval_hints_not_authority: '向量和 rollup 只是辅助召回',
  };
  return labels[value] || value;
}

function humanizeMetricKey(value: string) {
  const labels: Record<string, string> = {
    working_message_count: '工作记忆消息',
    working_turns: '工作记忆轮数',
    daily_recent_message_count: '日记忆近况',
    daily_messages: '日记忆消息',
    daily_days: '覆盖天数',
    session_state_count: '当前状态',
    scene_active: '现场激活',
    semantic_item_count: '语义事实',
    semantic_fact_count: '语义事实',
    relationship_label: '关系阶段',
    episodic_count: '情景记忆',
    vector_recall_count: '向量召回',
    rollup_count: 'rollup',
    user_understanding_projection: '理解投影',
    user_understanding_auto_facts: '自动理解',
    active_memory_count: '本轮激活',
  };
  return labels[value] || value;
}

function humanizeUnknown(value: unknown) {
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (Array.isArray(value)) return `${value.length} 项`;
  if (value === null || value === undefined || value === '') return '暂无';
  if (typeof value === 'object') return '已生成';
  return String(value);
}

function formatMb(value?: number | null) {
  return `${((value || 0) / 1024).toFixed(2)} MB`;
}

function humanizeExpressionMode(value?: string) {
  const labels: Record<string, string> = {
    explicit_recall: '直接提起',
    light_reference: '轻描淡写地带出',
    silent_influence: '只影响语气和分寸',
    ask_before_entering: '先确认再展开',
    avoid: '不要主动提',
  };
  return labels[value || ''] || value || '未标注';
}

function RelationshipMetric({ label, value, tone }: { label: string; value: number; tone: string }) {
  const safeValue = Math.max(0, Math.min(100, value));
  return (
    <div style={{ display: 'grid', gap: 6, minWidth: 140 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
        <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{label}</span>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>{safeValue.toFixed(0)}</span>
      </div>
      <div style={{ height: 6, borderRadius: 999, backgroundColor: 'var(--bg-tertiary)', overflow: 'hidden' }}>
        <div style={{ width: `${safeValue}%`, height: '100%', backgroundColor: tone }} />
      </div>
    </div>
  );
}

function SceneCapsuleCard({ scene }: { scene?: SceneCapsule | null }) {
  const capsule = scene || {};
  const active = Boolean(capsule.active);
  const location = capsule.location || '';
  const activity = capsule.activity || '';
  const nextAction = capsule.next_action || '';
  const spatial = capsule.spatial || '';
  const stateCount = capsule.state_count ?? (Array.isArray(capsule.states) ? capsule.states.length : 0);

  return (
    <Card style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}>
      <CardHeader style={{ padding: '16px 20px 10px', marginBottom: 0, borderBottom: 'none' }}>
        <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <MapPin style={{ width: 18, height: 18, color: 'var(--accent)' }} />
          当前现场
          <Badge variant={active ? 'success' : 'default'}>{active ? '已激活' : '未激活'}</Badge>
          {capsule.hard_constraint_ready && <Badge variant="info">已进入硬约束</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent style={{ padding: '0 20px 20px', display: 'grid', gap: 12 }}>
        {!active ? (
          <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            当前没有足够明确的共享现场状态。没有现场锚点时，系统会更多依赖短期上下文和长期事实。
          </p>
        ) : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 }}>
              <SceneFact label="地点" value={location || '暂无'} />
              <SceneFact label="正在做" value={activity || '暂无'} />
              <SceneFact label="下一步" value={nextAction || '暂无'} />
              <SceneFact label="空间关系" value={spatial || '暂无'} />
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <Badge>{stateCount} 条现场状态</Badge>
              <Badge variant="info">{capsule.hard_constraint_ready ? '回复必须承接现场' : '仅作为现场摘要'}</Badge>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function SceneFact({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ padding: 12, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)', display: 'grid', gap: 6 }}>
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.5 }}>{value}</span>
    </div>
  );
}

function MemoryAuthorityCard({ authority }: { authority?: MemoryAuthorityView | null }) {
  const policy = Array.isArray(authority?.policy) ? authority?.policy : [];
  const layers = authority?.layers || {};
  const hasLayerData = Object.keys(layers).length > 0;
  const order = [
    { key: 'short_term_authority', label: '短期权威', tone: 'var(--accent)' },
    { key: 'long_term_authority', label: '长期权威', tone: 'var(--success)' },
    { key: 'derived_projection', label: '派生投影', tone: 'var(--warning)' },
    { key: 'turn_activation', label: '本轮激活', tone: 'var(--info)' },
  ];

  return (
    <Card style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}>
      <CardHeader style={{ padding: '16px 20px 10px', marginBottom: 0, borderBottom: 'none' }}>
        <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <ShieldCheck style={{ width: 18, height: 18, color: 'var(--accent)' }} />
          本页怎么判断“该信谁”
          {authority?.mode && <Badge>{authority.mode}</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent style={{ padding: '0 20px 20px', display: 'grid', gap: 12 }}>
        <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          {authority?.summary || '本轮会先承接当前场景和短期状态，再参考长期事实；派生索引只辅助召回，不覆盖权威记忆。'}
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
          {order.map((item) => (
            <AuthorityStageCard
              key={item.key}
              title={item.label}
              tone={item.tone}
              layer={layers[item.key] as Record<string, unknown> | undefined}
            />
          ))}
        </div>
        {!hasLayerData && (
          <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6 }}>
            当前接口还没有返回分层命中明细，页面会继续使用可信视图和各记忆库列表作为诊断依据。
          </p>
        )}
        {policy.length > 0 && (
          <div style={{ display: 'grid', gap: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>裁决规则</span>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {policy.map((item) => (
                <Badge key={item} variant="info">{humanizePolicy(item)}</Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function AuthorityStageCard({
  title,
  tone,
  layer,
}: {
  title: string;
  tone: string;
  layer?: Record<string, unknown>;
}) {
  const sources = Array.isArray(layer?.sources) ? layer?.sources.map(String) : [];
  const priority = typeof layer?.priority === 'number' ? layer.priority : undefined;
  const metrics = Object.entries(layer || {})
    .filter(([key]) => key !== 'sources' && key !== 'priority')
    .slice(0, 4);

  return (
    <div style={{ padding: 14, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)', display: 'grid', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{title}</span>
        {priority !== undefined && <Badge style={{ backgroundColor: `${tone}18`, color: tone }}>P{priority}</Badge>}
      </div>
      {sources.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {sources.map((source) => (
            <Badge key={source}>{source}</Badge>
          ))}
        </div>
      )}
      <div style={{ display: 'grid', gap: 4 }}>
        {metrics.length === 0 ? (
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>暂无命中明细</span>
        ) : (
          metrics.map(([key, value]) => (
            <div key={key} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 12 }}>
              <span style={{ color: 'var(--text-muted)' }}>{humanizeMetricKey(key)}</span>
              <span style={{ color: 'var(--text-secondary)' }}>{humanizeUnknown(value)}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function MemoryArchitecturePanel({ payload }: { payload: MemoryTrustPayload | null }) {
  const layers = payload?.memory_layers || {};
  const authoritySummary = layers.authority?.summary || '短期状态、长期事实、派生投影和本轮激活现在各有明确职责。';
  const projectionSummary = layers.projection?.summary || 'UserUnderstanding、向量索引和 rollup 负责帮助理解和召回，但不再被当作真相源。';
  const operationsSummary = layers.operations?.summary || '整理、维护和写入流程负责把候选记忆变成稳定事实，或把它们留在派生层。';
  const explainabilitySummary = layers.explainability?.summary || '诊断层解释本轮为什么这样记、为什么这样召回。';

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <Card style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}>
        <CardHeader style={{ padding: '16px 20px 10px', marginBottom: 0, borderBottom: 'none' }}>
          <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Layers3 style={{ width: 18, height: 18, color: 'var(--accent)' }} />
            记忆系统四层结构
          </CardTitle>
        </CardHeader>
        <CardContent style={{ padding: '0 20px 20px', display: 'grid', gap: 12 }}>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            先判断当前现场和短期状态，再承接长期事实；投影和索引只辅助，不直接盖过真相源。下面四层对应的是“存什么、怎么用、谁说了算”。
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
            <ArchitectureCard title="1. 权威记忆" badges={['Working', 'Daily', 'Session', 'Semantic', 'Relationship']} description={authoritySummary} />
            <ArchitectureCard title="2. 派生投影与索引" badges={['Understanding', 'Vector', 'Rollup']} description={projectionSummary} />
            <ArchitectureCard title="3. 整理与维护" badges={['Governor', 'Maintenance', 'Dreaming']} description={operationsSummary} />
            <ArchitectureCard title="4. 解释与诊断" badges={['Trust View', 'Prompt', 'Trace']} description={explainabilitySummary} />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function ArchitectureCard({
  title,
  badges,
  description,
}: {
  title: string;
  badges: string[];
  description: string;
}) {
  return (
    <div style={{ padding: 14, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)', display: 'grid', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{title}</span>
        {badges.map((item) => (
          <Badge key={item}>{item}</Badge>
        ))}
      </div>
      <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{description}</p>
    </div>
  );
}

function MemoryOverviewPanel({
  memoryStats,
  memoryTrust,
  dreamingStatus,
  onSelectTab,
  botId,
}: {
  memoryStats: MemoryStats | null;
  memoryTrust: MemoryTrustPayload | null;
  dreamingStatus: DreamingStatusPayload | null;
  onSelectTab: (tab: MemoryTab) => void;
  botId: string;
}) {
  const layers = [
    {
      tab: 'working' as const,
      title: '1. 工作记忆',
      subtitle: '当前会话里刚说过的话',
      description: '只负责接住最近几轮对话，不会直接变成长期印象。',
      count: memoryStats?.working_count ?? 0,
      size: formatMb(memoryStats?.working_size_kb),
      badge: '短期',
      tone: 'var(--accent)',
      icon: Clock,
    },
    {
      tab: 'daily' as const,
      title: '2. 日记忆',
      subtitle: '最近几天、跨会话的连续性',
      description: '帮助 Bot 在不同通道和会话之间继续接住上下文。',
      count: memoryStats?.daily_count ?? 0,
      size: formatMb(memoryStats?.daily_size_kb),
      badge: '短期',
      tone: 'var(--success)',
      icon: CalendarDays,
    },
    {
      tab: 'episodic' as const,
      title: '3. 情景记忆',
      subtitle: '共同经历与关键事件',
      description: '保存值得长期记住的片段，适合清理误抽取的经历。',
      count: memoryStats?.episodic_count ?? 0,
      size: formatMb(memoryStats?.episodic_size_kb),
      badge: '长期',
      tone: 'var(--warning)',
      icon: Brain,
    },
    {
      tab: 'semantic' as const,
      title: '4. 语义记忆',
      subtitle: '稳定事实与关系状态',
      description: '这里是长期真相源，改这里才是在真正修正长期画像。',
      count: memoryStats?.semantic_count ?? 0,
      size: formatMb(memoryStats?.semantic_size_kb),
      badge: '长期',
      tone: 'var(--info)',
      icon: User,
    },
  ];

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <Card style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}>
        <CardContent style={{ padding: 20, display: 'grid', gap: 16 }}>
          <div style={{ display: 'grid', gap: 8 }}>
            <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.08em', color: 'var(--accent)' }}>MEMORY MAP</span>
            <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>先看地图，再进单层</h2>
            <p style={{ margin: 0, fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
              这个页面现在按“短期承接 → 长期沉淀 → 派生维护”的顺序来看。你不用先理解所有卡片，只要先判断问题落在哪一层，再点进去处理。
            </p>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
            <OverviewStep
              index="01"
              title="先看现在 Bot 正在承接什么"
              description="下面的“当前正在生效的记忆”会告诉你这轮回复优先信哪一层。"
            />
            <OverviewStep
              index="02"
              title="再进对应记忆层"
              description="刚说过的话去工作/日记忆，长期记错去语义/情景记忆。"
            />
            <OverviewStep
              index="03"
              title="最后再动维护工具"
              description="向量、整理和清空全部都放到单独页签，避免和事实层混在一起。"
            />
          </div>
        </CardContent>
      </Card>

      <Card style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}>
        <CardHeader style={{ borderBottom: 'none', marginBottom: 0, padding: '16px 20px 8px' }}>
          <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <Layers3 style={{ width: 18, height: 18, color: 'var(--accent)' }} />
            记忆层级地图
            <Badge variant="info">按职责分层</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent style={{ padding: '8px 20px 20px', display: 'grid', gap: 12 }}>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            只有前四层是真正的“记忆库”。向量索引、可信视图、梦境整理都是派生层或维护层，不应该和记忆真相源混为一谈。
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
            {layers.map((layer) => (
              <LayerEntryCard key={layer.tab} {...layer} onOpen={() => onSelectTab(layer.tab)} />
            ))}
            <LayerUtilityCard
              title="5. 派生层与维护"
              subtitle="向量索引、可信视图、梦境整理"
              description="它们负责召回、解释和整理，不直接决定长期真相。"
              vectorCount={memoryStats?.vector_count ?? 0}
              dreamingEnabled={dreamingStatus?.enabled ?? false}
              onOpen={() => onSelectTab('tools')}
            />
          </div>
        </CardContent>
      </Card>

      <MemoryTrustPanel payload={memoryTrust} botId={botId} />
    </div>
  );
}

function OverviewStep({
  index,
  title,
  description,
}: {
  index: string;
  title: string;
  description: string;
}) {
  return (
    <div style={{ padding: 14, borderRadius: 10, backgroundColor: 'var(--bg-tertiary)', display: 'grid', gap: 8 }}>
      <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.06em', color: 'var(--accent)' }}>{index}</span>
      <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{title}</span>
      <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{description}</p>
    </div>
  );
}

function LayerEntryCard({
  title,
  subtitle,
  description,
  count,
  size,
  badge,
  tone,
  icon: Icon,
  onOpen,
}: {
  title: string;
  subtitle: string;
  description: string;
  count: number;
  size: string;
  badge: string;
  tone: string;
  icon: typeof Clock;
  onOpen: () => void;
}) {
  return (
    <div style={{ padding: 14, borderRadius: 10, backgroundColor: 'var(--bg-tertiary)', display: 'grid', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
        <div style={{ display: 'grid', gap: 6 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <div style={{ width: 30, height: 30, borderRadius: 8, backgroundColor: `${tone}18`, color: tone, display: 'grid', placeItems: 'center' }}>
              <Icon style={{ width: 16, height: 16 }} />
            </div>
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{title}</span>
          </div>
          <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{subtitle}</span>
        </div>
        <Badge variant={badge === '长期' ? 'warning' : 'info'}>{badge}</Badge>
      </div>
      <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{description}</p>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Badge>{count} 条</Badge>
        <Badge>{size}</Badge>
        {count === 0 && <Badge variant="default">当前为空</Badge>}
      </div>
      <Button variant="secondary" size="sm" onClick={onOpen} style={{ justifyContent: 'space-between' }}>
        查看这一层
        <ArrowRight style={{ width: 14, height: 14 }} />
      </Button>
    </div>
  );
}

function LayerUtilityCard({
  title,
  subtitle,
  description,
  vectorCount,
  dreamingEnabled,
  onOpen,
}: {
  title: string;
  subtitle: string;
  description: string;
  vectorCount: number;
  dreamingEnabled: boolean;
  onOpen: () => void;
}) {
  return (
    <div style={{ padding: 14, borderRadius: 10, backgroundColor: 'var(--bg-tertiary)', display: 'grid', gap: 10 }}>
      <div style={{ display: 'grid', gap: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <div style={{ width: 30, height: 30, borderRadius: 8, backgroundColor: 'var(--accent-light)', color: 'var(--accent)', display: 'grid', placeItems: 'center' }}>
            <Wrench style={{ width: 16, height: 16 }} />
          </div>
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{title}</span>
        </div>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{subtitle}</span>
      </div>
      <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{description}</p>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Badge>向量 {vectorCount} 条</Badge>
        <Badge variant={dreamingEnabled ? 'success' : 'default'}>{dreamingEnabled ? '整理开启中' : '整理未开启'}</Badge>
      </div>
      <Button variant="secondary" size="sm" onClick={onOpen} style={{ justifyContent: 'space-between' }}>
        打开维护工具
        <ArrowRight style={{ width: 14, height: 14 }} />
      </Button>
    </div>
  );
}

function MemoryTrustPanel({ payload, botId }: { payload: MemoryTrustPayload | null; botId: string }) {
  const view = payload?.memory_trust_view || {};
  const evolutionRefs = payload?.evolution_refs;
  const authority = payload?.memory_authority || {};
  const scene = payload?.scene_capsule || view.scene_capsule || {};
  const sessionStates = sessionStateItems(payload?.session_state ?? (view as { session_state?: SessionStateItem[] }).session_state);
  const recently = trustItems(view.recently_remembered);
  const stable = trustItems(view.stable_understanding);
  const pending = trustItems(view.pending_confirmation);
  const corrected = trustItems(view.corrected_memories);
  const archived = trustItems(view.archived_or_suppressed);
  const relationship = view.relationship_anchor || {};
  const contract = payload?.continuity_contract || null;
  const relationshipProjection = payload?.relationship_projection || null;
  const openThreads = Array.isArray(view.open_threads) ? view.open_threads : [];
  const commitments = Array.isArray(view.commitments) ? view.commitments : [];
  const activeMemoryDetails = Array.isArray(view.active_memory_details)
    ? view.active_memory_details.filter(Boolean)
    : Array.isArray(payload?.active_memory_details)
      ? payload.active_memory_details.filter(Boolean)
      : [];
  const hasRelationship = Boolean(relationship.label || relationship.status || relationship.narrative || relationship.guidance);
  const activeInsightCount = activeMemoryDetails.length || (sessionStates.length + recently.length + stable.length + pending.length);
  const hasAttentionItems = pending.length > 0 || corrected.length > 0 || archived.length > 0 || openThreads.length > 0 || commitments.length > 0;
  const hasRelationshipInsights = hasRelationship || Boolean(contract) || Boolean(relationshipProjection);
  const hasCurrentContext = Boolean(scene.active) || sessionStates.length > 0 || recently.length > 0 || stable.length > 0 || activeMemoryDetails.length > 0;
  const focusOptions = useMemo(() => ([
    { key: 'active' as const, label: '当前线索', value: activeInsightCount, tone: 'var(--accent)', icon: <Brain size={16} /> },
    { key: 'recent' as const, label: '最近记住', value: recently.length, tone: 'var(--accent)', icon: <Clock size={16} /> },
    { key: 'stable' as const, label: '稳定理解', value: stable.length, tone: 'var(--success)', icon: <CheckCircle2 size={16} /> },
    { key: 'pending' as const, label: '待确认', value: pending.length, tone: 'var(--warning)', icon: <HelpCircle size={16} /> },
    { key: 'changes' as const, label: '已纠正/归档', value: corrected.length + archived.length, tone: 'var(--info)', icon: <Archive size={16} /> },
  ]), [activeInsightCount, archived.length, corrected.length, pending.length, recently.length, stable.length]);
  const [selectedFocus, setSelectedFocus] = useState<ActiveMemoryFocusKey>('active');

  useEffect(() => {
    const hasSelectedContent = focusOptions.some((item) => item.key === selectedFocus && item.value > 0);
    if (hasSelectedContent) return;
    const fallback = focusOptions.find((item) => item.value > 0);
    if (fallback) {
      setSelectedFocus(fallback.key);
    }
  }, [focusOptions, selectedFocus]);

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <Card style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}>
        <CardHeader style={{ borderBottom: 'none', marginBottom: 0, padding: '16px 20px 8px' }}>
          <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <Brain style={{ width: 18, height: 18, color: 'var(--accent)' }} />
            当前正在生效的记忆
            {payload?.user_id && <Badge>{payload.user_id}</Badge>}
            <Badge variant="info">先判断这轮回复在信什么</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent style={{ padding: '8px 20px 20px', display: 'grid', gap: 16 }}>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            这里回答三件事：现在 Bot 处在什么现场、这轮优先信哪层记忆、有没有需要你介入的冲突或脏数据。下面只展示正在起作用的内容，没有内容的块会自动收起。
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
            {focusOptions.map((item) => (
              <TrustSummary
                key={item.key}
                icon={item.icon}
                label={item.label}
                value={item.value}
                tone={item.tone}
                selected={selectedFocus === item.key}
                onClick={() => setSelectedFocus(item.key)}
              />
            ))}
          </div>
          <SelectedFocusDetail
            selectedFocus={selectedFocus}
            activeMemoryDetails={activeMemoryDetails}
            recently={recently}
            stable={stable}
            pending={pending}
            corrected={corrected}
            archived={archived}
          />
        </CardContent>
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
        <SceneCapsuleCard scene={scene} />
        <MemoryAuthorityCard authority={authority} />
      </div>

      <MemoryArchitecturePanel payload={payload} />

      {hasCurrentContext && (
        <Card style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}>
          <CardHeader style={{ borderBottom: 'none', marginBottom: 0, padding: '16px 20px 8px' }}>
            <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <ShieldCheck style={{ width: 18, height: 18, color: 'var(--accent)' }} />
              这轮回复最可能用到的线索
            </CardTitle>
          </CardHeader>
          <CardContent style={{ padding: '8px 20px 20px', display: 'grid', gap: 12 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
              {activeMemoryDetails.length > 0 && <ActiveMemorySection items={activeMemoryDetails} />}
              {sessionStates.length > 0 && <SessionStateSection items={sessionStates} />}
              {recently.length > 0 && <TrustSection title="最近会自然想起" items={recently} empty="暂无最近激活的记忆" />}
              {stable.length > 0 && <TrustSection title="稳定用户理解" items={stable} empty="暂无高置信用户事实" />}
              {pending.length > 0 && <TrustSection title="需要继续确认" items={pending} empty="暂无低置信待确认事实" />}
            </div>
          </CardContent>
        </Card>
      )}

      {hasRelationshipInsights && (
        <Card style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}>
          <CardHeader style={{ borderBottom: 'none', marginBottom: 0, padding: '16px 20px 8px' }}>
            <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Heart style={{ width: 18, height: 18, color: 'var(--error)' }} />
              长期关系与连续性
            </CardTitle>
          </CardHeader>
          <CardContent style={{ padding: '8px 20px 20px', display: 'grid', gap: 16 }}>
            {hasRelationship && (
              <div style={{ padding: 14, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)', display: 'grid', gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>关系锚点</span>
                  {relationship.label && <Badge variant="success">{relationship.label}</Badge>}
                  {relationship.status && <Badge>{relationship.status}</Badge>}
                  {typeof relationship.score === 'number' && <Badge variant="info">{relationship.score.toFixed(0)}</Badge>}
                </div>
                {relationship.narrative && <p style={{ margin: 0, fontSize: 13, color: 'var(--text-primary)' }}>{relationship.narrative}</p>}
                {relationship.guidance && <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)' }}>{relationship.guidance}</p>}
              </div>
            )}

            {(contract || relationshipProjection) && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
                {contract && (
                  <div style={{ display: 'grid', gap: 12 }}>
                    <ContractFactList title="连续性硬事实" items={contract.hard_facts || []} empty="暂无硬事实" />
                    <ContractFactList title="当前约束" items={contract.active_boundaries || []} empty="暂无当前约束" />
                    <ContractFactList title="软语境" items={contract.soft_context || []} empty="暂无软语境" />
                    <ContractFactList title="表达自由" items={contract.style_freedom || []} empty="暂无表达自由" />
                    {(contract.risk_flags || []).length > 0 && (
                      <div style={{ padding: 14, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
                          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>风险标记</span>
                          <Badge>{(contract.risk_flags || []).length}</Badge>
                        </div>
                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                          {(contract.risk_flags || []).map((flag) => (
                            <Badge key={flag} variant="warning">{flag}</Badge>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
                <RelationshipProjectionCard projection={relationshipProjection} />
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {(hasAttentionItems || evolutionRefs) && (
        <Card style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}>
          <CardHeader style={{ borderBottom: 'none', marginBottom: 0, padding: '16px 20px 8px' }}>
            <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Archive style={{ width: 18, height: 18, color: 'var(--warning)' }} />
              需要你关注的变化
            </CardTitle>
          </CardHeader>
          <CardContent style={{ padding: '8px 20px 20px', display: 'grid', gap: 12 }}>
            {(openThreads.length > 0 || commitments.length > 0 || corrected.length > 0 || archived.length > 0) && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
                {(openThreads.length > 0 || commitments.length > 0) && (
                  <div style={{ padding: 14, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)', display: 'grid', gap: 8 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Link2 style={{ width: 16, height: 16, color: 'var(--accent)' }} />
                      <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>未完成线索</span>
                    </div>
                    {[...openThreads, ...commitments].slice(0, 6).map((item, index) => (
                      <p key={index} style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)' }}>{trustText(item)}</p>
                    ))}
                  </div>
                )}
                {corrected.length > 0 && <TrustSection title="已纠正的事实" items={corrected} empty="暂无纠正记录" mode="correction" />}
                {archived.length > 0 && <TrustSection title="已归档或抑制" items={archived} empty="暂无归档记录" mode="event" />}
              </div>
            )}

            <EvolutionRefsPanel botId={botId} refs={evolutionRefs} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function EvolutionRefsPanel({ botId, refs }: { botId: string; refs?: EvolutionRefsView }) {
  if (!refs) return null;
  const timeline = Array.isArray(refs?.timeline_preview) ? refs.timeline_preview : [];
  const diagnostics = refs?.diagnostics;
  const pendingCount = refs?.pending_candidates?.length ?? 0;

  return (
    <div style={{ padding: 14, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)', display: 'grid', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Link2 style={{ width: 16, height: 16, color: 'var(--accent)' }} />
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>相关人格演化</span>
        </div>
        <Link to="/evolution" style={{ color: 'var(--accent)', fontSize: 12, fontWeight: 600, textDecoration: 'none' }}>
          查看完整演化页
        </Link>
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Badge variant="info">活跃 signals {diagnostics?.captured_signal_count ?? 0}</Badge>
        <Badge variant="warning">待晋升 {diagnostics?.pending_promotion_count ?? pendingCount}</Badge>
        <Badge>已抑制 {diagnostics?.suppressed_promotions ?? 0}</Badge>
      </div>
      {timeline.length === 0 ? (
        <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          当前还没有可追踪的人格演化事件，后续当共同经历、关系变化或风格漂移被捕获后，这里会直接给出跳转入口。
        </p>
      ) : (
        <div style={{ display: 'grid', gap: 8 }}>
          {timeline.map((item) => (
            <EvolutionInlineLink key={item.id} botId={botId} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

function EvolutionInlineLink({ botId, item }: { botId: string; item: EvolutionTimelineItem }) {
  return (
    <Link
      to={`/evolution?bot=${encodeURIComponent(botId)}&event=${encodeURIComponent(item.id)}`}
      style={{
        display: 'grid',
        gap: 4,
        padding: 10,
        borderRadius: 8,
        textDecoration: 'none',
        border: '1px solid var(--border-subtle)',
        backgroundColor: 'var(--bg-secondary)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{clipText(item.summary || item.event_type, 72)}</span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{item.dimension || 'mixed'}</span>
      </div>
      <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
        {clipText(item.human_readable_reason || '查看这次演化的原因、证据和 diff', 96)}
      </span>
    </Link>
  );
}

function SessionStateSection({ items }: { items: SessionStateItem[] }) {
  return (
    <div style={{ padding: 14, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)', display: 'grid', gap: 10, alignContent: 'start' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>当前状态记忆</span>
        <Badge>{items.length}</Badge>
      </div>
      {items.length === 0 ? (
        <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)' }}>暂无当前场景状态</p>
      ) : (
        items.slice(0, 8).map((item, index) => (
          <div key={`${item.state_id || item.scope || 'state'}-${index}`} style={{ display: 'grid', gap: 5, paddingTop: 8, borderTop: '1px solid var(--border-subtle)' }}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
                {item.scope || 'unknown'} / {item.predicate || 'unknown'}
              </span>
              {typeof item.confidence === 'number' && <Badge variant={item.confidence >= 0.85 ? 'success' : 'warning'}>{(item.confidence * 100).toFixed(0)}%</Badge>}
              {item.status && <Badge>{item.status}</Badge>}
              {item.source_kind && <Badge variant="info">{item.source_kind}</Badge>}
            </div>
            {item.value && <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>{clipText(item.value, 120)}</p>}
            {item.updated_at && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{trustDate(item.updated_at)}</span>}
          </div>
        ))
      )}
    </div>
  );
}

function ContractFactList({ title, items, empty }: { title: string; items: ContinuityContractFact[]; empty: string }) {
  return (
    <div style={{ padding: 14, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)', display: 'grid', gap: 10, alignContent: 'start' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{title}</span>
        <Badge>{items.length}</Badge>
      </div>
      {items.length === 0 ? (
        <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)' }}>{empty}</p>
      ) : (
        items.slice(0, 6).map((item, index) => (
          <div key={`${item.kind || 'fact'}-${index}`} style={{ display: 'grid', gap: 5, paddingTop: 8, borderTop: '1px solid var(--border-subtle)' }}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>{item.kind || 'fact'}</span>
              {item.source && <Badge>{item.source}</Badge>}
              {typeof item.priority === 'number' && <Badge variant="info">P{item.priority}</Badge>}
            </div>
            {item.text && <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>{clipText(item.text, 120)}</p>}
          </div>
        ))
      )}
    </div>
  );
}

function RelationshipProjectionCard({ projection }: { projection: RelationshipProjectionView | null | undefined }) {
  if (!projection) return null;
  const needs = Array.isArray(projection.need_from_bot) ? projection.need_from_bot : [];
  const repairs = Array.isArray(projection.repair_preferences) ? projection.repair_preferences : [];
  const threads = Array.isArray(projection.open_threads) ? projection.open_threads : [];
  return (
    <Card style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: 8, border: '1px solid var(--border-subtle)' }}>
      <CardHeader style={{ borderBottom: 'none', padding: '16px 20px' }}>
        <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Link2 style={{ width: 18, height: 18, color: 'var(--accent)' }} />
          关系投影诊断
          {projection.label && <Badge variant="success">{projection.label}</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent style={{ padding: '0 20px 20px', display: 'grid', gap: 12 }}>
        <ContractFactList title="Bot 需要承接" items={needs.map((text, index) => ({ kind: `need_${index}`, text }))} empty="暂无投影内容" />
        <ContractFactList title="修复偏好" items={repairs.map((text, index) => ({ kind: `repair_${index}`, text }))} empty="暂无修复偏好" />
        <ContractFactList title="开放线程" items={threads.map((text, index) => ({ kind: `thread_${index}`, text }))} empty="暂无开放线程" />
      </CardContent>
    </Card>
  );
}

function TrustSummary({
  icon,
  label,
  value,
  tone,
  selected = false,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  tone: string;
  selected?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: 14,
        borderRadius: 8,
        backgroundColor: selected ? `${tone}12` : 'var(--bg-tertiary)',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        border: selected ? `1px solid ${tone}` : '1px solid var(--border-subtle)',
        width: '100%',
        textAlign: 'left',
        cursor: 'pointer',
      }}
    >
      <div style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: `${tone}18`, color: tone, display: 'grid', placeItems: 'center', flex: '0 0 auto' }}>
        {icon}
      </div>
      <div>
        <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1 }}>{value}</div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>{label}</div>
      </div>
    </button>
  );
}

function ActiveMemoryPreview({ items }: { items: ActiveMemoryDetail[] }) {
  return (
    <div style={{ padding: 14, borderRadius: 10, backgroundColor: 'var(--bg-tertiary)', display: 'grid', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Search style={{ width: 16, height: 16, color: 'var(--accent)' }} />
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>这轮正在用的线索明细</span>
        </div>
        <Badge variant="info">{items.length} 条</Badge>
      </div>
      <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
        下面这些就是“当前正在生效的记忆”的具体内容，不只是条数。
      </p>
      {items.length === 0 ? (
        <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)' }}>当前没有可展示的线索明细</p>
      ) : (
        <div style={{ display: 'grid', gap: 8 }}>
          {items.slice(0, 8).map((item, index) => (
            <div
              key={`${item.text || item.source || 'preview'}-${index}`}
              style={{ display: 'grid', gap: 6, paddingTop: 8, borderTop: '1px solid var(--border-subtle)' }}
            >
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>线索 {index + 1}</span>
                {item.source && <Badge variant="info">{item.source}</Badge>}
                {typeof item.score === 'number' && <Badge>{item.score.toFixed(2)}</Badge>}
                {item.expression_mode && <Badge>{humanizeExpressionMode(item.expression_mode)}</Badge>}
              </div>
              {item.text && <p style={{ margin: 0, fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.6 }}>{item.text}</p>}
              {item.reason && <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>为什么会生效：{item.reason}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SelectedFocusDetail({
  selectedFocus,
  activeMemoryDetails,
  recently,
  stable,
  pending,
  corrected,
  archived,
}: {
  selectedFocus: ActiveMemoryFocusKey;
  activeMemoryDetails: ActiveMemoryDetail[];
  recently: MemoryTrustItem[];
  stable: MemoryTrustItem[];
  pending: MemoryTrustItem[];
  corrected: MemoryTrustItem[];
  archived: MemoryTrustItem[];
}) {
  if (selectedFocus === 'active') {
    return <ActiveMemoryPreview items={activeMemoryDetails} />;
  }
  if (selectedFocus === 'recent') {
    return <TrustSection title="最近记住的内容明细" items={recently} empty="最近没有可展示的激活记忆" />;
  }
  if (selectedFocus === 'stable') {
    return <TrustSection title="稳定理解明细" items={stable} empty="当前没有高置信稳定理解" />;
  }
  if (selectedFocus === 'pending') {
    return <TrustSection title="待确认明细" items={pending} empty="当前没有待确认线索" />;
  }
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
      <TrustSection title="已纠正的事实明细" items={corrected} empty="当前没有已纠正事实" mode="correction" />
      <TrustSection title="已归档或抑制明细" items={archived} empty="当前没有归档或抑制项" mode="event" />
    </div>
  );
}

function ActiveMemorySection({ items }: { items: ActiveMemoryDetail[] }) {
  return (
    <div style={{ padding: 14, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)', display: 'grid', gap: 10, alignContent: 'start' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>本轮激活明细</span>
        <Badge>{items.length}</Badge>
      </div>
      {items.length === 0 ? (
        <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)' }}>当前没有可展示的激活明细</p>
      ) : (
        items.slice(0, 8).map((item, index) => (
          <div key={`${item.text || item.source || 'active'}-${index}`} style={{ display: 'grid', gap: 6, paddingTop: 8, borderTop: '1px solid var(--border-subtle)' }}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
              {item.source && <Badge variant="info">{item.source}</Badge>}
              {typeof item.score === 'number' && <Badge>{item.score.toFixed(2)}</Badge>}
              {item.expression_mode && <Badge>{humanizeExpressionMode(item.expression_mode)}</Badge>}
            </div>
            {item.text && <p style={{ margin: 0, fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.6 }}>{clipText(item.text, 160)}</p>}
            {item.reason && <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>原因：{item.reason}</span>}
          </div>
        ))
      )}
    </div>
  );
}

function TrustSection({
  title,
  items,
  empty,
  mode = 'memory',
}: {
  title: string;
  items: MemoryTrustItem[];
  empty: string;
  mode?: 'memory' | 'correction' | 'event';
}) {
  return (
    <div style={{ padding: 14, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)', display: 'grid', gap: 10, alignContent: 'start' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{title}</span>
        <Badge>{items.length}</Badge>
      </div>
      {items.length === 0 ? (
        <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)' }}>{empty}</p>
      ) : (
        items.slice(0, 5).map((item, index) => <TrustItemRow key={`${item.key || item.created_at || index}-${index}`} item={item} mode={mode} />)
      )}
    </div>
  );
}

function TrustItemRow({ item, mode }: { item: MemoryTrustItem; mode: 'memory' | 'correction' | 'event' }) {
  const title = item.key || item.type || item.action || '记忆';
  const detail =
    mode === 'correction'
      ? `${trustText(item.old_value)} -> ${trustText(item.new_value)}`
      : item.value || item.reason || item.new_value || '';
  const timestamp = item.updated_at || item.superseded_at || item.created_at;
  return (
    <div style={{ display: 'grid', gap: 5, paddingTop: 8, borderTop: '1px solid var(--border-subtle)' }}>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>{title}</span>
        {typeof item.confidence === 'number' && <Badge variant={item.confidence >= 0.85 ? 'success' : 'warning'}>{(item.confidence * 100).toFixed(0)}%</Badge>}
        {item.source && <Badge>{item.source}</Badge>}
        {item.action && <Badge variant="info">{item.action}</Badge>}
      </div>
      {detail && <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>{clipText(detail, 110)}</p>}
      {timestamp && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{trustDate(timestamp)}</span>}
    </div>
  );
}

function MemoryMaintenancePanel({
  memoryStats,
  dreamingStatus,
  dreamingDoctor,
  rebuildingVector,
  runningDreaming,
  doctoringDreaming,
  deletingDreaming,
  onRebuildVector,
  onRunDreaming,
  onDoctorDreaming,
  onDeleteDreaming,
  onClearAll,
}: {
  memoryStats: MemoryStats | null;
  dreamingStatus: DreamingStatusPayload | null;
  dreamingDoctor: DreamingDoctorPayload | null;
  rebuildingVector: boolean;
  runningDreaming: boolean;
  doctoringDreaming: boolean;
  deletingDreaming: boolean;
  onRebuildVector: () => void;
  onRunDreaming: () => void;
  onDoctorDreaming: () => void;
  onDeleteDreaming: () => void;
  onClearAll: () => void;
}) {
  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <Card style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}>
        <CardContent style={{ padding: 20, display: 'grid', gap: 12 }}>
          <div style={{ display: 'grid', gap: 6 }}>
            <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: 'var(--text-primary)' }}>维护工具只处理“怎么用记忆”</h2>
            <p style={{ margin: 0, fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
              这里放的是向量索引、梦境整理和整库清理。它们会影响召回、解释和维护流程，但不等于在直接编辑长期事实本身。
            </p>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10 }}>
            <ActionHint title="回复接不上刚才的话" target="工作记忆 / 日记忆" description="先去短期层排查，不要急着清空整库。" />
            <ActionHint title="长期把你记错了" target="语义记忆 / 情景记忆" description="先删具体事实或经历，再考虑重建索引。" />
            <ActionHint title="召回顺序很怪" target="重建向量索引" description="索引是派生层，重建比删真相源更安全。" />
            <ActionHint title="自动整理结果可疑" target="梦境整理" description="先看最近提升项和诊断结果，再决定是否回滚。" />
          </div>
        </CardContent>
      </Card>

      <Card style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}>
        <CardHeader style={{ paddingBottom: 8 }}>
          <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <Database style={{ width: 18, height: 18, color: 'var(--accent)' }} />
            向量索引
            <Badge variant={memoryStats?.embedding_enabled ? 'success' : 'default'}>
              {memoryStats?.embedding_enabled ? '已启用' : '未启用'}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent style={{ paddingTop: 0, display: 'grid', gap: 12 }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Badge>索引 {memoryStats?.vector_count ?? 0} 条</Badge>
            <Badge>目录 {formatMb(memoryStats?.vector_size_kb)}</Badge>
            {memoryStats?.daily_summary_count !== undefined && <Badge>日摘要 {memoryStats.daily_summary_count} 条</Badge>}
          </div>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            向量索引是召回辅助层，不是第二份记忆库。重建它适合解决“能记住但找不准”的问题，不适合解决“根本记错了”的问题。
          </p>
          <Button variant="secondary" size="sm" onClick={onRebuildVector} loading={rebuildingVector}>
            <RefreshCw style={{ width: 14, height: 14, marginRight: 4 }} />
            重建向量索引
          </Button>
        </CardContent>
      </Card>

      <Card style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}>
        <CardHeader style={{ paddingBottom: 8 }}>
          <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <Brain style={{ width: 18, height: 18, color: 'var(--accent)' }} />
            梦境整理
            <Badge variant={dreamingStatus?.enabled ? 'success' : 'default'}>
              {dreamingStatus?.enabled ? '已开启' : '未开启'}
            </Badge>
            <Badge>{dreamingStatus?.last_status || '暂无运行'}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent style={{ paddingTop: 0, display: 'grid', gap: 14 }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Badge>候选上限 {dreamingStatus?.max_candidates ?? 0}</Badge>
            <Badge>提升上限 {dreamingStatus?.max_promotions ?? 0}</Badge>
            <Badge>报告保留 {dreamingStatus?.report_retention ?? 0}</Badge>
            <Badge>{dreamingStatus?.auto_run_enabled ? '允许自动运行' : '仅手动运行'}</Badge>
          </div>
          <div style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>最近运行时间：{dreamingStatus?.last_run_at || '暂无'}</span>
            <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>最近错误：{dreamingStatus?.last_error || '无'}</span>
            <p style={{ margin: 0, fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.6 }}>
              {dreamingStatus?.latest_report?.user_summary || dreamingStatus?.last_summary || '最近还没有记忆整理报告。'}
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Button variant="secondary" size="sm" onClick={onRunDreaming} loading={runningDreaming}>
              <RefreshCw style={{ width: 14, height: 14, marginRight: 4 }} />
              立即整理一次
            </Button>
            <Button variant="secondary" size="sm" onClick={onDoctorDreaming} loading={doctoringDreaming}>
              <HelpCircle style={{ width: 14, height: 14, marginRight: 4 }} />
              诊断
            </Button>
            <Button variant="danger" size="sm" onClick={onDeleteDreaming} loading={deletingDreaming}>
              <Trash2 style={{ width: 14, height: 14, marginRight: 4 }} />
              删除最近整理新增项
            </Button>
          </div>
          {dreamingStatus?.latest_report?.promoted_items?.length ? (
            <div style={{ display: 'grid', gap: 8 }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>最近一次提升到长期层的内容</span>
              <div style={{ display: 'grid', gap: 8 }}>
                {dreamingStatus.latest_report.promoted_items.slice(0, 6).map((item) => (
                  <div key={item.candidate_id} style={{ padding: 10, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)' }}>
                    <div style={{ fontSize: 13, color: 'var(--text-primary)' }}>{item.summary}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                      来源 {item.source_layer} · 目标 {item.target_store || 'unknown'}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {dreamingStatus?.latest_report?.kept_short_term_items?.length ? (
            <div style={{ display: 'grid', gap: 8 }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>这次看过，但仍留在短期层的内容</span>
              <div style={{ display: 'grid', gap: 8 }}>
                {dreamingStatus.latest_report.kept_short_term_items.slice(0, 6).map((item) => (
                  <div key={item.candidate_id} style={{ padding: 10, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)' }}>
                    <div style={{ fontSize: 13, color: 'var(--text-primary)' }}>{item.summary}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                      来源 {item.source_layer} · {item.reason_tags?.join(' / ') || 'keep_short_term'}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {dreamingDoctor && (
            <div style={{ padding: 12, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)', display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                诊断结果：{dreamingDoctor.ok ? '正常' : '需要关注'}
              </span>
              {(dreamingDoctor.issues || []).map((issue) => (
                <span key={issue} style={{ fontSize: 12, color: 'var(--error)' }}>问题：{issue}</span>
              ))}
              {(dreamingDoctor.suggestions || []).map((item) => (
                <span key={item} style={{ fontSize: 12, color: 'var(--text-secondary)' }}>建议：{item}</span>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}>
        <CardHeader style={{ paddingBottom: 8 }}>
          <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Trash2 style={{ width: 18, height: 18, color: 'var(--error)' }} />
            高风险操作
          </CardTitle>
        </CardHeader>
        <CardContent style={{ paddingTop: 0, display: 'grid', gap: 10 }}>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            只有在确认整个 Bot 的记忆库都需要重置时，才建议使用清空全部。大多数情况下，按关键词删单条会更安全。
          </p>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Badge variant="info">优先删单条</Badge>
            <Badge>语义事实可删</Badge>
            <Badge>情景记忆可删</Badge>
            <Badge>工作/日记忆可删</Badge>
          </div>
          <Button variant="danger" size="sm" onClick={onClearAll}>
            <Trash2 style={{ width: 14, height: 14, marginRight: 4 }} />
            清空全部
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

export function Memory() {
  const { currentBotId } = useBotStore();
  const toast = useToast();

  const [activeTab, setActiveTab] = useState<MemoryTab>('overview');
  const [memoryStats, setMemoryStats] = useState<MemoryStats | null>(null);
  const [memoryTrust, setMemoryTrust] = useState<MemoryTrustPayload | null>(null);
  const [workingMemory, setWorkingMemory] = useState<Message[]>([]);
  const [dailyMemory, setDailyMemory] = useState<DailyMemoryPayload>({ messages: [], summaries: [] });
  const [episodicMemory, setEpisodicMemory] = useState<EpisodicItem[]>([]);
  const [semanticMemory, setSemanticMemory] = useState<SemanticMemory | null>(null);
  const [dreamingStatus, setDreamingStatus] = useState<DreamingStatusPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [rebuildingVector, setRebuildingVector] = useState(false);
  const [runningDreaming, setRunningDreaming] = useState(false);
  const [doctoringDreaming, setDoctoringDreaming] = useState(false);
  const [deletingDreaming, setDeletingDreaming] = useState(false);
  const [dreamingDoctor, setDreamingDoctor] = useState<DreamingDoctorPayload | null>(null);
  const [workingQuery, setWorkingQuery] = useState('');
  const [dailyQuery, setDailyQuery] = useState('');
  const [episodicQuery, setEpisodicQuery] = useState('');
  const [semanticQuery, setSemanticQuery] = useState('');

  const fetchAllData = useCallback(
    async (mode: 'initial' | 'refresh' = 'refresh') => {
      if (!currentBotId) return;
      if (mode === 'initial') {
        setLoading(true);
      } else {
        setRefreshing(true);
      }
      try {
        const [stats, trust, working, daily, episodic, semantic, dreaming] = await Promise.all([
          memoryApi.getStats(currentBotId),
          memoryApi.getTrust(currentBotId),
          memoryApi.getWorking(currentBotId),
          memoryApi.getDaily(currentBotId).catch((error) => {
            console.warn('Daily memory API unavailable:', error);
            return { messages: [], summaries: [] };
          }),
          memoryApi.getEpisodic(currentBotId),
          memoryApi.getSemantic(currentBotId),
          memoryApi.getDreamingStatus(currentBotId).catch(() => null),
        ]);
        setMemoryStats(stats);
        setMemoryTrust(trust);
        setWorkingMemory(working);
        setDailyMemory(daily);
        setEpisodicMemory(episodic);
        setSemanticMemory(semantic);
        setDreamingStatus(dreaming);
      } catch (err) {
        toast.error(`获取记忆数据失败: ${err}`);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [currentBotId, toast]
  );

  useEffect(() => {
    fetchAllData('initial');
  }, [fetchAllData]);

  const openDeleteModal = useCallback((target: DeleteTarget) => {
    setDeleteTarget(target);
    setDeleteModalOpen(true);
  }, []);

  const closeDeleteModal = useCallback(() => {
    if (deleting) return;
    setDeleteModalOpen(false);
    setDeleteTarget(null);
  }, [deleting]);

  const handleDeleteMemory = useCallback(async () => {
    if (!deleteTarget || !currentBotId) return;
    setDeleting(true);
    try {
      await memoryApi.deleteMemory(currentBotId, deleteTarget.type, deleteTarget.id);
      toast.success(`已删除${deleteTarget.label}`);
      closeDeleteModal();
      await fetchAllData('refresh');
    } catch (err) {
      toast.error(`删除记忆失败: ${err}`);
    } finally {
      setDeleting(false);
    }
  }, [closeDeleteModal, currentBotId, deleteTarget, fetchAllData, toast]);

  const handleClearAll = useCallback(async () => {
    if (!currentBotId) return;
    if (!confirm('确定要清空这个 Bot 的全部记忆吗？此操作不可恢复。')) return;
    try {
      await memoryApi.clearAll(currentBotId);
      toast.success('所有记忆已清空');
      await fetchAllData('refresh');
    } catch (err) {
      toast.error(`清空记忆失败: ${err}`);
    }
  }, [currentBotId, fetchAllData, toast]);

  const handleRebuildVector = useCallback(async () => {
    if (!currentBotId) return;
    setRebuildingVector(true);
    try {
      const result = await memoryApi.rebuildVector(currentBotId);
      const indexed = result.indexed ?? 0;
      const candidates = result.candidate_docs ?? indexed;
      toast.success(result.enabled ? `向量索引已重建：${indexed}/${candidates}` : '向量索引未启用');
      await fetchAllData('refresh');
    } catch (err) {
      toast.error(`向量索引重建失败: ${err}`);
    } finally {
      setRebuildingVector(false);
    }
  }, [currentBotId, fetchAllData, toast]);

  const handleRunDreaming = useCallback(async () => {
    if (!currentBotId) return;
    setRunningDreaming(true);
    try {
      await memoryApi.runDreaming(currentBotId);
      toast.success('记忆整理已执行');
      await fetchAllData('refresh');
    } catch (err) {
      toast.error(`记忆整理执行失败: ${err}`);
    } finally {
      setRunningDreaming(false);
    }
  }, [currentBotId, fetchAllData, toast]);

  const handleDoctorDreaming = useCallback(async () => {
    if (!currentBotId) return;
    setDoctoringDreaming(true);
    try {
      const result = await memoryApi.doctorDreaming(currentBotId);
      setDreamingDoctor(result);
      toast.success(result.ok ? '记忆整理状态正常' : '记忆整理需要关注');
    } catch (err) {
      toast.error(`记忆整理诊断失败: ${err}`);
    } finally {
      setDoctoringDreaming(false);
    }
  }, [currentBotId, toast]);

  const handleDeleteDreaming = useCallback(async () => {
    if (!currentBotId) return;
    setDeletingDreaming(true);
    try {
      const result = await memoryApi.deleteLatestDreaming(currentBotId);
      toast.success(result.ok ? '已删除最近一次整理新增的自动记忆' : (result.message || '没有可删除结果'));
      await fetchAllData('refresh');
    } catch (err) {
      toast.error(`删除最近整理结果失败: ${err}`);
    } finally {
      setDeletingDreaming(false);
    }
  }, [currentBotId, fetchAllData, toast]);

  const getImportanceStars = (importance: number) => {
    const stars = Math.max(0, Math.min(5, Math.round(importance * 5)));
    return (
      <div style={{ display: 'flex', gap: 2 }}>
        {[...Array(5)].map((_, i) => (
          <Star
            key={i}
            style={{
              width: 12,
              height: 12,
              color: i < stars ? 'var(--warning)' : 'var(--text-muted)',
              fill: i < stars ? 'var(--warning)' : 'none',
            }}
          />
        ))}
      </div>
    );
  };

  const workingItems = useMemo(
    () => workingMemory.filter((msg) => textIncludes(`${msg.role} ${msg.content}`, workingQuery)),
    [workingMemory, workingQuery]
  );

  const dailyItems = useMemo(
    () =>
      dailyMemory.messages.filter((msg) =>
        textIncludes(`${msg.role} ${msg.platform || ''} ${msg.content}`, dailyQuery)
      ),
    [dailyMemory.messages, dailyQuery]
  );

  const episodicItems = useMemo(
    () =>
      episodicMemory.filter((item) =>
        textIncludes(
          `${item.summary} ${item.content} ${item.recall_style || ''} ${parseList(item.cue_tags_json).join(' ')}`,
          episodicQuery
        )
      ),
    [episodicMemory, episodicQuery]
  );

  const semanticFacts = useMemo(
    () =>
      (semanticMemory?.facts || []).filter((fact) =>
        textIncludes(`${fact.key} ${fact.value} ${fact.category || ''} ${fact.source || ''}`, semanticQuery)
      ),
    [semanticMemory?.facts, semanticQuery]
  );

  const tabs: { key: MemoryTab; label: string; count?: number }[] = [
    { key: 'overview', label: '总览' },
    { key: 'working', label: '工作记忆', count: memoryStats?.working_count },
    { key: 'daily', label: '日记忆', count: memoryStats?.daily_count },
    { key: 'episodic', label: '情景记忆', count: memoryStats?.episodic_count },
    { key: 'semantic', label: '语义记忆', count: memoryStats?.semantic_count },
    { key: 'tools', label: '维护工具' },
  ];

  if (loading) {
    return (
      <div style={{ display: 'grid', gap: 16 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)' }}>记忆管理</h1>
        <div
          style={{
            height: 120,
            borderRadius: 8,
            backgroundColor: 'var(--bg-secondary)',
            border: '1px solid var(--border-subtle)',
          }}
        />
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ display: 'grid', gap: 6 }}>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)' }}>记忆管理</h1>
          <p style={{ fontSize: 14, color: 'var(--text-secondary)' }}>
            现在按“先看当前生效的记忆，再进对应层处理，最后才动维护工具”的顺序来组织，避免几十张卡片同时抢注意力。
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          {currentBotId && <Badge>{currentBotId}</Badge>}
          <Button variant="secondary" size="sm" onClick={() => fetchAllData('refresh')} loading={refreshing}>
            <RefreshCw style={{ width: 14, height: 14, marginRight: 4 }} />
            刷新
          </Button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 4, borderBottom: '1px solid var(--border-subtle)', overflowX: 'auto' }}>
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            style={{
              padding: '12px 20px',
              fontSize: 14,
              fontWeight: 500,
              border: 'none',
              backgroundColor: 'transparent',
              cursor: 'pointer',
              borderBottom: `2px solid ${activeTab === tab.key ? 'var(--accent)' : 'transparent'}`,
              color: activeTab === tab.key ? 'var(--accent)' : 'var(--text-secondary)',
              whiteSpace: 'nowrap',
            }}
          >
            {tab.label}
            {tab.count !== undefined && <Badge style={{ marginLeft: 8, fontSize: 11 }}>{tab.count}</Badge>}
          </button>
        ))}
      </div>

      {activeTab === 'overview' && (
        <div style={{ display: 'grid', gap: 16 }}>
          <MemoryOverviewPanel
            memoryStats={memoryStats}
            memoryTrust={memoryTrust}
            dreamingStatus={dreamingStatus}
            onSelectTab={setActiveTab}
            botId={currentBotId || ''}
          />

          {memoryStats && (
            <Card style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}>
              <CardHeader style={{ borderBottom: 'none', marginBottom: 0, padding: '16px 20px 8px' }}>
                <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Filter style={{ width: 16, height: 16, color: 'var(--text-secondary)' }} />
                  存量一眼看懂
                </CardTitle>
              </CardHeader>
              <CardContent style={{ padding: '8px 20px 20px', display: 'grid', gap: 12 }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
                  {[
                    { label: '工作记忆', value: memoryStats.working_count, tone: 'var(--accent)' },
                    { label: '日记忆', value: memoryStats.daily_count ?? 0, tone: 'var(--success)' },
                    { label: '情景记忆', value: memoryStats.episodic_count, tone: 'var(--warning)' },
                    { label: '语义记忆', value: memoryStats.semantic_count, tone: 'var(--info)' },
                  ].map((item) => (
                    <div key={item.label} style={{ padding: 14, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)', display: 'grid', gap: 4 }}>
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{item.label}</span>
                      <span style={{ fontSize: 24, fontWeight: 700, color: item.tone }}>{item.value}</span>
                    </div>
                  ))}
                </div>
                <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                  如果你是为了清理“长期记错”，优先看语义记忆和情景记忆；如果只是最近几轮没接住，优先看工作记忆和日记忆。
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {activeTab === 'working' && (
        <div style={{ display: 'grid', gap: 16 }}>
          <LayerHint
            title="当前与短期：Working"
            badges={['当前会话', '短期上下文']}
            description="这里是当前会话的原始对话和压缩摘要，只影响最近几轮的承接，不是长期记忆真相。"
          />
          <SearchBar
            value={workingQuery}
            onChange={setWorkingQuery}
            placeholder="搜索工作记忆内容，比如某句误记住的话"
            resultCount={workingItems.length}
          />
          <MemoryListCard
            emptyIcon={<Clock style={{ width: 48, height: 48, color: 'var(--text-muted)', opacity: 0.5 }} />}
            emptyText={workingQuery ? '没有匹配到工作记忆' : '工作记忆为空'}
          >
            {workingItems.map((msg) => (
              <MessageRow
                key={msg.id}
                role={msg.role}
                content={msg.content}
                createdAt={msg.created_at}
                onDelete={() =>
                  openDeleteModal({
                    type: 'working',
                    id: msg.id,
                    label: '这条工作记忆',
                    detail: clipText(msg.content),
                  })
                }
              />
            ))}
          </MemoryListCard>
        </div>
      )}

      {activeTab === 'daily' && (
        <div style={{ display: 'grid', gap: 16 }}>
          <LayerHint
            title="当前与短期：Daily"
            badges={['跨通道短期连续性', '今日上下文']}
            description="这里是最近几天的连续性和未完成线索，用来让 Bot 在不同会话和通道之间不至于立刻失忆。"
          />
          <Card style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: 8, border: '1px solid var(--border-subtle)' }}>
            <CardHeader style={{ borderBottom: 'none', padding: '16px 20px' }}>
              <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <CalendarDays style={{ width: 18, height: 18, color: 'var(--success)' }} />
                最近十天摘要
              </CardTitle>
            </CardHeader>
            <CardContent style={{ padding: '0 20px 20px', display: 'grid', gap: 12 }}>
              {dailyMemory.summaries.length === 0 ? (
                <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>暂无日记忆摘要</p>
              ) : (
                dailyMemory.summaries.map((summary) => {
                  const topics = parseList(summary.topics_json);
                  const openThreads = parseList(summary.open_threads_json);
                  return (
                    <div key={summary.id} style={{ padding: 14, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 8 }}>
                        <Badge variant="success">{summary.local_date}</Badge>
                        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{summary.message_count ?? 0} 条</span>
                      </div>
                      <p style={{ fontSize: 14, color: 'var(--text-primary)', marginBottom: 8 }}>{summary.summary}</p>
                      {(topics.length > 0 || openThreads.length > 0) && (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                          {topics.slice(0, 4).map((topic) => (
                            <Badge key={`topic-${summary.id}-${topic}`} variant="info">
                              {topic}
                            </Badge>
                          ))}
                          {openThreads.slice(0, 3).map((thread) => (
                            <Badge key={`thread-${summary.id}-${thread}`}>{thread}</Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </CardContent>
          </Card>

          <SearchBar
            value={dailyQuery}
            onChange={setDailyQuery}
            placeholder="搜索日记忆流水"
            resultCount={dailyItems.length}
          />

          <MemoryListCard
            emptyIcon={<CalendarDays style={{ width: 48, height: 48, color: 'var(--text-muted)', opacity: 0.5 }} />}
            emptyText={dailyQuery ? '没有匹配到日记忆流水' : '日记忆流水为空'}
          >
            {dailyItems.map((msg) => (
              <MessageRow
                key={msg.id}
                role={msg.role}
                content={msg.content}
                createdAt={msg.created_at}
                platform={msg.platform || undefined}
                onDelete={() =>
                  openDeleteModal({
                    type: 'daily',
                    id: msg.id,
                    label: '这条日记忆',
                    detail: clipText(msg.content),
                  })
                }
              />
            ))}
          </MemoryListCard>
        </div>
      )}

      {activeTab === 'episodic' && (
        <div style={{ display: 'grid', gap: 16 }}>
          <LayerHint
            title="长期与关系：Episodic"
            badges={['共同经历真相源', '长期情景记忆']}
            description="这里保存的是值得长期记住的共同经历、冲突和和解、承诺与关键时刻。它属于长期真相源，不是临时投影。"
          />
          <SearchBar
            value={episodicQuery}
            onChange={setEpisodicQuery}
            placeholder="搜索情景记忆摘要、正文或标签"
            resultCount={episodicItems.length}
          />
          <MemoryListCard
            emptyIcon={<Brain style={{ width: 48, height: 48, color: 'var(--text-muted)', opacity: 0.5 }} />}
            emptyText={episodicQuery ? '没有匹配到情景记忆' : '情景记忆为空'}
          >
            {episodicItems.map((item) => {
              const cueTags = parseList(item.cue_tags_json);
              const topics = parseList(item.topics_json);
              const emotionTags = parseList(item.emotion_tags_json);
              return (
                <div key={item.id} style={{ padding: 16, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, marginBottom: 8 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      {getImportanceStars(item.importance)}
                      {typeof item.confidence === 'number' && <Badge variant="info">置信度 {(item.confidence * 100).toFixed(0)}%</Badge>}
                      {item.relationship_effect && item.relationship_effect !== '普通' && (
                        <Badge variant="warning">{item.relationship_effect}</Badge>
                      )}
                      {item.sensitivity === 'sensitive' && <Badge variant="error">敏感</Badge>}
                      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                        {new Date(item.created_at).toLocaleDateString('zh-CN')}
                      </span>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() =>
                        openDeleteModal({
                          type: 'episodic',
                          id: item.id,
                          label: '这条情景记忆',
                          detail: clipText(item.summary || item.content),
                        })
                      }
                      style={{ padding: 4 }}
                    >
                      <Trash2 style={{ width: 14, height: 14 }} />
                    </Button>
                  </div>
                  <p style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>{item.summary}</p>
                  <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{item.content}</p>
                  {(cueTags.length > 0 || topics.length > 0 || emotionTags.length > 0 || item.recall_style) && (
                    <div style={{ display: 'grid', gap: 8, marginTop: 10 }}>
                      {(cueTags.length > 0 || topics.length > 0 || emotionTags.length > 0) && (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                          {cueTags.slice(0, 5).map((tag) => (
                            <Badge key={`cue-${item.id}-${tag}`}>{tag}</Badge>
                          ))}
                          {topics.slice(0, 3).map((topic) => (
                            <Badge key={`topic-${item.id}-${topic}`} variant="info">
                              {topic}
                            </Badge>
                          ))}
                          {emotionTags.slice(0, 3).map((tag) => (
                            <Badge key={`emotion-${item.id}-${tag}`} variant="success">
                              {tag}
                            </Badge>
                          ))}
                        </div>
                      )}
                      {item.recall_style && (
                        <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>使用方式：{item.recall_style}</p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </MemoryListCard>
        </div>
      )}

      {activeTab === 'semantic' && semanticMemory && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <LayerHint
            title="长期与关系：Semantic / Relationship"
            badges={['结构化真相源', '长期事实', '关系状态']}
            description="这里包含结构化用户事实和长期关系状态。它们是长期真相源；而“长期理解投影”是从这些真相里整理出来的派生表达层。"
          />
          <Card style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: 8, border: '1px solid var(--border-subtle)' }}>
            <CardHeader style={{ borderBottom: 'none', padding: '16px 20px' }}>
                <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Heart style={{ width: 18, height: 18, color: 'var(--error)' }} />
                长期关系状态
                </CardTitle>
              </CardHeader>
            <CardContent style={{ padding: '16px 20px' }}>
              <div style={{ display: 'grid', gap: 18 }}>
                {(() => {
                  const relationship = semanticMemory.relationship_state ?? {};
                  const score = scoreValue(relationship.relationship_score ?? semanticMemory.attitude_score);
                  return (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap' }}>
                      <div style={{ textAlign: 'center' }}>
                        <div style={{ fontSize: 36, fontWeight: 700, color: 'var(--accent)' }}>{score.toFixed(0)}</div>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>综合关系温度 / 100</div>
                      </div>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                        <Badge variant="success" style={{ fontSize: 14, padding: '6px 12px' }}>
                          {relationship.relationship_label ?? semanticMemory.relationship_level}
                        </Badge>
                        {relationship.relationship_status && relationship.relationship_status !== '稳定' && (
                          <Badge variant="warning" style={{ fontSize: 14, padding: '6px 12px' }}>
                            {relationship.relationship_status}
                          </Badge>
                        )}
                        {typeof relationship.stage_confidence === 'number' && (
                          <Badge>稳定度 {(relationship.stage_confidence * 100).toFixed(0)}%</Badge>
                        )}
                      </div>
                    </div>
                  );
                })()}
                {(() => {
                  const relationship = semanticMemory.relationship_state ?? {};
                  return (
                    <div style={{ display: 'grid', gap: 14 }}>
                      {(relationship.relationship_narrative || relationship.current_posture || relationship.interaction_guidance) && (
                        <div style={{ display: 'grid', gap: 8, padding: 14, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)' }}>
                          {relationship.relationship_narrative && <p style={{ fontSize: 14, color: 'var(--text-primary)' }}>{relationship.relationship_narrative}</p>}
                          {relationship.current_posture && <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>当前姿态：{relationship.current_posture}</p>}
                          {relationship.interaction_guidance && <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>互动建议：{relationship.interaction_guidance}</p>}
                        </div>
                      )}
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 14 }}>
                        <RelationshipMetric label="亲密" value={scoreValue(relationship.intimacy_score)} tone="var(--accent)" />
                        <RelationshipMetric label="信任" value={scoreValue(relationship.trust_score)} tone="var(--success)" />
                        <RelationshipMetric
                          label="心动/好感"
                          value={scoreValue(relationship.affection_score ?? relationship.attitude_score)}
                          tone="var(--error)"
                        />
                        <RelationshipMetric label="紧张" value={scoreValue(relationship.tension_score)} tone="var(--warning)" />
                      </div>
                    </div>
                  );
                })()}
              </div>
            </CardContent>
          </Card>

          <SearchBar
            value={semanticQuery}
            onChange={setSemanticQuery}
            placeholder="搜索语义事实 key 或 value"
            resultCount={semanticFacts.length}
          />

          <Card style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: 8, border: '1px solid var(--border-subtle)' }}>
            <CardHeader style={{ borderBottom: 'none', padding: '16px 20px' }}>
              <CardTitle>结构化用户事实</CardTitle>
            </CardHeader>
            <CardContent style={{ padding: '0 20px 20px' }}>
              {semanticFacts.length === 0 ? (
                <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                  {semanticQuery ? '没有匹配到语义事实' : '暂无用户画像'}
                </p>
              ) : (
                <div style={{ display: 'grid', gap: 12 }}>
                  <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)' }}>
                    这里展示的是长期事实真相源，不等于“用户长期理解投影”。后者是给系统投影和给用户编辑的派生层。
                  </p>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
                  {semanticFacts.map((fact) => (
                    <SemanticFactCard
                      key={fact.key}
                      fact={fact}
                      onDelete={() =>
                        openDeleteModal({
                          type: 'semantic',
                          id: fact.key,
                          label: `语义事实「${fact.key}」`,
                          detail: clipText(fact.value),
                        })
                      }
                    />
                  ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === 'tools' && (
        <MemoryMaintenancePanel
          memoryStats={memoryStats}
          dreamingStatus={dreamingStatus}
          dreamingDoctor={dreamingDoctor}
          rebuildingVector={rebuildingVector}
          runningDreaming={runningDreaming}
          doctoringDreaming={doctoringDreaming}
          deletingDreaming={deletingDreaming}
          onRebuildVector={handleRebuildVector}
          onRunDreaming={handleRunDreaming}
          onDoctorDreaming={handleDoctorDreaming}
          onDeleteDreaming={handleDeleteDreaming}
          onClearAll={handleClearAll}
        />
      )}

      <Modal isOpen={deleteModalOpen} onClose={closeDeleteModal} title="确认删除">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <p style={{ color: 'var(--text-secondary)', margin: 0 }}>
            确定要删除{deleteTarget?.label || '这条记忆'}吗？此操作不可恢复。
          </p>
          {deleteTarget?.detail && (
            <div
              style={{
                padding: 12,
                borderRadius: 8,
                backgroundColor: 'var(--bg-tertiary)',
                border: '1px solid var(--border-subtle)',
                fontSize: 13,
                color: 'var(--text-secondary)',
                lineHeight: 1.6,
              }}
            >
              {deleteTarget.detail}
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <Button variant="secondary" onClick={closeDeleteModal} disabled={deleting}>
              取消
            </Button>
            <Button variant="danger" onClick={handleDeleteMemory} loading={deleting}>
              确认删除
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

function ActionHint({
  title,
  target,
  description,
}: {
  title: string;
  target: string;
  description: string;
}) {
  return (
    <div style={{ padding: 12, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)', display: 'grid', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{title}</span>
        <Badge variant="info">{target}</Badge>
      </div>
      <p style={{ margin: 0, fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{description}</p>
    </div>
  );
}

function SearchBar({
  value,
  onChange,
  placeholder,
  resultCount,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  resultCount: number;
}) {
  return (
    <Card style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}>
      <CardContent style={{ padding: 16, display: 'grid', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Search style={{ width: 15, height: 15, color: 'var(--text-secondary)' }} />
          <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>搜索并筛选</span>
          <Badge style={{ marginLeft: 'auto' }}>{resultCount} 条</Badge>
        </div>
        <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
      </CardContent>
    </Card>
  );
}

function MemoryListCard({
  children,
  emptyIcon,
  emptyText,
}: {
  children: React.ReactNode;
  emptyIcon: React.ReactNode;
  emptyText: string;
}) {
  const isEmpty = Array.isArray(children) && children.length === 0;
  return (
    <Card style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: 8, border: '1px solid var(--border-subtle)' }}>
      <CardContent style={{ padding: isEmpty ? '48px 0' : 16 }}>
        {isEmpty ? (
          <div style={{ textAlign: 'center' }}>
            <div style={{ marginBottom: 16 }}>{emptyIcon}</div>
            <p style={{ color: 'var(--text-muted)' }}>{emptyText}</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>{children}</div>
        )}
      </CardContent>
    </Card>
  );
}

function MessageRow({
  role,
  content,
  createdAt,
  platform,
  onDelete,
}: {
  role: string;
  content: string;
  createdAt: string;
  platform?: string;
  onDelete: () => void;
}) {
  return (
    <div style={{ padding: 12, borderRadius: 8, backgroundColor: role === 'user' ? 'var(--accent-light)' : 'var(--bg-tertiary)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
        <Badge variant={role === 'user' ? 'info' : 'default'}>{role === 'user' ? '用户' : 'Bot'}</Badge>
        {platform && <Badge>{platform}</Badge>}
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{new Date(createdAt).toLocaleString('zh-CN')}</span>
        <Button variant="ghost" size="sm" onClick={onDelete} style={{ marginLeft: 'auto', padding: 4 }}>
          <Trash2 style={{ width: 14, height: 14 }} />
        </Button>
      </div>
      <p style={{ fontSize: 13, color: 'var(--text-primary)', margin: 0 }}>{content}</p>
    </div>
  );
}

function SemanticFactCard({ fact, onDelete }: { fact: Fact; onDelete: () => void }) {
  return (
    <div style={{ padding: 12, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)', display: 'grid', gap: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{fact.key}</div>
        <Button variant="ghost" size="sm" onClick={onDelete} style={{ padding: 4 }}>
          <Trash2 style={{ width: 14, height: 14 }} />
        </Button>
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {fact.category && <Badge variant="info">{fact.category}</Badge>}
        {typeof fact.confidence === 'number' && <Badge>{(fact.confidence * 100).toFixed(0)}%</Badge>}
        {fact.source && <Badge>{fact.source}</Badge>}
      </div>
      <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)' }}>{fact.value}</div>
      <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>更新于 {new Date(fact.updated_at).toLocaleDateString('zh-CN')}</div>
    </div>
  );
}
