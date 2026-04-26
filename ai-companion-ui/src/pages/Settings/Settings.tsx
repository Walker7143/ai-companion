import { useEffect, useState, useCallback } from 'react';
import { Moon, Sun, TestTube, Save, RotateCcw, Globe, Zap } from 'lucide-react';
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

  // Model config
  const [provider, setProvider] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [model, setModel] = useState('');
  const [temperature, setTemperature] = useState(0.8);
  const [maxTokens, setMaxTokens] = useState(1024);

  // Platform config
  const [platforms, setPlatforms] = useState<{ name: string; enabled: boolean }[]>([
    { name: 'cli', enabled: true },
    { name: 'feishu', enabled: false },
    { name: 'webhook', enabled: false },
  ]);

  // Proactive config
  const [proactiveEnabled, setProactiveEnabled] = useState(false);
  const [idleThresholdHours, setIdleThresholdHours] = useState(24);
  const [minIntervalHours, setMinIntervalHours] = useState(3);
  const [maxDaily, setMaxDaily] = useState(5);
  const [emotionKeywords, setEmotionKeywords] = useState('');

  const [hasChanges, setHasChanges] = useState(false);

  const fetchConfig = useCallback(async () => {
    if (!currentBotId) return;
    try {
      const data = await configApi.getConfig(currentBotId);
      setConfig(data);
      // Model
      setProvider(data.model.provider);
      setApiKey(data.model.api_key);
      setBaseUrl(data.model.base_url);
      setModel(data.model.model);
      setTemperature(data.model.temperature);
      setMaxTokens(data.model.max_tokens);
      // Platform
      setPlatforms(data.platforms.map(p => ({ name: p.name, enabled: p.enabled })));
      // Proactive
      setProactiveEnabled(data.proactive.enabled);
      setIdleThresholdHours(data.proactive.idle_threshold_hours);
      setMinIntervalHours(data.proactive.min_interval_hours);
      setMaxDaily(data.proactive.max_daily);
      setEmotionKeywords(data.proactive.emotion_keywords.join(', '));
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

  const handleToggle = (setter: (value: boolean) => void) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setter(e.target.checked);
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
        proactive: {
          enabled: proactiveEnabled,
          idle_threshold_hours: idleThresholdHours,
          min_interval_hours: minIntervalHours,
          max_daily: maxDaily,
          emotion_keywords: emotionKeywords.split(',').map(k => k.trim()).filter(Boolean),
        },
        platforms: platforms.map(p => ({
          name: p.name,
          enabled: p.enabled,
          config: {},
        })),
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
      setPlatforms(config.platforms.map(p => ({ name: p.name, enabled: p.enabled })));
      setProactiveEnabled(config.proactive.enabled);
      setIdleThresholdHours(config.proactive.idle_threshold_hours);
      setMinIntervalHours(config.proactive.min_interval_hours);
      setMaxDaily(config.proactive.max_daily);
      setEmotionKeywords(config.proactive.emotion_keywords.join(', '));
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

  const handlePlatformToggle = (name: string) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setPlatforms(prev => prev.map(p => p.name === name ? { ...p, enabled: e.target.checked } : p));
    setHasChanges(true);
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
          </div>
        </CardContent>
      </Card>

      {/* Platform Configuration */}
      <Card style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: '12px', border: '1px solid var(--border-subtle)' }}>
        <CardHeader style={{ borderBottom: '1px solid var(--border-subtle)', padding: '16px 20px' }}>
          <CardTitle style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Globe style={{ width: '18px', height: '18px', color: 'var(--accent)' }} />
            平台配置
          </CardTitle>
        </CardHeader>
        <CardContent style={{ padding: '20px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {platforms.map((platform) => (
              <div
                key={platform.name}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '12px 16px',
                  borderRadius: '8px',
                  backgroundColor: 'var(--bg-tertiary)',
                }}
              >
                <div>
                  <div style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-primary)' }}>
                    {platform.name === 'cli' ? 'CLI' :
                     platform.name === 'feishu' ? '飞书' :
                     platform.name === 'webhook' ? 'Webhook' : platform.name}
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                    {platform.name === 'cli' ? '命令行交互界面' :
                     platform.name === 'feishu' ? '飞书平台接入' :
                     platform.name === 'webhook' ? '自定义 Webhook' : ''}
                  </div>
                </div>
                <Toggle
                  checked={platform.enabled}
                  onChange={handlePlatformToggle(platform.name)}
                />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Proactive Configuration */}
      <Card style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: '12px', border: '1px solid var(--border-subtle)' }}>
        <CardHeader style={{ borderBottom: '1px solid var(--border-subtle)', padding: '16px 20px' }}>
          <CardTitle style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Zap style={{ width: '18px', height: '18px', color: 'var(--warning)' }} />
            主动唤醒
          </CardTitle>
        </CardHeader>
        <CardContent style={{ padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
            <div>
              <div style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-primary)' }}>
                启用主动唤醒
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                Bot 会主动找你聊天、提醒事情
              </div>
            </div>
            <Toggle
              checked={proactiveEnabled}
              onChange={handleToggle(setProactiveEnabled)}
            />
          </div>

          {proactiveEnabled && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px' }}>
              <Input
                label="空闲触发阈值（小时）"
                type="number"
                min="1"
                max="168"
                value={idleThresholdHours}
                onChange={handleNumberChange(setIdleThresholdHours)}
              />
              <Input
                label="最小消息间隔（小时）"
                type="number"
                min="1"
                max="24"
                value={minIntervalHours}
                onChange={handleNumberChange(setMinIntervalHours)}
              />
              <Input
                label="每日最大次数"
                type="number"
                min="1"
                max="50"
                value={maxDaily}
                onChange={handleNumberChange(setMaxDaily)}
              />
            </div>
          )}

          {proactiveEnabled && (
            <div style={{ marginTop: '16px' }}>
              <Input
                label="情绪关键词（逗号分隔）"
                value={emotionKeywords}
                onChange={handleFieldChange(setEmotionKeywords)}
                placeholder="难过, 生气, 委屈, 累"
              />
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                当用户消息包含这些词时，Bot 会更主动地关心
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Action Buttons */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', paddingTop: '8px' }}>
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
