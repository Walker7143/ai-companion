import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRightLeft,
  Brain,
  Clock3,
  Eye,
  Filter,
  GitCommitHorizontal,
  RefreshCw,
  Sparkles,
  TrendingUp,
  Wand2,
} from 'lucide-react';
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, EmptyState, Select, useToast } from '../../components/ui';
import { useBotStore, useEvolutionStore } from '../../stores';
import type { EvolutionTimelineItem, PromotionCandidateView } from '../../types';

const POLL_INTERVAL_MS = 10_000;

const dimensionOptions = [
  { value: 'all', label: '全部维度' },
  { value: 'backstory', label: '经历' },
  { value: 'personality', label: '性格' },
  { value: 'speaking_style', label: '说话风格' },
  { value: 'values', label: '价值观' },
  { value: 'relationship', label: '关系' },
];

const statusOptions = [
  { value: 'all', label: '全部状态' },
  { value: 'promoted', label: '已晋升' },
  { value: 'suppressed', label: '被抑制' },
  { value: 'runtime', label: '仅 runtime' },
];

function formatDateTime(value?: string) {
  if (!value) return '暂无';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN');
}

function renderJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

function statusTone(status: string) {
  if (status === 'promoted') return 'success';
  if (status === 'suppressed') return 'warning';
  if (status === 'runtime') return 'info';
  return 'default';
}

function eventLabel(item: EvolutionTimelineItem) {
  const mapping: Record<string, string> = {
    signal_captured: 'Signal 捕获',
    reflection_generated: '反思生成',
    promotion_suppressed: '晋升抑制',
    core_patch_applied: 'Core Patch',
    state_rebuilt: '状态回建',
  };
  return mapping[item.event_type] || item.event_type;
}

function snapshotTag(label: string, tone: 'default' | 'success' | 'warning' | 'info' = 'default') {
  return <Badge variant={tone}>{label}</Badge>;
}

