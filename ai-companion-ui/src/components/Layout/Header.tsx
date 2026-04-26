import { Sun, Moon, Bot, Menu } from 'lucide-react';
import { useThemeStore, useBotStore } from '../../stores';

interface HeaderProps {
  onMenuClick: () => void;
}

export function Header({ onMenuClick }: HeaderProps) {
  const { theme, toggleTheme } = useThemeStore();
  const { bots, currentBotId, setCurrentBot } = useBotStore();

  return (
    <header
      style={{
        height: '56px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 16px',
        borderBottom: '1px solid var(--border-subtle)',
        backgroundColor: 'var(--bg-secondary)',
      }}
    >
      {/* Left section */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        {/* Mobile menu button */}
        <button
          onClick={onMenuClick}
          style={{
            padding: '8px',
            borderRadius: '6px',
            border: 'none',
            backgroundColor: 'transparent',
            cursor: 'pointer',
            display: 'flex',
          }}
          className="lg:hidden"
        >
          <Menu className="w-5 h-5" style={{ color: 'var(--text-primary)' }} />
        </button>

        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Bot className="w-6 h-6" style={{ color: 'var(--accent)' }} />
          <span
            className="hidden lg:block"
            style={{ fontWeight: 600, fontSize: '15px', color: 'var(--text-primary)' }}
          >
            AI Companion
          </span>
        </div>
      </div>

      {/* Right section */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        {/* Bot Selector */}
        <div style={{ position: 'relative' }}>
          <select
            value={currentBotId || ''}
            onChange={(e) => setCurrentBot(e.target.value)}
            style={{
              appearance: 'none',
              padding: '6px 32px 6px 12px',
              borderRadius: '6px',
              border: '1px solid var(--border-subtle)',
              backgroundColor: 'var(--bg-tertiary)',
              color: 'var(--text-primary)',
              fontSize: '13px',
              cursor: 'pointer',
              outline: 'none',
            }}
          >
            {bots.map((bot) => (
              <option key={bot.id} value={bot.id}>
                {bot.name}
              </option>
            ))}
          </select>
          <Bot
            style={{
              position: 'absolute',
              right: '8px',
              top: '50%',
              transform: 'translateY(-50%)',
              width: '14px',
              height: '14px',
              color: 'var(--text-muted)',
              pointerEvents: 'none',
            }}
          />
        </div>

        {/* Theme Toggle */}
        <button
          onClick={toggleTheme}
          style={{
            padding: '8px',
            borderRadius: '6px',
            border: 'none',
            backgroundColor: 'transparent',
            cursor: 'pointer',
            display: 'flex',
            transition: 'background-color 150ms ease',
          }}
          title={theme === 'dark' ? '切换到亮色主题' : '切换到暗色主题'}
        >
          {theme === 'dark' ? (
            <Sun className="w-5 h-5" style={{ color: 'var(--text-primary)' }} />
          ) : (
            <Moon className="w-5 h-5" style={{ color: 'var(--text-primary)' }} />
          )}
        </button>
      </div>
    </header>
  );
}
