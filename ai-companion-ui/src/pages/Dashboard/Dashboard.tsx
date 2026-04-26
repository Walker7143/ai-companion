import { useEffect, useState, useCallback } from 'react';
import { Activity, MessageSquare, Brain, Zap, RefreshCw } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, Button } from '../../components/ui';
import { useBotStore } from '../../stores';
import { useToast } from '../../components/ui/Toast';
import { systemApi } from '../../api';
import type { SystemMetrics, BotMetrics } from '../../types';

function StatCard({
  title,
  value,
  subtitle,
  icon,
  accentColor,
}: {
  title: string;
  value: string | number;
  subtitle: string;
  icon: React.ReactNode;
  accentColor: string;
}) {
  return (
    <div
      style={{
        backgroundColor: 'var(--bg-secondary)',
        borderRadius: '12px',
        border: '1px solid var(--border-subtle)',
        padding: '20px',
        transition: 'all 200ms ease',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '4px' }}>
            {title}
          </p>
          <p style={{ fontSize: '28px', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.2 }}>
            {value}
          </p>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
            {subtitle}
          </p>
        </div>
        <div
          style={{
            padding: '10px',
            borderRadius: '10px',
            backgroundColor: accentColor,
          }}
        >
          {icon}
        </div>
      </div>
    </div>
  );
}

