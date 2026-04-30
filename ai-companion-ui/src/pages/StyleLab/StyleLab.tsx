import { useEffect, useState } from 'react';
import { Save, RefreshCw, Wand2 } from 'lucide-react';
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)' }}>人格与对话风格</h1>
          <p style={{ fontSize: 14, color: 'var(--text-secondary)' }}>编辑 conversation_style_rules，控制 Bot 怎么说话、不要怎么说话</p>
          {path && <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>{path}</p>}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button variant="secondary" onClick={load}><RefreshCw size={14} style={{ marginRight: 4 }} />刷新</Button>
          <Button onClick={save} disabled={saving}><Save size={14} style={{ marginRight: 4 }} />{saving ? '保存中' : '保存'}</Button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 360px', gap: 16 }}>
        <Card>
          <CardHeader><CardTitle>conversation_style_rules.json</CardTitle></CardHeader>
          <CardContent>
            <textarea
              value={styleText}
              onChange={(e) => setStyleText(e.target.value)}
              rows={30}
              style={{ width: '100%', fontFamily: 'monospace', fontSize: 12, backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)', borderRadius: 8, padding: 12 }}
            />
          </CardContent>
        </Card>
        <Card>
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
