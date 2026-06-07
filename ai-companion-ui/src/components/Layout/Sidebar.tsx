import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  MessageSquare,
  FileText,
  Brain,
  HeartHandshake,
  Wand2,
  Activity,
  TrendingUp,
  Bug,
  Settings,
  X,
  ChevronLeft,
  ChevronRight,
  Bot,
} from 'lucide-react';

interface SidebarProps {
  collapsed: boolean;
  mobileOpen: boolean;
  onClose: () => void;
  onToggle: () => void;
}

const navItems = [
  { path: '/', icon: LayoutDashboard, label: '监控面板', end: true },
  { path: '/session', icon: MessageSquare, label: '会话管理' },
  { path: '/logs', icon: FileText, label: '日志查看' },
  { path: '/memory', icon: Brain, label: '记忆系统' },
  { path: '/understanding', icon: HeartHandshake, label: '长期理解投影' },
  { path: '/style', icon: Wand2, label: '风格调教' },
  { path: '/operations', icon: Activity, label: '运营台' },
  { path: '/evolution', icon: TrendingUp, label: '人格演化' },
  { path: '/debug', icon: Bug, label: '调试工具' },
  { path: '/settings', icon: Settings, label: '设置' },
];

export function Sidebar({ collapsed, mobileOpen, onClose, onToggle }: SidebarProps) {
  const sidebarWidth = collapsed ? '64px' : '240px';

  const baseStyle: React.CSSProperties = {
    height: '100vh',
    display: 'flex',
    flexDirection: 'column',
    transition: 'width 200ms ease, transform 200ms ease',
    backgroundColor: 'var(--bg-secondary)',
    borderRight: '1px solid var(--border-subtle)',
  };

  // Mobile overlay style
  const mobileOverlayStyle: React.CSSProperties = {
    ...baseStyle,
    position: 'fixed',
    left: 0,
    top: 0,
    width: '240px',
    zIndex: 50,
    transform: mobileOpen ? 'translateX(0)' : 'translateX(-100%)',
  };

  // Desktop collapsible style
  const desktopStyle: React.CSSProperties = {
    ...baseStyle,
    width: sidebarWidth,
    position: 'relative',
  };

  return (
    <>
      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            zIndex: 40,
          }}
          className="lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar */}
      <aside
        style={window.innerWidth < 1024 ? mobileOverlayStyle : desktopStyle}
        className="hidden lg:flex"
      >
        <SidebarContent collapsed={collapsed} onToggle={onToggle} onClose={onClose} />
      </aside>

      {/* Mobile sidebar */}
      <aside
        style={mobileOverlayStyle}
        className="flex lg:hidden"
      >
        <SidebarContent collapsed={false} onToggle={onToggle} onClose={onClose} />
      </aside>
    </>
  );
}

function SidebarContent({
  collapsed,
  onToggle,
  onClose,
}: {
  collapsed: boolean;
  onToggle: () => void;
  onClose: () => void;
}) {
  return (
    <>
      {/* Header */}
      <div
        style={{
          height: '56px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'space-between',
          padding: collapsed ? '0' : '0 16px',
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        {collapsed ? (
          <Bot className="w-6 h-6" style={{ color: 'var(--accent)' }} />
        ) : (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Bot className="w-6 h-6" style={{ color: 'var(--accent)' }} />
              <span style={{ fontWeight: 600, fontSize: '15px', color: 'var(--text-primary)' }}>
                AI Companion
              </span>
            </div>
            <button
              onClick={onClose}
              style={{
                padding: '6px',
                borderRadius: '4px',
                border: 'none',
                backgroundColor: 'transparent',
                cursor: 'pointer',
                display: 'flex',
              }}
              className="lg:hidden"
            >
              <X className="w-5 h-5" style={{ color: 'var(--text-muted)' }} />
            </button>
          </>
        )}
      </div>

      {/* Navigation */}
      <nav
        style={{
          flex: 1,
          padding: '12px 8px',
          display: 'flex',
          flexDirection: 'column',
          gap: '2px',
          overflowY: 'auto',
        }}
      >
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.end}
            onClick={onClose}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              padding: collapsed ? '10px' : '10px 12px',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: 500,
              textDecoration: 'none',
              justifyContent: collapsed ? 'center' : 'flex-start',
              backgroundColor: isActive ? 'var(--accent)' : 'transparent',
              color: isActive ? '#ffffff' : 'var(--text-secondary)',
              transition: 'all 150ms ease',
            })}
          >
            <item.icon style={{ width: '20px', height: '20px', flexShrink: 0 }} />
            {!collapsed && <span>{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Collapse toggle - desktop only */}
      <div
        style={{
          padding: '8px',
          borderTop: '1px solid var(--border-subtle)',
          display: 'flex',
          justifyContent: collapsed ? 'center' : 'flex-end',
        }}
        className="hidden lg:flex"
      >
        <button
          onClick={onToggle}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
            padding: '8px',
            borderRadius: '6px',
            border: 'none',
            backgroundColor: 'transparent',
            cursor: 'pointer',
            color: 'var(--text-muted)',
            width: '100%',
            transition: 'all 150ms ease',
          }}
        >
          {collapsed ? (
            <ChevronRight style={{ width: '18px', height: '18px' }} />
          ) : (
            <>
              <ChevronLeft style={{ width: '18px', height: '18px' }} />
              {!collapsed && (
                <span style={{ fontSize: '13px' }}>收起</span>
              )}
            </>
          )}
        </button>
      </div>
    </>
  );
}
