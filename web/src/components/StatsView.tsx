import { useEffect, useState } from 'react';
import { getFeedbackStats } from '../api/client';
import type { FeedbackStats } from '../api/types';

interface Props {
  onClose: () => void;
  sourceId?: string;
}

export function StatsView({ onClose, sourceId }: Props) {
  const [stats, setStats] = useState<FeedbackStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadStats() {
      try {
        const data = await getFeedbackStats(sourceId);
        setStats(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load stats');
      } finally {
        setLoading(false);
      }
    }
    loadStats();
  }, [sourceId]);

  const formatDuration = (ms: number): string => {
    if (ms < 1000) return `${Math.round(ms)}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}m`;
  };

  const formatTotalTime = (ms: number): string => {
    const minutes = Math.floor(ms / 60000);
    const hours = Math.floor(minutes / 60);
    if (hours > 0) {
      return `${hours}h ${minutes % 60}m`;
    }
    return `${minutes}m`;
  };

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
      <div className="bg-neutral-900 rounded-lg w-full max-w-4xl max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="px-4 py-3 border-b border-neutral-800 flex items-center justify-between">
          <h2 className="text-lg font-medium">
            {sourceId ? 'Source Engagement Stats' : 'Engagement Statistics by Source'}
          </h2>
          <button
            onClick={onClose}
            className="text-neutral-400 hover:text-white transition-colors"
          >
            Close
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading && (
            <div className="text-center text-neutral-500 py-8">Loading...</div>
          )}

          {error && (
            <div className="text-center text-red-400 py-8">{error}</div>
          )}

          {stats && (
            <div className="space-y-6">
              {/* Summary */}
              <div className="text-sm text-neutral-400">
                {stats.total_events} total events
                {!sourceId && ` across ${stats.slices.length} sources`}
              </div>

              {/* Per-source stats table */}
              {stats.slices.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-neutral-700 text-left text-neutral-400">
                        <th className="pb-2 pr-4">Source</th>
                        <th className="pb-2 pr-4 text-right">Engagements</th>
                        <th className="pb-2 pr-4 text-right">Avg Time</th>
                        <th className="pb-2 pr-4 text-right">Avg Progress</th>
                        <th className="pb-2 pr-4 text-right">Completion</th>
                        <th className="pb-2 text-right">Total Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stats.slices.map((slice) => (
                        <tr
                          key={slice.filter.source_id}
                          className="border-b border-neutral-800 hover:bg-neutral-800/50"
                        >
                          <td className="py-2 pr-4 font-medium truncate max-w-[200px]">
                            {slice.filter.source_name}
                          </td>
                          <td className="py-2 pr-4 text-right">
                            {slice.stats.total_engagements}
                          </td>
                          <td className="py-2 pr-4 text-right text-neutral-300">
                            {formatDuration(slice.stats.avg_time_spent_ms)}
                          </td>
                          <td className="py-2 pr-4 text-right text-neutral-300">
                            {slice.stats.avg_progress_pct.toFixed(0)}%
                          </td>
                          <td className="py-2 pr-4 text-right">
                            <span
                              className={
                                slice.stats.completion_rate >= 70
                                  ? 'text-green-400'
                                  : slice.stats.completion_rate >= 40
                                  ? 'text-yellow-400'
                                  : 'text-neutral-400'
                              }
                            >
                              {slice.stats.completion_rate.toFixed(0)}%
                            </span>
                          </td>
                          <td className="py-2 text-right text-neutral-300">
                            {formatTotalTime(slice.stats.total_time_spent_ms)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center text-neutral-500 py-8">
                  No engagement data yet. Open some items to start tracking.
                </div>
              )}

              {/* Recent Events */}
              <div className="bg-neutral-800 rounded-lg p-4">
                <h3 className="font-medium mb-3">Recent Events</h3>
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {stats.recent_events.map((event) => (
                    <div
                      key={event.id}
                      className="flex items-center justify-between text-sm py-1 border-b border-neutral-700 last:border-0"
                    >
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 bg-neutral-700 rounded text-xs">
                          {event.event_type}
                        </span>
                        <span className="text-neutral-500 text-xs truncate max-w-[150px]">
                          {event.item_id}
                        </span>
                      </div>
                      <span className="text-neutral-500 text-xs">
                        {new Date(event.timestamp).toLocaleString()}
                      </span>
                    </div>
                  ))}
                  {stats.recent_events.length === 0 && (
                    <div className="text-neutral-500 text-sm">No events yet</div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
