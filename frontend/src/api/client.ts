// API base URL: use env var for Railway, relative for Docker, absolute for dev
const API_BASE = import.meta.env.VITE_API_BASE
  || (import.meta.env.DEV ? 'http://localhost:8000/api' : '/api');

// Auth types and functions
export interface User {
  email: string;
  name: string;
  picture: string;
}

export async function getCurrentUser(): Promise<User | null> {
  try {
    const response = await fetch(`${API_BASE}/auth/me`, {
      credentials: 'include',
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
    headers: { 'Content-Type': 'application/json' },
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
    headers: { 'Content-Type': 'application/json' },
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
    headers: { 'Content-Type': 'application/json' },
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
