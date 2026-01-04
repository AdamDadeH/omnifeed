import { useState, useCallback, useEffect } from 'react';
import { Sidebar, FeedList, AddSourceModal, ReaderPane, StatsView, SourcesView, CreatorsView, RatedView, ExploreView, QueueView, StrategiesView } from './components';
import type { ViewType } from './components/Sidebar';
import type { ReadingFeedback } from './components';
import type { FeedItem } from './api/types';
import { markSeen, recordFeedback, pollAllSources, getObjectives } from './api/client';
import type { Objective } from './api/client';

function App() {
  // Navigation
  const [currentView, setCurrentView] = useState<ViewType>('explore');

  // Subscribed view filters
  const [selectedSource, setSelectedSource] = useState<string | undefined>();
  const [showSeen, setShowSeen] = useState(false);
  const [selectedObjective, setSelectedObjective] = useState<string | undefined>();

  // Modals (work on top of any view)
  const [showAddModal, setShowAddModal] = useState(false);
  const [readingItem, setReadingItem] = useState<FeedItem | null>(null);

  // Other state
  const [refreshKey, setRefreshKey] = useState(0);
  const [polling, setPolling] = useState(false);
  const [objectives, setObjectives] = useState<Objective[]>([]);

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
      await pollAllSources();
      handleRefresh();
    } catch (err) {
      console.error('Failed to poll:', err);
    } finally {
      setPolling(false);
    }
  }, [handleRefresh]);

  const handleSourceAdded = useCallback(() => {
    handleRefresh();
  }, [handleRefresh]);

  const handleOpenItem = useCallback(async (item: FeedItem) => {
    setReadingItem(item);
    await recordFeedback(item.id, 'click', {});
  }, []);

  const handleCloseReader = useCallback(() => {
    setReadingItem(null);
    handleRefresh();
  }, [handleRefresh]);

  const handleReadingFeedback = useCallback(async (feedback: ReadingFeedback) => {
    await markSeen(feedback.item_id);
    await recordFeedback(feedback.item_id, 'reading_complete', {
      time_spent_ms: feedback.time_spent_ms,
      max_scroll_pct: feedback.max_scroll_pct,
      completed: feedback.completed,
      scroll_events: feedback.scroll_events,
    });
  }, []);

  // Render the current view
  const renderView = () => {
    switch (currentView) {
      case 'explore':
        return (
          <ExploreView
            onClose={() => setCurrentView('subscribed')}
            onRefresh={handleRefresh}
            onOpenItem={handleOpenItem}
            isFullPage
          />
        );

      case 'subscribed':
        return (
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Header */}
            <header className="px-4 pt-3 pb-2 border-b border-neutral-800">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-lg font-medium">
                  {selectedSource ? 'Source Feed' : 'All Items'}
                </h2>
                <button
                  onClick={handlePoll}
                  disabled={polling}
                  className="px-3 py-1.5 text-sm bg-neutral-800 hover:bg-neutral-700 disabled:opacity-50 rounded transition-colors"
                >
                  {polling ? 'Refreshing...' : 'Refresh All'}
                </button>
              </div>

              <div className="flex items-center gap-4">
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

            <div className="flex-1 overflow-y-auto">
              <FeedList
                sourceFilter={selectedSource}
                showSeen={showSeen}
                objective={selectedObjective}
                refreshKey={refreshKey}
                onOpenItem={handleOpenItem}
              />
            </div>
          </div>
        );

      case 'queue':
        return (
          <QueueView
            onClose={() => setCurrentView('subscribed')}
            onOpenItem={handleOpenItem}
            isFullPage
          />
        );

      case 'rated':
        return (
          <RatedView
            onClose={() => setCurrentView('subscribed')}
            onOpenItem={handleOpenItem}
            isFullPage
          />
        );

      case 'sources':
        return (
          <SourcesView
            onClose={() => setCurrentView('subscribed')}
            onRefresh={handleRefresh}
            isFullPage
          />
        );

      case 'creators':
        return (
          <CreatorsView
            onClose={() => setCurrentView('subscribed')}
            isFullPage
          />
        );

      case 'models':
        return (
          <StatsView
            onClose={() => setCurrentView('subscribed')}
            sourceId={selectedSource}
            isFullPage
          />
        );

      case 'strategies':
        return (
          <StrategiesView
            onClose={() => setCurrentView('subscribed')}
            isFullPage
          />
        );

      default:
        return null;
    }
  };

  return (
    <div className="flex h-screen bg-neutral-950">
      {/* Sidebar navigation */}
      <Sidebar
        currentView={currentView}
        onViewChange={setCurrentView}
        selectedSource={selectedSource}
        onSelectSource={setSelectedSource}
      />

      {/* Main content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {renderView()}
      </main>

      {/* Modal overlays (work on any view) */}
      {showAddModal && (
        <AddSourceModal
          onClose={() => setShowAddModal(false)}
          onAdded={handleSourceAdded}
        />
      )}

      {readingItem && (
        <ReaderPane
          item={readingItem}
          onClose={handleCloseReader}
          onFeedback={handleReadingFeedback}
        />
      )}
    </div>
  );
}

export default App;
