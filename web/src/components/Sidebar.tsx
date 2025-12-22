import { useEffect, useState } from 'react';
import { getSources, pollAllSources } from '../api/client';
import type { Source } from '../api/types';

interface Props {
  selectedSource: string | undefined;
  onSelectSource: (id: string | undefined) => void;
  onAddSource: () => void;
  onRefresh: () => void;
}

export function Sidebar({ selectedSource, onSelectSource, onAddSource, onRefresh }: Props) {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(false);

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

  const handlePollAll = async () => {
    setPolling(true);
    try {
      const results = await pollAllSources();
      const totalNew = results.reduce((sum, r) => sum + r.new_items, 0);
      if (totalNew > 0) {
        onRefresh();
        loadSources();
      }
    } catch (err) {
      console.error('Failed to poll:', err);
    } finally {
      setPolling(false);
    }
  };

  return (
    <aside className="w-64 h-screen bg-neutral-900 border-r border-neutral-800 flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-neutral-800">
        <h1 className="text-lg font-semibold text-neutral-100">OmniFeed</h1>
      </div>

      {/* Actions */}
      <div className="p-2 border-b border-neutral-800 flex gap-2">
        <button
          onClick={handlePollAll}
          disabled={polling}
          className="flex-1 px-3 py-1.5 text-sm bg-neutral-800 hover:bg-neutral-700 disabled:opacity-50 rounded transition-colors"
        >
          {polling ? 'Polling...' : 'Refresh All'}
        </button>
        <button
          onClick={onAddSource}
          className="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 rounded transition-colors"
        >
          + Add
        </button>
      </div>

      {/* Feed filters */}
      <div className="p-2 border-b border-neutral-800">
        <button
          onClick={() => onSelectSource(undefined)}
          className={`w-full text-left px-3 py-2 rounded text-sm transition-colors ${
            !selectedSource
              ? 'bg-neutral-800 text-neutral-100'
              : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/50'
          }`}
        >
          All Sources
        </button>
      </div>

      {/* Sources list */}
      <div className="flex-1 overflow-y-auto p-2">
        {loading ? (
          <div className="text-sm text-neutral-500 p-3">Loading...</div>
        ) : sources.length === 0 ? (
          <div className="text-sm text-neutral-500 p-3">No sources yet</div>
        ) : (
          <div className="space-y-1">
            {sources.map((source) => (
              <button
                key={source.id}
                onClick={() => onSelectSource(source.id)}
                className={`w-full text-left px-3 py-2 rounded text-sm transition-colors ${
                  selectedSource === source.id
                    ? 'bg-neutral-800 text-neutral-100'
                    : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="truncate">{source.display_name}</span>
                  <span className="text-xs text-neutral-600 ml-2">
                    {source.item_count}
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
