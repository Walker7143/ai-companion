import { useThemeStore } from '../../stores';
import { Toggle, Card, CardHeader, CardTitle, CardContent } from '../../components/ui';

export function Settings() {
  const { theme, toggleTheme } = useThemeStore();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">设置</h1>
        <p className="text-text-secondary mt-1">配置 AI 伴侣的各项功能</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>外观</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium text-text-primary">深色模式</div>
              <div className="text-xs text-text-muted">切换深色/浅色主题</div>
            </div>
            <Toggle checked={theme === 'dark'} onChange={toggleTheme} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>关于</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-text-secondary">
            <p>AI Companion v0.1.0</p>
            <p className="mt-1">一个基于 Tauri + React 的 AI 伴侣应用</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
