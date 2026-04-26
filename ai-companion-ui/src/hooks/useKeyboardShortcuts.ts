import { useEffect, useCallback } from 'react';

interface Shortcut {
  key: string;
  ctrl?: boolean;
  meta?: boolean;
  shift?: boolean;
  handler: () => void;
  description?: string;
}

export function useKeyboardShortcuts(shortcuts: Shortcut[]) {
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    for (const shortcut of shortcuts) {
      const keyMatch = e.key.toLowerCase() === shortcut.key.toLowerCase();
      const ctrlMatch = shortcut.ctrl ? (e.ctrlKey || e.metaKey) : true;
      const shiftMatch = shortcut.shift ? e.shiftKey : !e.shiftKey;

      if (keyMatch && ctrlMatch && shiftMatch) {
        e.preventDefault();
        shortcut.handler();
        break;
      }
    }
  }, [shortcuts]);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);
}

// Predefined shortcuts
export const shortcuts = {
  refresh: { key: 'r', handler: () => window.location.reload(), description: '刷新页面' },
  goToDashboard: { key: 'd', meta: true, handler: () => window.location.href = '/', description: '跳转监控' },
  goToSettings: { key: 's', meta: true, handler: () => window.location.href = '/settings', description: '跳转设置' },
  goToLogs: { key: 'l', meta: true, handler: () => window.location.href = '/logs', description: '跳转日志' },
  toggleTheme: { key: 't', meta: true, handler: () => document.documentElement.classList.toggle('light'), description: '切换主题' },
};
