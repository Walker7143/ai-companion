import { useEffect, useState, useCallback } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Brain, Trash2, Star, Clock, User, Heart } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, Badge, Button, Modal, useToast } from '../../components/ui';
import { useBotStore } from '../../stores';
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
    const botId = currentBotId || 'suqing';
    try {
      const [stats, working, episodic, semantic] = await Promise.all([
        invoke<MemoryStats>('get_memory_stats', { botId }),
        invoke<Message[]>('get_working_memory', { botId }),
        invoke<EpisodicItem[]>('get_episodic_memory', { botId, query: null, limit: null }),
        invoke<SemanticMemory>('get_semantic_memory', { botId }),
      ]);
      setMemoryStats(stats);
      setWorkingMemory(working);
      setEpisodicMemory(episodic);
      setSemanticMemory(semantic);
    } catch (err) {
      toast('error', `获取记忆数据失败: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [currentBotId, toast]);

  useEffect(() => {
    fetchAllData();
  }, [fetchAllData]);

  const handleDeleteMemory = async () => {
    if (!deleteTarget) return;

    setDeleting(true);
    try {
      await invoke('delete_memory', {
        botId: currentBotId || 'suqing',
        memoryType: deleteTarget.type,
        memoryId: deleteTarget.id,
      });
      toast('success', '记忆已删除');
      setDeleteModalOpen(false);
      setDeleteTarget(null);
      fetchAllData();
    } catch (err) {
      toast('error', `删除记忆失败: ${err}`);
    } finally {
      setDeleting(false);
    }
  };

  const handleClearAll = async () => {
    if (!confirm('确定要清空所有记忆吗？此操作不可恢复。')) return;

    try {
      await invoke('clear_all_memory', { botId: currentBotId || 'suqing' });
      toast('success', '所有记忆已清空');
      fetchAllData();
    } catch (err) {
      toast('error', `清空记忆失败: ${err}`);
    }
  };

  const getImportanceStars = (importance: number) => {
    const stars = Math.round(importance);
    return (
      <div className="flex gap-0.5">
        {[...Array(5)].map((_, i) => (
          <Star
            key={i}
            className={`w-3 h-3 ${i < stars ? 'text-warning fill-warning' : 'text-text-muted'}`}
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
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">情景记忆</h1>
          <p className="text-text-secondary mt-1">管理 AI 伴侣的情景记忆和上下文</p>
        </div>
        <div className="bg-bg-secondary border border-border-subtle rounded-lg p-8 animate-pulse">
          <div className="h-4 bg-bg-tertiary rounded w-1/4 mb-4" />
          <div className="grid grid-cols-3 gap-4">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-24 bg-bg-tertiary rounded" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">情景记忆</h1>
          <p className="text-text-secondary mt-1">管理 AI 伴侣的情景记忆和上下文</p>
        </div>
        <Button variant="secondary" size="sm" onClick={handleClearAll}>
          <Trash2 className="w-4 h-4 mr-1" />
          清空全部
        </Button>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-border-subtle">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.key
                ? 'border-accent text-accent'
                : 'border-transparent text-text-secondary hover:text-text-primary'
            }`}
          >
            {tab.label}
            {tab.count !== undefined && (
              <Badge variant="default" className="ml-2">
                {tab.count}
              </Badge>
            )}
          </button>
        ))}
      </div>

      {/* Stats Tab */}
      {activeTab === 'stats' && memoryStats && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <CardContent className="flex items-center gap-4">
              <div className="p-3 bg-accent/20 rounded-lg">
                <Clock className="w-6 h-6 text-accent" />
              </div>
              <div>
                <div className="text-2xl font-bold text-text-primary">
                  {memoryStats.working_count}
                </div>
                <div className="text-sm text-text-secondary">工作记忆</div>
                <div className="text-xs text-text-muted">
                  {(memoryStats.working_size_kb / 1024).toFixed(2)} MB
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="flex items-center gap-4">
              <div className="p-3 bg-warning/20 rounded-lg">
                <Brain className="w-6 h-6 text-warning" />
              </div>
              <div>
                <div className="text-2xl font-bold text-text-primary">
                  {memoryStats.episodic_count}
                </div>
                <div className="text-sm text-text-secondary">情景记忆</div>
                <div className="text-xs text-text-muted">
                  {(memoryStats.episodic_size_kb / 1024).toFixed(2)} MB
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="flex items-center gap-4">
              <div className="p-3 bg-info/20 rounded-lg">
                <User className="w-6 h-6 text-info" />
              </div>
              <div>
                <div className="text-2xl font-bold text-text-primary">
                  {memoryStats.semantic_count}
                </div>
                <div className="text-sm text-text-secondary">语义记忆</div>
                <div className="text-xs text-text-muted">
                  {(memoryStats.semantic_size_kb / 1024).toFixed(2)} MB
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Working Memory Tab */}
      {activeTab === 'working' && (
        <Card>
          <CardContent>
            {workingMemory.length === 0 ? (
              <div className="text-center py-8">
                <Clock className="w-12 h-12 text-text-muted mx-auto mb-3" />
                <p className="text-text-muted">工作记忆为空</p>
              </div>
            ) : (
              <div className="space-y-3">
                {workingMemory.map((msg) => (
                  <div
                    key={msg.id}
                    className={`p-3 rounded-lg ${
                      msg.role === 'user' ? 'bg-accent/10' : 'bg-bg-tertiary'
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <Badge variant={msg.role === 'user' ? 'info' : 'default'}>
                        {msg.role === 'user' ? '用户' : 'Bot'}
                      </Badge>
                      <span className="text-xs text-text-muted">
                        {new Date(msg.created_at).toLocaleString('zh-CN')}
                      </span>
                    </div>
                    <p className="text-sm text-text-primary">{msg.content}</p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Episodic Memory Tab */}
      {activeTab === 'episodic' && (
        <Card>
          <CardContent>
            {episodicMemory.length === 0 ? (
              <div className="text-center py-8">
                <Brain className="w-12 h-12 text-text-muted mx-auto mb-3" />
                <p className="text-text-muted">情景记忆为空</p>
              </div>
            ) : (
              <div className="space-y-4">
                {episodicMemory.map((item) => (
                  <div
                    key={item.id}
                    className="p-4 bg-bg-tertiary rounded-lg hover:bg-bg-tertiary/80 transition-colors"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-2">
                        {getImportanceStars(item.importance)}
                        <span className="text-xs text-text-muted">
                          {new Date(item.created_at).toLocaleDateString('zh-CN')}
                        </span>
                      </div>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => {
                          setDeleteTarget({ type: 'episodic', id: item.id });
                          setDeleteModalOpen(true);
                        }}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                    <p className="text-sm font-medium text-text-primary mb-1">
                      {item.summary}
                    </p>
                    <p className="text-sm text-text-secondary">{item.content}</p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Semantic Memory Tab */}
      {activeTab === 'semantic' && semanticMemory && (
        <div className="space-y-6">
          {/* Relationship Status */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Heart className="w-5 h-5 text-error" />
                关系状态
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-6">
                <div className="text-center">
                  <div className="text-3xl font-bold text-accent">
                    {semanticMemory.attitude_score.toFixed(1)}
                  </div>
                  <div className="text-sm text-text-secondary">好感度</div>
                </div>
                <div className="flex-1">
                  <Badge variant="dialogue" className="text-lg px-3 py-1">
                    {semanticMemory.relationship_level}
                  </Badge>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* User Facts */}
          <Card>
            <CardHeader>
              <CardTitle>用户画像</CardTitle>
            </CardHeader>
            <CardContent>
              {semanticMemory.facts.length === 0 ? (
                <div className="text-center py-4">
                  <User className="w-8 h-8 text-text-muted mx-auto mb-2" />
                  <p className="text-text-muted text-sm">暂无用户画像</p>
                </div>
              ) : (
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                  {semanticMemory.facts.map((fact) => (
                    <div
                      key={fact.key}
                      className="p-3 bg-bg-tertiary rounded-lg"
                    >
                      <div className="text-xs text-text-muted mb-1">{fact.key}</div>
                      <div className="text-sm font-medium text-text-primary">
                        {fact.value}
                      </div>
                      <div className="text-xs text-text-muted mt-1">
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

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={deleteModalOpen}
        onClose={() => {
          setDeleteModalOpen(false);
          setDeleteTarget(null);
        }}
        title="确认删除"
        size="sm"
      >
        <div className="space-y-4">
          <p className="text-text-secondary">
            确定要删除这条记忆吗？此操作不可恢复。
          </p>
          <div className="flex gap-3 justify-end">
            <Button
              variant="secondary"
              onClick={() => {
                setDeleteModalOpen(false);
                setDeleteTarget(null);
              }}
            >
              取消
            </Button>
            <Button variant="primary" onClick={handleDeleteMemory} disabled={deleting}>
              {deleting ? '删除中...' : '确认删除'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}