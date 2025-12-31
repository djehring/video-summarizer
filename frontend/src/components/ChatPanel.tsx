import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { generateSummary, sendChatMessage, type ChatMessage } from '../api/client';

interface ChatPanelProps {
  jobId: string;
  initialMessages?: ChatMessage[];
  fullScreen?: boolean;
}

// Copy button component
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  return (
    <button
      onClick={handleCopy}
      className="absolute top-2 right-2 p-1.5 rounded-md bg-gray-100 hover:bg-gray-200 text-gray-500 hover:text-gray-700 transition-colors"
      title="Copy to clipboard"
    >
      {copied ? (
        <svg className="w-4 h-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      ) : (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
        </svg>
      )}
    </button>
  );
}

export function ChatPanel({ jobId, initialMessages, fullScreen = false }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages || []);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string>();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const currentJobIdRef = useRef<string>(jobId);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // Reset state when jobId changes (new video selected)
  useEffect(() => {
    currentJobIdRef.current = jobId;
    setMessages(initialMessages || []);
    setIsLoading(false);
    setError(undefined);
  }, [jobId, initialMessages]);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleGenerateSummary = async () => {
    const requestJobId = jobId;
    setIsLoading(true);
    setError(undefined);
    try {
      const summary = await generateSummary(requestJobId);
      // Only update if still on the same video
      if (currentJobIdRef.current !== requestJobId) return;
      setMessages([
        { role: 'user', content: 'Generate annotated summary' },
        { role: 'assistant', content: summary }
      ]);
    } catch (err) {
      if (currentJobIdRef.current !== requestJobId) return;
      setError(err instanceof Error ? err.message : 'Failed to generate summary');
    } finally {
      if (currentJobIdRef.current === requestJobId) {
        setIsLoading(false);
      }
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const requestJobId = jobId;
    const userMessage = input.trim();
    setInput('');
    setError(undefined);

    const newMessages: ChatMessage[] = [...messages, { role: 'user', content: userMessage }];
    setMessages(newMessages);
    setIsLoading(true);

    try {
      const response = await sendChatMessage(requestJobId, userMessage, messages);
      // Only update if still on the same video
      if (currentJobIdRef.current !== requestJobId) return;
      setMessages([...newMessages, { role: 'assistant', content: response }]);
    } catch (err) {
      if (currentJobIdRef.current !== requestJobId) return;
      setError(err instanceof Error ? err.message : 'Failed to send message');
    } finally {
      if (currentJobIdRef.current === requestJobId) {
        setIsLoading(false);
      }
    }
  };

  const containerClass = fullScreen
    ? "bg-gray-50 flex flex-col h-full"
    : "bg-white border border-gray-200 rounded-lg shadow-sm flex flex-col h-full min-h-[400px] max-h-[calc(100vh-200px)]";

  return (
    <div className={containerClass}>
      {/* Header - only show when not fullScreen */}
      {!fullScreen && (
        <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between shrink-0">
          <h3 className="font-semibold text-gray-800">AI Assistant</h3>
          {messages.length === 0 && (
            <button
              onClick={handleGenerateSummary}
              disabled={isLoading}
              className="px-3 py-1.5 bg-purple-600 text-white text-sm font-medium rounded-lg hover:bg-purple-700 disabled:bg-gray-400 transition-colors"
            >
              {isLoading ? 'Generating...' : 'Generate Summary'}
            </button>
          )}
        </div>
      )}

      {/* Messages */}
      <div className={`flex-1 overflow-y-auto space-y-4 min-h-0 ${fullScreen ? 'px-4 py-6' : 'p-4'}`}>
        {messages.length === 0 ? (
          <div className={`text-center text-gray-500 ${fullScreen ? 'mt-16' : 'mt-8'}`}>
            <p className="mb-4 text-lg">Ask questions about this video</p>
            <p className="text-sm mb-6">Or generate an AI summary to get started</p>
            {fullScreen && (
              <button
                onClick={handleGenerateSummary}
                disabled={isLoading}
                className="px-4 py-2 bg-purple-600 text-white text-sm font-medium rounded-lg hover:bg-purple-700 disabled:bg-gray-400 transition-colors"
              >
                {isLoading ? 'Generating...' : 'Generate Summary'}
              </button>
            )}
          </div>
        ) : (
          messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`rounded-lg relative ${
                  msg.role === 'user'
                    ? 'bg-blue-600 text-white max-w-[80%] px-4 py-2'
                    : fullScreen
                      ? 'bg-white text-gray-800 border border-gray-200 max-w-[85%] px-4 py-3 pr-10 shadow-sm'
                      : 'bg-gray-50 text-gray-800 border border-gray-200 max-w-full px-4 py-2 pr-10'
                }`}
              >
                {msg.role === 'assistant' && <CopyButton text={msg.content} />}
                {msg.role === 'assistant' ? (
                  <div className="prose prose-sm max-w-none prose-headings:text-gray-900 prose-p:text-gray-700 prose-li:text-gray-700 prose-table:text-sm">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        a: ({ href, children }) => (
                          <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
                            {children}
                          </a>
                        )
                      }}
                    >
                      {msg.content}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <div className="text-sm">{msg.content}</div>
                )}
              </div>
            </div>
          ))
        )}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 text-gray-800 px-4 py-2 rounded-lg">
              <div className="flex items-center space-x-2">
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Error */}
      {error && (
        <div className="px-4 py-2 bg-red-50 border-t border-red-200 text-red-700 text-sm shrink-0">
          {error}
        </div>
      )}

      {/* Input */}
      <form onSubmit={handleSendMessage} className={`shrink-0 ${fullScreen ? 'p-4 bg-gray-50' : 'p-4 border-t border-gray-200'}`}>
        <div className={`flex gap-2 ${fullScreen ? 'max-w-3xl mx-auto' : ''}`}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about the video..."
            className={`flex-1 px-4 py-2 border border-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none text-gray-900 ${
              fullScreen ? 'rounded-full bg-white shadow-sm' : 'rounded-lg'
            }`}
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className={`px-4 py-2 bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors ${
              fullScreen ? 'rounded-full' : 'rounded-lg'
            }`}
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
