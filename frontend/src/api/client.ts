const API_BASE = 'http://localhost:8000/api';

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
  });
  if (!response.ok) {
    throw new Error('Failed to submit video');
  }
  return response.json();
}

export async function getJobStatus(jobId: string): Promise<JobResponse> {
  const response = await fetch(`${API_BASE}/videos/${jobId}`);
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
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to send message');
  }
  const data = await response.json();
  return data.response;
}
