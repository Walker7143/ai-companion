import { List, Sun, Moon, Bot } from 'lucide-react';
import { useThemeStore, useBotStore, useUIStore } from '../../stores';
import { Button } from '../ui';

export function Header() {
  const { theme, toggleTheme } = useThemeStore();
  const { bots, currentBotId, setCurrentBot } = useBotStore();
  const { toggleSidebar } = useUIStore();

  return (
    <header className="h-14 bg-bg-secondary border-b border-border-subtle flex items-center justify-between px-4">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="sm" onClick={toggleSidebar} className="lg:hidden">
          <List className="w-5 h-5" />
        </Button>
        <div className="flex items-center gap-2">
          <Bot className="w-6 h-6 text-accent" />
          <span className="font-semibold text-text-primary hidden sm:block">AI Companion</span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {/* Bot Selector */}
        <div className="relative">
          <select
            value={currentBotId || ''}
            onChange={(e) => setCurrentBot(e.target.value)}
            className="appearance-none pl-3 pr-8 py-1.5 rounded-md bg-bg-tertiary border border-border-subtle text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent cursor-pointer"
          >
            {bots.map((bot) => (
              <option key={bot.id} value={bot.id}>
                {bot.name}
              </option>
            ))}
          </select>
          <Bot className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted pointer-events-none" />
        </div>

        {/* Theme Toggle */}
        <Button variant="ghost" size="sm" onClick={toggleTheme}>
          {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
        </Button>
      </div>
    </header>
  );
}
