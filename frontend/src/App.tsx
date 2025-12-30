import { useState } from 'react';
import { VideoForm } from './components/VideoForm';
import { SummaryView } from './components/SummaryView';
import { submitVideo, pollUntilComplete, type VideoAnalysis } from './api/client';

function App() {
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState<string>();
  const [analysis, setAnalysis] = useState<VideoAnalysis>();
  const [error, setError] = useState<string>();

  const handleSubmit = async (url: string) => {
    setIsLoading(true);
    setStatus('Submitting...');
    setError(undefined);
    setAnalysis(undefined);

    try {
      const job = await submitVideo(url);
      setStatus('Processing video...');

      const result = await pollUntilComplete(job.job_id, (j) => {
        if (j.status === 'processing') {
          setStatus('Downloading and analyzing...');
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

  return (
    <div className="min-h-screen bg-gray-100 py-8 px-4">
      <div className="max-w-4xl mx-auto space-y-8">
        <header className="text-center">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            Video Summarizer
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

        {analysis && <SummaryView analysis={analysis} />}
      </div>
    </div>
  );
}

export default App;
