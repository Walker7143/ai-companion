import { useEffect, useState } from 'react';
import { Brain, Save, RefreshCw } from 'lucide-react';
import { memoryApi } from '../../api';
import { useBotStore } from '../../stores';
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, useToast } from '../../components/ui';

function stringify(data: unknown) {
  return JSON.stringify(data ?? {}, null, 2);
}

export function Understanding() {
  const { currentBotId } = useBotStore();
  const toast = useToast();
  const [data, setData] = useState<Record<string, unknown>>({});
  const [manualText, setManualText] = useState('{}');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [path, setPath] = useState<string | null>(null);

  const load = async () => {
    if (!currentBotId) return;
    setLoading(true);
    try {
      const payload = await memoryApi.getUnderstanding(currentBotId);
      setData(payload.data || {});
      setPath(payload.path || null);
      const manual = (payload.data?.manual || {}) as Record<string, unknown>;
      setManualText(stringify(manual));
    } catch (err) {
      toast.error(`读取用户理解失败: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [currentBotId]);

  const save = async () => {
    if (!currentBotId) return;
    setSaving(true);
    try {
      const manual = JSON.parse(manualText);
      const next = { ...data, manual };
      const payload = await memoryApi.updateUnderstanding(currentBotId, next);
      setData(payload.data || next);
      toast.success('用户理解已保存');
    } catch (err) {
      toast.error(`保存失败: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  const auto = (data.auto || {}) as Record<string, unknown>;
  const relationship = (data.relationship_memory || {}) as Record<string, unknown>;
  const meta = (data.meta || {}) as Record<string, unknown>;

  if (loading) return <div style={{ color: 'var(--text-muted)' }}>加载中...</div>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '4px' }}>用户理解</h1>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>编辑 manual，审阅 auto 和关系记忆，让 Bot 更懂用户</p>
          {path && <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>{path}</p>}
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <Button variant="secondary" onClick={load}><RefreshCw style={{ width: 14, height: 14, marginRight: 4 }} />刷新</Button>
          <Button onClick={save} disabled={saving}><Save style={{ width: 14, height: 14, marginRight: 4 }} />{saving ? '保存中' : '保存 manual'}</Button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: '16px' }}>
        <Card>
          <CardHeader><CardTitle>Manual 手动理解</CardTitle></CardHeader>
          <CardContent>
            <textarea
              value={manualText}
              onChange={(e) => setManualText(e.target.value)}
              rows={26}
              style={{
                width: '100%',
                fontFamily: 'monospace',
                fontSize: '12px',
                color: 'var(--text-primary)',
                backgroundColor: 'var(--bg-tertiary)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '8px',
                padding: '12px',
              }}
            />
          </CardContent>
        </Card>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <Card>
            <CardHeader><CardTitle style={{ display: 'flex', gap: 8, alignItems: 'center' }}><Brain size={18} />Auto 自动理解</CardTitle></CardHeader>
            <CardContent>
              <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, color: 'var(--text-secondary)' }}>{stringify(auto)}</pre>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Relationship Memory</CardTitle></CardHeader>
            <CardContent>
              <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, color: 'var(--text-secondary)' }}>{stringify(relationship)}</pre>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>冲突与置信度</CardTitle></CardHeader>
            <CardContent style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {((meta.contradictions as string[]) || []).length === 0 && ((meta.confidence_notes as string[]) || []).length === 0 ? (
                <span style={{ color: 'var(--text-muted)' }}>暂无冲突</span>
              ) : (
                <>
                  {((meta.contradictions as string[]) || []).map((item, idx) => <Badge key={`c-${idx}`} variant="warning">{item}</Badge>)}
                  {((meta.confidence_notes as string[]) || []).map((item, idx) => <Badge key={`n-${idx}`}>{item}</Badge>)}
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
