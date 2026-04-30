import { useEffect, useState } from 'react';
import { Bug, RefreshCw } from 'lucide-react';
import { debugApi } from '../../api';
import { useBotStore } from '../../stores';
import { Button, Card, CardContent, CardHeader, CardTitle, useToast } from '../../components/ui';
import type { DebugContextPayload } from '../../types';

export function Debug() {
  const { currentBotId } = useBotStore();
  const toast = useToast();
  const [payload, setPayload] = useState<DebugContextPayload | null>(null);

  const load = async () => {
    if (!currentBotId) return;
    try {
      setPayload(await debugApi.getLastContext(currentBotId));
    } catch (err) {
      toast.error(`读取调试上下文失败: ${err}`);
    }
  };

  useEffect(() => {
    load();
  }, [currentBotId]);

  const ctx = payload?.last_context;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)' }}>调试与评估</h1>
          <p style={{ fontSize: 14, color: 'var(--text-secondary)' }}>查看 prompt、记忆召回和回复风格追踪的调试摘要</p>
        </div>
        <Button variant="secondary" onClick={load}><RefreshCw size={14} style={{ marginRight: 4 }} />刷新</Button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
        <DebugCard title="Prompt Inspector" data={ctx?.system_prompt} />
        <DebugCard title="Memory Trace" data={ctx?.retrieved_memory} />
        <DebugCard title="Response Style Trace" data={ctx?.response_style_trace} />
      </div>

      <Card>
        <CardHeader><CardTitle style={{ display: 'flex', gap: 8, alignItems: 'center' }}><Bug size={18} />Working History</CardTitle></CardHeader>
        <CardContent>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, color: 'var(--text-secondary)' }}>{JSON.stringify(ctx?.working_history || [], null, 2)}</pre>
        </CardContent>
      </Card>
    </div>
  );
}

function DebugCard({ title, data }: { title: string; data: unknown }) {
  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent>
        <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, color: 'var(--text-secondary)' }}>{typeof data === 'string' ? data : JSON.stringify(data || {}, null, 2)}</pre>
      </CardContent>
    </Card>
  );
}