export function Dashboard() {
  const { currentBotId, fetchBots } = useBotStore();
  const toast = useToast();

  const [systemMetrics, setSystemMetrics] = useState<SystemMetrics | null>(null);
  const [botMetrics, setBotMetrics] = useState<BotMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState(new Date());

  const fetchMetrics = useCallback(async () => {
    try {
      const sysMetrics = await systemApi.getSystemMetrics();
      setSystemMetrics(sysMetrics);
      if (currentBotId) {
        const bMetrics = await systemApi.getBotMetrics(currentBotId);
        setBotMetrics(bMetrics);
      }
      setLastRefresh(new Date());
    } catch (err) {
      toast.error(`获取监控数据失败: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [currentBotId, toast]);

  useEffect(() => {
    fetchBots();
  }, [fetchBots]);

  useEffect(() => {
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 5000);
    return () => clearInterval(interval);
  }, [fetchMetrics]);

  const formatUptime = (seconds: number) => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    if (days > 0) return `${days}天 ${hours}小时`;
    if (hours > 0) return `${hours}小时 ${mins}分钟`;
    return `${mins}分钟`;
  };

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  if (loading && !systemMetrics) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        {/* Header skeleton */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ height: '32px', width: '120px', borderRadius: '6px', backgroundColor: 'var(--bg-tertiary)', marginBottom: '8px' }} />
            <div style={{ height: '16px', width: '200px', borderRadius: '4px', backgroundColor: 'var(--bg-tertiary)' }} />
          </div>
        </div>
        {/* Cards skeleton */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '16px' }}>
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              style={{
                height: '120px',
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

  const totalMemory =
    (botMetrics?.memory_stats.working_count ?? 0) +
    (botMetrics?.memory_stats.episodic_count ?? 0) +
    (botMetrics?.memory_stats.semantic_count ?? 0);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1
            style={{
              fontSize: '24px',
              fontWeight: 700,
              color: 'var(--text-primary)',
              marginBottom: '4px',
            }}
          >
            监控面板
          </h1>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
            实时监控 AI 伴侣的运行状态
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            最后更新: {formatTime(lastRefresh)}
          </span>
          <Button variant="secondary" size="sm" onClick={fetchMetrics}>
            <RefreshCw style={{ width: '14px', height: '14px', marginRight: '4px' }} />
            刷新
          </Button>
        </div>
      </div>

      {/* Status Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '16px',
        }}
      >
        <StatCard
          title="今日会话"
          value={botMetrics?.conversations_today ?? 0}
          subtitle="条对话"
          icon={<MessageSquare style={{ width: '20px', height: '20px', color: 'var(--accent)' }} />}
          accentColor="var(--accent-light)"
        />
        <StatCard
          title="运行时长"
          value={systemMetrics?.uptime_seconds ? formatUptime(systemMetrics.uptime_seconds) : '--'}
          subtitle="连续运行"
          icon={<Activity style={{ width: '20px', height: '20px', color: 'var(--success)' }} />}
          accentColor="var(--success-light)"
        />
        <StatCard
          title="记忆总数"
          value={totalMemory}
          subtitle="条记忆"
          icon={<Brain style={{ width: '20px', height: '20px', color: 'var(--warning)' }} />}
          accentColor="var(--warning-light)"
        />
        <StatCard
          title="Bot 状态"
          value={botMetrics?.status === 'running' ? '运行中' : '已停止'}
          subtitle={botMetrics?.status === 'running' ? '正常' : '需要重启'}
          icon={
            <Zap
              style={{
                width: '20px',
                height: '20px',
                color: botMetrics?.status === 'running' ? 'var(--success)' : 'var(--error)',
              }}
            />
          }
          accentColor={botMetrics?.status === 'running' ? 'var(--success-light)' : 'var(--error-light)'}
        />
      </div>

      {/* Bot Metrics Details */}
      {botMetrics && (
        <Card
          style={{
            backgroundColor: 'var(--bg-secondary)',
            borderRadius: '12px',
            border: '1px solid var(--border-subtle)',
            padding: '20px',
          }}
        >
          <CardHeader style={{ borderBottom: '1px solid var(--border-subtle)', padding: 0, marginBottom: '20px' }}>
            <CardTitle>会话统计</CardTitle>
          </CardHeader>
          <CardContent style={{ padding: 0 }}>
            {/* Stats grid */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
                gap: '12px',
                marginBottom: '24px',
              }}
            >
              {[
                { label: '今日会话', value: botMetrics.conversations_today },
                { label: '主动消息', value: botMetrics.proactive_messages_today },
                { label: '输入字符', value: botMetrics.input_tokens_today.toLocaleString() },
                { label: '输出字符', value: botMetrics.output_tokens_today.toLocaleString() },
              ].map((item) => (
                <div
                  key={item.label}
                  style={{
                    backgroundColor: 'var(--bg-tertiary)',
                    borderRadius: '8px',
                    padding: '16px',
                    textAlign: 'center',
                  }}
                >
                  <div
                    style={{
                      fontSize: '20px',
                      fontWeight: 700,
                      color: 'var(--text-primary)',
                    }}
                  >
                    {item.value}
                  </div>
                  <div
                    style={{
                      fontSize: '12px',
                      color: 'var(--text-secondary)',
                      marginTop: '4px',
                    }}
                  >
                    {item.label}
                  </div>
                </div>
              ))}
            </div>

            {/* Memory Distribution */}
            <div>
              <h4
                style={{
                  fontSize: '14px',
                  fontWeight: 600,
                  color: 'var(--text-primary)',
                  marginBottom: '12px',
                }}
              >
                记忆分布
              </h4>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(3, 1fr)',
                  gap: '12px',
                }}
              >
                {[
                  { label: '工作记忆', value: botMetrics.memory_stats.working_count, color: 'var(--accent)' },
                  { label: '情景记忆', value: botMetrics.memory_stats.episodic_count, color: 'var(--warning)' },
                  { label: '语义记忆', value: botMetrics.memory_stats.semantic_count, color: 'var(--info)' },
                ].map((item) => (
                  <div
                    key={item.label}
                    style={{
                      backgroundColor: 'var(--bg-tertiary)',
                      borderRadius: '8px',
                      padding: '16px',
                      textAlign: 'center',
                    }}
                  >
                    <div
                      style={{
                        fontSize: '24px',
                        fontWeight: 700,
                        color: item.color,
                      }}
                    >
                      {item.value}
                    </div>
                    <div
                      style={{
                        fontSize: '12px',
                        color: 'var(--text-secondary)',
                        marginTop: '4px',
                      }}
                    >
                      {item.label}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
