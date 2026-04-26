import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  MessageSquare,
  FileText,
  Brain,
  Settings,
  X,
} from 'lucide-react';
import { useUIStore } from '../../stores';
import { cn } from '../../utils/cn';

const navItems = [
  { path: '/', icon: LayoutDashboard, label: '监控', end: true },
  { path: '/session', icon: MessageSquare, label: '会话' },
  { path: '/logs', icon: FileText, label: '日志' },
  { path: '/memory', icon: Brain, label: '记忆' },
  { path: '/settings', icon: Settings, label: '设置' },
];

export function Sidebar() {
  const { sidebarCollapsed, toggleSidebar } = useUIStore();

  return (
    <>
      {/* Mobile overlay */}
      {sidebarCollapsed && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={toggleSidebar}
        />
      )}

      <aside
        className={cn(
          'fixed lg:static inset-y-0 left-0 z-50 w-56 bg-bg-secondary border-r border-border-subtle transform transition-transform duration-200 lg:translate-x-0',
          sidebarCollapsed ? '-translate-x-full' : 'translate-x-0'
        )}
      >
        <div className="flex flex-col h-full">
          {/* Mobile close button */}
          <div className="flex items-center justify-between p-4 border-b border-border-subtle lg:hidden">
            <span className="font-semibold text-text-primary">菜单</span>
            <button
              onClick={toggleSidebar}
              className="p-1 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-tertiary"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-4 space-y-1">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.end}
                onClick={() => {
                  if (window.innerWidth < 1024) {
                    toggleSidebar();
                  }
                }}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-accent text-white'
                      : 'text-text-secondary hover:bg-bg-tertiary hover:text-text-primary'
                  )
                }
              >
                <item.icon className="w-5 h-5" />
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </aside>
    </>
  );
}
