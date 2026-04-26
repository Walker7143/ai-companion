export function Session() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">会话管理</h1>
        <p className="text-text-secondary mt-1">查看和管理与 AI 伴侣的对话记录</p>
      </div>
      <div className="bg-bg-secondary border border-border-subtle rounded-lg p-8 text-center">
        <p className="text-text-muted">会话列表将显示在这里</p>
      </div>
    </div>
  );
}
