import { useEffect, useState } from 'react';
import { getFeedbackStats, getModelStatus, trainModel } from '../api/client';
import type { FeedbackStats, ModelStatus, TrainResult } from '../api/types';

interface Props {
  onClose: () => void;
  sourceId?: string;
}

export function StatsView({ onClose, sourceId }: Props) {
  const [stats, setStats] = useState<FeedbackStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);
  const [training, setTraining] = useState(false);
  const [trainResult, setTrainResult] = useState<TrainResult | null>(null);

  useEffect(() => {
    async function loadStats() {
      try {
        const [feedbackData, modelData] = await Promise.all([
          getFeedbackStats(sourceId),
          getModelStatus(),
        ]);
        setStats(feedbackData);
        setModelStatus(modelData);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load stats');
      } finally {
        setLoading(false);
      }
    }
    loadStats();
  }, [sourceId]);

  const handleTrain = async () => {
    setTraining(true);
    setTrainResult(null);
    try {
      const result = await trainModel();
      setTrainResult(result);
      // Refresh model status
      const status = await getModelStatus();
      setModelStatus(status);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Training failed');
    } finally {
      setTraining(false);
    }
  };

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
              {/* Model Status */}
              {modelStatus && (
                <div className="bg-neutral-800 rounded-lg p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-medium mb-1">Ranking Model</h3>
                      <div className="text-sm text-neutral-400">
                        {modelStatus.is_trained ? (
                          <span className="text-green-400">Trained</span>
                        ) : (
                          <span className="text-yellow-400">Not trained</span>
                        )}
                        {modelStatus.source_count > 0 && (
                          <span className="ml-2">
                            ({modelStatus.source_count} source stats)
                          </span>
                        )}
                      </div>
                      {trainResult && (
                        <div className="text-sm mt-2">
                          {trainResult.status === 'success' ? (
                            <span className="text-green-400">
                              Trained on {trainResult.example_count} examples
                              ({trainResult.click_examples} clicks, {trainResult.reward_examples} rated)
                            </span>
                          ) : (
                            <div className="space-y-1">
                              <div className="text-yellow-400">
                                {trainResult.status}: {trainResult.example_count}/5 examples
                              </div>
                              {trainResult.issues && trainResult.issues.length > 0 && (
                                <ul className="text-neutral-400 text-xs list-disc ml-4">
                                  {trainResult.issues.map((issue, i) => (
                                    <li key={i}>{issue}</li>
                                  ))}
                                </ul>
                              )}
                              {trainResult.items_with_embeddings !== undefined && (
                                <div className="text-neutral-500 text-xs">
                                  {trainResult.items_with_embeddings}/{trainResult.total_items} items have embeddings,{' '}
                                  {trainResult.click_events} clicks, {trainResult.explicit_feedbacks} ratings
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                    <button
                      onClick={handleTrain}
                      disabled={training}
                      className={`px-4 py-2 rounded font-medium transition-colors ${
                        training
                          ? 'bg-neutral-700 text-neutral-400 cursor-not-allowed'
                          : 'bg-blue-600 hover:bg-blue-500 text-white'
                      }`}
                    >
                      {training ? 'Training...' : 'Train Model'}
                    </button>
                  </div>
                </div>
              )}

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
