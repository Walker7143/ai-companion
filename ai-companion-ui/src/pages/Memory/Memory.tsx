import { useEffect, useState, useCallback } from 'react';
import { Brain, Trash2, Star, Clock, User, Heart, RefreshCw } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, Badge, Button, Modal, useToast } from '../../components/ui';
import { useBotStore } from '../../stores';
import { memoryApi } from '../../api';
import type { MemoryStats, Message, EpisodicItem, SemanticMemory } from '../../types';

type MemoryTab = 'stats' | 'working' | 'episodic' | 'semantic';

export function Memory() {
  const { currentBotId } = useBotStore();
  const toast = useToast();

  const [activeTab, setActiveTab] = useState<MemoryTab>('stats');
  const [memoryStats, setMemoryStats] = useState<MemoryStats | null>(null);
  const [workingMemory, setWorkingMemory] = useState<Message[]>([]);
  const [episodicMemory, setEpisodicMemory] = useState<EpisodicItem[]>([]);
  const [semanticMemory, setSemanticMemory] = useState<SemanticMemory | null>(null);
  const [loading, setLoading] = useState(true);

  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ type: string; id: string } | null>(null);
  const [deleting, setDeleting] = useState(false);

  const fetchAllData = useCallback(async () => {
    if (!currentBotId) return;
    try {
      const [stats, working, episodic, semantic] = await Promise.all([
        memoryApi.getStats(currentBotId),
        memoryApi.getWorking(currentBotId),
        memoryApi.getEpisodic(currentBotId),
        memoryApi.getSemantic(currentBotId),
      ]);
      setMemoryStats(stats);
      setWorkingMemory(working);
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
      <div style={{ display: 'flex', gap: '2px' }}>
        {[...Array(5)].map((_, i) => (
          <Star
            key={i}
            style={{
              width: '12px',
              height: '12px',
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
    { key: 'episodic', label: '情景记忆', count: memoryStats?.episodic_count },
    { key: 'semantic', label: '语义记忆', count: memoryStats?.semantic_count },
  ];

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '4px' }}>
            记忆管理
          </h1>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
            管理 AI 伴侣的三层记忆系统
          </p>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
          {[...Array(3)].map((_, i) => (
            <div
              key={i}
              style={{
                height: '100px',
                borderRadius: '12px',
                backgroundColor: 'var(--bg-secondary)',
                border: '1px solid var(--border-subtle)',
              }}
            />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '4px' }}>
            记忆管理
          </h1>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
            管理 AI 伴侣的三层记忆系统
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <Button variant="secondary" size="sm" onClick={fetchAllData}>
            <RefreshCw style={{ width: '14px', height: '14px', marginRight: '4px' }} />
            刷新
          </Button>
          <Button variant="danger" size="sm" onClick={handleClearAll}>
            <Trash2 style={{ width: '14px', height: '14px', marginRight: '4px' }} />
            清空全部
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '4px', borderBottom: '1px solid var(--border-subtle)' }}>
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            style={{
              padding: '12px 20px',
              fontSize: '14px',
              fontWeight: 500,
              border: 'none',
              backgroundColor: 'transparent',
              cursor: 'pointer',
              borderBottom: `2px solid ${activeTab === tab.key ? 'var(--accent)' : 'transparent'}`,
              color: activeTab === tab.key ? 'var(--accent)' : 'var(--text-secondary)',
              transition: 'all 150ms ease',
            }}
          >
            {tab.label}
            {tab.count !== undefined && (
              <Badge variant="default" style={{ marginLeft: '8px', fontSize: '11px' }}>
                {tab.count}
              </Badge>
            )}
          </button>
        ))}
      </div>

      {/* Stats Tab */}
      {activeTab === 'stats' && memoryStats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
          {[
            { label: '工作记忆', value: memoryStats.working_count, icon: Clock, color: 'var(--accent)', size: (memoryStats.working_size_kb / 1024).toFixed(2) },
            { label: '情景记忆', value: memoryStats.episodic_count, icon: Brain, color: 'var(--warning)', size: (memoryStats.episodic_size_kb / 1024).toFixed(2) },
            { label: '语义记忆', value: memoryStats.semantic_count, icon: User, color: 'var(--info)', size: (memoryStats.semantic_size_kb / 1024).toFixed(2) },
          ].map((item) => (
            <Card
              key={item.label}
              style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: '12px', border: '1px solid var(--border-subtle)' }}
            >
              <CardContent style={{ padding: '20px', display: 'flex', alignItems: 'center', gap: '16px' }}>
                <div style={{ padding: '12px', borderRadius: '10px', backgroundColor: item.color + '15' }}>
                  <item.icon style={{ width: '24px', height: '24px', color: item.color }} />
                </div>
                <div>
                  <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.2 }}>
                    {item.value}
                  </div>
                  <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                    {item.label}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                    {item.size} MB
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Working Memory Tab */}
      {activeTab === 'working' && (
        <Card style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: '12px', border: '1px solid var(--border-subtle)' }}>
          <CardContent style={{ padding: '0' }}>
            {workingMemory.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '48px 0' }}>
                <Clock style={{ width: '48px', height: '48px', margin: '0 auto 16px', color: 'var(--text-muted)', opacity: 0.5 }} />
                <p style={{ color: 'var(--text-muted)' }}>工作记忆为空</p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '16px' }}>
                {workingMemory.map((msg) => (
                  <div
                    key={msg.id}
                    style={{
                      padding: '12px',
                      borderRadius: '8px',
                      backgroundColor: msg.role === 'user' ? 'var(--accent-light)' : 'var(--bg-tertiary)',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                      <Badge variant={msg.role === 'user' ? 'info' : 'default'} style={{ fontSize: '10px' }}>
                        {msg.role === 'user' ? '用户' : 'Bot'}
                      </Badge>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                        {new Date(msg.created_at).toLocaleString('zh-CN')}
                      </span>
                    </div>
                    <p style={{ fontSize: '13px', color: 'var(--text-primary)' }}>{msg.content}</p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Episodic Memory Tab */}
      {activeTab === 'episodic' && (
        <Card style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: '12px', border: '1px solid var(--border-subtle)' }}>
          <CardContent style={{ padding: '0' }}>
            {episodicMemory.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '48px 0' }}>
                <Brain style={{ width: '48px', height: '48px', margin: '0 auto 16px', color: 'var(--text-muted)', opacity: 0.5 }} />
                <p style={{ color: 'var(--text-muted)' }}>情景记忆为空</p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', padding: '16px' }}>
                {episodicMemory.map((item) => (
                  <div
                    key={item.id}
                    style={{
                      padding: '16px',
                      borderRadius: '8px',
                      backgroundColor: 'var(--bg-tertiary)',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {getImportanceStars(item.importance)}
                        {typeof item.confidence === 'number' && (
                          <Badge variant="info" style={{ fontSize: '10px' }}>
                            置信度 {(item.confidence * 100).toFixed(0)}%
                          </Badge>
                        )}
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                          {new Date(item.created_at).toLocaleDateString('zh-CN')}
                        </span>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setDeleteTarget({ type: 'episodic', id: item.id });
                          setDeleteModalOpen(true);
                        }}
                        style={{ padding: '4px' }}
                      >
                        <Trash2 style={{ width: '14px', height: '14px' }} />
                      </Button>
                    </div>
                    <p style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-primary)', marginBottom: '4px' }}>
                      {item.summary}
                    </p>
                    <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{item.content}</p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Semantic Memory Tab */}
      {activeTab === 'semantic' && semanticMemory && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <Card style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: '12px', border: '1px solid var(--border-subtle)' }}>
            <CardHeader style={{ borderBottom: 'none', padding: '16px 20px' }}>
              <CardTitle style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Heart style={{ width: '18px', height: '18px', color: 'var(--error)' }} />
                关系状态
              </CardTitle>
            </CardHeader>
            <CardContent style={{ padding: '16px 20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '36px', fontWeight: 700, color: 'var(--accent)' }}>
                    {semanticMemory.attitude_score.toFixed(1)}
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>好感度</div>
                </div>
                <Badge variant="success" style={{ fontSize: '14px', padding: '6px 12px' }}>
                  {semanticMemory.relationship_level}
                </Badge>
              </div>
            </CardContent>
          </Card>

          <Card style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: '12px', border: '1px solid var(--border-subtle)' }}>
            <CardHeader style={{ borderBottom: 'none', padding: '16px 20px' }}>
              <CardTitle>用户画像</CardTitle>
            </CardHeader>
            <CardContent style={{ padding: '0 20px 20px' }}>
              {semanticMemory.facts.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '24px 0' }}>
                  <User style={{ width: '32px', height: '32px', margin: '0 auto 8px', color: 'var(--text-muted)', opacity: 0.5 }} />
                  <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>暂无用户画像</p>
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '12px' }}>
                  {semanticMemory.facts.map((fact) => (
                    <div
                      key={fact.key}
                      style={{
                        padding: '12px',
                        borderRadius: '8px',
                        backgroundColor: 'var(--bg-tertiary)',
                      }}
                    >
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>
                        {fact.key}
                      </div>
                      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '6px' }}>
                        {fact.category && <Badge variant="info">{fact.category}</Badge>}
                        {typeof fact.confidence === 'number' && (
                          <Badge>{(fact.confidence * 100).toFixed(0)}%</Badge>
                        )}
                        {fact.source && <Badge>{fact.source}</Badge>}
                      </div>
                      <div style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-primary)' }}>
                        {fact.value}
                      </div>
                      <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '4px' }}>
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

      {/* Delete Modal */}
      <Modal
        isOpen={deleteModalOpen}
        onClose={() => {
          setDeleteModalOpen(false);
          setDeleteTarget(null);
        }}
        title="确认删除"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <p style={{ color: 'var(--text-secondary)' }}>
            确定要删除这条记忆吗？此操作不可恢复。
          </p>
          <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
            <Button
              variant="secondary"
              onClick={() => {
                setDeleteModalOpen(false);
                setDeleteTarget(null);
              }}
            >
              取消
            </Button>
            <Button variant="danger" onClick={handleDeleteMemory} disabled={deleting}>
              {deleting ? '删除中...' : '确认删除'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
