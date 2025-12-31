import { useState } from 'react';
import type { VideoAnalysis } from '../api/client';

interface SummaryViewProps {
  analysis: VideoAnalysis;
}

function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
}

function isUrl(str: string): boolean {
  return str.startsWith('http://') || str.startsWith('https://');
}

function getSearchUrl(item: string, type: string): string {
  const query = encodeURIComponent(item);
  switch (type) {
    case 'studies':
      return `https://scholar.google.com/scholar?q=${query}`;
    case 'people':
      return `https://www.google.com/search?q=${query}`;
    case 'books':
      return `https://www.google.com/search?q=${query}+book`;
    case 'organizations':
      return `https://www.google.com/search?q=${query}`;
    case 'terms':
      return `https://www.google.com/search?q=${query}+definition`;
    default:
      return `https://www.google.com/search?q=${query}`;
  }
}

function ReferenceSection({ title, items, icon, type }: { title: string; items: string[]; icon: string; type: string }) {
  const [isOpen, setIsOpen] = useState(true);

  if (items.length === 0) return null;

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-4 py-3 bg-gray-50 flex items-center justify-between hover:bg-gray-100 transition-colors"
      >
        <span className="font-medium text-gray-700">
          {icon} {title} ({items.length})
        </span>
        <span className="text-gray-500">{isOpen ? '−' : '+'}</span>
      </button>
      {isOpen && (
        <ul className="px-4 py-3 space-y-1">
          {items.map((item, i) => (
            <li key={i} className="text-gray-600">
              •{' '}
              {isUrl(item) ? (
                <a
                  href={item}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 hover:underline break-all"
                >
                  {item}
                </a>
              ) : (
                <a
                  href={getSearchUrl(item, type)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 hover:underline"
                >
                  {item}
                </a>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function SummaryView({ analysis }: SummaryViewProps) {
  const [showTranscript, setShowTranscript] = useState(false);
  const [copied, setCopied] = useState(false);

  const { video, references, transcript, llm_prompt, synopsis } = analysis;

  const copyPrompt = async () => {
    await navigator.clipboard.writeText(llm_prompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="w-full max-w-4xl space-y-6">
      {/* Video Metadata */}
      <div className="bg-white border border-gray-200 rounded-lg p-6 shadow-sm">
        <h2 className="text-2xl font-bold text-gray-900 mb-2">{video.title}</h2>
        <div className="flex flex-wrap gap-4 text-sm text-gray-600 mb-4">
          <span>Channel: <strong>{video.channel}</strong></span>
          <span>Duration: <strong>{formatDuration(video.duration)}</strong></span>
          <a
            href={video.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 hover:underline"
          >
            Watch on YouTube
          </a>
        </div>
        {synopsis && (
          <p className="text-gray-700 leading-relaxed border-t border-gray-100 pt-4">
            {synopsis}
          </p>
        )}
      </div>

      {/* References */}
      <div className="space-y-3">
        <h3 className="text-lg font-semibold text-gray-800">Extracted References</h3>
        <ReferenceSection title="Studies & Papers" items={references.studies} icon="📚" type="studies" />
        <ReferenceSection title="People Mentioned" items={references.people} icon="👤" type="people" />
        <ReferenceSection title="Books" items={references.books} icon="📖" type="books" />
        <ReferenceSection title="Organizations" items={references.organizations} icon="🏛️" type="organizations" />
        <ReferenceSection title="Scientific Terms" items={references.terms} icon="🔬" type="terms" />
        <ReferenceSection title="Research Papers" items={references.paper_links || []} icon="📄" type="urls" />
        <ReferenceSection title="Other Links" items={references.urls} icon="🔗" type="urls" />
      </div>

      {/* LLM Prompt */}
      <div className="bg-white border border-gray-200 rounded-lg p-6 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-800">LLM Summary Prompt</h3>
          <button
            onClick={copyPrompt}
            className="px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 transition-colors"
          >
            {copied ? 'Copied!' : 'Copy Prompt'}
          </button>
        </div>
        <p className="text-sm text-gray-600">
          Copy this prompt and paste it into Claude or another LLM to get a detailed summary.
        </p>
      </div>

      {/* Transcript */}
      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <button
          onClick={() => setShowTranscript(!showTranscript)}
          className="w-full px-4 py-3 bg-gray-50 flex items-center justify-between hover:bg-gray-100 transition-colors"
        >
          <span className="font-medium text-gray-700">
            Full Transcript ({transcript.split(' ').length.toLocaleString()} words)
          </span>
          <span className="text-gray-500">{showTranscript ? '−' : '+'}</span>
        </button>
        {showTranscript && (
          <div className="px-4 py-3 max-h-96 overflow-y-auto">
            <p className="text-gray-600 whitespace-pre-wrap text-sm leading-relaxed">
              {transcript}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
