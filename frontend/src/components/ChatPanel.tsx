import { useState, useRef, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { generateSummary, sendChatMessage, clearChatHistory, type ChatMessage } from '../api/client';

// Helper to convert File to base64
function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      // Remove the data URL prefix (e.g., "data:image/jpeg;base64,")
      const base64 = result.split(',')[1];
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

// Validate image file
function isValidImageFile(file: File): boolean {
  const validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp'];
  return validTypes.includes(file.type) && file.size <= 20 * 1024 * 1024; // Max 20MB
}

interface ChatPanelProps {
  jobId: string;
  initialMessages?: ChatMessage[];
  fullScreen?: boolean;
  onChatCleared?: () => void;
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
      // Fallback for iOS and other browsers with clipboard restrictions
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.left = '-9999px';
      textArea.style.top = '0';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      try {
        document.execCommand('copy');
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch {
        console.error('Copy fallback also failed:', err);
      }
      document.body.removeChild(textArea);
    }
  };

  return (
    <button
      onClick={handleCopy}
      className="absolute top-2 right-2 p-1.5 rounded-md bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 transition-colors"
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

export function ChatPanel({ jobId, initialMessages, fullScreen = false, onChatCleared }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages || []);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string>();
  const [selectedImage, setSelectedImage] = useState<{ file: File; base64: string; preview: string } | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const currentJobIdRef = useRef<string>(jobId);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // Reset state when jobId changes (new video selected)
  useEffect(() => {
    currentJobIdRef.current = jobId;
    setMessages(initialMessages || []);
    setIsLoading(false);
    setError(undefined);
    setSelectedImage(null);
  }, [jobId, initialMessages]);

  // Handle image file selection
  const handleImageSelect = useCallback(async (file: File) => {
    if (!isValidImageFile(file)) {
      setError('Please select a valid image (JPEG, PNG, or WebP, max 20MB)');
      return;
    }
    try {
      const base64 = await fileToBase64(file);
      const preview = URL.createObjectURL(file);
      setSelectedImage({ file, base64, preview });
      setError(undefined);
    } catch {
      setError('Failed to load image');
    }
  }, []);

  // Handle file input change
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleImageSelect(file);
    e.target.value = ''; // Reset to allow re-selecting same file
  };

  // Handle drag and drop
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('image/')) {
      handleImageSelect(file);
    }
  }, [handleImageSelect]);

  // Clear selected image
  const clearImage = () => {
    if (selectedImage?.preview) {
      URL.revokeObjectURL(selectedImage.preview);
    }
    setSelectedImage(null);
  };

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

  const handleClearChat = async () => {
    if (!confirm('Clear chat history for this video? This cannot be undone.')) return;
    
    setIsLoading(true);
    setError(undefined);
    try {
      await clearChatHistory(jobId);
      setMessages([]);
      onChatCleared?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to clear chat');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if ((!input.trim() && !selectedImage) || isLoading) return;

    const requestJobId = jobId;
    const userMessage = input.trim() || (selectedImage ? 'Please analyse this image' : '');
    const imageBase64 = selectedImage?.base64;
    
    setInput('');
    clearImage();
    setError(undefined);

    // Include image reference in the displayed message
    const displayMessage = selectedImage 
      ? `${userMessage}\n\n[📎 Image attached]`
      : userMessage;
    
    const newMessage: ChatMessage = { 
      role: 'user', 
      content: displayMessage,
      image_base64: imageBase64
    };
    const newMessages: ChatMessage[] = [...messages, newMessage];
    setMessages(newMessages);
    setIsLoading(true);

    try {
      const response = await sendChatMessage(requestJobId, userMessage, messages, imageBase64);
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
    ? "bg-gray-50 dark:bg-gray-950 flex flex-col h-full"
    : "bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg shadow-sm flex flex-col h-full min-h-[400px] max-h-[calc(100vh-200px)]";

  return (
    <div className={containerClass}>
      {/* Header - only show when not fullScreen */}
      {!fullScreen && (
        <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between shrink-0">
          <h3 className="font-semibold text-gray-800 dark:text-gray-100">AI Assistant</h3>
          <div className="flex items-center gap-2">
            {messages.length > 0 && (
              <button
                onClick={handleClearChat}
                disabled={isLoading}
                className="px-3 py-1.5 text-gray-600 dark:text-gray-400 text-sm font-medium rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50 transition-colors"
                title="Clear chat history"
              >
                Clear Chat
              </button>
            )}
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
        </div>
      )}

      {/* Messages */}
      {/* Clear Chat button for fullScreen mode */}
      {fullScreen && messages.length > 0 && (
        <div className="px-4 py-2 flex justify-end">
          <button
            onClick={handleClearChat}
            disabled={isLoading}
            className="px-3 py-1.5 text-gray-600 dark:text-gray-400 text-sm font-medium rounded-lg hover:bg-gray-200 dark:hover:bg-gray-800 disabled:opacity-50 transition-colors"
            title="Clear chat history"
          >
            Clear Chat
          </button>
        </div>
      )}

      <div className={`flex-1 overflow-y-auto space-y-4 min-h-0 ${fullScreen ? 'px-4 py-6' : 'p-4'}`}>
        {messages.length === 0 ? (
          <div className={`text-center text-gray-500 dark:text-gray-400 ${fullScreen ? 'mt-16' : 'mt-8'}`}>
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
                      ? 'bg-white dark:bg-gray-900 text-gray-800 dark:text-gray-100 border border-gray-200 dark:border-gray-800 max-w-[85%] px-4 py-3 pr-10 shadow-sm'
                      : 'bg-gray-50 dark:bg-gray-800/60 text-gray-800 dark:text-gray-100 border border-gray-200 dark:border-gray-800 max-w-full px-4 py-2 pr-10'
                }`}
              >
                {msg.role === 'assistant' && <CopyButton text={msg.content} />}
                {msg.role === 'assistant' ? (
                  <div className="prose prose-sm max-w-none dark:prose-invert prose-table:text-sm">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        a: ({ href, children }) => (
                          <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-600 dark:text-blue-400 hover:underline">
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
            <div className="bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-100 px-4 py-2 rounded-lg">
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
        <div className="px-4 py-2 bg-red-50 dark:bg-red-950/40 border-t border-red-200 dark:border-red-900/60 text-red-700 dark:text-red-300 text-sm shrink-0">
          {error}
        </div>
      )}

      {/* Input */}
      <form 
        onSubmit={handleSendMessage} 
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`shrink-0 ${fullScreen ? 'p-4 bg-gray-50 dark:bg-gray-950' : 'p-4 border-t border-gray-200 dark:border-gray-800'} ${
          isDragging ? 'ring-2 ring-blue-500 ring-inset bg-blue-50 dark:bg-blue-950/30' : ''
        }`}
      >
        {/* Image preview */}
        {selectedImage && (
          <div className={`mb-2 ${fullScreen ? 'max-w-3xl mx-auto' : ''}`}>
            <div className="relative inline-block">
              <img 
                src={selectedImage.preview} 
                alt="Selected" 
                className="h-20 rounded-lg border border-gray-300 dark:border-gray-700 object-cover"
              />
              <button
                type="button"
                onClick={clearImage}
                className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 text-white rounded-full flex items-center justify-center text-xs hover:bg-red-600"
                title="Remove image"
              >
                ×
              </button>
            </div>
          </div>
        )}
        
        {/* Drag hint */}
        {isDragging && (
          <div className={`mb-2 text-center text-blue-600 dark:text-blue-400 text-sm ${fullScreen ? 'max-w-3xl mx-auto' : ''}`}>
            Drop image here
          </div>
        )}
        
        <div className={`flex gap-2 ${fullScreen ? 'max-w-3xl mx-auto' : ''}`}>
          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={handleFileChange}
            className="hidden"
          />
          
          {/* Image upload button */}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
            className={`px-3 py-2 border border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors ${
              fullScreen ? 'rounded-full' : 'rounded-lg'
            }`}
            title="Attach image (screenshot of slide, references, etc.)"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
          </button>
          
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={selectedImage ? "Add a message about this image..." : "Ask about the video..."}
            className={`flex-1 px-4 py-2 border border-gray-300 dark:border-gray-700 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none text-gray-900 dark:text-gray-100 ${
              fullScreen ? 'rounded-full bg-white dark:bg-gray-900 shadow-sm' : 'rounded-lg bg-white dark:bg-gray-900'
            }`}
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={isLoading || (!input.trim() && !selectedImage)}
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
