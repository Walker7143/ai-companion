import { useEffect, useState } from 'react';
import { Save, RefreshCw, Wand2, MessageCircle, ShieldCheck, Sparkles } from 'lucide-react';
import { personaApi } from '../../api';
import { useBotStore } from '../../stores';
import { Button, Card, CardContent, CardHeader, CardTitle, useToast } from '../../components/ui';

const defaultStyle = {
  reply_principles: [],
  avoid_phrases: [],
  avoid_patterns: [],
  natural_patterns: [],
  intent_style: {},
};

const heroStyle: React.CSSProperties = {
  borderRadius: '18px',
  padding: '24px',
  border: '1px solid var(--border-subtle)',
  background: 'linear-gradient(135deg, var(--warning-light), var(--bg-secondary) 55%, var(--bg-tertiary))',
  boxShadow: 'var(--shadow-sm)',
};

export function StyleLab() {
  const { currentBotId } = useBotStore();
  const toast = useToast();
  const [styleText, setStyleText] = useState(JSON.stringify(defaultStyle, null, 2));
  const [path, setPath] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    if (!currentBotId) return;
    try {
      const payload = await personaApi.getConversationStyle(currentBotId);
      setStyleText(JSON.stringify(payload.data || defaultStyle, null, 2));
      setPath(payload.path || null);
    } catch (err) {
      toast.error(`读取对话风格失败: ${err}`);
    }
  };

  useEffect(() => {
    load();
  }, [currentBotId]);

  const save = async () => {
    if (!currentBotId) return;
    setSaving(true);
    try {
      const data = JSON.parse(styleText);
      const payload = await personaApi.updateConversationStyle(currentBotId, data);
      setStyleText(JSON.stringify(payload.data || data, null, 2));
      toast.success('对话风格已保存');
    } catch (err) {
      toast.error(`保存失败: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div style={{ ...heroStyle, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <Wand2 size={22} color="var(--warning)" />
            <h1 style={{ fontSize: 26, fontWeight: 800, color: 'var(--text-primary)' }}>人格与对话风格</h1>
          </div>
          <p style={{ fontSize: 14, color: 'var(--text-secondary)', maxWidth: 720 }}>
            把“怎么说话”和“不要怎么说话”从人格故事里拆出来，让 Bot 更稳定、更少 AI 味。
          </p>
          {path && <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 8 }}>{path}</p>}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button variant="secondary" onClick={load}><RefreshCw size={14} style={{ marginRight: 4 }} />刷新</Button>
          <Button onClick={save} disabled={saving}><Save size={14} style={{ marginRight: 4 }} />{saving ? '保存中' : '保存'}</Button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
        <Card><CardContent style={{ padding: 16 }}><MessageCircle size={20} color="var(--accent)" /><h3 style={{ marginTop: 8, color: 'var(--text-primary)' }}>场景分寸</h3><p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>情绪、任务、修复、闲聊分别定义口吻。</p></CardContent></Card>
        <Card><CardContent style={{ padding: 16 }}><ShieldCheck size={20} color="var(--success)" /><h3 style={{ marginTop: 8, color: 'var(--text-primary)' }}>反 AI 规则</h3><p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>统一禁用客服式和模板式表达。</p></CardContent></Card>
        <Card><CardContent style={{ padding: 16 }}><Sparkles size={20} color="var(--warning)" /><h3 style={{ marginTop: 8, color: 'var(--text-primary)' }}>自然表达</h3><p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>允许短句、停顿、个人反应。</p></CardContent></Card>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 360px', gap: 16 }}>
        <Card variant="elevated">
          <CardHeader><CardTitle>conversation_style_rules.json</CardTitle></CardHeader>
          <CardContent>
            <textarea
              value={styleText}
              onChange={(e) => setStyleText(e.target.value)}
              rows={30}
              style={{ width: '100%', minHeight: 560, fontFamily: 'monospace', fontSize: 12, lineHeight: 1.6, backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)', borderRadius: 12, padding: 14 }}
            />
          </CardContent>
        </Card>
        <Card variant="elevated">
          <CardHeader><CardTitle style={{ display: 'flex', gap: 8, alignItems: 'center' }}><Wand2 size={18} />调教建议</CardTitle></CardHeader>
          <CardContent style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.7 }}>
            <p>把“怎么说话”写在这里，比塞进 backstory 更稳。</p>
            <p>建议重点配置：</p>
            <ul>
              <li>禁用 AI/客服式表达。</li>
              <li>情绪支持少讲道理。</li>
              <li>任务请求直接完成。</li>
              <li>关系修复时收起调侃。</li>
            </ul>
            <p>保存后下一轮对话会重新读取。</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
