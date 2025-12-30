import { useState } from 'react';

interface VideoFormProps {
  onSubmit: (url: string) => void;
  isLoading: boolean;
  status?: string;
}

export function VideoForm({ onSubmit, isLoading, status }: VideoFormProps) {
  const [url, setUrl] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (url.trim()) {
      onSubmit(url.trim());
    }
  };

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-2xl">
      <div className="flex flex-col gap-4">
        <label htmlFor="url" className="text-lg font-medium text-gray-700">
          YouTube URL
        </label>
        <div className="flex gap-2">
          <input
            type="url"
            id="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.youtube.com/watch?v=..."
            className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none text-gray-900"
            disabled={isLoading}
            required
          />
          <button
            type="submit"
            disabled={isLoading || !url.trim()}
            className="px-6 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? 'Analysing...' : 'Analyse'}
          </button>
        </div>
        {status && (
          <p className="text-sm text-gray-600">
            Status: <span className="font-medium">{status}</span>
          </p>
        )}
      </div>
    </form>
  );
}
