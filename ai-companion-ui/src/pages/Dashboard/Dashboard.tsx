export function Dashboard() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">监控面板</h1>
        <p className="text-text-secondary mt-1">实时监控 AI 伴侣的运行状态</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-bg-secondary border border-border-subtle rounded-lg p-4">
          <div className="text-2xl font-bold text-accent">24</div>
          <div className="text-sm text-text-secondary">今日会话</div>
        </div>
        <div className="bg-bg-secondary border border-border-subtle rounded-lg p-4">
          <div className="text-2xl font-bold text-success">98%</div>
          <div className="text-sm text-text-secondary">响应率</div>
        </div>
        <div className="bg-bg-secondary border border-border-subtle rounded-lg p-4">
          <div className="text-2xl font-bold text-warning">12</div>
          <div className="text-sm text-text-secondary">记忆条目</div>
        </div>
        <div className="bg-bg-secondary border border-border-subtle rounded-lg p-4">
          <div className="text-2xl font-bold text-info">5</div>
          <div className="text-sm text-text-secondary">活跃日志</div>
        </div>
      </div>
    </div>
  );
}
