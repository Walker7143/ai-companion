import { useEffect, useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../../components/ui';
import { useLogStore } from '../../stores';
import type { LogEntry } from '../../types';

export function Logs() {
  const { logs, fetchLogs, loading } = useLogStore();
  const [page, setPage] = useState(1);

  useEffect(() => {
    fetchLogs({ page, pageSize: 20 });
  }, [page, fetchLogs]);

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
        <CardContent>
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
                  <span style={{ color: log.level === 'error' ? 'var(--error)' : log.level === 'warning' ? 'var(--warning)' : 'var(--text-secondary)' }}>
                    [{log.level.toUpperCase()}]
                  </span>{' '}
                  <span style={{ color: 'var(--text-primary)' }}>{log.message}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
