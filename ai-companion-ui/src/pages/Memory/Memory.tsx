import { useCallback, useEffect, useMemo, useState } from 'react';
import { Archive, Brain, CalendarDays, CheckCircle2, Clock, Database, Filter, Heart, HelpCircle, Link2, RefreshCw, Search, Star, Trash2, User } from 'lucide-react';
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, Modal, useToast } from '../../components/ui';
import { memoryApi } from '../../api';
import { useBotStore } from '../../stores';
import type { DailyMemoryPayload, DreamingDoctorPayload, DreamingStatusPayload, EpisodicItem, Fact, MemoryStats, MemoryTrustItem, MemoryTrustPayload, Message, SemanticMemory, SessionStateItem } from '../../types';

type MemoryTab = 'stats' | 'working' | 'daily' | 'episodic' | 'semantic';
type MemoryDeleteType = 'working' | 'daily' | 'episodic' | 'semantic';

interface DeleteTarget {
  type: MemoryDeleteType;
  id: string;
  label: string;
  detail?: string;
}

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

function MemoryTrustPanel({ payload }: { payload: MemoryTrustPayload | null }) {
  const view = payload?.memory_trust_view || {};
  const sessionStates = sessionStateItems(payload?.session_state ?? (view as { session_state?: SessionStateItem[] }).session_state);
  const recently = trustItems(view.recently_remembered);
  const stable = trustItems(view.stable_understanding);
  const pending = trustItems(view.pending_confirmation);
  const corrected = trustItems(view.corrected_memories);
  const archived = trustItems(view.archived_or_suppressed);
  const relationship = view.relationship_anchor || {};
  const openThreads = Array.isArray(view.open_threads) ? view.open_threads : [];
  const commitments = Array.isArray(view.commitments) ? view.commitments : [];
  const hasRelationship = Boolean(relationship.label || relationship.status || relationship.narrative || relationship.guidance);

  return (
    <Card style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}>
      <CardHeader style={{ borderBottom: 'none', marginBottom: 0, padding: '16px 20px 8px' }}>
        <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Brain style={{ width: 18, height: 18, color: 'var(--accent)' }} />
          记忆可信视图
          {payload?.user_id && <Badge>{payload.user_id}</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent style={{ padding: '8px 20px 20px', display: 'grid', gap: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
          <TrustSummary icon={<Clock size={16} />} label="最近记住" value={recently.length} tone="var(--accent)" />
          <TrustSummary icon={<CheckCircle2 size={16} />} label="稳定理解" value={stable.length} tone="var(--success)" />
          <TrustSummary icon={<HelpCircle size={16} />} label="待确认" value={pending.length} tone="var(--warning)" />
          <TrustSummary icon={<Archive size={16} />} label="已纠正/归档" value={corrected.length + archived.length} tone="var(--info)" />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
          <SessionStateSection items={sessionStates} />
          <TrustSection title="最近会自然想起" items={recently} empty="暂无最近激活的记忆" />
          <TrustSection title="稳定用户理解" items={stable} empty="暂无高置信用户事实" />
          <TrustSection title="需要继续确认" items={pending} empty="暂无低置信待确认事实" />
        </div>

        {hasRelationship && (
          <div style={{ padding: 14, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)', display: 'grid', gap: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <Heart style={{ width: 16, height: 16, color: 'var(--error)' }} />
              <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>关系锚点</span>
              {relationship.label && <Badge variant="success">{relationship.label}</Badge>}
              {relationship.status && <Badge>{relationship.status}</Badge>}
              {typeof relationship.score === 'number' && <Badge variant="info">{relationship.score.toFixed(0)}</Badge>}
            </div>
            {relationship.narrative && <p style={{ margin: 0, fontSize: 13, color: 'var(--text-primary)' }}>{relationship.narrative}</p>}
            {relationship.guidance && <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)' }}>{relationship.guidance}</p>}
          </div>
        )}

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
            <TrustSection title="已纠正的事实" items={corrected} empty="暂无纠正记录" mode="correction" />
            <TrustSection title="已归档或抑制" items={archived} empty="暂无归档记录" mode="event" />
          </div>
        )}
      </CardContent>
    </Card>
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

function TrustSummary({ icon, label, value, tone }: { icon: React.ReactNode; label: string; value: number; tone: string }) {
  return (
    <div style={{ padding: 14, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)', display: 'flex', alignItems: 'center', gap: 12 }}>
      <div style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: `${tone}18`, color: tone, display: 'grid', placeItems: 'center', flex: '0 0 auto' }}>
        {icon}
      </div>
      <div>
        <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1 }}>{value}</div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>{label}</div>
      </div>
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

export function Memory() {
  const { currentBotId } = useBotStore();
  const toast = useToast();

  const [activeTab, setActiveTab] = useState<MemoryTab>('stats');
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
    { key: 'stats', label: '统计概览' },
    { key: 'working', label: '工作记忆', count: memoryStats?.working_count },
    { key: 'daily', label: '日记忆', count: memoryStats?.daily_count },
    { key: 'episodic', label: '情景记忆', count: memoryStats?.episodic_count },
    { key: 'semantic', label: '语义记忆', count: memoryStats?.semantic_count },
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
            这里不只是“看记忆列表”，而是整个记忆系统的操作与解释中心：你可以区分当前/短期、长期/关系、索引/投影，以及整理/诊断这几类能力。
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Button variant="secondary" size="sm" onClick={() => fetchAllData('refresh')} loading={refreshing}>
            <RefreshCw style={{ width: 14, height: 14, marginRight: 4 }} />
            刷新
          </Button>
          <Button variant="secondary" size="sm" onClick={handleRebuildVector} loading={rebuildingVector}>
            <Database style={{ width: 14, height: 14, marginRight: 4 }} />
            重建向量索引
          </Button>
          <Button variant="danger" size="sm" onClick={handleClearAll}>
            <Trash2 style={{ width: 14, height: 14, marginRight: 4 }} />
            清空全部
          </Button>
        </div>
      </div>

      <MemoryTrustPanel payload={memoryTrust} />

      {dreamingStatus && (
        <Card style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}>
          <CardHeader style={{ paddingBottom: 8 }}>
            <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Brain style={{ width: 18, height: 18, color: 'var(--accent)' }} />
              记忆整理 / 梦境
              <Badge variant={dreamingStatus.enabled ? 'success' : 'default'}>
                {dreamingStatus.enabled ? '已开启' : '未开启'}
              </Badge>
              <Badge>{dreamingStatus.last_status || '暂无运行'}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent style={{ paddingTop: 0, display: 'grid', gap: 14 }}>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <Badge>候选上限 {dreamingStatus.max_candidates}</Badge>
              <Badge>提升上限 {dreamingStatus.max_promotions}</Badge>
              <Badge>报告保留 {dreamingStatus.report_retention}</Badge>
              <Badge>{dreamingStatus.auto_run_enabled ? '允许自动运行' : '仅手动运行'}</Badge>
            </div>
            <div style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>最近运行时间：{dreamingStatus.last_run_at || '暂无'}</span>
              <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>最近错误：{dreamingStatus.last_error || '无'}</span>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.6 }}>
                {dreamingStatus.latest_report?.user_summary || dreamingStatus.last_summary || '最近还没有记忆整理报告。'}
              </p>
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <Button variant="secondary" size="sm" onClick={handleRunDreaming} loading={runningDreaming}>
                <RefreshCw style={{ width: 14, height: 14, marginRight: 4 }} />
                立即整理一次
              </Button>
              <Button variant="secondary" size="sm" onClick={handleDoctorDreaming} loading={doctoringDreaming}>
                <HelpCircle style={{ width: 14, height: 14, marginRight: 4 }} />
                诊断
              </Button>
              <Button variant="danger" size="sm" onClick={handleDeleteDreaming} loading={deletingDreaming}>
                <Trash2 style={{ width: 14, height: 14, marginRight: 4 }} />
                删除最近整理新增项
              </Button>
            </div>
            {dreamingStatus.latest_report?.promoted_items?.length ? (
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
      )}

      <Card style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}>
        <CardContent style={{ padding: 16, display: 'grid', gap: 12 }}>
          <div style={{ display: 'grid', gap: 8 }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>如何理解这一页</span>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <Badge variant="info">当前与短期：工作记忆、日记忆</Badge>
              <Badge>长期与关系：语义、情景、关系状态</Badge>
              <Badge>索引与投影：向量索引、用户长期理解投影</Badge>
              <Badge>整理与解释：梦境整理、记忆可信视图、诊断</Badge>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <Badge variant="info">可编辑</Badge>
            <Badge>工作记忆可删</Badge>
            <Badge>日记忆可删</Badge>
            <Badge>情景记忆可删</Badge>
            <Badge>语义事实可删</Badge>
          </div>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)' }}>
            建议先在对应页签里搜关键词，再删单条。这样比整库清空安全得多，也更符合“结构化真相源 + 派生解释层”的设计。
          </p>
        </CardContent>
      </Card>

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

      {activeTab === 'stats' && memoryStats && (
        <div style={{ display: 'grid', gap: 16 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
            <LayerHint
              title="当前与短期"
              badges={['Working', 'Daily']}
              description="这一层负责当前会话和最近连续性。它决定 Bot 能不能接住你刚才说的话，不等于长期记忆。"
            />
            <LayerHint
              title="长期与关系"
              badges={['Semantic', 'Episodic', 'Relationship']}
              description="这一层是长期真相源，保存稳定事实、共同经历和关系状态。删这里，才是在真正改 Bot 的长期记忆。"
            />
            <LayerHint
              title="索引与投影"
              badges={['Vector Index', 'Understanding Projection']}
              description="这一层是派生层：帮助系统召回和表达，不是第二份真相源。索引可重建，长期理解投影可手动校准。"
            />
            <LayerHint
              title="整理与解释"
              badges={['Dreaming', 'Trust View', 'Doctor']}
              description="这一层不负责存真相，而是负责整理、解释、诊断和纠错，让系统行为更可见。"
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
            {[
              { label: '工作记忆', value: memoryStats.working_count, icon: Clock, color: 'var(--accent)', size: memoryStats.working_size_kb },
              { label: '日记忆', value: memoryStats.daily_count ?? 0, icon: CalendarDays, color: 'var(--success)', size: memoryStats.daily_size_kb ?? 0 },
              { label: '情景记忆', value: memoryStats.episodic_count, icon: Brain, color: 'var(--warning)', size: memoryStats.episodic_size_kb },
              { label: '语义记忆', value: memoryStats.semantic_count, icon: User, color: 'var(--info)', size: memoryStats.semantic_size_kb },
              { label: '向量索引', value: memoryStats.vector_count ?? 0, icon: Database, color: 'var(--accent)', size: memoryStats.vector_size_kb ?? 0 },
            ].map((item) => (
              <Card key={item.label} style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: 8, border: '1px solid var(--border-subtle)' }}>
                <CardContent style={{ padding: 20, display: 'flex', alignItems: 'center', gap: 16 }}>
                  <div style={{ padding: 12, borderRadius: 8, backgroundColor: `${item.color}15` }}>
                    <item.icon style={{ width: 24, height: 24, color: item.color }} />
                  </div>
                  <div>
                    <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.2 }}>{item.value}</div>
                    <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>{item.label}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{(item.size / 1024).toFixed(2)} MB</div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          <Card style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}>
            <CardContent style={{ padding: 16, display: 'grid', gap: 8 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <Filter style={{ width: 14, height: 14, color: 'var(--text-secondary)' }} />
                <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>记忆系统分层提示</span>
              </div>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)' }}>
                如果你是为了“手动删脏记忆”，优先看“语义记忆”和“情景记忆”；前者是结构化事实真相，后者是共同经历真相。工作记忆和日记忆更偏当前/短期连续性。
              </p>
            </CardContent>
          </Card>

          <Card style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}>
            <CardContent style={{ padding: 16, display: 'grid', gap: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <Database style={{ width: 16, height: 16, color: 'var(--accent)' }} />
                  <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>统一向量索引（派生层）</span>
                  <Badge variant={memoryStats.embedding_enabled ? 'success' : 'default'}>
                    {memoryStats.embedding_enabled ? '已启用' : '未启用'}
                  </Badge>
                </div>
                <Button variant="secondary" size="sm" onClick={handleRebuildVector} loading={rebuildingVector}>
                  <RefreshCw style={{ width: 14, height: 14, marginRight: 4 }} />
                  重建
                </Button>
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <Badge>索引 {memoryStats.vector_count ?? 0} 条</Badge>
                <Badge>目录 {((memoryStats.vector_size_kb ?? 0) / 1024).toFixed(2)} MB</Badge>
                {memoryStats.daily_summary_count !== undefined && <Badge>日摘要 {memoryStats.daily_summary_count} 条</Badge>}
              </div>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)' }}>
                这是召回索引，不是第二份记忆库。索引来源包含语义事实、用户长期理解投影、关系脉络、日摘要和 Bot 人生轨迹；结构化数据库仍是事实源。
              </p>
            </CardContent>
          </Card>
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
