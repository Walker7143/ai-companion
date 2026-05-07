import { useEffect, useState, useCallback } from 'react';
import { Brain, CalendarDays, Clock, Heart, RefreshCw, Star, Trash2, User } from 'lucide-react';
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Modal, useToast } from '../../components/ui';
import { useBotStore } from '../../stores';
import { memoryApi } from '../../api';
import type { DailyMemoryPayload, EpisodicItem, MemoryStats, Message, SemanticMemory } from '../../types';

type MemoryTab = 'stats' | 'working' | 'daily' | 'episodic' | 'semantic';

function parseList(value?: string | null): string[] {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.map(String).filter(Boolean) : [];
  } catch {
    return [];
  }
}

export function Memory() {
  const { currentBotId } = useBotStore();
  const toast = useToast();

  const [activeTab, setActiveTab] = useState<MemoryTab>('stats');
  const [memoryStats, setMemoryStats] = useState<MemoryStats | null>(null);
  const [workingMemory, setWorkingMemory] = useState<Message[]>([]);
  const [dailyMemory, setDailyMemory] = useState<DailyMemoryPayload>({ messages: [], summaries: [] });
  const [episodicMemory, setEpisodicMemory] = useState<EpisodicItem[]>([]);
  const [semanticMemory, setSemanticMemory] = useState<SemanticMemory | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ type: string; id: string } | null>(null);
  const [deleting, setDeleting] = useState(false);

  const fetchAllData = useCallback(async () => {
    if (!currentBotId) return;
    setLoading(true);
    try {
      const [stats, working, daily, episodic, semantic] = await Promise.all([
        memoryApi.getStats(currentBotId),
        memoryApi.getWorking(currentBotId),
        memoryApi.getDaily(currentBotId),
        memoryApi.getEpisodic(currentBotId),
        memoryApi.getSemantic(currentBotId),
      ]);
      setMemoryStats(stats);
      setWorkingMemory(working);
      setDailyMemory(daily);
      setEpisodicMemory(episodic);
      setSemanticMemory(semantic);
    } catch (err) {
      toast.error(`获取记忆数据失败: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [currentBotId, toast]);

  useEffect(() => {
    fetchAllData();
  }, [fetchAllData]);

  const handleDeleteMemory = async () => {
    if (!deleteTarget || !currentBotId) return;
    setDeleting(true);
    try {
      await memoryApi.deleteMemory(currentBotId, deleteTarget.type, deleteTarget.id);
      toast.success('记忆已删除');
      setDeleteModalOpen(false);
      setDeleteTarget(null);
      fetchAllData();
    } catch (err) {
      toast.error(`删除记忆失败: ${err}`);
    } finally {
      setDeleting(false);
    }
  };

  const handleClearAll = async () => {
    if (!confirm('确定要清空所有记忆吗？此操作不可恢复。')) return;
    if (!currentBotId) return;
    try {
      await memoryApi.clearAll(currentBotId);
      toast.success('所有记忆已清空');
      fetchAllData();
    } catch (err) {
      toast.error(`清空记忆失败: ${err}`);
    }
  };

  const getImportanceStars = (importance: number) => {
    const stars = Math.round(importance * 5);
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
        <div style={{ height: 120, borderRadius: 8, backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }} />
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>记忆管理</h1>
          <p style={{ fontSize: 14, color: 'var(--text-secondary)' }}>
            管理工作记忆、日记忆、情景记忆和语义记忆。
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button variant="secondary" size="sm" onClick={fetchAllData}>
            <RefreshCw style={{ width: 14, height: 14, marginRight: 4 }} />
            刷新
          </Button>
          <Button variant="danger" size="sm" onClick={handleClearAll}>
            <Trash2 style={{ width: 14, height: 14, marginRight: 4 }} />
            清空全部
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

      {activeTab === 'stats' && memoryStats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
          {[
            { label: '工作记忆', value: memoryStats.working_count, icon: Clock, color: 'var(--accent)', size: memoryStats.working_size_kb },
            { label: '日记忆', value: memoryStats.daily_count ?? 0, icon: CalendarDays, color: 'var(--success)', size: memoryStats.daily_size_kb ?? 0 },
            { label: '情景记忆', value: memoryStats.episodic_count, icon: Brain, color: 'var(--warning)', size: memoryStats.episodic_size_kb },
            { label: '语义记忆', value: memoryStats.semantic_count, icon: User, color: 'var(--info)', size: memoryStats.semantic_size_kb },
          ].map((item) => (
            <Card key={item.label} style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: 8, border: '1px solid var(--border-subtle)' }}>
              <CardContent style={{ padding: 20, display: 'flex', alignItems: 'center', gap: 16 }}>
                <div style={{ padding: 12, borderRadius: 8, backgroundColor: item.color + '15' }}>
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
      )}

      {activeTab === 'working' && (
        <MemoryListCard
          emptyIcon={<Clock style={{ width: 48, height: 48, color: 'var(--text-muted)', opacity: 0.5 }} />}
          emptyText="工作记忆为空"
        >
          {workingMemory.map((msg) => (
            <MessageRow key={msg.id} role={msg.role} content={msg.content} createdAt={msg.created_at} />
          ))}
        </MemoryListCard>
      )}

      {activeTab === 'daily' && (
        <div style={{ display: 'grid', gap: 16 }}>
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
                          {topics.slice(0, 4).map((topic) => <Badge key={`topic-${topic}`} variant="info">{topic}</Badge>)}
                          {openThreads.slice(0, 3).map((thread) => <Badge key={`thread-${thread}`}>{thread}</Badge>)}
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </CardContent>
          </Card>

          <MemoryListCard
            emptyIcon={<CalendarDays style={{ width: 48, height: 48, color: 'var(--text-muted)', opacity: 0.5 }} />}
            emptyText="日记忆流水为空"
          >
            {dailyMemory.messages.map((msg) => (
              <div key={msg.id} style={{ padding: 12, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
                  <Badge variant={msg.role === 'user' ? 'info' : 'default'}>{msg.role === 'user' ? '用户' : 'Bot'}</Badge>
                  <Badge>{msg.platform || 'unknown'}</Badge>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{new Date(msg.created_at).toLocaleString('zh-CN')}</span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setDeleteTarget({ type: 'daily', id: msg.id });
                      setDeleteModalOpen(true);
                    }}
                    style={{ marginLeft: 'auto', padding: 4 }}
                  >
                    <Trash2 style={{ width: 14, height: 14 }} />
                  </Button>
                </div>
                <p style={{ fontSize: 13, color: 'var(--text-primary)' }}>{msg.content}</p>
              </div>
            ))}
          </MemoryListCard>
        </div>
      )}

      {activeTab === 'episodic' && (
        <MemoryListCard
          emptyIcon={<Brain style={{ width: 48, height: 48, color: 'var(--text-muted)', opacity: 0.5 }} />}
          emptyText="情景记忆为空"
        >
          {episodicMemory.map((item) => (
            <div key={item.id} style={{ padding: 16, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  {getImportanceStars(item.importance)}
                  {typeof item.confidence === 'number' && <Badge variant="info">置信度 {(item.confidence * 100).toFixed(0)}%</Badge>}
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{new Date(item.created_at).toLocaleDateString('zh-CN')}</span>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setDeleteTarget({ type: 'episodic', id: item.id });
                    setDeleteModalOpen(true);
                  }}
                  style={{ padding: 4 }}
                >
                  <Trash2 style={{ width: 14, height: 14 }} />
                </Button>
              </div>
              <p style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>{item.summary}</p>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{item.content}</p>
            </div>
          ))}
        </MemoryListCard>
      )}

      {activeTab === 'semantic' && semanticMemory && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Card style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: 8, border: '1px solid var(--border-subtle)' }}>
            <CardHeader style={{ borderBottom: 'none', padding: '16px 20px' }}>
              <CardTitle style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Heart style={{ width: 18, height: 18, color: 'var(--error)' }} />
                关系状态
              </CardTitle>
            </CardHeader>
            <CardContent style={{ padding: '16px 20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 36, fontWeight: 700, color: 'var(--accent)' }}>{semanticMemory.attitude_score.toFixed(1)}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>好感度</div>
                </div>
                <Badge variant="success" style={{ fontSize: 14, padding: '6px 12px' }}>{semanticMemory.relationship_level}</Badge>
              </div>
            </CardContent>
          </Card>

          <Card style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: 8, border: '1px solid var(--border-subtle)' }}>
            <CardHeader style={{ borderBottom: 'none', padding: '16px 20px' }}>
              <CardTitle>用户画像</CardTitle>
            </CardHeader>
            <CardContent style={{ padding: '0 20px 20px' }}>
              {semanticMemory.facts.length === 0 ? (
                <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>暂无用户画像</p>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
                  {semanticMemory.facts.map((fact) => (
                    <div key={fact.key} style={{ padding: 12, borderRadius: 8, backgroundColor: 'var(--bg-tertiary)' }}>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>{fact.key}</div>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 6 }}>
                        {fact.category && <Badge variant="info">{fact.category}</Badge>}
                        {typeof fact.confidence === 'number' && <Badge>{(fact.confidence * 100).toFixed(0)}%</Badge>}
                        {fact.source && <Badge>{fact.source}</Badge>}
                      </div>
                      <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)' }}>{fact.value}</div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>
                        更新于 {new Date(fact.updated_at).toLocaleDateString('zh-CN')}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      <Modal
        isOpen={deleteModalOpen}
        onClose={() => {
          setDeleteModalOpen(false);
          setDeleteTarget(null);
        }}
        title="确认删除"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <p style={{ color: 'var(--text-secondary)' }}>确定要删除这条记忆吗？此操作不可恢复。</p>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <Button variant="secondary" onClick={() => setDeleteModalOpen(false)}>取消</Button>
            <Button variant="danger" onClick={handleDeleteMemory} disabled={deleting}>
              {deleting ? '删除中...' : '确认删除'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

function MemoryListCard({ children, emptyIcon, emptyText }: { children: React.ReactNode; emptyIcon: React.ReactNode; emptyText: string }) {
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

function MessageRow({ role, content, createdAt }: { role: string; content: string; createdAt: string }) {
  return (
    <div style={{ padding: 12, borderRadius: 8, backgroundColor: role === 'user' ? 'var(--accent-light)' : 'var(--bg-tertiary)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <Badge variant={role === 'user' ? 'info' : 'default'}>{role === 'user' ? '用户' : 'Bot'}</Badge>
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{new Date(createdAt).toLocaleString('zh-CN')}</span>
      </div>
      <p style={{ fontSize: 13, color: 'var(--text-primary)' }}>{content}</p>
    </div>
  );
}
