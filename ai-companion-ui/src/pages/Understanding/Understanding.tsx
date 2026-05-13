import { useEffect, useState } from 'react';
import { Brain, Save, RefreshCw, Sparkles, HeartHandshake, AlertTriangle } from 'lucide-react';
import { memoryApi } from '../../api';
import { useBotStore } from '../../stores';
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, useToast } from '../../components/ui';

function stringify(data: unknown) {
  return JSON.stringify(data ?? {}, null, 2);
}

const heroStyle: React.CSSProperties = {
  borderRadius: '18px',
  padding: '24px',
  border: '1px solid var(--border-subtle)',
  background: 'linear-gradient(135deg, var(--accent-light), var(--bg-secondary) 55%, var(--bg-tertiary))',
  boxShadow: 'var(--shadow-sm)',
};

function CodeBlock({ children, maxHeight = 360 }: { children: string; maxHeight?: number }) {
  return (
    <pre
      style={{
        whiteSpace: 'pre-wrap',
        maxHeight,
        overflow: 'auto',
        fontSize: 12,
        lineHeight: 1.6,
        color: 'var(--text-secondary)',
        backgroundColor: 'var(--bg-tertiary)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 10,
        padding: 14,
      }}
    >
      {children}
    </pre>
  );
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
  const layered = (data.layered || {}) as Record<string, unknown>;
  const meta = (data.meta || {}) as Record<string, unknown>;

  if (loading) return <div style={{ color: 'var(--text-muted)' }}>加载中...</div>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div style={{ ...heroStyle, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <Sparkles size={22} color="var(--accent)" />
            <h1 style={{ fontSize: '26px', fontWeight: 800, color: 'var(--text-primary)' }}>用户理解</h1>
          </div>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)', maxWidth: 720 }}>
            把 Bot 对用户的理解拆成可手动校准的 manual、自动沉淀的 auto、关系记忆，以及用于聊天投影的分层画像。
          </p>
          {path && <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '8px' }}>{path}</p>}
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <Button variant="secondary" onClick={load}><RefreshCw style={{ width: 14, height: 14, marginRight: 4 }} />刷新</Button>
          <Button onClick={save} disabled={saving}><Save style={{ width: 14, height: 14, marginRight: 4 }} />{saving ? '保存中' : '保存 manual'}</Button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
        <Card><CardContent style={{ padding: 16 }}><Badge variant="info">Manual 优先</Badge><p style={{ marginTop: 8, color: 'var(--text-secondary)', fontSize: 13 }}>用户手动写的内容永不被 auto 覆盖。</p></CardContent></Card>
        <Card><CardContent style={{ padding: 16 }}><Badge variant="success">Auto 沉淀</Badge><p style={{ marginTop: 8, color: 'var(--text-secondary)', fontSize: 13 }}>系统会从对话和关系状态中持续整理理解。</p></CardContent></Card>
        <Card><CardContent style={{ padding: 16 }}><Badge variant="info">Layered 投影</Badge><p style={{ marginTop: 8, color: 'var(--text-secondary)', fontSize: 13 }}>聊天时优先使用 core、current、deep、sensitive 四层小画像。</p></CardContent></Card>
        <Card><CardContent style={{ padding: 16 }}><Badge variant="warning">冲突可见</Badge><p style={{ marginTop: 8, color: 'var(--text-secondary)', fontSize: 13 }}>自动理解和手动理解冲突时会进入 meta。</p></CardContent></Card>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.05fr) minmax(0, 0.95fr)', gap: '16px' }}>
        <Card variant="elevated">
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
                borderRadius: '12px',
                padding: '14px',
                minHeight: 520,
              }}
            />
          </CardContent>
        </Card>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <Card variant="elevated">
            <CardHeader><CardTitle style={{ display: 'flex', gap: 8, alignItems: 'center' }}><Brain size={18} />Auto 自动理解</CardTitle></CardHeader>
            <CardContent>
              <CodeBlock>{stringify(auto)}</CodeBlock>
            </CardContent>
          </Card>
          <Card variant="elevated">
            <CardHeader><CardTitle style={{ display: 'flex', gap: 8, alignItems: 'center' }}><HeartHandshake size={18} />Relationship Memory</CardTitle></CardHeader>
            <CardContent>
              <CodeBlock maxHeight={260}>{stringify(relationship)}</CodeBlock>
            </CardContent>
          </Card>
          <Card variant="elevated">
            <CardHeader><CardTitle style={{ display: 'flex', gap: 8, alignItems: 'center' }}><Sparkles size={18} />Layered Prompt Projection</CardTitle></CardHeader>
            <CardContent>
              <CodeBlock maxHeight={300}>{stringify(layered)}</CodeBlock>
            </CardContent>
          </Card>
          <Card variant="elevated">
            <CardHeader><CardTitle style={{ display: 'flex', gap: 8, alignItems: 'center' }}><AlertTriangle size={18} />冲突与置信度</CardTitle></CardHeader>
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
