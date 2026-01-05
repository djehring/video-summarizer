import { useState, useEffect } from 'react';
import { VideoForm } from './components/VideoForm';
import { SummaryView } from './components/SummaryView';
import { ChatPanel } from './components/ChatPanel';
import { HistorySidebar } from './components/HistorySidebar';
import {
  submitVideo,
  pollUntilComplete,
  getCurrentUser,
  getLoginUrl,
  exchangeAuthToken,
  setStoredToken,
  getHistoryItem,
  type VideoAnalysis,
  type User,
  type ChatMessage
} from './api/client';

type ViewMode = 'initial' | 'summary' | 'chat';

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState<string>();
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState<string>();
  const [jobId, setJobId] = useState<string>();
  const [analysis, setAnalysis] = useState<VideoAnalysis>();
  const [error, setError] = useState<string>();
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const [loadedChatMessages, setLoadedChatMessages] = useState<ChatMessage[]>();
  const [viewMode, setViewMode] = useState<ViewMode>('initial');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Check auth state on mount
  useEffect(() => {
    const checkAuth = async () => {
      const params = new URLSearchParams(window.location.search);

      // Check for auth error in URL
      if (params.get('error') === 'not_authorized') {
        setAuthError('Your email is not on the allowed users list.');
        window.history.replaceState({}, '', window.location.pathname);
        setAuthLoading(false);
        return;
      }

      // Check for auth token in URL (mobile browsers with blocked cookies)
      const authToken = params.get('auth_token');
      if (authToken) {
        try {
          const result = await exchangeAuthToken(authToken);
          setStoredToken(result.token);
          setUser(result.user);
          // Clear token from URL
          window.history.replaceState({}, '', window.location.pathname);
          setAuthLoading(false);
          return;
        } catch {
          // Token exchange failed, fall through to normal auth check
          console.error('Token exchange failed');
        }
        // Clear invalid token from URL
        window.history.replaceState({}, '', window.location.pathname);
      }

      const currentUser = await getCurrentUser();
      setUser(currentUser);
      setAuthLoading(false);
    };
    checkAuth();
  }, []);

  const handleSubmit = async (url: string) => {
    setIsLoading(true);
    setStatus('Submitting...');
    setError(undefined);
    setAnalysis(undefined);
    setJobId(undefined);
    setLoadedChatMessages(undefined);

    try {
      const job = await submitVideo(url);
      setJobId(job.job_id);
      setStatus('Processing video...');

      const result = await pollUntilComplete(job.job_id, (j) => {
        if (j.status === 'processing') {
          setStatus('Downloading and analysing...');
        }
      });

      if (result.result) {
        setAnalysis(result.result);
        setStatus(undefined);
        setViewMode('summary');
        // Refresh history after successful analysis
        setHistoryRefresh(prev => prev + 1);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      setStatus(undefined);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectHistory = async (selectedJobId: string) => {
    setIsLoading(true);
    setStatus('Loading from history...');
    setError(undefined);

    try {
      const historyItem = await getHistoryItem(selectedJobId);

      // Convert history item to VideoAnalysis format
      const loadedAnalysis: VideoAnalysis = {
        video: {
          video_id: historyItem.video_id,
          title: historyItem.title || '',
          channel: historyItem.channel || '',
          duration: historyItem.duration || 0,
          url: historyItem.url || '',
        },
        references: historyItem.references || {
          studies: [],
          people: [],
          books: [],
          organizations: [],
          terms: [],
          paper_links: [],
          urls: [],
        },
        transcript: historyItem.transcript || '',
        llm_prompt: historyItem.llm_prompt || '',
      };

      setJobId(selectedJobId);
      setAnalysis(loadedAnalysis);
      const messages = historyItem.chat_messages.map(m => ({
        role: m.role as 'user' | 'assistant',
        content: m.content,
      }));
      setLoadedChatMessages(messages);
      // Always start with summary view when loading from history
      setViewMode('summary');
      setStatus(undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load history');
      setStatus(undefined);
    } finally {
      setIsLoading(false);
    }
  };

  const handleNewAnalysis = () => {
    setJobId(undefined);
    setAnalysis(undefined);
    setError(undefined);
    setStatus(undefined);
    setLoadedChatMessages(undefined);
    setViewMode('initial');
  };

  const handleRefreshSummary = async () => {
    if (!analysis) return;

    setIsLoading(true);
    setStatus('Refreshing summary...');
    setError(undefined);
    setLoadedChatMessages(undefined);

    try {
      const job = await submitVideo(analysis.video.url, true); // force_refresh = true
      setJobId(job.job_id);
      setStatus('Processing video...');

      const result = await pollUntilComplete(job.job_id, (j) => {
        if (j.status === 'processing') {
          setStatus('Downloading and analysing...');
        }
      });

      if (result.result) {
        setAnalysis(result.result);
        setStatus(undefined);
        setViewMode('summary');
        // Refresh history after successful analysis
        setHistoryRefresh(prev => prev + 1);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      setStatus(undefined);
    } finally {
      setIsLoading(false);
    }
  };

  // Loading state
  if (authLoading) {
    return (
      <div className="min-h-screen bg-gray-100 dark:bg-gray-950 flex items-center justify-center">
        <div className="text-gray-600 dark:text-gray-300">Loading...</div>
      </div>
    );
  }

  // Not logged in - show login screen
  if (!user) {
    return (
      <div className="min-h-screen bg-gray-100 dark:bg-gray-950 flex items-center justify-center px-4">
        <div className="max-w-md w-full bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg shadow-lg p-8 text-center">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">
            Video Summariser
          </h1>
          <p className="text-gray-600 dark:text-gray-300 mb-6">
            Extract transcripts and references from YouTube videos
          </p>

          {authError && (
            <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/60 rounded-lg p-4 text-red-700 dark:text-red-300 mb-6 text-sm">
              {authError}
            </div>
          )}

          <a
            href={getLoginUrl()}
            className="inline-flex items-center gap-3 px-6 py-3 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-lg shadow-sm hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            <span className="text-gray-700 dark:text-gray-200 font-medium">Sign in with Google</span>
          </a>

          <p className="mt-6 text-xs text-gray-500 dark:text-gray-400">
            Access is restricted to authorised users only.
          </p>
        </div>
      </div>
    );
  }

  // Logged in - show main app with sidebar
  return (
    <div className="h-screen bg-gray-100 dark:bg-gray-950 flex overflow-hidden">
      {/* History Sidebar */}
      <HistorySidebar
        onSelectItem={handleSelectHistory}
        selectedJobId={jobId}
        refreshTrigger={historyRefresh}
        user={user}
        viewMode={viewMode}
        onNewAnalysis={handleNewAnalysis}
        onViewModeChange={setViewMode}
        hasVideo={!!analysis}
        onCollapsedChange={setSidebarCollapsed}
      />

      {/* Main content area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-gray-100 dark:bg-gray-950">

        {/* INITIAL MODE - Big header + search form */}
        {viewMode === 'initial' && (
          <>
            <header className="shrink-0 bg-gray-100 dark:bg-gray-950 pt-16 pb-4 px-4 lg:pl-8">
              <div className="max-w-2xl mx-auto text-center">
                <h1 className="text-4xl font-bold text-gray-900 dark:text-gray-100 mb-3">
                  Video Summariser
                </h1>
                <p className="text-gray-600 dark:text-gray-300 text-lg">
                  Extract transcripts and references from YouTube videos
                </p>
              </div>
            </header>

            <main className="flex-1 overflow-auto px-4 lg:pl-8 pb-8">
              <div className="max-w-2xl mx-auto">
                <div className="py-8">
                  <VideoForm onSubmit={handleSubmit} isLoading={isLoading} status={status} />
                </div>

                {error && (
                  <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/60 rounded-lg p-4 text-red-700 dark:text-red-300">
                    {error}
                  </div>
                )}
              </div>
            </main>
          </>
        )}

        {/* SUMMARY MODE - Full summary view */}
        {viewMode === 'summary' && analysis && jobId && (
          <>
            {/* Compact header */}
            <header className="shrink-0 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-4 lg:px-8 py-3">
              <div className={`mx-auto ${sidebarCollapsed ? 'max-w-6xl' : 'max-w-5xl'}`}>
                <div className="min-w-0">
                  <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100 truncate">
                    {analysis.video.title}
                  </h1>
                  <p className="text-sm text-gray-500 dark:text-gray-400 truncate">{analysis.video.channel}</p>
                </div>
              </div>
            </header>

            <main className="flex-1 overflow-auto px-4 lg:px-8 py-6">
              <div className={`mx-auto ${sidebarCollapsed ? 'max-w-5xl' : 'max-w-4xl'}`}>
                <SummaryView
                  analysis={analysis}
                  onRefresh={handleRefreshSummary}
                  isRefreshing={isLoading}
                />
              </div>
            </main>
          </>
        )}

        {/* CHAT MODE - Full chatbot UI */}
        {viewMode === 'chat' && analysis && jobId && (
          <>
            {/* Minimal header */}
            <header className="shrink-0 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-4 lg:px-8 py-3">
              <div className={`mx-auto ${sidebarCollapsed ? 'max-w-5xl' : 'max-w-4xl'}`}>
                <h1 className="text-sm font-medium text-gray-700 dark:text-gray-200 truncate">
                  {analysis.video.title}
                </h1>
              </div>
            </header>

            <main className="flex-1 overflow-hidden">
              <div className={`h-full mx-auto ${sidebarCollapsed ? 'max-w-5xl' : 'max-w-4xl'}`}>
                <ChatPanel
                  jobId={jobId}
                  initialMessages={loadedChatMessages}
                  fullScreen
                />
              </div>
            </main>
          </>
        )}

        {/* Loading overlay for mode transitions */}
        {isLoading && viewMode !== 'initial' && (
          <div className="absolute inset-0 bg-gray-100/80 dark:bg-gray-950/70 flex items-center justify-center">
            <div className="text-gray-600 dark:text-gray-300">{status || 'Loading...'}</div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
