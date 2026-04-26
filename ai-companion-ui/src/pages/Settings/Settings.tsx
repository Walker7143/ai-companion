import { useEffect, useState, useCallback } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Moon, Sun, TestTube, Save, RotateCcw } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, Toggle, Button, Input, Select, useToast } from '../../components/ui';
import { useThemeStore } from '../../stores';
import type { BotConfig } from '../../types';

export function Settings() {
  const { theme, toggleTheme } = useThemeStore();
  const toast = useToast();

  const [config, setConfig] = useState<BotConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  // Form state
  const [provider, setProvider] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [model, setModel] = useState('');
  const [temperature, setTemperature] = useState(0.8);
  const [maxTokens, setMaxTokens] = useState(1024);

  const [hasChanges, setHasChanges] = useState(false);

  const fetchConfig = useCallback(async () => {
    try {
      const data = await invoke<BotConfig>('get_config', { botId: 'suqing' });
      setConfig(data);
      setProvider(data.model.provider);
      setApiKey(data.model.api_key);
      setBaseUrl(data.model.base_url);
      setModel(data.model.model);
      setTemperature(data.model.temperature);
      setMaxTokens(data.model.max_tokens);
    } catch (err) {
      toast('error', `获取配置失败: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const handleFieldChange = (setter: (value: string) => void) => (value: string) => {
    setter(value);
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
      const newConfig: BotConfig = {
        ...config,
        model: {
          provider,
          api_key: apiKey,
          base_url: baseUrl,
          model,
          temperature,
          max_tokens: maxTokens,
        },
      };
      await invoke('update_config', { botId: config.bot_id, config: newConfig });
      toast('success', '配置已保存');
      setHasChanges(false);
      fetchConfig();
    } catch (err) {
      toast('error', `保存配置失败: ${err}`);
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
      const result = await invoke<boolean>('test_api_connection', {
        provider,
        apiKey,
        baseUrl,
      });
      if (result) {
        toast('success', 'API 连接测试成功');
      } else {
        toast('error', 'API 连接测试失败');
      }
    } catch (err) {
      toast('error', `测试连接失败: ${err}`);
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
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">设置</h1>
          <p className="text-text-secondary mt-1">配置 AI 伴侣的各项功能</p>
        </div>
        <div className="space-y-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="bg-bg-secondary border border-border-subtle rounded-lg p-6 animate-pulse">
              <div className="h-4 bg-bg-tertiary rounded w-1/4 mb-4" />
              <div className="space-y-3">
                <div className="h-10 bg-bg-tertiary rounded" />
                <div className="h-10 bg-bg-tertiary rounded" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">设置</h1>
        <p className="text-text-secondary mt-1">配置 AI 伴侣的各项功能</p>
      </div>

      {/* Appearance */}
      <Card>
        <CardHeader>
          <CardTitle>外观</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {theme === 'dark' ? (
                <Moon className="w-5 h-5 text-text-primary" />
              ) : (
                <Sun className="w-5 h-5 text-text-primary" />
              )}
              <div>
                <div className="text-sm font-medium text-text-primary">深色模式</div>
                <div className="text-xs text-text-muted">切换深色/浅色主题</div>
              </div>
            </div>
            <Toggle checked={theme === 'dark'} onChange={toggleTheme} />
          </div>
        </CardContent>
      </Card>

      {/* Model Configuration */}
      <Card>
        <CardHeader>
          <CardTitle>模型配置</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Select
              label=" Provider"
              options={providerOptions}
              value={provider}
              onChange={(e) => handleFieldChange(setProvider)(e.target.value)}
            />
            <Input
              label="API Key"
              type="password"
              value={apiKey}
              onChange={(e) => handleFieldChange(setApiKey)(e.target.value)}
              placeholder="输入 API Key"
            />
            <Input
              label="Base URL"
              value={baseUrl}
              onChange={(e) => handleFieldChange(setBaseUrl)(e.target.value)}
              placeholder="https://api.minimax.chat/v1"
            />
            <Input
              label="Model"
              value={model}
              onChange={(e) => handleFieldChange(setModel)(e.target.value)}
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

          <div className="flex gap-3 pt-4 border-t border-border-subtle">
            <Button
              variant="secondary"
              onClick={handleTestConnection}
              disabled={testing || !apiKey || !baseUrl}
            >
              <TestTube className="w-4 h-4 mr-1" />
              {testing ? '测试中...' : '测试连接'}
            </Button>
            <div className="flex-1" />
            <Button variant="secondary" onClick={handleReset} disabled={!hasChanges}>
              <RotateCcw className="w-4 h-4 mr-1" />
              重置
            </Button>
            <Button
              variant="primary"
              onClick={handleSave}
              disabled={saving || !hasChanges}
            >
              <Save className="w-4 h-4 mr-1" />
              {saving ? '保存中...' : '保存配置'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* About */}
      <Card>
        <CardHeader>
          <CardTitle>关于</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-text-secondary">
            <p>AI Companion v0.1.0</p>
            <p className="mt-1">一个基于 Tauri + React 的 AI 伴侣应用</p>
            <p className="mt-2 text-xs text-text-muted">
              当前 Bot: {config?.name || '未知'}
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}