import { useEffect, useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent, Button, Input, Select, Badge } from '../../components/ui';
import { useBotStore, useLogStore } from '../../stores';
import type { LogEntry } from '../../types';

export function Logs() {
  const { currentBotId } = useBotStore();
  const { logs, fetchLogs, loading, page, totalPages, streaming, startStreaming, stopStreaming } = useLogStore();
  const [level, setLevel] = useState('all');
  const [query, setQuery] = useState('');

  useEffect(() => {
    fetchLogs({ botId: currentBotId || '', page: 1, pageSize: 20, level });
  }, [currentBotId, fetchLogs, level]);

  const runSearch = () => {
    fetchLogs({ botId: currentBotId || '', page: 1, pageSize: 20, level, query });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div>
        <h1 style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '4px' }}>
          日志
        </h1>
        <p style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
          查看 Bot 运行日志
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>日志列表</CardTitle>
        </CardHeader>
        <CardContent style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <Select
              value={level}
              onChange={(e) => setLevel(e.target.value)}
              style={{ maxWidth: '140px' }}
              options={[
                { value: 'all', label: '全部级别' },
                { value: 'debug', label: 'DEBUG' },
                { value: 'info', label: 'INFO' },
                { value: 'warning', label: 'WARNING' },
                { value: 'error', label: 'ERROR' },
              ]}
            />
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索日志内容" style={{ maxWidth: '260px' }} />
            <Button variant="secondary" onClick={runSearch}>筛选</Button>
            <Button
              variant={streaming ? 'danger' : 'secondary'}
              onClick={() => streaming ? stopStreaming() : startStreaming(currentBotId || '', level === 'all' ? undefined : level)}
            >
              {streaming ? '停止实时流' : '开启实时流'}
            </Button>
          </div>
          {loading ? (
            <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)' }}>
              加载中...
            </div>
          ) : logs.length === 0 ? (
            <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)' }}>
              暂无日志
            </div>
          ) : (
            <div style={{ fontFamily: 'monospace', fontSize: '12px' }}>
              {logs.map((log: LogEntry, i) => (
                <div
                  key={i}
                  style={{
                    padding: '8px 12px',
                    borderBottom: '1px solid var(--border-subtle)',
                  }}
                >
                  <span style={{ color: 'var(--text-muted)' }}>{log.timestamp}</span>{' '}
                  <Badge variant={log.level === 'error' ? 'error' : log.level === 'warning' ? 'warning' : 'default'}>{log.level.toUpperCase()}</Badge>{' '}
                  <span style={{ color: 'var(--text-muted)' }}>[{log.platform}]</span>{' '}
                  <span style={{ color: 'var(--text-primary)' }}>{log.message}</span>
                  {log.details && (
                    <details style={{ marginTop: '6px', color: 'var(--text-muted)', whiteSpace: 'pre-wrap' }}>
                      <summary>详情</summary>
                      {log.details}
                    </details>
                  )}
                </div>
              ))}
            </div>
          )}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Button variant="secondary" disabled={page <= 1} onClick={() => fetchLogs({ botId: currentBotId || '', page: page - 1, pageSize: 20, level, query })}>上一页</Button>
            <span style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>第 {page} / {totalPages || 1} 页</span>
            <Button variant="secondary" disabled={page >= (totalPages || 1)} onClick={() => fetchLogs({ botId: currentBotId || '', page: page + 1, pageSize: 20, level, query })}>下一页</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
