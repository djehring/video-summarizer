import { useState, useEffect } from 'react';
import { VideoForm } from './components/VideoForm';
import { SummaryView } from './components/SummaryView';
import { ChatPanel } from './components/ChatPanel';
import {
  submitVideo,
  pollUntilComplete,
  getCurrentUser,
  getLoginUrl,
  getLogoutUrl,
  exchangeAuthToken,
  setStoredToken,
  clearStoredToken,
  type VideoAnalysis,
  type User
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

  // Logged in - show main app
  return (
    <div className="min-h-screen bg-gray-100 py-8 px-4">
      <div className="max-w-6xl mx-auto space-y-8">
        <header className="text-center relative">
          {/* User menu */}
          <div className="absolute right-0 top-0 flex items-center gap-3">
            <img
              src={user.picture}
              alt={user.name}
              className="w-8 h-8 rounded-full"
            />
            <span className="text-sm text-gray-600 hidden sm:inline">{user.email}</span>
            <a
              href={getLogoutUrl()}
              onClick={() => clearStoredToken()}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              Logout
            </a>
          </div>

          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            Video Summariser
          </h1>
          <p className="text-gray-600">
            Extract transcripts and references from YouTube videos
          </p>
        </header>

        <div className="flex justify-center">
          <VideoForm onSubmit={handleSubmit} isLoading={isLoading} status={status} />
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
            {error}
          </div>
        )}

        {analysis && jobId && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="space-y-6">
              <SummaryView analysis={analysis} />
            </div>
            <div className="lg:sticky lg:top-8 lg:self-start">
              <ChatPanel jobId={jobId} videoTitle={analysis.video.title} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
