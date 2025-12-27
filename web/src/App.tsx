import { useState, useCallback, useEffect } from 'react';
import { Sidebar, FeedList, AddSourceModal, ReaderPane, StatsView, SourcesView, CreatorsView, RatedView } from './components';
import type { ReadingFeedback } from './components';
import type { FeedItem } from './api/types';
import { markSeen, recordFeedback, pollSource, pollAllSources, getObjectives } from './api/client';
import type { Objective } from './api/client';

function App() {
  const [selectedSource, setSelectedSource] = useState<string | undefined>();
  const [showAddModal, setShowAddModal] = useState(false);
  const [showSeen, setShowSeen] = useState(false);
  const [showStats, setShowStats] = useState(false);
  const [showSources, setShowSources] = useState(false);
  const [showCreators, setShowCreators] = useState(false);
  const [showRated, setShowRated] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [readingItem, setReadingItem] = useState<FeedItem | null>(null);
  const [polling, setPolling] = useState(false);
  const [objectives, setObjectives] = useState<Objective[]>([]);
  const [selectedObjective, setSelectedObjective] = useState<string | undefined>();

  // Load objectives on mount
  useEffect(() => {
    getObjectives().then((data) => {
      setObjectives(data.objectives);
    }).catch(console.error);
  }, []);

  const handleRefresh = useCallback(() => {
    setRefreshKey((k) => k + 1);
  }, []);

  const handlePoll = useCallback(async () => {
    setPolling(true);
    try {
      if (selectedSource) {
        // Poll just the selected source
        await pollSource(selectedSource);
      } else {
        // Poll all sources
        await pollAllSources();
      }
      handleRefresh();
    } catch (err) {
      console.error('Failed to poll:', err);
    } finally {
      setPolling(false);
    }
  }, [selectedSource, handleRefresh]);

  const handleSourceAdded = useCallback(() => {
    handleRefresh();
  }, [handleRefresh]);

  const handleOpenItem = useCallback(async (item: FeedItem) => {
    setReadingItem(item);
    // Don't mark as seen yet - only when user completes (clicks "Rate")
    // Record click event for analytics
    await recordFeedback(item.id, 'click', {});
  }, []);

  const handleCloseReader = useCallback(() => {
    setReadingItem(null);
    handleRefresh(); // Refresh to update seen status
  }, [handleRefresh]);

  const handleReadingFeedback = useCallback(async (feedback: ReadingFeedback) => {
    // Mark as seen now that user completed the item
    await markSeen(feedback.item_id);

    // Record completion event
    await recordFeedback(feedback.item_id, 'reading_complete', {
      time_spent_ms: feedback.time_spent_ms,
      max_scroll_pct: feedback.max_scroll_pct,
      completed: feedback.completed,
      scroll_events: feedback.scroll_events,
    });
  }, []);

  return (
    <div className="flex h-screen bg-neutral-950">
      {/* Sidebar */}
      <Sidebar
        selectedSource={selectedSource}
        onSelectSource={setSelectedSource}
        onAddSource={() => setShowAddModal(true)}
        onRefresh={handleRefresh}
      />

      {/* Main content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Header - Row 1: View selectors */}
        <header className="px-4 pt-3 pb-2 border-b border-neutral-800">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-lg font-medium">
              {selectedSource ? 'Source Feed' : 'All Items'}
            </h2>

            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowCreators(true)}
                className="px-3 py-1.5 text-sm bg-neutral-800 hover:bg-neutral-700 rounded transition-colors"
              >
                Creators
              </button>

              <button
                onClick={() => setShowSources(true)}
                className="px-3 py-1.5 text-sm bg-neutral-800 hover:bg-neutral-700 rounded transition-colors"
              >
                Sources
              </button>

              <button
                onClick={() => setShowRated(true)}
                className="px-3 py-1.5 text-sm bg-neutral-800 hover:bg-neutral-700 rounded transition-colors"
              >
                Rated
              </button>

              <button
                onClick={() => setShowStats(true)}
                className="px-3 py-1.5 text-sm bg-neutral-800 hover:bg-neutral-700 rounded transition-colors"
              >
                Models
              </button>

              <div className="w-px h-6 bg-neutral-700 mx-1" />

              <button
                onClick={handlePoll}
                disabled={polling}
                className="px-3 py-1.5 text-sm bg-neutral-800 hover:bg-neutral-700 disabled:opacity-50 rounded transition-colors"
              >
                {polling ? 'Refreshing...' : selectedSource ? 'Refresh Source' : 'Refresh All'}
              </button>
            </div>
          </div>

          {/* Row 2: Filters */}
          <div className="flex items-center gap-4">
            {/* Objective selector */}
            {objectives.length > 0 && (
              <select
                value={selectedObjective || ''}
                onChange={(e) => setSelectedObjective(e.target.value || undefined)}
                className="px-3 py-1.5 text-sm bg-neutral-800 hover:bg-neutral-700 rounded border border-neutral-700 text-neutral-200"
              >
                <option value="">All objectives</option>
                {objectives.map((obj) => (
                  <option key={obj.id} value={obj.id}>
                    {obj.label} {obj.training_count > 0 ? `(${obj.training_count})` : ''}
                  </option>
                ))}
              </select>
            )}

            <label className="flex items-center gap-2 text-sm text-neutral-400">
              <input
                type="checkbox"
                checked={showSeen}
                onChange={(e) => setShowSeen(e.target.checked)}
                className="rounded bg-neutral-800 border-neutral-600"
              />
              Show read
            </label>
          </div>
        </header>

        {/* Feed */}
        <div className="flex-1 overflow-y-auto">
          <FeedList
            sourceFilter={selectedSource}
            showSeen={showSeen}
            objective={selectedObjective}
            refreshKey={refreshKey}
            onOpenItem={handleOpenItem}
          />
        </div>
      </main>

      {/* Add source modal */}
      {showAddModal && (
        <AddSourceModal
          onClose={() => setShowAddModal(false)}
          onAdded={handleSourceAdded}
        />
      )}

      {/* Reader pane */}
      {readingItem && (
        <ReaderPane
          item={readingItem}
          onClose={handleCloseReader}
          onFeedback={handleReadingFeedback}
        />
      )}

      {/* Stats view */}
      {showStats && (
        <StatsView onClose={() => setShowStats(false)} sourceId={selectedSource} />
      )}

      {/* Sources view */}
      {showSources && (
        <SourcesView onClose={() => setShowSources(false)} onRefresh={handleRefresh} />
      )}

      {/* Creators view */}
      {showCreators && (
        <CreatorsView onClose={() => setShowCreators(false)} />
      )}

      {/* Rated items view */}
      {showRated && (
        <RatedView onClose={() => setShowRated(false)} onOpenItem={handleOpenItem} />
      )}
    </div>
  );
}

export default App;
