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

async function getErrorMessage(response: Response): Promise<string> {
  const contentType = response.headers.get('content-type') || '';

  // Best effort: our backend errors are usually { detail: string }
  if (contentType.includes('application/json')) {
    try {
      const data = await response.json() as { detail?: string; message?: string; error?: string };
      return data.detail || data.message || data.error || `Request failed (${response.status})`;
    } catch {
      // Fall through to text parsing below
    }
  }

  try {
    const text = await response.text();
    const snippet = text.trim().slice(0, 300);
    return snippet ? `Request failed (${response.status}): ${snippet}` : `Request failed (${response.status})`;
  } catch {
    return `Request failed (${response.status})`;
  }
}

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return response.json() as Promise<T>;
  }

  const text = await response.text();
  const snippet = text.trim().slice(0, 300);
  throw new Error(
    `Expected JSON but got ${contentType || 'unknown content-type'} (${response.status}).` +
    (snippet ? ` Body: ${snippet}` : '')
  );
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
    throw new Error(await getErrorMessage(response));
  }
  return parseJsonOrThrow(response);
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

export interface EnrichedReference {
  original_text: string;
  enriched_url: string | null;
  enriched_title: string | null;
  enriched_journal?: string | null;
  confidence: number;
  source: string;
}

export interface EnrichedPerson {
  original_text: string;  // The name as it appeared in transcript (possibly mispronounced)
  corrected_name: string;  // The correct spelling
  title?: string | null;  // e.g. "M.D.", "Ph.D."
  affiliation?: string | null;  // e.g. "UT Southwestern Medical Center"
  url?: string | null;  // Authoritative profile URL
  confidence: number;
}

export interface References {
  studies: string[];
  studies_enriched?: EnrichedReference[];
  people: string[];
  people_enriched?: EnrichedPerson[];
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
  synopsis?: string;
}

export interface JobResponse {
  job_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  error?: string;
  result?: VideoAnalysis;
}

export async function submitVideo(url: string, forceRefresh: boolean = false): Promise<JobResponse> {
  const response = await fetch(`${API_BASE}/videos/analyze`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ url, force_refresh: forceRefresh }),
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }
  return parseJsonOrThrow(response);
}

export async function getJobStatus(jobId: string): Promise<JobResponse> {
  const response = await fetch(`${API_BASE}/videos/${jobId}`, {
    credentials: 'include',
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }
  return parseJsonOrThrow(response);
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
  image_base64?: string;  // For messages with attached images
}

export async function generateSummary(jobId: string): Promise<string> {
  const response = await fetch(`${API_BASE}/chat/summarize`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ job_id: jobId }),
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }
  const data = await parseJsonOrThrow<{ summary: string }>(response);
  return data.summary;
}

export async function sendChatMessage(
  jobId: string,
  message: string,
  history: ChatMessage[],
  imageBase64?: string
): Promise<string> {
  const body: Record<string, unknown> = { job_id: jobId, message, history };
  if (imageBase64) {
    body.image_base64 = imageBase64;
  }
  
  const response = await fetch(`${API_BASE}/chat/message`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(body),
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }
  const data = await parseJsonOrThrow<{ response: string }>(response);
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

export interface ApiStatus {
  openai: boolean;
  exa: boolean;
}

export interface HistorySettings {
  max_entries: number;
  retention_days: number;
  current_count: number;
  api_status: ApiStatus;
}

export type SortOption = 'date' | 'title';

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

export async function getHistory(
  search?: string,
  sort: SortOption = 'date'
): Promise<HistoryListResponse> {
  const params = new URLSearchParams();
  if (search) params.set('search', search);
  if (sort) params.set('sort', sort);

  const queryString = params.toString();
  const url = queryString ? `${API_BASE}/history?${queryString}` : `${API_BASE}/history`;

  const response = await fetch(url, {
    credentials: 'include',
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    if (response.status === 503) {
      // History feature not available
      return { items: [], total: 0 };
    }
    throw new Error(await getErrorMessage(response));
  }
  return parseJsonOrThrow(response);
}

export async function getHistoryItem(jobId: string): Promise<HistoryDetail> {
  const response = await fetch(`${API_BASE}/history/${jobId}`, {
    credentials: 'include',
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }
  return parseJsonOrThrow(response);
}

export async function deleteHistoryItem(jobId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/history/${jobId}`, {
    method: 'DELETE',
    credentials: 'include',
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }
}

export async function clearAllHistory(): Promise<{ deleted_count: number }> {
  const response = await fetch(`${API_BASE}/history`, {
    method: 'DELETE',
    credentials: 'include',
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }
  return parseJsonOrThrow(response);
}

export async function getHistorySettings(): Promise<HistorySettings> {
  const response = await fetch(`${API_BASE}/history/settings/info`, {
    credentials: 'include',
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    if (response.status === 503) {
      return { max_entries: 50, retention_days: 90, current_count: 0, api_status: { openai: false, exa: false } };
    }
    throw new Error(await getErrorMessage(response));
  }
  return parseJsonOrThrow(response);
}

export function getExportHistoryUrl(): string {
  return `${API_BASE}/history/export/json`;
}
