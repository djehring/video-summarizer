import { useState, useEffect } from 'react';
import { getHistory, deleteHistoryItem, getLogoutUrl, clearStoredToken, type HistoryItem, type User } from '../api/client';

type ViewMode = 'initial' | 'summary' | 'chat';

interface HistorySidebarProps {
  onSelectItem: (jobId: string) => void;
  selectedJobId?: string;
  refreshTrigger?: number;
  user: User;
  viewMode: ViewMode;
  onNewAnalysis: () => void;
  onViewModeChange: (mode: ViewMode) => void;
  hasVideo: boolean;
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

// Icons
const SidebarIcon = () => (
  <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <line x1="9" y1="3" x2="9" y2="21" />
  </svg>
);

const VideoIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

const PlusIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
  </svg>
);

const SummaryIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
  </svg>
);

const ChatIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
  </svg>
);

const AppLogo = () => (
  <svg className="w-8 h-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
    <circle cx="12" cy="12" r="10" />
    <polygon points="10,8 16,12 10,16" fill="currentColor" stroke="none" />
  </svg>
);

export function HistorySidebar({
  onSelectItem,
  selectedJobId,
  refreshTrigger,
  user,
  viewMode,
  onNewAnalysis,
  onViewModeChange,
  hasVideo
}: HistorySidebarProps) {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [isOpen, setIsOpen] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [desktopCollapsed, setDesktopCollapsed] = useState(false);

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

  // Expanded sidebar content
  const expandedContent = (
    <div className="h-full flex flex-col bg-white">
      {/* Header with logo and toggle */}
      <div className="p-4 flex items-center justify-between">
        <div className="flex items-center gap-2 text-gray-700">
          <AppLogo />
          <span className="font-semibold text-lg">Video AI</span>
        </div>
        <button
          onClick={() => setDesktopCollapsed(true)}
          className="hidden lg:flex p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
          title="Hide sidebar"
        >
          <SidebarIcon />
        </button>
        <button
          onClick={() => setIsOpen(false)}
          className="lg:hidden p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* New Video button */}
      <div className="px-3 mb-2">
        <button
          onClick={onNewAnalysis}
          className="w-full flex items-center gap-3 px-3 py-2.5 text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <PlusIcon />
          <span className="font-medium">New Video</span>
        </button>
      </div>

      {/* View mode toggle - only show when video is selected */}
      {hasVideo && (
        <div className="px-3 mb-3">
          <div className="flex gap-1 p-1 bg-gray-100 rounded-lg">
            <button
              onClick={() => onViewModeChange('summary')}
              className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                viewMode === 'summary'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              <SummaryIcon />
              <span>Summary</span>
            </button>
            <button
              onClick={() => onViewModeChange('chat')}
              className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                viewMode === 'chat'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              <ChatIcon />
              <span>Chat</span>
            </button>
          </div>
        </div>
      )}

      {/* Divider */}
      <div className="border-t border-gray-200 mx-3 mb-2" />

      {/* History section */}
      <div className="px-3 mb-2">
        <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide px-3">History</h3>
      </div>

      <div className="flex-1 overflow-y-auto px-3">
        {loading ? (
          <div className="p-3 text-sm text-gray-500">Loading...</div>
        ) : items.length === 0 ? (
          <div className="p-3 text-sm text-gray-500">No history yet</div>
        ) : (
          <div className="space-y-4">
            {groupOrder.map(group => {
              const groupItems = groupedItems.get(group);
              if (!groupItems || groupItems.length === 0) return null;

              return (
                <div key={group}>
                  <div className="px-3 py-1 text-xs font-medium text-gray-400 uppercase tracking-wide">
                    {group}
                  </div>
                  {groupItems.map(item => (
                    <button
                      key={item.job_id}
                      onClick={() => onSelectItem(item.job_id)}
                      className={`w-full text-left px-3 py-2 hover:bg-gray-100 rounded-lg transition-colors group ${
                        selectedJobId === item.job_id ? 'bg-blue-50' : ''
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium text-gray-900 truncate">
                            {item.title || 'Untitled'}
                          </div>
                          <div className="text-xs text-gray-500 truncate">
                            {item.channel}
                            {item.duration ? ` · ${formatDuration(item.duration)}` : ''}
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

  // Collapsed sidebar content (icon strip)
  const collapsedContent = (
    <div className="h-full flex flex-col items-center bg-white py-4">
      {/* Logo - swaps to sidebar icon on hover */}
      <button
        onClick={() => setDesktopCollapsed(false)}
        className="mb-4 p-1 text-gray-700 hover:text-gray-900 transition-colors relative group"
        title="Open sidebar"
      >
        {/* Default: App logo */}
        <div className="group-hover:hidden">
          <AppLogo />
        </div>
        {/* On hover: Sidebar icon */}
        <div className="hidden group-hover:block">
          <svg className="w-8 h-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <line x1="9" y1="3" x2="9" y2="21" />
          </svg>
        </div>
        {/* Tooltip */}
        <div className="absolute left-full ml-2 top-1/2 -translate-y-1/2 px-2 py-1 bg-gray-900 text-white text-xs rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
          Open sidebar
        </div>
      </button>

      {/* New Video */}
      <button
        onClick={onNewAnalysis}
        className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors mb-2"
        title="New Video"
      >
        <PlusIcon />
      </button>

      {/* View mode icons - only show when video is selected */}
      {hasVideo && (
        <>
          <button
            onClick={() => onViewModeChange('summary')}
            className={`p-2 rounded-lg transition-colors mb-1 ${
              viewMode === 'summary'
                ? 'bg-blue-100 text-blue-600'
                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
            }`}
            title="Summary"
          >
            <SummaryIcon />
          </button>
          <button
            onClick={() => onViewModeChange('chat')}
            className={`p-2 rounded-lg transition-colors mb-2 ${
              viewMode === 'chat'
                ? 'bg-blue-100 text-blue-600'
                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
            }`}
            title="Chat"
          >
            <ChatIcon />
          </button>
        </>
      )}

      {/* Divider */}
      <div className="w-8 border-t border-gray-200 my-2" />

      {/* History items as icons */}
      <div className="flex-1 overflow-y-auto flex flex-col items-center gap-1 w-full px-2">
        {items.slice(0, 8).map(item => (
          <button
            key={item.job_id}
            onClick={() => onSelectItem(item.job_id)}
            className={`p-2 rounded-lg transition-colors ${
              selectedJobId === item.job_id
                ? 'bg-blue-100 text-blue-600'
                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
            }`}
            title={item.title || 'Untitled'}
          >
            <VideoIcon />
          </button>
        ))}
        {items.length > 8 && (
          <div className="text-xs text-gray-400 mt-1">+{items.length - 8}</div>
        )}
      </div>

      {/* User avatar */}
      <div className="mt-auto pt-4 border-t border-gray-200 w-full flex justify-center">
        <img
          src={user.picture}
          alt={user.name}
          className="w-8 h-8 rounded-full cursor-pointer"
          title={user.name}
        />
      </div>
    </div>
  );

  return (
    <>
      {/* Mobile toggle button */}
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
          h-full bg-white border-r border-gray-200 lg:shrink-0
          transform transition-all duration-200 ease-in-out
          ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
          ${desktopCollapsed ? 'lg:w-16' : 'lg:w-72'}
          ${desktopCollapsed ? '' : 'w-72'}
        `}
      >
        {desktopCollapsed ? (
          <div className="hidden lg:block h-full">{collapsedContent}</div>
        ) : null}
        <div className={desktopCollapsed ? 'lg:hidden h-full' : 'h-full'}>
          {expandedContent}
        </div>
      </aside>
    </>
  );
}
