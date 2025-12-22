import { useState } from 'react';
import { previewSource, addSource, pollSource } from '../api/client';
import type { SourcePreview } from '../api/types';

interface Props {
  onClose: () => void;
  onAdded: () => void;
}

export function AddSourceModal({ onClose, onAdded }: Props) {
  const [url, setUrl] = useState('');
  const [preview, setPreview] = useState<SourcePreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handlePreview = async () => {
    if (!url.trim()) return;

    setLoading(true);
    setError(null);
    setPreview(null);

    try {
      const data = await previewSource(url.trim());
      setPreview(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to preview source');
    } finally {
      setLoading(false);
    }
  };

  const handleAdd = async () => {
    if (!url.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const source = await addSource(url.trim());
      // Poll immediately
      await pollSource(source.id);
      onAdded();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add source');
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !loading) {
      if (preview) {
        handleAdd();
      } else {
        handlePreview();
      }
    }
    if (e.key === 'Escape') {
      onClose();
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-neutral-900 rounded-lg shadow-xl w-full max-w-md mx-4 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-4 py-3 border-b border-neutral-800">
          <h2 className="text-lg font-medium">Add Source</h2>
        </div>

        {/* Content */}
        <div className="p-4 space-y-4">
          {/* URL Input */}
          <div>
            <label className="block text-sm text-neutral-400 mb-1">
              Feed URL
            </label>
            <input
              type="url"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                setPreview(null);
                setError(null);
              }}
              onKeyDown={handleKeyDown}
              placeholder="https://example.com/feed.xml"
              className="w-full px-3 py-2 bg-neutral-800 border border-neutral-700 rounded text-neutral-100 placeholder-neutral-500 focus:outline-none focus:border-blue-500"
              autoFocus
            />
          </div>

          {/* Error */}
          {error && (
            <div className="text-sm text-red-400 bg-red-900/20 px-3 py-2 rounded">
              {error}
            </div>
          )}

          {/* Preview */}
          {preview && (
            <div className="bg-neutral-800/50 rounded p-3 space-y-2">
              <div className="font-medium">{preview.display_name}</div>
              <div className="text-sm text-neutral-400">
                Type: {preview.source_type}
              </div>
              {preview.description && (
                <div className="text-sm text-neutral-500 line-clamp-2">
                  {preview.description}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-neutral-800 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-neutral-400 hover:text-neutral-200 transition-colors"
          >
            Cancel
          </button>
          {preview ? (
            <button
              onClick={handleAdd}
              disabled={loading}
              className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded transition-colors"
            >
              {loading ? 'Adding...' : 'Add Source'}
            </button>
          ) : (
            <button
              onClick={handlePreview}
              disabled={loading || !url.trim()}
              className="px-4 py-2 text-sm bg-neutral-700 hover:bg-neutral-600 disabled:opacity-50 rounded transition-colors"
            >
              {loading ? 'Loading...' : 'Preview'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
