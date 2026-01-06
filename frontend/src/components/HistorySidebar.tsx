import { useState, useEffect, useRef, useCallback } from 'react';
import { getHistory, deleteHistoryItem, getLogoutUrl, clearStoredToken, type HistoryItem, type User, type SortOption } from '../api/client';
import { SettingsDialog } from './SettingsDialog';

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
  onCollapsedChange?: (collapsed: boolean) => void;
  onItemDeleted?: (jobId: string) => void;
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

const SettingsIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
  </svg>
);

const LogoutIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
  </svg>
);

const SearchIcon = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
  </svg>
);

const SortIcon = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4h13M3 8h9m-9 4h6m4 0l4-4m0 0l4 4m-4-4v12" />
  </svg>
);

const ClearIcon = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
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
  hasVideo,
  onCollapsedChange,
  onItemDeleted
}: HistorySidebarProps) {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [isOpen, setIsOpen] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [confirmDeleteItem, setConfirmDeleteItem] = useState<HistoryItem | null>(null);
  const [desktopCollapsed, setDesktopCollapsed] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortOption, setSortOption] = useState<SortOption>('date');
  const [showSortMenu, setShowSortMenu] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const collapsedUserMenuRef = useRef<HTMLDivElement>(null);
  const sortMenuRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Memoize loadHistory to avoid dependency issues
  const loadHistory = useCallback(async (search?: string, sort?: SortOption) => {
    try {
      setLoading(true);
      const response = await getHistory(search, sort);
      setItems(response.items);
    } catch (error) {
      console.error('Failed to load history:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHistory(searchQuery || undefined, sortOption);
  }, [refreshTrigger, sortOption, searchQuery, loadHistory]);

  // Debounced search
  useEffect(() => {
    const timer = setTimeout(() => {
      loadHistory(searchQuery || undefined, sortOption);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery, sortOption, loadHistory]);

  // Notify parent of collapsed state changes
  useEffect(() => {
    onCollapsedChange?.(desktopCollapsed);
  }, [desktopCollapsed, onCollapsedChange]);

  // Close menus when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      const clickedInExpandedMenu = userMenuRef.current?.contains(target);
      const clickedInCollapsedMenu = collapsedUserMenuRef.current?.contains(target);
      const clickedInSortMenu = sortMenuRef.current?.contains(target);

      if (!clickedInExpandedMenu && !clickedInCollapsedMenu) {
        setUserMenuOpen(false);
      }
      if (!clickedInSortMenu) {
        setShowSortMenu(false);
      }
    };

    if (userMenuOpen || showSortMenu) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [userMenuOpen, showSortMenu]);

  const handleDeleteClick = (e: React.MouseEvent, item: HistoryItem) => {
    e.stopPropagation();
    if (deletingId) return;
    setConfirmDeleteItem(item);
  };

  const handleConfirmDelete = async () => {
    if (!confirmDeleteItem || deletingId) return;

    const jobId = confirmDeleteItem.job_id;
    setDeletingId(jobId);
    setConfirmDeleteItem(null);
    
    try {
      await deleteHistoryItem(jobId);
      setItems(items.filter(item => item.job_id !== jobId));
      // Notify parent that this item was deleted
      onItemDeleted?.(jobId);
    } catch (error) {
      console.error('Failed to delete:', error);
    } finally {
      setDeletingId(null);
    }
  };

  const handleCancelDelete = () => {
    setConfirmDeleteItem(null);
  };

  const groupedItems = groupByDate(items);
  const groupOrder = ['Today', 'Yesterday', 'Last 7 Days', 'Older'];

  // Expanded sidebar content
  const expandedContent = (
    <div className="h-full flex flex-col bg-white dark:bg-gray-900">
      {/* Header with logo and toggle */}
      <div className="p-4 flex items-center justify-between">
        <div className="flex items-center gap-2 text-gray-700 dark:text-gray-200">
          <AppLogo />
          <span className="font-semibold text-lg">Video Summariser</span>
        </div>
        <button
          onClick={() => setDesktopCollapsed(true)}
          className="hidden lg:flex p-2 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
          title="Hide sidebar"
        >
          <SidebarIcon />
        </button>
        <button
          onClick={() => setIsOpen(false)}
          className="lg:hidden p-2 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
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
          className="w-full flex items-center gap-3 px-3 py-2.5 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
        >
          <PlusIcon />
          <span className="font-medium">New Video</span>
        </button>
      </div>

      {/* View mode toggle - only show when video is selected */}
      {hasVideo && (
        <div className="px-3 mb-3">
          <div className="flex gap-1 p-1 bg-gray-100 dark:bg-gray-800 rounded-lg">
            <button
              onClick={() => onViewModeChange('summary')}
              className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                viewMode === 'summary'
                  ? 'bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 shadow-sm'
                  : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100'
              }`}
            >
              <SummaryIcon />
              <span>Summary</span>
            </button>
            <button
              onClick={() => onViewModeChange('chat')}
              className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                viewMode === 'chat'
                  ? 'bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 shadow-sm'
                  : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100'
              }`}
            >
              <ChatIcon />
              <span>Chat</span>
            </button>
          </div>
        </div>
      )}

      {/* Divider */}
      <div className="border-t border-gray-200 dark:border-gray-800 mx-3 mb-2" />

      {/* History section with search and sort */}
      <div className="px-3 mb-2 space-y-2">
        <div className="flex items-center justify-between px-1">
          <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide">History</h3>
          {/* Sort dropdown */}
          <div className="relative" ref={sortMenuRef}>
            <button
              onClick={() => setShowSortMenu(!showSortMenu)}
              className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded transition-colors"
              title={`Sort by ${sortOption === 'date' ? 'date' : 'title'}`}
            >
              <SortIcon />
            </button>
            {showSortMenu && (
              <div className="absolute right-0 top-full mt-1 bg-white dark:bg-gray-900 rounded-lg shadow-lg border border-gray-200 dark:border-gray-800 overflow-hidden z-10 min-w-[120px]">
                <button
                  onClick={() => { setSortOption('date'); setShowSortMenu(false); }}
                  className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-800 ${
                    sortOption === 'date'
                      ? 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/40'
                      : 'text-gray-700 dark:text-gray-200'
                  }`}
                >
                  Date
                </button>
                <button
                  onClick={() => { setSortOption('title'); setShowSortMenu(false); }}
                  className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-800 ${
                    sortOption === 'title'
                      ? 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/40'
                      : 'text-gray-700 dark:text-gray-200'
                  }`}
                >
                  Title
                </button>
              </div>
            )}
          </div>
        </div>
        {/* Search input */}
        <div className="relative">
          <div className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
            <SearchIcon />
          </div>
          <input
            ref={searchInputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search videos..."
            className="w-full pl-9 pr-8 py-2 text-sm bg-gray-100 dark:bg-gray-800 border-0 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white dark:focus:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
            >
              <ClearIcon />
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3">
        {loading ? (
          <div className="p-3 text-sm text-gray-500 dark:text-gray-400">Loading...</div>
        ) : items.length === 0 ? (
          <div className="p-3 text-sm text-gray-500 dark:text-gray-400">
            {searchQuery ? 'No videos found' : 'No history yet'}
          </div>
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
                      className={`w-full text-left px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors group ${
                        selectedJobId === item.job_id ? 'bg-blue-50 dark:bg-blue-950/40' : ''
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                            {item.title || 'Untitled'}
                          </div>
                          <div className="text-xs text-gray-500 dark:text-gray-400 truncate">
                            {item.channel}
                            {item.duration ? ` · ${formatDuration(item.duration)}` : ''}
                          </div>
                          {item.message_count > 0 && (
                            <div className="text-xs text-blue-600 dark:text-blue-400 mt-0.5">
                              {item.message_count} message{item.message_count !== 1 ? 's' : ''}
                            </div>
                          )}
                        </div>
                        <button
                          onClick={(e) => handleDeleteClick(e, item)}
                          disabled={deletingId === item.job_id}
                          className="opacity-0 group-hover:opacity-100 p-1 text-gray-400 hover:text-red-500 dark:hover:text-red-400 transition-all"
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

      {/* User footer with popup menu */}
      <div className="shrink-0 border-t border-gray-200 dark:border-gray-800 p-4 relative" ref={userMenuRef}>
        <button
          onClick={() => setUserMenuOpen(!userMenuOpen)}
          className="w-full flex items-center gap-3 p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
        >
          <img
            src={user.picture}
            alt={user.name}
            className="w-8 h-8 rounded-full"
          />
          <div className="flex-1 min-w-0 text-left">
            <div className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{user.name}</div>
            <div className="text-xs text-gray-500 dark:text-gray-400 truncate">{user.email}</div>
          </div>
          <svg className={`w-4 h-4 text-gray-400 transition-transform ${userMenuOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
          </svg>
        </button>

        {/* Popup menu */}
        {userMenuOpen && (
          <div className="absolute bottom-full left-4 right-4 mb-2 bg-white dark:bg-gray-900 rounded-lg shadow-lg border border-gray-200 dark:border-gray-800 overflow-hidden">
            <button
              onClick={() => {
                setUserMenuOpen(false);
                setSettingsOpen(true);
              }}
              className="w-full flex items-center gap-3 px-4 py-3 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            >
              <SettingsIcon />
              <span>Settings</span>
            </button>
            <div className="border-t border-gray-100 dark:border-gray-800" />
            <a
              href={getLogoutUrl()}
              onClick={() => {
                clearStoredToken();
                setUserMenuOpen(false);
              }}
              className="w-full flex items-center gap-3 px-4 py-3 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            >
              <LogoutIcon />
              <span>Log out</span>
            </a>
          </div>
        )}
      </div>
    </div>
  );

  // Collapsed sidebar content (icon strip)
  const collapsedContent = (
    <div className="h-full flex flex-col items-center bg-white dark:bg-gray-900 py-4">
      {/* Logo - swaps to sidebar icon on hover */}
      <button
        onClick={() => setDesktopCollapsed(false)}
        className="mb-4 p-1 text-gray-700 dark:text-gray-200 hover:text-gray-900 dark:hover:text-gray-100 transition-colors relative group"
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
        <div className="absolute left-full ml-2 top-1/2 -translate-y-1/2 px-2 py-1 bg-gray-900 dark:bg-gray-700 text-white text-xs rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
          Open sidebar
        </div>
      </button>

      {/* New Video */}
      <button
        onClick={onNewAnalysis}
        className="p-2 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors mb-2"
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
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800'
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
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800'
            }`}
            title="Chat"
          >
            <ChatIcon />
          </button>
        </>
      )}

      {/* Divider */}
      <div className="w-8 border-t border-gray-200 dark:border-gray-800 my-2" />

      {/* History items as icons */}
      <div className="flex-1 overflow-y-auto flex flex-col items-center gap-1 w-full px-2">
        {items.slice(0, 8).map(item => (
          <button
            key={item.job_id}
            onClick={() => onSelectItem(item.job_id)}
            className={`p-2 rounded-lg transition-colors ${
              selectedJobId === item.job_id
                ? 'bg-blue-100 text-blue-600'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800'
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

      {/* User avatar with popup menu */}
      <div className="mt-auto pt-4 border-t border-gray-200 dark:border-gray-800 w-full flex justify-center relative" ref={collapsedUserMenuRef}>
        <button
          onClick={() => setUserMenuOpen(!userMenuOpen)}
          className="relative group"
        >
          <img
            src={user.picture}
            alt={user.name}
            className="w-8 h-8 rounded-full cursor-pointer hover:ring-2 hover:ring-gray-300 transition-all"
          />
          {/* Username tooltip on hover */}
          {!userMenuOpen && (
            <div className="absolute left-full ml-2 top-1/2 -translate-y-1/2 px-2 py-1 bg-gray-900 dark:bg-gray-700 text-white text-xs rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
              {user.name}
            </div>
          )}
        </button>

        {/* Popup menu - positioned to the right of avatar */}
        {userMenuOpen && (
          <div className="absolute bottom-0 left-full ml-2 bg-white dark:bg-gray-900 rounded-lg shadow-lg border border-gray-200 dark:border-gray-800 overflow-hidden min-w-[200px] z-50">
            {/* User info header */}
            <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-800">
              <div className="text-sm font-medium text-gray-900 dark:text-gray-100">{user.name}</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">{user.email}</div>
            </div>
            <button
              onClick={() => {
                setUserMenuOpen(false);
                setSettingsOpen(true);
              }}
              className="w-full flex items-center gap-3 px-4 py-3 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            >
              <SettingsIcon />
              <span>Settings</span>
            </button>
            <div className="border-t border-gray-100 dark:border-gray-800" />
            <a
              href={getLogoutUrl()}
              onClick={() => {
                clearStoredToken();
                setUserMenuOpen(false);
              }}
              className="w-full flex items-center gap-3 px-4 py-3 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            >
              <LogoutIcon />
              <span>Log out</span>
            </a>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <>
      {/* Mobile toggle button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="lg:hidden fixed top-4 left-4 z-50 p-2 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg shadow-md"
        >
          <svg className="w-6 h-6 text-gray-600 dark:text-gray-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
          h-full bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 lg:shrink-0
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

      {/* Settings Dialog */}
      <SettingsDialog
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onHistoryCleared={() => {
          setItems([]);
          setSettingsOpen(false);
        }}
      />

      {/* Delete Confirmation Dialog */}
      {confirmDeleteItem && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/50 z-50"
            onClick={handleCancelDelete}
          />
          {/* Dialog */}
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="bg-white dark:bg-gray-900 rounded-xl shadow-xl border border-gray-200 dark:border-gray-800 max-w-md w-full p-6">
              <div className="flex items-start gap-4">
                {/* Warning icon */}
                <div className="flex-shrink-0 w-10 h-10 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                  <svg className="w-5 h-5 text-red-600 dark:text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                </div>
                <div className="flex-1">
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                    Delete video from history?
                  </h3>
                  <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
                    Are you sure you want to delete "<span className="font-medium text-gray-900 dark:text-gray-100">{confirmDeleteItem.title || 'Untitled'}</span>"? This will also remove all chat messages associated with this video.
                  </p>
                </div>
              </div>
              <div className="mt-6 flex gap-3 justify-end">
                <button
                  onClick={handleCancelDelete}
                  className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfirmDelete}
                  disabled={deletingId !== null}
                  className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {deletingId ? 'Deleting...' : 'Delete'}
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </>
  );
}
