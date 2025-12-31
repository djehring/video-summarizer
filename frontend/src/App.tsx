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
  const [isFromHistory, setIsFromHistory] = useState(false);

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
    setIsFromHistory(false);

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
      setLoadedChatMessages(
        historyItem.chat_messages.map(m => ({
          role: m.role as 'user' | 'assistant',
          content: m.content,
        }))
      );
      setIsFromHistory(true);
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
    setIsFromHistory(false);
  };

  // Loading state
  if (authLoading) {
    return (
      <div className="min-h-screen bg-gray-100 flex items-center justify-center">
        <div className="text-gray-600">Loading...</div>
      </div>
    );
  }

  // Not logged in - show login screen
  if (!user) {
    return (
      <div className="min-h-screen bg-gray-100 flex items-center justify-center px-4">
        <div className="max-w-md w-full bg-white rounded-lg shadow-lg p-8 text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-2">
            Video Summariser
          </h1>
          <p className="text-gray-600 mb-6">
            Extract transcripts and references from YouTube videos
          </p>

          {authError && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 mb-6 text-sm">
              {authError}
            </div>
          )}

          <a
            href={getLoginUrl()}
            className="inline-flex items-center gap-3 px-6 py-3 bg-white border border-gray-300 rounded-lg shadow-sm hover:bg-gray-50 transition-colors"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            <span className="text-gray-700 font-medium">Sign in with Google</span>
          </a>

          <p className="mt-6 text-xs text-gray-500">
            Access is restricted to authorised users only.
          </p>
        </div>
      </div>
    );
  }

  // Logged in - show main app with sidebar
  return (
    <div className="h-screen bg-gray-100 flex overflow-hidden">
      {/* History Sidebar */}
      <HistorySidebar
        onSelectItem={handleSelectHistory}
        selectedJobId={jobId}
        refreshTrigger={historyRefresh}
        user={user}
      />

      {/* Main content area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-gray-100">
        {/* Fixed header */}
        <header className="shrink-0 bg-gray-100 pt-8 pb-4 px-4 lg:pl-8">
          <div className="max-w-5xl mx-auto text-center">
            <h1 className="text-3xl font-bold text-gray-900 mb-2">
              Video Summariser
            </h1>
            <p className="text-gray-600">
              Extract transcripts and references from YouTube videos
            </p>
          </div>
        </header>

        {/* Scrollable content area */}
        <main className="flex-1 overflow-hidden px-4 lg:pl-8 pb-8">
          <div className="max-w-5xl mx-auto h-full flex flex-col">
            {/* New Analysis button when viewing history */}
            {isFromHistory && (
              <div className="flex justify-center py-4 shrink-0">
                <button
                  onClick={handleNewAnalysis}
                  className="px-4 py-2 text-sm bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  + New Analysis
                </button>
              </div>
            )}

            {/* Video form - hide when viewing from history */}
            {!isFromHistory && (
              <div className="flex justify-center py-4 shrink-0">
                <VideoForm onSubmit={handleSubmit} isLoading={isLoading} status={status} />
              </div>
            )}

            {error && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 mb-4 shrink-0">
                {error}
              </div>
            )}

            {analysis && jobId && (
              <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-6 min-h-0">
                {/* Left column - scrollable summary */}
                <div className="overflow-y-auto pr-2">
                  <div className="space-y-6 pb-4">
                    <SummaryView analysis={analysis} />
                  </div>
                </div>
                {/* Right column - chat panel with its own scroll */}
                <div className="flex flex-col min-h-0">
                  <ChatPanel
                    jobId={jobId}
                    videoTitle={analysis.video.title}
                    initialMessages={loadedChatMessages}
                  />
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

export default App;
