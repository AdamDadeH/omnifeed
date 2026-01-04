import { useEffect, useState } from 'react';
import { getSources, pollSource, disableSource } from '../api/client';
import type { Source } from '../api/types';

interface Props {
  onClose: () => void;
  onRefresh: () => void;
  isFullPage?: boolean;
}

export function SourcesView({ onClose, onRefresh, isFullPage }: Props) {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [pollingId, setPollingId] = useState<string | null>(null);

  const loadSources = async () => {
    try {
      const data = await getSources();
      setSources(data);
    } catch (err) {
      console.error('Failed to load sources:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSources();
  }, []);

  const handlePoll = async (sourceId: string) => {
    setPollingId(sourceId);
    try {
      const result = await pollSource(sourceId);
      if (result.new_items > 0) {
        onRefresh();
      }
      loadSources();
    } catch (err) {
      console.error('Failed to poll:', err);
    } finally {
      setPollingId(null);
    }
  };

  const handleDelete = async (source: Source) => {
    if (!confirm(`Delete "${source.display_name}"?\n\nThis will disable the source. Items will remain in your feed.`)) {
      return;
    }
    try {
      await disableSource(source.id);
      loadSources();
      onRefresh();
    } catch (err) {
      console.error('Failed to delete:', err);
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'Never';
    return new Date(dateStr).toLocaleDateString();
  };

  const content = (
    <>
      {loading ? (
        <div className="text-center text-neutral-500 py-8">Loading...</div>
      ) : sources.length === 0 ? (
        <div className="text-center text-neutral-500 py-8">No sources added yet.</div>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-neutral-700 text-left text-neutral-400">
              <th className="pb-2 pr-4">Source</th>
              <th className="pb-2 pr-4">Type</th>
              <th className="pb-2 pr-4 text-right">Items</th>
              <th className="pb-2 pr-4">Last Polled</th>
              <th className="pb-2 pr-4">Status</th>
              <th className="pb-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((source) => (
              <tr
                key={source.id}
                className="border-b border-neutral-800 hover:bg-neutral-800/50"
              >
                <td className="py-3 pr-4">
                  <div className="font-medium">{source.display_name}</div>
                  <div className="text-xs text-neutral-500 truncate max-w-[250px]">
                    {source.uri}
                  </div>
                </td>
                <td className="py-3 pr-4 text-neutral-400">
                  {source.source_type}
                </td>
                <td className="py-3 pr-4 text-right">
                  {source.item_count}
                </td>
                <td className="py-3 pr-4 text-neutral-400">
                  {formatDate(source.last_polled_at)}
                </td>
                <td className="py-3 pr-4">
                  <span className={`px-2 py-0.5 rounded text-xs ${
                    source.status === 'active'
                      ? 'bg-green-900 text-green-300'
                      : 'bg-neutral-700 text-neutral-400'
                  }`}>
                    {source.status}
                  </span>
                </td>
                <td className="py-3 text-right">
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => handlePoll(source.id)}
                      disabled={pollingId !== null}
                      className="px-2 py-1 text-xs bg-neutral-700 hover:bg-neutral-600 rounded disabled:opacity-50"
                    >
                      {pollingId === source.id ? 'Polling...' : 'Poll'}
                    </button>
                    <button
                      onClick={() => handleDelete(source)}
                      className="px-2 py-1 text-xs text-red-400 hover:bg-red-900/30 rounded"
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );

  if (isFullPage) {
    return (
      <div className="flex-1 flex flex-col overflow-hidden">
        <header className="px-4 pt-3 pb-2 border-b border-neutral-800">
          <h2 className="text-lg font-medium">Sources</h2>
          <p className="text-sm text-neutral-500 mt-1">
            {sources.length} sources configured
          </p>
        </header>
        <div className="flex-1 overflow-y-auto p-4">
          {content}
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
      <div className="bg-neutral-900 rounded-lg w-full max-w-4xl max-h-[80vh] flex flex-col">
        <div className="px-4 py-3 border-b border-neutral-800 flex items-center justify-between">
          <h2 className="text-lg font-medium">Manage Sources</h2>
          <button
            onClick={onClose}
            className="text-neutral-400 hover:text-white transition-colors"
          >
            Close
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {content}
        </div>
      </div>
    </div>
  );
}
