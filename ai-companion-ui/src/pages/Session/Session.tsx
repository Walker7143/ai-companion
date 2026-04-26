import { useEffect, useState, useCallback } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { MessageSquare, RefreshCw, Pause, Play, Clock, User, Cpu } from 'lucide-react';
import { Card, CardContent, Badge, Button, Modal, useToast } from '../../components/ui';
import { useBotStore } from '../../stores';
import type { SessionInfo, SessionDetail, ContextDetail } from '../../types';

export function Session() {
  const { currentBotId } = useBotStore();
  const toast = useToast();

  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [platformFilter, setPlatformFilter] = useState<string>('all');
  const [selectedSession, setSelectedSession] = useState<SessionDetail | null>(null);
  const [sessionContext, setSessionContext] = useState<ContextDetail | null>(null);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [contextLoading, setContextLoading] = useState(false);

  const fetchSessions = useCallback(async () => {
    try {
      const data = await invoke<SessionInfo[]>('list_sessions', {
        botId: currentBotId || 'suqing',
      });
      setSessions(data);
    } catch (err) {
      toast('error', `获取会话列表失败: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [currentBotId, toast]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const handleViewDetail = async (sessionKey: string) => {
    setContextLoading(true);
    setDetailModalOpen(true);
    try {
      const [detail, context] = await Promise.all([
        invoke<SessionDetail>('get_session_detail', { sessionKey }),
        invoke<ContextDetail>('get_session_context', { sessionKey }),
      ]);
      setSelectedSession(detail);
      setSessionContext(context);
    } catch (err) {
      toast('error', `获取会话详情失败: ${err}`);
    } finally {
      setContextLoading(false);
    }
  };

  const handleResetSession = async (sessionKey: string) => {
    try {
      await invoke('reset_session', { sessionKey });
      toast('success', '会话已重置');
      fetchSessions();
    } catch (err) {
      toast('error', `重置会话失败: ${err}`);
    }
  };

  const handleSuspendSession = async (sessionKey: string) => {
    try {
      await invoke('suspend_session', { sessionKey });
      toast('success', '会话已挂起');
      fetchSessions();
    } catch (err) {
      toast('error', `挂起会话失败: ${err}`);
    }
  };

  const filteredSessions = sessions.filter((s) => {
    if (platformFilter === 'all') return true;
    return s.platform === platformFilter;
  });

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'active':
        return <Badge variant="success">活跃</Badge>;
      case 'suspended':
        return <Badge variant="warning">已挂起</Badge>;
      default:
        return <Badge variant="default">{status}</Badge>;
    }
  };

  const getPlatformBadge = (platform: string) => {
    switch (platform) {
      case 'cli':
        return <Badge variant="info">CLI</Badge>;
      case 'feishu':
        return <Badge variant="dialogue">飞书</Badge>;
      default:
        return <Badge variant="default">{platform}</Badge>;
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">会话管理</h1>
          <p className="text-text-secondary mt-1">查看和管理与 AI 伴侣的对话记录</p>
        </div>
        <div className="bg-bg-secondary border border-border-subtle rounded-lg p-8 animate-pulse">
          <div className="h-4 bg-bg-tertiary rounded w-1/4 mb-4" />
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-20 bg-bg-tertiary rounded" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">会话管理</h1>
        <p className="text-text-secondary mt-1">查看和管理与 AI 伴侣的对话记录</p>
      </div>

      {/* Filters */}
      <div className="flex gap-4 items-center">
        <div className="flex gap-2">
          <Button
            variant={platformFilter === 'all' ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setPlatformFilter('all')}
          >
            全部
          </Button>
          <Button
            variant={platformFilter === 'cli' ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setPlatformFilter('cli')}
          >
            CLI
          </Button>
          <Button
            variant={platformFilter === 'feishu' ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setPlatformFilter('feishu')}
          >
            飞书
          </Button>
        </div>
        <div className="flex-1" />
        <Button variant="secondary" size="sm" onClick={fetchSessions}>
          <RefreshCw className="w-4 h-4 mr-1" />
          刷新
        </Button>
      </div>

      {/* Session List */}
      {filteredSessions.length === 0 ? (
        <div className="bg-bg-secondary border border-border-subtle rounded-lg p-8 text-center">
          <MessageSquare className="w-12 h-12 text-text-muted mx-auto mb-3" />
          <p className="text-text-muted">暂无会话记录</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredSessions.map((session) => (
            <Card key={session.session_key}>
              <CardContent className="flex items-center gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium text-text-primary truncate">
                      {session.user}
                    </span>
                    {getPlatformBadge(session.platform)}
                    {getStatusBadge(session.status)}
                  </div>
                  <div className="flex items-center gap-4 text-xs text-text-secondary">
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {formatDate(session.created_at)}
                    </span>
                    <span className="flex items-center gap-1">
                      <Cpu className="w-3 h-3" />
                      {session.total_tokens.toLocaleString()} tokens
                    </span>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleViewDetail(session.session_key)}
                  >
                    详情
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleResetSession(session.session_key)}
                  >
                    <RefreshCw className="w-4 h-4" />
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleSuspendSession(session.session_key)}
                  >
                    {session.status === 'suspended' ? (
                      <Play className="w-4 h-4" />
                    ) : (
                      <Pause className="w-4 h-4" />
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Detail Modal */}
      <Modal
        isOpen={detailModalOpen}
        onClose={() => {
          setDetailModalOpen(false);
          setSelectedSession(null);
          setSessionContext(null);
        }}
        title="会话详情"
        size="lg"
      >
        {contextLoading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin w-8 h-8 border-2 border-accent border-t-transparent rounded-full" />
          </div>
        ) : selectedSession && sessionContext ? (
          <div className="space-y-4">
            {/* Session Info */}
            <div className="grid grid-cols-2 gap-4">
              <div className="p-3 bg-bg-tertiary rounded-lg">
                <div className="text-xs text-text-secondary mb-1">用户</div>
                <div className="text-sm font-medium text-text-primary">
                  <User className="w-4 h-4 inline mr-1" />
                  {selectedSession.info.user}
                </div>
              </div>
              <div className="p-3 bg-bg-tertiary rounded-lg">
                <div className="text-xs text-text-secondary mb-1">平台</div>
                <div className="text-sm font-medium text-text-primary">
                  {getPlatformBadge(selectedSession.info.platform)}
                </div>
              </div>
              <div className="p-3 bg-bg-tertiary rounded-lg">
                <div className="text-xs text-text-secondary mb-1">Token 统计</div>
                <div className="text-sm font-medium text-text-primary">
                  输入: {selectedSession.input_tokens.toLocaleString()} / 输出:{' '}
                  {selectedSession.output_tokens.toLocaleString()}
                </div>
              </div>
              <div className="p-3 bg-bg-tertiary rounded-lg">
                <div className="text-xs text-text-secondary mb-1">预估费用</div>
                <div className="text-sm font-medium text-text-primary">
                  ${selectedSession.estimated_cost_usd.toFixed(4)}
                </div>
              </div>
            </div>

            {/* Context Token Usage */}
            <div className="p-3 bg-bg-tertiary rounded-lg">
              <div className="flex justify-between items-center mb-2">
                <span className="text-xs text-text-secondary">上下文使用</span>
                <span className="text-xs text-text-secondary">
                  {sessionContext.current_tokens} / {sessionContext.hard_limit}
                </span>
              </div>
              <div className="w-full bg-bg-secondary rounded-full h-2">
                <div
                  className={`h-2 rounded-full ${
                    sessionContext.current_tokens / sessionContext.hard_limit > 0.8
                      ? 'bg-error'
                      : sessionContext.current_tokens / sessionContext.hard_limit > 0.6
                      ? 'bg-warning'
                      : 'bg-success'
                  }`}
                  style={{
                    width: `${(sessionContext.current_tokens / sessionContext.hard_limit) * 100}%`,
                  }}
                />
              </div>
            </div>

            {/* Working History */}
            <div>
              <h4 className="text-sm font-medium text-text-primary mb-2">工作历史</h4>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {sessionContext.working_history.map((msg) => (
                  <div
                    key={msg.id}
                    className={`p-2 rounded text-sm ${
                      msg.role === 'user'
                        ? 'bg-accent/10 text-text-primary'
                        : 'bg-bg-tertiary text-text-secondary'
                    }`}
                  >
                    <span className="font-medium">
                      {msg.role === 'user' ? '用户' : 'Bot'}:
                    </span>{' '}
                    {msg.content}
                  </div>
                ))}
              </div>
            </div>

            {/* Semantic Facts */}
            {Object.keys(sessionContext.semantic_facts).length > 0 && (
              <div>
                <h4 className="text-sm font-medium text-text-primary mb-2">用户画像</h4>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(sessionContext.semantic_facts).map(([key, value]) => (
                    <Badge key={key} variant="memory">
                      {key}: {value}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : null}
      </Modal>
    </div>
  );
}