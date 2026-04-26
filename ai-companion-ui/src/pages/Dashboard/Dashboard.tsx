import { useEffect, useState, useCallback } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Activity, MessageSquare, Brain, FileText, Cpu, HardDrive } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '../../components/ui';
import { useBotStore } from '../../stores';
import { useToast } from '../../components/ui/Toast';
import type { SystemMetrics, BotMetrics } from '../../types';

export function Dashboard() {
  const { currentBotId, setBots } = useBotStore();
  const toast = useToast();

  const [systemMetrics, setSystemMetrics] = useState<SystemMetrics | null>(null);
  const [botMetrics, setBotMetrics] = useState<BotMetrics | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchBots = useCallback(async () => {
    try {
      const botsData = await invoke<{ id: string; name: string; status: string }[]>('get_available_bots');
      setBots(botsData.map(b => ({ id: b.id, name: b.name })));
    } catch (err) {
      console.error('Failed to fetch bots:', err);
    }
  }, [setBots]);

  const fetchMetrics = useCallback(async () => {
    try {
      const [sysMetrics, bMetrics] = await Promise.all([
        invoke<SystemMetrics>('get_system_metrics'),
        invoke<BotMetrics>('get_bot_metrics', { botId: currentBotId || 'suqing' }),
      ]);
      setSystemMetrics(sysMetrics);
      setBotMetrics(bMetrics);
    } catch (err) {
      toast('error', `获取监控数据失败: ${err}`);
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

  if (loading && !systemMetrics) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">监控面板</h1>
          <p className="text-text-secondary mt-1">实时监控 AI 伴侣的运行状态</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="bg-bg-secondary border border-border-subtle rounded-lg p-4 animate-pulse">
              <div className="h-8 bg-bg-tertiary rounded mb-2" />
              <div className="h-4 bg-bg-tertiary rounded w-2/3" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">监控面板</h1>
        <p className="text-text-secondary mt-1">实时监控 AI 伴侣的运行状态</p>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardContent className="flex items-center gap-4">
            <div className="p-3 bg-accent/20 rounded-lg">
              <MessageSquare className="w-6 h-6 text-accent" />
            </div>
            <div>
              <div className="text-2xl font-bold text-accent">
                {botMetrics?.conversations_today ?? 0}
              </div>
              <div className="text-sm text-text-secondary">今日会话</div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex items-center gap-4">
            <div className="p-3 bg-success/20 rounded-lg">
              <Activity className="w-6 h-6 text-success" />
            </div>
            <div>
              <div className="text-2xl font-bold text-success">
                {systemMetrics?.uptime_seconds ? formatUptime(systemMetrics.uptime_seconds) : '--'}
              </div>
              <div className="text-sm text-text-secondary">运行时长</div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex items-center gap-4">
            <div className="p-3 bg-warning/20 rounded-lg">
              <Brain className="w-6 h-6 text-warning" />
            </div>
            <div>
              <div className="text-2xl font-bold text-warning">
                {(botMetrics?.memory_stats.working_count ?? 0) +
                  (botMetrics?.memory_stats.episodic_count ?? 0) +
                  (botMetrics?.memory_stats.semantic_count ?? 0)}
              </div>
              <div className="text-sm text-text-secondary">记忆条目</div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex items-center gap-4">
            <div className="p-3 bg-info/20 rounded-lg">
              <FileText className="w-6 h-6 text-info" />
            </div>
            <div>
              <div className="text-2xl font-bold text-info">
                {botMetrics?.status === 'running' ? '运行中' : '已停止'}
              </div>
              <div className="text-sm text-text-secondary">Bot 状态</div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* System Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Cpu className="w-5 h-5" />
              CPU 使用率
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-text-secondary">当前使用</span>
                <span className="font-medium text-text-primary">
                  {systemMetrics?.cpu_percent.toFixed(1) ?? '0'}%
                </span>
              </div>
              <div className="w-full bg-bg-tertiary rounded-full h-2">
                <div
                  className="bg-accent h-2 rounded-full transition-all duration-300"
                  style={{ width: `${systemMetrics?.cpu_percent ?? 0}%` }}
                />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <HardDrive className="w-5 h-5" />
              内存使用
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-text-secondary">已用 / 总计</span>
                <span className="font-medium text-text-primary">
                  {systemMetrics?.memory_used_mb ?? 0} MB / {((systemMetrics?.memory_used_mb ?? 0) / ((systemMetrics?.memory_percent ?? 1) / 100)).toFixed(0)} MB
                </span>
              </div>
              <div className="w-full bg-bg-tertiary rounded-full h-2">
                <div
                  className="bg-info h-2 rounded-full transition-all duration-300"
                  style={{ width: `${systemMetrics?.memory_percent ?? 0}%` }}
                />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Bot Metrics Details */}
      {botMetrics && (
        <Card>
          <CardHeader>
            <CardTitle>Bot 运行时统计</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="text-center p-3 bg-bg-tertiary rounded-lg">
                <div className="text-lg font-bold text-text-primary">
                  {botMetrics.conversations_today}
                </div>
                <div className="text-xs text-text-secondary">今日会话</div>
              </div>
              <div className="text-center p-3 bg-bg-tertiary rounded-lg">
                <div className="text-lg font-bold text-text-primary">
                  {botMetrics.proactive_messages_today}
                </div>
                <div className="text-xs text-text-secondary">主动消息</div>
              </div>
              <div className="text-center p-3 bg-bg-tertiary rounded-lg">
                <div className="text-lg font-bold text-text-primary">
                  {botMetrics.input_tokens_today.toLocaleString()}
                </div>
                <div className="text-xs text-text-secondary">输入 Token</div>
              </div>
              <div className="text-center p-3 bg-bg-tertiary rounded-lg">
                <div className="text-lg font-bold text-text-primary">
                  {botMetrics.output_tokens_today.toLocaleString()}
                </div>
                <div className="text-xs text-text-secondary">输出 Token</div>
              </div>
            </div>

            <div className="mt-4 pt-4 border-t border-border-subtle">
              <h4 className="text-sm font-medium text-text-primary mb-3">记忆统计</h4>
              <div className="grid grid-cols-3 gap-4">
                <div className="text-center p-3 bg-bg-tertiary rounded-lg">
                  <div className="text-lg font-bold text-text-primary">
                    {botMetrics.memory_stats.working_count}
                  </div>
                  <div className="text-xs text-text-secondary">工作记忆</div>
                </div>
                <div className="text-center p-3 bg-bg-tertiary rounded-lg">
                  <div className="text-lg font-bold text-text-primary">
                    {botMetrics.memory_stats.episodic_count}
                  </div>
                  <div className="text-xs text-text-secondary">情景记忆</div>
                </div>
                <div className="text-center p-3 bg-bg-tertiary rounded-lg">
                  <div className="text-lg font-bold text-text-primary">
                    {botMetrics.memory_stats.semantic_count}
                  </div>
                  <div className="text-xs text-text-secondary">语义记忆</div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}