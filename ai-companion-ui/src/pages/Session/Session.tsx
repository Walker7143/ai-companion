import { useEffect, useState, useCallback } from 'react';
import { MessageSquare, RefreshCw, ChevronRight } from 'lucide-react';
import { Card, CardContent, Badge, Button, Modal, useToast } from '../../components/ui';
import { useBotStore } from '../../stores';
import { sessionApi } from '../../api';
import type { SessionInfo, SessionDetail } from '../../types';

export function Session() {
  const { currentBotId } = useBotStore();
  const toast = useToast();

  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [platformFilter, setPlatformFilter] = useState<string>('all');
  const [selectedSession, setSelectedSession] = useState<SessionDetail | null>(null);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);

  const fetchSessions = useCallback(async () => {
    if (!currentBotId) return;
    try {
      const data = await sessionApi.listSessions(currentBotId);
      setSessions(data);
    } catch (err) {
      toast.error(`获取会话列表失败: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [currentBotId, toast]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const handleViewDetail = async (sessionKey: string) => {
    setDetailLoading(true);
    setDetailModalOpen(true);
    try {
      const detail = await sessionApi.getSessionDetail(sessionKey);
      setSelectedSession(detail);
    } catch (err) {
      toast.error(`获取会话详情失败: ${err}`);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleResetSession = async (sessionKey: string) => {
    if (!confirm('确定要重置此会话吗？')) return;
    try {
      await sessionApi.resetSession(sessionKey);
      toast.success('会话已重置');
      fetchSessions();
    } catch {
      toast.error('重置失败');
    }
  };

  const handleSuspendSession = async (sessionKey: string) => {
    if (!confirm('确定要挂起此会话吗？')) return;
    try {
      await sessionApi.suspendSession(sessionKey);
      toast.success('会话已挂起');
      fetchSessions();
    } catch {
      toast.error('挂起失败');
    }
  };

  const filteredSessions = sessions.filter((s) => {
    if (platformFilter !== 'all' && s.platform !== platformFilter) return false;
    return true;
  });

  const formatTime = (dateStr: string) => {
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
        return <Badge variant="success">运行中</Badge>;
      case 'paused':
        return <Badge variant="warning">已暂停</Badge>;
      default:
        return <Badge>{status}</Badge>;
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header */}
      <div>
        <h1 style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '4px' }}>
          会话管理
        </h1>
        <p style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
          查看和管理与 Bot 的对话记录
        </p>
      </div>

      {/* Filters */}
      <Card style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: '12px', border: '1px solid var(--border-subtle)' }}>
        <CardContent style={{ padding: '16px' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'center' }}>
            <select
              value={platformFilter}
              onChange={(e) => setPlatformFilter(e.target.value)}
              style={{
                padding: '8px 32px 8px 12px',
                borderRadius: '6px',
                border: '1px solid var(--border-subtle)',
                backgroundColor: 'var(--bg-tertiary)',
                color: 'var(--text-primary)',
                fontSize: '13px',
                cursor: 'pointer',
                outline: 'none',
                appearance: 'none',
              }}
            >
              <option value="all">全部平台</option>
              <option value="cli">CLI</option>
              <option value="feishu">飞书</option>
            </select>
            <Button variant="secondary" size="sm" onClick={fetchSessions}>
              <RefreshCw style={{ width: '14px', height: '14px', marginRight: '4px' }} />
              刷新
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Session list */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--text-muted)' }}>
          加载中...
        </div>
      ) : filteredSessions.length === 0 ? (
        <Card style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: '12px', border: '1px solid var(--border-subtle)' }}>
          <CardContent style={{ padding: '48px 0', textAlign: 'center' }}>
            <MessageSquare style={{ width: '48px', height: '48px', margin: '0 auto 16px', color: 'var(--text-muted)', opacity: 0.5 }} />
            <p style={{ color: 'var(--text-muted)' }}>暂无会话</p>
          </CardContent>
        </Card>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {filteredSessions.map((session) => (
            <Card
              key={session.session_key}
              style={{
                backgroundColor: 'var(--bg-secondary)',
                borderRadius: '12px',
                border: '1px solid var(--border-subtle)',
                cursor: 'pointer',
                transition: 'all 150ms ease',
              }}
              onClick={() => handleViewDetail(session.session_key)}
            >
              <CardContent style={{ padding: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  {/* Left section */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div
                      style={{
                        padding: '10px',
                        borderRadius: '8px',
                        backgroundColor: 'var(--bg-tertiary)',
                      }}
                    >
                      <MessageSquare style={{ width: '20px', height: '20px', color: 'var(--accent)' }} />
                    </div>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                        <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                          {session.user || session.session_id.slice(0, 8)}
                        </span>
                        {getStatusBadge(session.status)}
                      </div>
                      <div style={{ display: 'flex', gap: '16px', fontSize: '12px', color: 'var(--text-muted)' }}>
                        <span>{session.platform}</span>
                        <span>{formatTime(session.updated_at)}</span>
                        <span>{session.total_tokens.toLocaleString()} 字符</span>
                      </div>
                    </div>
                  </div>

                  {/* Right section */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleResetSession(session.session_key);
                      }}
                      style={{ fontSize: '13px' }}
                    >
                      重置
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleSuspendSession(session.session_key);
                      }}
                      style={{ fontSize: '13px' }}
                    >
                      挂起
                    </Button>
                    <ChevronRight style={{ width: '20px', height: '20px', color: 'var(--text-muted)' }} />
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Detail Modal */}
      <Modal
        isOpen={detailModalOpen}
        onClose={() => setDetailModalOpen(false)}
        title="会话详情"
      >
        {detailLoading ? (
          <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-muted)' }}>
            加载中...
          </div>
        ) : selectedSession ? (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div style={{ backgroundColor: 'var(--bg-tertiary)', borderRadius: '8px', padding: '16px' }}>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>输入字符</div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)' }}>
                {selectedSession.input_tokens.toLocaleString()}
              </div>
            </div>
            <div style={{ backgroundColor: 'var(--bg-tertiary)', borderRadius: '8px', padding: '16px' }}>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>输出字符</div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)' }}>
                {selectedSession.output_tokens.toLocaleString()}
              </div>
            </div>
            <div style={{ backgroundColor: 'var(--bg-tertiary)', borderRadius: '8px', padding: '16px' }}>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>预估费用</div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)' }}>
                ${selectedSession.estimated_cost_usd.toFixed(4)}
              </div>
            </div>
            <div style={{ backgroundColor: 'var(--bg-tertiary)', borderRadius: '8px', padding: '16px' }}>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>总字符</div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)' }}>
                {(selectedSession.input_tokens + selectedSession.output_tokens).toLocaleString()}
              </div>
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
