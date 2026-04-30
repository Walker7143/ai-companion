import { useEffect, useState } from 'react';
import { Activity, RefreshCw, Zap } from 'lucide-react';
import { configApi, systemApi } from '../../api';
import { useBotStore } from '../../stores';
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, useToast } from '../../components/ui';
import type { BotConfig, BotMetrics } from '../../types';

export function Operations() {
  const { currentBotId } = useBotStore();
  const toast = useToast();
  const [config, setConfig] = useState<BotConfig | null>(null);
  const [metrics, setMetrics] = useState<BotMetrics | null>(null);

  const load = async () => {
    if (!currentBotId) return;
    try {
      const [cfg, m] = await Promise.all([
        configApi.getConfig(currentBotId),
        systemApi.getBotMetrics(currentBotId),
      ]);
      setConfig(cfg);
      setMetrics(m);
    } catch (err) {
      toast.error(`读取运营数据失败: ${err}`);
    }
  };

  useEffect(() => {
    load();
  }, [currentBotId]);

  const proactive = config?.proactive;
  const life = config?.life;
  const lifeStatus = config?.diagnostics?.life_status || {};

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)' }}>主动唤醒与人生轨迹</h1>
          <p style={{ fontSize: 14, color: 'var(--text-secondary)' }}>观察主动消息频率、冷却策略、Bot 当前人生状态</p>
        </div>
        <Button variant="secondary" onClick={load}><RefreshCw size={14} style={{ marginRight: 4 }} />刷新</Button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>
        <Card>
          <CardHeader><CardTitle style={{ display: 'flex', gap: 8, alignItems: 'center' }}><Zap size={18} />主动唤醒</CardTitle></CardHeader>
          <CardContent style={{ display: 'grid', gap: 10, color: 'var(--text-secondary)' }}>
            <div>状态：<Badge variant={proactive?.enabled ? 'success' : 'warning'}>{proactive?.enabled ? '启用' : '关闭'}</Badge></div>
            <div>模式：{proactive?.mode || '--'}</div>
            <div>检查间隔：{proactive?.check_interval_seconds ?? '--'} 秒</div>
            <div>空闲阈值：{proactive?.idle_threshold_hours ?? '--'} 小时</div>
            <div>每日上限：{proactive?.max_daily ?? '--'} 条</div>
            <div>今日主动消息：{metrics?.proactive_messages_today ?? 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle style={{ display: 'flex', gap: 8, alignItems: 'center' }}><Activity size={18} />人生轨迹</CardTitle></CardHeader>
          <CardContent style={{ display: 'grid', gap: 10, color: 'var(--text-secondary)' }}>
            <div>时间倍率：{life?.time_ratio ?? '--'}x</div>
            <div>日常间隔：{life?.daily_interval_seconds ?? '--'} 秒</div>
            <div>大事间隔：{life?.major_interval_seconds ?? '--'} 秒</div>
            <div>当前日期：{String(lifeStatus.current_date || '--')}</div>
            <div>当前年龄：{String(lifeStatus.bot_real_age || '--')}</div>
            <div>当前心情：{String(lifeStatus.bot_mood || '--')}</div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Life 状态快照</CardTitle></CardHeader>
        <CardContent>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, color: 'var(--text-secondary)' }}>{JSON.stringify(lifeStatus, null, 2)}</pre>
        </CardContent>
      </Card>
    </div>
  );
}
