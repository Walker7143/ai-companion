import { useEffect, useState, useCallback } from 'react';
import { Moon, Sun, TestTube, Save, RotateCcw } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, Toggle, Button, Input, Select, useToast } from '../../components/ui';
import { useThemeStore, useBotStore } from '../../stores';
import { configApi } from '../../api';
import type { BotConfig } from '../../types';

export function Settings() {
  const { theme, toggleTheme } = useThemeStore();
  const { currentBotId } = useBotStore();
  const toast = useToast();

  const [config, setConfig] = useState<BotConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  const [provider, setProvider] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [model, setModel] = useState('');
  const [temperature, setTemperature] = useState(0.8);
  const [maxTokens, setMaxTokens] = useState(1024);

  const [hasChanges, setHasChanges] = useState(false);

  const fetchConfig = useCallback(async () => {
    try {
      const data = await configApi.getConfig(currentBotId || 'suqing');
      setConfig(data);
      setProvider(data.model.provider);
      setApiKey(data.model.api_key);
      setBaseUrl(data.model.base_url);
      setModel(data.model.model);
      setTemperature(data.model.temperature);
      setMaxTokens(data.model.max_tokens);
    } catch (err) {
      toast.error(`获取配置失败: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [currentBotId, toast]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const handleFieldChange = (setter: (value: string) => void) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setter(e.target.value);
    setHasChanges(true);
  };

  const handleNumberChange = (setter: (value: number) => void) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setter(Number(e.target.value));
    setHasChanges(true);
  };

  const handleSave = async () => {
    if (!config) return;

    setSaving(true);
    try {
      const newConfig: Partial<BotConfig> = {
        model: {
          provider,
          api_key: apiKey,
          base_url: baseUrl,
          model,
          temperature,
          max_tokens: maxTokens,
        },
      };
      await configApi.updateConfig(config.bot_id, newConfig);
      toast.success('配置已保存');
      setHasChanges(false);
      fetchConfig();
    } catch (err) {
      toast.error(`保存配置失败: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    if (config) {
      setProvider(config.model.provider);
      setApiKey(config.model.api_key);
      setBaseUrl(config.model.base_url);
      setModel(config.model.model);
      setTemperature(config.model.temperature);
      setMaxTokens(config.model.max_tokens);
      setHasChanges(false);
    }
  };

  const handleTestConnection = async () => {
    setTesting(true);
    try {
      const result = await configApi.testConnection(provider, apiKey, baseUrl);
      if (result) {
        toast.success('API 连接测试成功');
      } else {
        toast.error('API 连接测试失败');
      }
    } catch (err) {
      toast.error(`测试连接失败: ${err}`);
    } finally {
      setTesting(false);
    }
  };

  const providerOptions = [
    { value: 'minimax', label: 'MiniMax' },
    { value: 'openai', label: 'OpenAI' },
    { value: 'anthropic', label: 'Anthropic' },
    { value: 'ollama', label: 'Ollama' },
    { value: 'custom', label: '自定义' },
  ];

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '4px' }}>
            设置
          </h1>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
            配置 AI 伴侣的各项功能
          </p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {[...Array(3)].map((_, i) => (
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header */}
      <div>
        <h1 style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '4px' }}>
          设置
        </h1>
        <p style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
          配置 AI 伴侣的各项功能
        </p>
      </div>

      {/* Appearance */}
      <Card style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: '12px', border: '1px solid var(--border-subtle)' }}>
        <CardHeader style={{ borderBottom: 'none', padding: '16px 20px' }}>
          <CardTitle>外观</CardTitle>
        </CardHeader>
        <CardContent style={{ padding: '16px 20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              {theme === 'dark' ? (
                <Moon style={{ width: '20px', height: '20px', color: 'var(--text-primary)' }} />
              ) : (
                <Sun style={{ width: '20px', height: '20px', color: 'var(--text-primary)' }} />
              )}
              <div>
                <div style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-primary)' }}>
                  深色模式
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                  切换深色/浅色主题
                </div>
              </div>
            </div>
            <Toggle checked={theme === 'dark'} onChange={toggleTheme} />
          </div>
        </CardContent>
      </Card>

      {/* Model Configuration */}
      <Card style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: '12px', border: '1px solid var(--border-subtle)' }}>
        <CardHeader style={{ borderBottom: '1px solid var(--border-subtle)', padding: '16px 20px' }}>
          <CardTitle>模型配置</CardTitle>
        </CardHeader>
        <CardContent style={{ padding: '20px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '20px' }}>
            <Select
              label="Provider"
              options={providerOptions}
              value={provider}
              onChange={handleFieldChange(setProvider)}
            />
            <Input
              label="API Key"
              type="password"
              value={apiKey}
              onChange={handleFieldChange(setApiKey)}
              placeholder="输入 API Key"
            />
            <Input
              label="Base URL"
              value={baseUrl}
              onChange={handleFieldChange(setBaseUrl)}
              placeholder="https://api.minimax.chat/v1"
            />
            <Input
              label="Model"
              value={model}
              onChange={handleFieldChange(setModel)}
              placeholder="MiniMax-M2.7"
            />
            <Input
              label="Temperature"
              type="number"
              step="0.1"
              min="0"
              max="2"
              value={temperature}
              onChange={handleNumberChange(setTemperature)}
            />
            <Input
              label="Max Tokens"
              type="number"
              min="1"
              max="100000"
              value={maxTokens}
              onChange={handleNumberChange(setMaxTokens)}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', paddingTop: '16px', borderTop: '1px solid var(--border-subtle)' }}>
            <Button
              variant="secondary"
              onClick={handleTestConnection}
              disabled={testing || !apiKey || !baseUrl}
            >
              <TestTube style={{ width: '14px', height: '14px', marginRight: '6px' }} />
              {testing ? '测试中...' : '测试连接'}
            </Button>
            <div style={{ flex: 1 }} />
            <Button variant="secondary" onClick={handleReset} disabled={!hasChanges}>
              <RotateCcw style={{ width: '14px', height: '14px', marginRight: '6px' }} />
              重置
            </Button>
            <Button
              variant="primary"
              onClick={handleSave}
              disabled={saving || !hasChanges}
            >
              <Save style={{ width: '14px', height: '14px', marginRight: '6px' }} />
              {saving ? '保存中...' : '保存配置'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* About */}
      <Card style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: '12px', border: '1px solid var(--border-subtle)' }}>
        <CardHeader style={{ borderBottom: 'none', padding: '16px 20px' }}>
          <CardTitle>关于</CardTitle>
        </CardHeader>
        <CardContent style={{ padding: '16px 20px' }}>
          <div style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
            <p>AI Companion 管理后台 v0.1.0</p>
            <p style={{ marginTop: '4px' }}>一个基于 React 的 AI 伴侣管理界面</p>
            <p style={{ marginTop: '8px', fontSize: '12px', color: 'var(--text-muted)' }}>
              当前 Bot: {config?.name || '未知'}
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
