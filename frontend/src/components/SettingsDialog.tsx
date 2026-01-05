import { useState, useEffect, useRef } from 'react';
import {
  getHistorySettings,
  getExportHistoryUrl,
  clearAllHistory,
  getStoredToken,
  type HistorySettings
} from '../api/client';

interface SettingsDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onHistoryCleared: () => void;
}

// Icons
const CloseIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
  </svg>
);

const DownloadIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
  </svg>
);

const TrashIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
  </svg>
);

const WarningIcon = () => (
  <svg className="w-12 h-12 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
  </svg>
);

export function SettingsDialog({ isOpen, onClose, onHistoryCleared }: SettingsDialogProps) {
  const [settings, setSettings] = useState<HistorySettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [exporting, setExporting] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      loadSettings();
    }
  }, [isOpen]);

  // Close on escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (showClearConfirm) {
          setShowClearConfirm(false);
        } else {
          onClose();
        }
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      return () => document.removeEventListener('keydown', handleEscape);
    }
  }, [isOpen, showClearConfirm, onClose]);

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dialogRef.current && !dialogRef.current.contains(e.target as Node)) {
        if (showClearConfirm) {
          setShowClearConfirm(false);
        } else {
          onClose();
        }
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen, showClearConfirm, onClose]);

  const loadSettings = async () => {
    setLoading(true);
    try {
      const data = await getHistorySettings();
      setSettings(data);
    } catch (error) {
      console.error('Failed to load settings:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const url = getExportHistoryUrl();
      const token = getStoredToken();

      const response = await fetch(url, {
        credentials: 'include',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
      });

      if (!response.ok) {
        throw new Error('Failed to export history');
      }

      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = `video-history-${new Date().toISOString().split('T')[0]}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(downloadUrl);
    } catch (error) {
      console.error('Failed to export:', error);
      alert('Failed to export history. Please try again.');
    } finally {
      setExporting(false);
    }
  };

  const handleClearAll = async () => {
    setClearing(true);
    try {
      await clearAllHistory();
      setSettings(prev => prev ? { ...prev, current_count: 0 } : null);
      setShowClearConfirm(false);
      onHistoryCleared();
    } catch (error) {
      console.error('Failed to clear history:', error);
      alert('Failed to clear history. Please try again.');
    } finally {
      setClearing(false);
    }
  };

  if (!isOpen) return null;

  const usagePercent = settings ? (settings.current_count / settings.max_entries) * 100 : 0;

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div
        ref={dialogRef}
        className="bg-white rounded-xl shadow-2xl w-full max-w-md overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Settings</h2>
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-gray-600 transition-colors rounded-lg hover:bg-gray-100"
          >
            <CloseIcon />
          </button>
        </div>

        {/* Content */}
        <div className="px-6 py-5 space-y-6">
          {loading ? (
            <div className="text-center py-8 text-gray-500">Loading...</div>
          ) : (
            <>
              {/* Storage Usage Section */}
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-3">Storage Usage</h3>
                <div className="bg-gray-50 rounded-lg p-4 space-y-3">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600">Videos stored</span>
                    <span className="font-medium text-gray-900">
                      {settings?.current_count ?? 0} / {settings?.max_entries ?? 50}
                    </span>
                  </div>
                  <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className={`h-full transition-all ${
                        usagePercent > 80 ? 'bg-red-500' : usagePercent > 50 ? 'bg-yellow-500' : 'bg-blue-500'
                      }`}
                      style={{ width: `${Math.min(usagePercent, 100)}%` }}
                    />
                  </div>
                  <p className="text-xs text-gray-500">
                    Oldest videos are automatically removed when the limit is reached.
                  </p>
                </div>
              </div>

              {/* Retention Info */}
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-3">Data Retention</h3>
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-600">
                    Videos and chat history are stored for up to{' '}
                    <span className="font-medium text-gray-900">{settings?.retention_days ?? 90} days</span>.
                  </p>
                </div>
              </div>

              {/* API Status */}
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-3">API Integrations</h3>
                <div className="bg-gray-50 rounded-lg p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-600">OpenAI (Chat & Summaries)</span>
                    {settings?.api_status?.openai ? (
                      <span className="flex items-center gap-1 text-sm text-green-600 font-medium">
                        <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                        Connected
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-sm text-gray-400">
                        <span className="w-2 h-2 bg-gray-300 rounded-full"></span>
                        Not configured
                      </span>
                    )}
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-600">Exa AI (Study Links)</span>
                    {settings?.api_status?.exa ? (
                      <span className="flex items-center gap-1 text-sm text-green-600 font-medium">
                        <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                        Connected
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-sm text-gray-400">
                        <span className="w-2 h-2 bg-gray-300 rounded-full"></span>
                        Not configured
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Actions */}
              <div className="space-y-3">
                <h3 className="text-sm font-medium text-gray-700">Actions</h3>

                {/* Export Button */}
                <button
                  onClick={handleExport}
                  disabled={exporting || (settings?.current_count ?? 0) === 0}
                  className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-gray-100 hover:bg-gray-200 disabled:bg-gray-50 disabled:text-gray-400 text-gray-700 rounded-lg transition-colors font-medium"
                >
                  <DownloadIcon />
                  <span>{exporting ? 'Exporting...' : 'Export History as JSON'}</span>
                </button>

                {/* Clear All Button */}
                <button
                  onClick={() => setShowClearConfirm(true)}
                  disabled={(settings?.current_count ?? 0) === 0}
                  className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-red-50 hover:bg-red-100 disabled:bg-gray-50 disabled:text-gray-400 text-red-600 rounded-lg transition-colors font-medium"
                >
                  <TrashIcon />
                  <span>Clear All History</span>
                </button>
              </div>
            </>
          )}
        </div>

        {/* Clear Confirmation Modal */}
        {showClearConfirm && (
          <div className="absolute inset-0 bg-black/50 flex items-center justify-center p-4">
            <div className="bg-white rounded-xl shadow-2xl p-6 max-w-sm w-full text-center">
              <div className="flex justify-center mb-4">
                <WarningIcon />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">Clear All History?</h3>
              <p className="text-sm text-gray-600 mb-6">
                This will permanently delete all {settings?.current_count ?? 0} videos and their chat history.
                This action cannot be undone.
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => setShowClearConfirm(false)}
                  disabled={clearing}
                  className="flex-1 px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg font-medium transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleClearAll}
                  disabled={clearing}
                  className="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium transition-colors"
                >
                  {clearing ? 'Clearing...' : 'Clear All'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
