import { useState, useEffect } from 'react';
import { getHistory, deleteHistoryItem, getLogoutUrl, clearStoredToken, type HistoryItem, type User } from '../api/client';

interface HistorySidebarProps {
  onSelectItem: (jobId: string) => void;
  selectedJobId?: string;
  refreshTrigger?: number;
  user: User;
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return '';
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  if (hours > 0) {
    return `${hours}h ${mins}m`;
  }
  return `${mins}m`;
}

function groupByDate(items: HistoryItem[]): Map<string, HistoryItem[]> {
  const groups = new Map<string, HistoryItem[]>();
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const lastWeek = new Date(today.getTime() - 7 * 86400000);

  for (const item of items) {
    const itemDate = new Date(item.created_at);
    const itemDay = new Date(itemDate.getFullYear(), itemDate.getMonth(), itemDate.getDate());

    let group: string;
    if (itemDay.getTime() >= today.getTime()) {
      group = 'Today';
    } else if (itemDay.getTime() >= yesterday.getTime()) {
      group = 'Yesterday';
    } else if (itemDay.getTime() >= lastWeek.getTime()) {
      group = 'Last 7 Days';
    } else {
      group = 'Older';
    }

    if (!groups.has(group)) {
      groups.set(group, []);
    }
    groups.get(group)!.push(item);
  }

  return groups;
}

export function HistorySidebar({ onSelectItem, selectedJobId, refreshTrigger, user }: HistorySidebarProps) {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [isOpen, setIsOpen] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    loadHistory();
  }, [refreshTrigger]);

  const loadHistory = async () => {
    try {
      const response = await getHistory();
      setItems(response.items);
    } catch (error) {
      console.error('Failed to load history:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent, jobId: string) => {
    e.stopPropagation();
    if (deletingId) return;

    setDeletingId(jobId);
    try {
      await deleteHistoryItem(jobId);
      setItems(items.filter(item => item.job_id !== jobId));
    } catch (error) {
      console.error('Failed to delete:', error);
    } finally {
      setDeletingId(null);
    }
  };

  const groupedItems = groupByDate(items);
  const groupOrder = ['Today', 'Yesterday', 'Last 7 Days', 'Older'];

  const sidebarContent = (
    <div className="h-full flex flex-col">
      <div className="p-4 border-b border-gray-200">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">History</h2>
          {/* Close button - only visible on mobile when sidebar is open */}
          <button
            onClick={() => setIsOpen(false)}
            className="lg:hidden p-1 text-gray-400 hover:text-gray-600 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <p className="text-xs text-gray-500 mt-1">{items.length} videos</p>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-4 text-sm text-gray-500">Loading...</div>
        ) : items.length === 0 ? (
          <div className="p-4 text-sm text-gray-500">No history yet</div>
        ) : (
          <div className="py-2">
            {groupOrder.map(group => {
              const groupItems = groupedItems.get(group);
              if (!groupItems || groupItems.length === 0) return null;

              return (
                <div key={group} className="mb-4">
                  <div className="px-4 py-1 text-xs font-medium text-gray-400 uppercase tracking-wide">
                    {group}
                  </div>
                  {groupItems.map(item => (
                    <button
                      key={item.job_id}
                      onClick={() => onSelectItem(item.job_id)}
                      className={`w-full text-left px-4 py-2 hover:bg-gray-100 transition-colors group ${
                        selectedJobId === item.job_id ? 'bg-blue-50 border-l-2 border-blue-500' : ''
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium text-gray-900 truncate">
                            {item.title || 'Untitled'}
                          </div>
                          <div className="text-xs text-gray-500 truncate">
                            {item.channel}
                            {item.duration ? ` - ${formatDuration(item.duration)}` : ''}
                          </div>
                          {item.message_count > 0 && (
                            <div className="text-xs text-blue-600 mt-0.5">
                              {item.message_count} message{item.message_count !== 1 ? 's' : ''}
                            </div>
                          )}
                        </div>
                        <button
                          onClick={(e) => handleDelete(e, item.job_id)}
                          disabled={deletingId === item.job_id}
                          className="opacity-0 group-hover:opacity-100 p-1 text-gray-400 hover:text-red-500 transition-all"
                          title="Delete"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </div>
                    </button>
                  ))}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* User footer */}
      <div className="shrink-0 border-t border-gray-200 p-4">
        <div className="flex items-center gap-3">
          <img
            src={user.picture}
            alt={user.name}
            className="w-8 h-8 rounded-full"
          />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-gray-900 truncate">{user.name}</div>
            <div className="text-xs text-gray-500 truncate">{user.email}</div>
          </div>
          <a
            href={getLogoutUrl()}
            onClick={() => clearStoredToken()}
            className="p-1.5 text-gray-400 hover:text-gray-600 transition-colors"
            title="Logout"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
          </a>
        </div>
      </div>
    </div>
  );

  return (
    <>
      {/* Mobile toggle button - only show hamburger when sidebar is closed */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="lg:hidden fixed top-4 left-4 z-50 p-2 bg-white rounded-lg shadow-md"
        >
          <svg className="w-6 h-6 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
      )}

      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="lg:hidden fixed inset-0 bg-black/50 z-30"
          onClick={() => setIsOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed lg:static inset-y-0 left-0 z-40
          w-72 h-full bg-white border-r border-gray-200
          transform transition-transform duration-200 ease-in-out
          lg:transform-none lg:shrink-0
          ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
        `}
      >
        {sidebarContent}
      </aside>
    </>
  );
}
