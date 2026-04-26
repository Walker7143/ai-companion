import { ReactNode } from 'react';
import { FileX, Search, Inbox } from 'lucide-react';

interface EmptyStateProps {
  icon?: 'file' | 'search' | 'inbox';
  title: string;
  description?: string;
  action?: ReactNode;
}

const icons = {
  file: FileX,
  search: Search,
  inbox: Inbox,
};

export function EmptyState({ icon = 'inbox', title, description, action }: EmptyStateProps) {
  const Icon = icons[icon];

  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <div className="w-16 h-16 rounded-full bg-bg-tertiary flex items-center justify-center mb-4">
        <Icon className="w-8 h-8 text-text-muted" />
      </div>
      <h3 className="text-lg font-medium text-text-primary mb-1">{title}</h3>
      {description && (
        <p className="text-sm text-text-secondary max-w-sm mb-4">{description}</p>
      )}
      {action && <div>{action}</div>}
    </div>
  );
}