function OverviewMetric({
  title,
  value,
  icon,
  accent,
}: {
  title: string;
  value: string | number;
  icon: React.ReactNode;
  accent: string;
}) {
  return (
    <div
      style={{
        padding: 16,
        borderRadius: 12,
        border: '1px solid var(--border-subtle)',
        background: 'var(--bg-secondary)',
        display: 'grid',
        gap: 10,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{title}</span>
        <div
          style={{
            width: 34,
            height: 34,
            borderRadius: 10,
            display: 'grid',
            placeItems: 'center',
            backgroundColor: `${accent}18`,
            color: accent,
          }}
        >
          {icon}
        </div>
      </div>
      <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)' }}>{value}</div>
    </div>
  );
}

function PendingCard({
  item,
  acting,
  onApply,
  onReject,
}: {
  item: PromotionCandidateView;
  acting: boolean;
  onApply: (candidateId: string) => void;
  onReject: (candidateId: string) => void;
}) {
  return (
    <div
      style={{
        padding: 14,
        borderRadius: 10,
        border: '1px solid var(--border-subtle)',
        backgroundColor: 'var(--bg-tertiary)',
        display: 'grid',
        gap: 8,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{item.field_path}</div>
        <Badge variant="warning">{item.status}</Badge>
      </div>
      <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{item.summary}</div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        支持信号 {item.support_count} 条，跨 {item.window_count} 个反思窗口
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{item.promotion_reason}</div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Button size="sm" onClick={() => onApply(item.id)} disabled={acting}>
          批准
        </Button>
        <Button size="sm" variant="secondary" onClick={() => onReject(item.id)} disabled={acting}>
          拒绝
        </Button>
      </div>
    </div>
  );
}

export function Evolution() {
  const { currentBotId } = useBotStore();
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const {
    summary,
    timeline,
    selectedEvent,
    stateView,
    loading,
    refreshing,
    loadingDetail,
    loadingState,
    acting,
    error,
    timelineError,
    detailError,
    nextCursor,
    hasMore,
    filters,
    setFilters,
    fetchOverview,
    fetchTimeline,
    fetchEventDetail,
    fetchStateView,
    reflect,
    rebuild,
    applyPromotion,
    rejectPromotion,
    clearSelection,
  } = useEvolutionStore();
  const selectedEventIdFromQuery = searchParams.get('event') || '';

  const loadAll = async () => {
    if (!currentBotId) return;
    try {
      await Promise.all([
        fetchOverview(currentBotId),
        fetchTimeline(currentBotId),
        fetchStateView(currentBotId),
      ]);
    } catch (err) {
      toast.error(`加载人格演化失败：${err}`);
    }
  };

  useEffect(() => {
    loadAll();
  }, [currentBotId]);

  useEffect(() => {
    if (!currentBotId) return;
    const timer = window.setInterval(() => {
      fetchOverview(currentBotId).catch(() => undefined);
      fetchTimeline(currentBotId).catch(() => undefined);
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [currentBotId, filters.dimension, filters.status]);

  useEffect(() => {
    if (!currentBotId) return;
    fetchTimeline(currentBotId).catch((err) => {
      toast.error(`刷新时间线失败：${err}`);
    });
  }, [currentBotId, filters.dimension, filters.status]);

  useEffect(() => {
    if (!currentBotId || !selectedEventIdFromQuery) return;
    if (selectedEvent?.id === selectedEventIdFromQuery) return;
    fetchEventDetail(currentBotId, selectedEventIdFromQuery).catch((err) => {
      toast.error(`加载演化详情失败：${err}`);
    });
  }, [currentBotId, selectedEventIdFromQuery, selectedEvent?.id]);

  const handleSelectEvent = async (eventId: string) => {
    if (!currentBotId) return;
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('event', eventId);
    setSearchParams(nextParams, { replace: true });
    try {
      await fetchEventDetail(currentBotId, eventId);
    } catch (err) {
      toast.error(`加载事件详情失败：${err}`);
    }
  };

  const handleApply = async (candidateId: string) => {
    if (!currentBotId) return;
    try {
      await applyPromotion(currentBotId, candidateId);
      toast.success('已批准该条晋升');
    } catch (err) {
      toast.error(`批准失败：${err}`);
    }
  };

  const handleReject = async (candidateId: string) => {
    if (!currentBotId) return;
    const reason = window.prompt('请输入拒绝原因（会写入演化审计）', '证据暂时不足，先保留在 runtime 层观察');
    if (!reason) return;
    try {
      await rejectPromotion(currentBotId, candidateId, reason);
      toast.success('已记录拒绝原因');
    } catch (err) {
      toast.error(`拒绝失败：${err}`);
    }
  };

  const handleReflect = async () => {
    if (!currentBotId) return;
    try {
      await reflect(currentBotId);
      toast.success('已手动触发一次反思');
    } catch (err) {
      toast.error(`触发反思失败：${err}`);
    }
  };

  const handleRebuild = async () => {
    if (!currentBotId) return;
    try {
      await rebuild(currentBotId);
      toast.success('已从 runtime / relationship / life state 回建演化状态');
    } catch (err) {
      toast.error(`回建失败：${err}`);
    }
  };

  const handleLoadMore = async () => {
    if (!currentBotId || !hasMore || !nextCursor) return;
    try {
      await fetchTimeline(currentBotId, { append: true });
    } catch (err) {
      toast.error(`加载更多失败：${err}`);
    }
  };

  if (!currentBotId) {
    return (
      <EmptyState
        icon="inbox"
        title="还没有选中 Bot"
        description="先在左上角切换到一个 Bot，再查看人格演化过程。"
      />
    );
  }

  const overview = summary?.overview;
  const snapshot = summary?.snapshot;
  const diagnostics = summary?.diagnostics || stateView?.human_readable_diagnostics || [];
  const pending = snapshot?.pending || [];
  const rawState = stateView?.state || {};

  return (
    <div style={{ display: 'grid', gap: 24 }}>
      <div
        style={{
          borderRadius: 20,
          padding: 24,
          border: '1px solid var(--border-subtle)',
          background: 'linear-gradient(135deg, #f3f0e8 0%, #fff9ef 48%, #eef5ef 100%)',
          boxShadow: 'var(--shadow-sm)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          gap: 20,
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'grid', gap: 10, maxWidth: 760 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <TrendingUp size={22} color="var(--accent)" />
            <h1 style={{ margin: 0, fontSize: 28, fontWeight: 800, color: 'var(--text-primary)' }}>人格演化</h1>
            {refreshing && <Badge variant="info">轮询更新中</Badge>}
          </div>
          <div style={{ fontSize: 14, lineHeight: 1.7, color: 'var(--text-secondary)' }}>
            看见 Bot 为什么会变、变了什么、这些变化是怎么一步步从经历、反思和晋升里长出来的。
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <Button variant="secondary" onClick={loadAll} disabled={acting || loading}>
            <RefreshCw size={14} style={{ marginRight: 6 }} />
            刷新
          </Button>
          <Button variant="secondary" onClick={handleReflect} disabled={acting}>
            <Sparkles size={14} style={{ marginRight: 6 }} />
            手动反思
          </Button>
          <Button onClick={handleRebuild} disabled={acting}>
            <ArrowRightLeft size={14} style={{ marginRight: 6 }} />
            回建状态
          </Button>
        </div>
      </div>

      {error && (
        <Card>
          <CardContent style={{ padding: 18, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--error)' }}>
              <AlertTriangle size={16} />
              <span>{error}</span>
            </div>
            <Button variant="secondary" onClick={loadAll}>重试</Button>
          </CardContent>
        </Card>
      )}

      <section style={{ display: 'grid', gap: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Eye size={18} color="var(--accent)" />
          <h2 style={{ margin: 0, fontSize: 18, color: 'var(--text-primary)' }}>演化总览</h2>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 14 }}>
          <OverviewMetric title="当前阶段" value={overview?.phase || '暂无'} icon={<Sparkles size={18} />} accent="var(--accent)" />
          <OverviewMetric title="活跃信号" value={overview?.active_signal_count ?? 0} icon={<Brain size={18} />} accent="var(--success)" />
          <OverviewMetric title="待晋升数" value={overview?.pending_promotion_count ?? 0} icon={<GitCommitHorizontal size={18} />} accent="var(--warning)" />
          <OverviewMetric title="最近 7 天演化次数" value={overview?.evolution_count_7d ?? 0} icon={<TrendingUp size={18} />} accent="var(--info)" />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
          <Card>
            <CardContent style={{ padding: 16, display: 'grid', gap: 6 }}>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>最近一次反思</div>
              <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>{formatDateTime(overview?.last_reflection_at)}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent style={{ padding: 16, display: 'grid', gap: 6 }}>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>最近一次核心 persona 改写</div>
              <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>{formatDateTime(overview?.last_promotion_at)}</div>
            </CardContent>
          </Card>
        </div>
      </section>

      <section style={{ display: 'grid', gridTemplateColumns: 'minmax(320px, 1fr) minmax(320px, 1fr)', gap: 16 }}>
        <Card>
          <CardHeader>
            <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Brain size={18} />
              当前人格快照
            </CardTitle>
          </CardHeader>
          <CardContent style={{ display: 'grid', gap: 16 }}>
            <div style={{ display: 'grid', gap: 14 }}>
              <SnapshotRow label="personality_tags" value={(snapshot?.core.personality_tags || []).join('、') || '暂无'} tag={snapshotTag('core', 'success')} />
              <SnapshotRow label="speaking_style.tone" value={snapshot?.core.tone || '暂无'} tag={snapshotTag('core', 'success')} />
              <SnapshotRow label="values 摘要" value={snapshot?.core.values_summary || '暂无'} tag={snapshotTag('core', 'success')} />
              <SnapshotRow label="backstory growth summary" value={snapshot?.core.backstory_growth_summary || '暂无'} tag={snapshotTag('core', 'success')} />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Wand2 size={18} />
              runtime 演化态
            </CardTitle>
          </CardHeader>
          <CardContent style={{ display: 'grid', gap: 16 }}>
            <div style={{ display: 'grid', gap: 14 }}>
              <SnapshotRow label="shared_growth_summary" value={snapshot?.runtime.shared_growth_summary || '暂无'} tag={snapshotTag('runtime', 'info')} />
              <SnapshotRow label="life_growth_summary" value={snapshot?.runtime.life_growth_summary || '暂无'} tag={snapshotTag('runtime', 'info')} />
              <SnapshotRow label="active style drift" value={(snapshot?.runtime.active_style_drift || []).join('；') || '暂无'} tag={snapshotTag('runtime', 'info')} />
              <SnapshotRow label="active value drift" value={(snapshot?.runtime.active_value_drift || []).join('；') || '暂无'} tag={snapshotTag('runtime', 'info')} />
            </div>
            <div style={{ display: 'grid', gap: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>待晋升候选</div>
                {snapshotTag('pending', 'warning')}
              </div>
              {pending.length === 0 ? (
                <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>当前没有待处理的 promotion。</div>
              ) : (
                pending.map((item) => (
                  <PendingCard
                    key={item.id}
                    item={item}
                    acting={acting}
                    onApply={handleApply}
                    onReject={handleReject}
                  />
                ))
              )}
            </div>
          </CardContent>
        </Card>
      </section>

      <section style={{ display: 'grid', gridTemplateColumns: 'minmax(420px, 1.25fr) minmax(320px, 0.95fr)', gap: 16, alignItems: 'start' }}>
        <Card>
          <CardHeader>
            <CardTitle style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Clock3 size={18} />
                演化时间线
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Filter size={16} />
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>筛选</span>
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent style={{ display: 'grid', gap: 16 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <Select
                label="维度"
                options={dimensionOptions}
                value={filters.dimension}
                onChange={(event) => {
                  clearSelection();
                  const nextParams = new URLSearchParams(searchParams);
                  nextParams.delete('event');
                  setSearchParams(nextParams, { replace: true });
                  setFilters({ dimension: event.target.value as typeof filters.dimension });
                }}
              />
              <Select
                label="状态"
                options={statusOptions}
                value={filters.status}
                onChange={(event) => {
                  clearSelection();
                  const nextParams = new URLSearchParams(searchParams);
                  nextParams.delete('event');
                  setSearchParams(nextParams, { replace: true });
                  setFilters({ status: event.target.value as typeof filters.status });
                }}
              />
            </div>

            {timelineError ? (
              <EmptyState
                icon="search"
                title="时间线加载失败"
                description={timelineError}
                action={<Button variant="secondary" onClick={loadAll}>重试</Button>}
              />
            ) : timeline.length === 0 && !loading ? (
              <EmptyState
                icon="inbox"
                title="还没有演化记录"
                description="当前没有 signal、reflection 或 promotion 事件，Bot 暂时处于稳定阶段。"
              />
            ) : (
              <div style={{ display: 'grid', gap: 10 }}>
                {timeline.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => handleSelectEvent(item.id)}
                    style={{
                      textAlign: 'left',
                      borderRadius: 12,
                      border: selectedEvent?.id === item.id ? '1px solid var(--accent)' : '1px solid var(--border-subtle)',
                      backgroundColor: selectedEvent?.id === item.id ? 'var(--accent-light)' : 'var(--bg-tertiary)',
                      padding: 14,
                      cursor: 'pointer',
                      display: 'grid',
                      gap: 8,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                        <Badge variant={statusTone(item.status)}>{eventLabel(item)}</Badge>
                        <Badge>{item.dimension || 'mixed'}</Badge>
                        {item.wrote_core_persona && <Badge variant="success">已写入核心 persona</Badge>}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{formatDateTime(item.created_at)}</div>
                    </div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{item.summary || '暂无摘要'}</div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 12, color: 'var(--text-secondary)', flexWrap: 'wrap' }}>
                      <span>证据数：{item.evidence_count}</span>
                      <span>{item.human_readable_reason || '暂无说明'}</span>
                    </div>
                  </button>
                ))}
                {hasMore && (
                  <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 8 }}>
                    <Button variant="secondary" onClick={handleLoadMore} disabled={loading}>
                      加载更多
                    </Button>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <GitCommitHorizontal size={18} />
              本次变化详情
            </CardTitle>
          </CardHeader>
          <CardContent style={{ display: 'grid', gap: 14 }}>
            {detailError ? (
              <EmptyState
                icon="file"
                title="详情加载失败"
                description={detailError}
              />
            ) : loadingDetail ? (
              <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>正在加载详情...</div>
            ) : !selectedEvent ? (
              <EmptyState
                icon="search"
                title="点击左侧时间线查看详情"
                description="这里会展示证据引用、评分、candidate patch、before/after diff 和晋升或抑制原因。"
              />
            ) : (
              <div style={{ display: 'grid', gap: 14 }}>
                <DetailBlock label="summary" value={selectedEvent.summary || '暂无'} />
                <DetailBlock label="可读原因" value={selectedEvent.human_readable_reason || '暂无'} />
                <DetailBlock label="evidence refs" value={(selectedEvent.evidence_refs || []).join('\n') || '暂无'} mono />
                <DetailBlock
                  label="信心 / 稳定度 / 新颖度 / 重要度"
                  value={[
                    `confidence: ${selectedEvent.scores?.confidence ?? '暂无'}`,
                    `stability: ${selectedEvent.scores?.stability ?? '暂无'}`,
                    `novelty: ${selectedEvent.scores?.novelty ?? '暂无'}`,
                    `importance: ${selectedEvent.scores?.importance ?? '暂无'}`,
                  ].join('\n')}
                  mono
                />
                <DetailBlock label="candidate patch" value={renderJson(selectedEvent.candidate_patch)} mono />
                <DetailBlock label="promotion / suppression reason" value={selectedEvent.reason || '暂无'} />
                <div style={{ display: 'grid', gap: 10 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>前后 diff</div>
                  {selectedEvent.diffs?.length ? (
                    selectedEvent.diffs.map((diff, index) => (
                      <div
                        key={`${diff.field_path}-${index}`}
                        style={{
                          padding: 12,
                          borderRadius: 10,
                          border: '1px solid var(--border-subtle)',
                          backgroundColor: 'var(--bg-tertiary)',
                          display: 'grid',
                          gap: 10,
                        }}
                      >
                        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{diff.field_path}</div>
                        <div style={{ display: 'grid', gap: 8 }}>
                          <DiffPane title="before" value={diff.before} />
                          <DiffPane title="after" value={diff.after} />
                        </div>
                      </div>
                    ))
                  ) : (
                    <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>该事件暂时没有 before / after diff。</div>
                  )}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      <section style={{ display: 'grid', gridTemplateColumns: 'minmax(320px, 0.95fr) minmax(360px, 1.05fr)', gap: 16 }}>
        <Card>
          <CardHeader>
            <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <AlertTriangle size={18} />
              可解释诊断
            </CardTitle>
          </CardHeader>
          <CardContent style={{ display: 'grid', gap: 10 }}>
            {loadingState ? (
              <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>正在加载诊断...</div>
            ) : diagnostics.length === 0 ? (
              <EmptyState
                icon="inbox"
                title="当前没有额外诊断"
                description="没有待说明的阻塞条件，系统暂时处于稳定演化状态。"
              />
            ) : (
              diagnostics.map((item) => (
                <div
                  key={item}
                  style={{
                    padding: 12,
                    borderRadius: 10,
                    border: '1px solid var(--border-subtle)',
                    backgroundColor: 'var(--bg-tertiary)',
                    fontSize: 13,
                    lineHeight: 1.7,
                    color: 'var(--text-secondary)',
                  }}
                >
                  {item}
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Brain size={18} />
              演化状态视图
            </CardTitle>
          </CardHeader>
          <CardContent style={{ display: 'grid', gap: 14 }}>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
              这里保留结构化状态，方便管理员确认 signals、hypotheses、pending promotions 和 suppression 轨迹是否符合预期。
            </div>
            <div
              style={{
                borderRadius: 12,
                border: '1px solid var(--border-subtle)',
                backgroundColor: 'var(--bg-tertiary)',
                padding: 14,
                maxHeight: 460,
                overflow: 'auto',
              }}
            >
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: 12, lineHeight: 1.65, color: 'var(--text-secondary)' }}>
                {renderJson(rawState)}
              </pre>
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function SnapshotRow({ label, value, tag }: { label: string; value: string; tag: React.ReactNode }) {
  return (
    <div
      style={{
        padding: 14,
        borderRadius: 10,
        border: '1px solid var(--border-subtle)',
        backgroundColor: 'var(--bg-tertiary)',
        display: 'grid',
        gap: 8,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{label}</div>
        {tag}
      </div>
      <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>{value}</div>
    </div>
  );
}

function DetailBlock({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div style={{ display: 'grid', gap: 6 }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{label}</div>
      <div
        style={{
          padding: 12,
          borderRadius: 10,
          border: '1px solid var(--border-subtle)',
          backgroundColor: 'var(--bg-tertiary)',
          fontSize: 13,
          lineHeight: 1.7,
          color: 'var(--text-secondary)',
          fontFamily: mono ? 'Consolas, Monaco, monospace' : 'inherit',
          whiteSpace: 'pre-wrap',
        }}
      >
        {value}
      </div>
    </div>
  );
}

function DiffPane({ title, value }: { title: string; value: unknown }) {
  return (
    <div style={{ display: 'grid', gap: 4 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>{title}</div>
      <div
        style={{
          padding: 10,
          borderRadius: 8,
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border-subtle)',
          fontSize: 12,
          lineHeight: 1.65,
          color: 'var(--text-secondary)',
          fontFamily: 'Consolas, Monaco, monospace',
          whiteSpace: 'pre-wrap',
        }}
      >
        {renderJson(value)}
      </div>
    </div>
  );
}
