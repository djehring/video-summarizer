// API base URL: use env var for Railway, relative for Docker, absolute for dev
const API_BASE = import.meta.env.VITE_API_BASE
  || (import.meta.env.DEV ? 'http://localhost:8000/api' : '/api');

// Token storage for mobile browsers (localStorage fallback for cross-site cookie issues)
const AUTH_TOKEN_KEY = 'video_summariser_auth_token';

export function getStoredToken(): string | null {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setStoredToken(token: string): void {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearStoredToken(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

// Helper to get auth headers
function getAuthHeaders(): HeadersInit {
  const token = getStoredToken();
  const headers: HeadersInit = { 'Content-Type': 'application/json' };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

// Auth types and functions
export interface User {
  email: string;
  name: string;
  picture: string;
}

export async function exchangeAuthToken(token: string): Promise<{ token: string; user: User }> {
  const response = await fetch(`${API_BASE}/auth/exchange-token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error('Failed to exchange token');
  }
  return response.json();
}

export async function getCurrentUser(): Promise<User | null> {
  try {
    const response = await fetch(`${API_BASE}/auth/me`, {
      credentials: 'include',
      headers: getAuthHeaders(),
    });
    if (!response.ok) return null;
    return response.json();
  } catch {
    return null;
  }
}

export function getLoginUrl(): string {
  return `${API_BASE}/auth/login`;
}

export function getLogoutUrl(): string {
  return `${API_BASE}/auth/logout`;
}

export interface VideoMetadata {
  video_id: string;
  title: string;
  channel: string;
  duration: number;
  url: string;
}

export interface References {
  studies: string[];
  people: string[];
  books: string[];
  organizations: string[];
  terms: string[];
  paper_links: string[];
  urls: string[];
}

export interface VideoAnalysis {
  video: VideoMetadata;
  references: References;
  transcript: string;
  llm_prompt: string;
}

export interface JobResponse {
  job_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  error?: string;
  result?: VideoAnalysis;
}

export async function submitVideo(url: string): Promise<JobResponse> {
  const response = await fetch(`${API_BASE}/videos/analyze`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ url }),
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error('Failed to submit video');
  }
  return response.json();
}

export async function getJobStatus(jobId: string): Promise<JobResponse> {
  const response = await fetch(`${API_BASE}/videos/${jobId}`, {
    credentials: 'include',
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    throw new Error('Failed to get job status');
  }
  return response.json();
}

export async function pollUntilComplete(
  jobId: string,
  onUpdate?: (job: JobResponse) => void,
  intervalMs = 1000
): Promise<JobResponse> {
  return new Promise((resolve, reject) => {
    const poll = async () => {
      try {
        const job = await getJobStatus(jobId);
        onUpdate?.(job);

        if (job.status === 'completed') {
          resolve(job);
        } else if (job.status === 'failed') {
          reject(new Error(job.error || 'Analysis failed'));
        } else {
          setTimeout(poll, intervalMs);
        }
      } catch (error) {
        reject(error);
      }
    };
    poll();
  });
}

// Chat API
export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export async function generateSummary(jobId: string): Promise<string> {
  const response = await fetch(`${API_BASE}/chat/summarize`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ job_id: jobId }),
    credentials: 'include',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to generate summary');
  }
  const data = await response.json();
  return data.summary;
}

export async function sendChatMessage(
  jobId: string,
  message: string,
  history: ChatMessage[]
): Promise<string> {
  const response = await fetch(`${API_BASE}/chat/message`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ job_id: jobId, message, history }),
    credentials: 'include',
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to send message');
  }
  const data = await response.json();
  return data.response;
}

// History API
export interface HistoryItem {
  job_id: string;
  video_id: string;
  title: string | null;
  channel: string | null;
  duration: number | null;
  url: string | null;
  created_at: string;
  message_count: number;
}

export interface HistoryListResponse {
  items: HistoryItem[];
  total: number;
}

export interface HistoryChatMessage {
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface HistoryDetail {
  job_id: string;
  video_id: string;
  title: string | null;
  channel: string | null;
  duration: number | null;
  url: string | null;
  references: References | null;
  transcript: string | null;
  llm_prompt: string | null;
  chat_messages: HistoryChatMessage[];
  created_at: string;
}

export async function getHistory(): Promise<HistoryListResponse> {
  const response = await fetch(`${API_BASE}/history`, {
    credentials: 'include',
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    if (response.status === 503) {
      // History feature not available
      return { items: [], total: 0 };
    }
    throw new Error('Failed to get history');
  }
  return response.json();
}

export async function getHistoryItem(jobId: string): Promise<HistoryDetail> {
  const response = await fetch(`${API_BASE}/history/${jobId}`, {
    credentials: 'include',
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    throw new Error('Failed to get history item');
  }
  return response.json();
}

export async function deleteHistoryItem(jobId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/history/${jobId}`, {
    method: 'DELETE',
    credentials: 'include',
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    throw new Error('Failed to delete history item');
  }
}
