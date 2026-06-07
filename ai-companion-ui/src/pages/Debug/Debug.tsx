import { useEffect, useState } from 'react';
import { Bug, BrainCircuit, FileSearch, RefreshCw, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';
import { debugApi } from '../../api';
import { useBotStore } from '../../stores';
import { Button, Card, CardContent, CardHeader, CardTitle, useToast } from '../../components/ui';
import type { DebugContextPayload, EvolutionRefsView, EvolutionTimelineItem } from '../../types';

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
  const diagnostics = (ctx?.memory_prompt_diagnostics || {}) as Record<string, unknown>;
  const budget = (diagnostics.prompt_budget || {}) as Record<string, unknown>;
  const blocks = (budget.blocks || {}) as Record<string, unknown>;
  const blockEntries = Object.entries(blocks).map(([name, value]) => ({ name, value: value as Record<string, unknown> }));
  const evolutionRefs = ctx?.evolution_refs;
  const heroStyle: React.CSSProperties = {
    borderRadius: 18,
    padding: 24,
    border: '1px solid var(--border-subtle)',
    background: 'linear-gradient(135deg, var(--error-light), var(--bg-secondary) 55%, var(--bg-tertiary))',
    boxShadow: 'var(--shadow-sm)',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div style={{ ...heroStyle, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <Bug size={22} color="var(--error)" />
            <h1 style={{ fontSize: 26, fontWeight: 800, color: 'var(--text-primary)' }}>调试与评估</h1>
          </div>
          <p style={{ fontSize: 14, color: 'var(--text-secondary)', maxWidth: 720 }}>排查一次回复背后的 prompt、记忆召回和风格处理。适合调试“为什么 Bot 这样说”。</p>
        </div>
        <Button variant="secondary" onClick={load}><RefreshCw size={14} style={{ marginRight: 4 }} />刷新</Button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
        <DebugCard icon={<FileSearch size={18} />} title="Prompt Inspector" data={ctx?.system_prompt} />
        <DebugCard icon={<BrainCircuit size={18} />} title="Memory Trace" data={ctx?.retrieved_memory} />
        <DebugCard icon={<Sparkles size={18} />} title="Response Style Trace" data={ctx?.response_style_trace} />
      </div>

      <EvolutionLinksCard botId={currentBotId || ''} refs={evolutionRefs} />

      <Card variant="elevated">
        <CardHeader><CardTitle style={{ display: 'flex', gap: 8, alignItems: 'center' }}><FileSearch size={18} />Prompt Budget</CardTitle></CardHeader>
        <CardContent>
          <div style={{ display: 'grid', gap: 12 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
              <Metric label="Suffix chars" value={String(diagnostics.system_suffix_chars ?? ctx?.system_prompt?.length ?? 0)} />
              <Metric label="Truncated" value={String(Boolean(diagnostics.prompt_truncated ?? budget.truncated))} />
              <Metric label="Blocks" value={String(diagnostics.prompt_block_count ?? blockEntries.length)} />
            </div>
            {blockEntries.length > 0 && (
              <div style={{ display: 'grid', gap: 10 }}>
                {blockEntries.map(({ name, value }) => (
                  <div key={name} style={{ padding: 12, borderRadius: 10, backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 8 }}>
                      <strong style={{ color: 'var(--text-primary)' }}>{name}</strong>
                      <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{String(value.budget_chars ?? 0)} chars</span>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
                      <span>raw {String(value.raw_body_chars ?? 0)}</span>
                      <span>final {String(value.final_body_chars ?? 0)}</span>
                      <span>rendered {String(value.rendered_chars ?? 0)}</span>
                      <span>{value.truncated ? 'truncated' : 'ok'}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <Card variant="elevated">
        <CardHeader><CardTitle style={{ display: 'flex', gap: 8, alignItems: 'center' }}><Bug size={18} />Working History</CardTitle></CardHeader>
        <CardContent>
          <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 420, overflow: 'auto', fontSize: 12, lineHeight: 1.6, color: 'var(--text-secondary)', backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border-subtle)', borderRadius: 12, padding: 14 }}>{JSON.stringify(ctx?.working_history || [], null, 2)}</pre>
        </CardContent>
      </Card>
    </div>
  );
}

function EvolutionLinksCard({ botId, refs }: { botId: string; refs?: EvolutionRefsView }) {
  const timeline = Array.isArray(refs?.timeline_preview) ? refs.timeline_preview : [];
  const diagnostics = refs?.diagnostics;

  return (
    <Card variant="elevated">
      <CardHeader>
        <CardTitle style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Sparkles size={18} />
          Evolution Links
        </CardTitle>
      </CardHeader>
      <CardContent style={{ display: 'grid', gap: 12 }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <span style={pillStyle}>活跃信号 {diagnostics?.captured_signal_count ?? 0}</span>
          <span style={pillStyle}>待晋升 {diagnostics?.pending_promotion_count ?? 0}</span>
          <span style={pillStyle}>抑制 {diagnostics?.suppressed_promotions ?? 0}</span>
        </div>
        {timeline.length === 0 ? (
          <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
            当前还没有可追踪的人格演化事件，等产生 signal / reflection / promotion 后这里会出现跳转入口。
          </div>
        ) : (
          <div style={{ display: 'grid', gap: 10 }}>
            {timeline.map((item) => (
              <EvolutionEventLink key={item.id} botId={botId} item={item} />
            ))}
          </div>
        )}
        <div>
          <Link to="/evolution" style={linkStyle}>
            打开完整人格演化页
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}

function EvolutionEventLink({ botId, item }: { botId: string; item: EvolutionTimelineItem }) {
  return (
    <Link
      to={`/evolution?bot=${encodeURIComponent(botId)}&event=${encodeURIComponent(item.id)}`}
      style={{
        display: 'grid',
        gap: 6,
        padding: 12,
        borderRadius: 10,
        border: '1px solid var(--border-subtle)',
        backgroundColor: 'var(--bg-tertiary)',
        textDecoration: 'none',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <strong style={{ color: 'var(--text-primary)', fontSize: 13 }}>{item.summary || item.event_type}</strong>
        <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>{item.dimension || 'mixed'}</span>
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
        {item.human_readable_reason || '查看本次演化原因与前后变化'}
      </div>
    </Link>
  );
}

const pillStyle: React.CSSProperties = {
  padding: '4px 10px',
  borderRadius: 999,
  fontSize: 12,
  color: 'var(--text-secondary)',
  backgroundColor: 'var(--bg-tertiary)',
  border: '1px solid var(--border-subtle)',
};

const linkStyle: React.CSSProperties = {
  color: 'var(--accent)',
  fontSize: 13,
  fontWeight: 600,
  textDecoration: 'none',
};

function DebugCard({ icon, title, data }: { icon: React.ReactNode; title: string; data: unknown }) {
  return (
    <Card variant="elevated">
      <CardHeader><CardTitle style={{ display: 'flex', gap: 8, alignItems: 'center' }}>{icon}{title}</CardTitle></CardHeader>
      <CardContent>
        <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 320, overflow: 'auto', fontSize: 12, lineHeight: 1.6, color: 'var(--text-secondary)', backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border-subtle)', borderRadius: 12, padding: 14 }}>{typeof data === 'string' ? data : JSON.stringify(data || {}, null, 2)}</pre>
      </CardContent>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div style={{ padding: 12, borderRadius: 10, backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border-subtle)' }}>
      <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>{value}</div>
    </div>
  );
}
