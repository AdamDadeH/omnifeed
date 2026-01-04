import { useState, useCallback, useRef, useEffect } from 'react';
import { explore, addSource, recordFeedback, hideItem } from '../api/client';
import type { Retriever, ExploreResult } from '../api/client';
import type { FeedItem as FeedItemType } from '../api/types';
import { FeedItem } from './FeedItem';

interface ProgressEvent {
  event: string;
  strategy_id?: string;
  display_name?: string;
  strategies?: string[];
  topic?: string;
  retrievers?: number;
  items?: number;
  total_retrievers?: number;
  total_items?: number;
  message?: string;
}

interface Props {
  onClose: () => void;
  onRefresh: () => void;
  onOpenItem: (item: FeedItemType) => void;
  isFullPage?: boolean;
}

export function ExploreView({ onClose, onRefresh, onOpenItem, isFullPage }: Props) {
  const [loading, setLoading] = useState(false);
  const [topic, setTopic] = useState('');
  const [result, setResult] = useState<ExploreResult | null>(null);
  const [addingUri, setAddingUri] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [dismissedItems, setDismissedItems] = useState<Set<string>>(new Set());
  const [savedItems, setSavedItems] = useState<Set<string>>(new Set());

  // Progress tracking state
  const [progressEvents, setProgressEvents] = useState<ProgressEvent[]>([]);
  const [currentStrategy, setCurrentStrategy] = useState<string | null>(null);
  const [useStreaming, setUseStreaming] = useState(false); // Disabled for now - was causing double requests
  const eventSourceRef = useRef<EventSource | null>(null);

  // Cleanup EventSource on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  const handleExploreStreaming = useCallback(async () => {
    setLoading(true);
    setError(null);
    setProgressEvents([]);
    setCurrentStrategy(null);
    setDismissedItems(new Set());
    setSavedItems(new Set());

    // Close existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const params = new URLSearchParams();
    if (topic) params.set('topic', topic);
    params.set('limit', '9');

    const es = new EventSource(`/api/explore/stream?${params.toString()}`);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const data: ProgressEvent = JSON.parse(event.data);
        setProgressEvents((prev) => [...prev, data]);

        if (data.event === 'strategy_start') {
          setCurrentStrategy(data.display_name || data.strategy_id || null);
        } else if (data.event === 'strategy_complete') {
          // Strategy finished
        } else if (data.event === 'complete') {
          es.close();
          setLoading(false);
          setCurrentStrategy(null);
          // Fetch final results
          explore(topic || undefined, 9).then(setResult).catch(console.error);
        } else if (data.event === 'error') {
          es.close();
          setLoading(false);
          setError(data.message || 'Unknown error');
        }
      } catch (err) {
        console.error('Failed to parse SSE event:', err);
      }
    };

    es.onerror = () => {
      es.close();
      setLoading(false);
      setError('Connection lost');
    };
  }, [topic]);

  const handleExploreFallback = useCallback(async () => {
    setLoading(true);
    setError(null);
    setDismissedItems(new Set());
    setSavedItems(new Set());
    try {
      const data = await explore(topic || undefined, 9);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to explore');
    } finally {
      setLoading(false);
    }
  }, [topic]);

  const handleExplore = useCallback(() => {
    if (useStreaming) {
      handleExploreStreaming();
    } else {
      handleExploreFallback();
    }
  }, [useStreaming, handleExploreStreaming, handleExploreFallback]);

  const handleSkip = useCallback(async (item: FeedItemType) => {
    // Immediately remove from list (optimistic update)
    setDismissedItems(prev => new Set(prev).add(item.id));

    // Then persist to backend
    try {
      await recordFeedback(item.id, 'explore_skip', {
        context: 'explore_view',
        topic: result?.topic,
      });
    } catch (err) {
      console.error('Failed to record skip:', err);
    }
  }, [result?.topic]);

  const handleSave = useCallback(async (item: FeedItemType) => {
    setActionInProgress(item.id);
    try {
      await recordFeedback(item.id, 'explore_save', {
        context: 'explore_view',
        topic: result?.topic,
      });
      setSavedItems(prev => new Set(prev).add(item.id));
    } catch (err) {
      console.error('Failed to record save:', err);
    } finally {
      setActionInProgress(null);
    }
  }, [result?.topic]);

  const handleHide = useCallback(async (item: FeedItemType) => {
    // Immediately remove from list (optimistic update)
    setDismissedItems(prev => new Set(prev).add(item.id));

    // Then persist to backend
    try {
      await hideItem(item.id);
      await recordFeedback(item.id, 'explore_hide', {
        context: 'explore_view',
        topic: result?.topic,
        strong_negative: true,
      });
    } catch (err) {
      console.error('Failed to hide item:', err);
    }
  }, [result?.topic]);

  const handleOpenItem = useCallback((item: FeedItemType) => {
    // Record click for analytics
    recordFeedback(item.id, 'explore_click', {
      context: 'explore_view',
      topic: result?.topic,
    });
    onOpenItem(item);
  }, [result?.topic, onOpenItem]);

  const handleAddRetriever = useCallback(async (retriever: Retriever) => {
    setAddingUri(retriever.uri);
    try {
      // Extract the source URL from the URI (format: source:type:url)
      const parts = retriever.uri.split(':');
      const sourceUrl = parts.length >= 3 ? parts.slice(2).join(':') : retriever.uri;
      await addSource(sourceUrl);
      onRefresh();
    } catch (err) {
      // Already exists is fine
      if (!(err instanceof Error && err.message.includes('already exists'))) {
        console.error('Failed to add source:', err);
      }
    } finally {
      setAddingUri(null);
    }
  }, [onRefresh]);

  const getActionsForItem = useCallback((item: FeedItemType) => {
    const isSaved = savedItems.has(item.id);
    const isProcessing = actionInProgress === item.id;

    if (isSaved) {
      return []; // No actions needed, saved indicator shown via isSaved prop
    }

    return [
      {
        label: 'Skip',
        onClick: () => handleSkip(item),
        disabled: isProcessing,
      },
      {
        label: 'Save',
        onClick: () => handleSave(item),
        variant: 'primary' as const,
        disabled: isProcessing,
      },
      {
        label: 'Hide',
        onClick: () => handleHide(item),
        variant: 'danger' as const,
        disabled: isProcessing,
      },
    ];
  }, [savedItems, actionInProgress, handleSkip, handleSave, handleHide]);

  // Full page layout
  if (isFullPage) {
    return (
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="px-4 pt-3 pb-2 border-b border-neutral-800">
          <h2 className="text-lg font-medium mb-2">Explore</h2>
          <div className="flex gap-2">
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="Enter a topic (or leave blank for random)"
              className="flex-1 px-3 py-1.5 text-sm bg-neutral-800 border border-neutral-700 rounded text-neutral-200 placeholder-neutral-500"
              onKeyDown={(e) => e.key === 'Enter' && handleExplore()}
            />
            <button
              onClick={handleExplore}
              disabled={loading}
              className="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded transition-colors"
            >
              {loading ? 'Exploring...' : 'Explore'}
            </button>
          </div>
          {result?.topic && (
            <p className="mt-2 text-sm text-neutral-400">
              Exploring: <span className="text-neutral-200">{result.topic}</span>
            </p>
          )}
        </header>

        {/* Error */}
        {error && (
          <div className="px-4 py-2 bg-red-900/20 border-b border-red-800 text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* Progress Display */}
        {loading && progressEvents.length > 0 && (
          <div className="px-4 py-3 border-b border-neutral-800 bg-neutral-800/50">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
              <span className="text-sm text-neutral-300">
                {currentStrategy ? `Running: ${currentStrategy}` : 'Starting...'}
              </span>
            </div>
            <div className="space-y-1 max-h-32 overflow-y-auto text-xs font-mono text-neutral-500">
              {progressEvents.map((evt, i) => (
                <div key={i} className="flex gap-2">
                  <span className="text-neutral-600">[{evt.event}]</span>
                  <span>
                    {evt.event === 'start' && `Strategies: ${evt.strategies?.join(', ')}`}
                    {evt.event === 'strategy_start' && evt.display_name}
                    {evt.event === 'strategy_complete' && `${evt.strategy_id}: ${evt.retrievers || 0} sources, ${evt.items || 0} items`}
                    {evt.event === 'complete' && `Done: ${evt.total_retrievers} sources, ${evt.total_items} items`}
                    {evt.event === 'error' && <span className="text-red-400">{evt.message}</span>}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Results */}
        <div className="flex-1 overflow-y-auto">
          {!result && !loading && (
            <div className="text-center text-neutral-500 py-12">
              <p className="text-lg mb-2">Discover new sources</p>
              <p className="text-sm">Click "Explore" to discover content based on a topic or random exploration</p>
            </div>
          )}

          {result && (
            <div>
              {/* Content Items */}
              {result.items.length > 0 && (
                <div>
                  <div className="px-4 py-2 text-sm text-neutral-400 border-b border-neutral-800">
                    Discovered Content ({result.items.filter(i => !dismissedItems.has(i.id)).length} remaining)
                  </div>
                  {result.items
                    .filter(item => !dismissedItems.has(item.id))
                    .map((item) => (
                      <FeedItem
                        key={item.id}
                        item={item}
                        onOpen={() => handleOpenItem(item)}
                        actions={getActionsForItem(item)}
                        isSaved={savedItems.has(item.id)}
                      />
                    ))}

                  {/* All items dismissed */}
                  {result.items.filter(i => !dismissedItems.has(i.id)).length === 0 && (
                    <div className="text-center py-8 text-neutral-500">
                      <p>All items reviewed!</p>
                      <button
                        onClick={handleExplore}
                        className="mt-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-white text-sm"
                      >
                        Explore More
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Discovered Sources */}
              {result.retrievers.length > 0 && (
                <div className="p-4 border-t border-neutral-800">
                  <h3 className="text-sm font-medium text-neutral-400 mb-3">Discovered Sources</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {result.retrievers.map((retriever) => (
                      <div
                        key={retriever.id}
                        className="bg-neutral-800 rounded-lg p-3 border border-neutral-700"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <h4 className="text-sm font-medium truncate">{retriever.display_name}</h4>
                            <p className="text-xs text-neutral-500 truncate mt-0.5">
                              {retriever.handler_type}
                            </p>
                          </div>
                          <button
                            onClick={() => handleAddRetriever(retriever)}
                            disabled={addingUri === retriever.uri}
                            className="px-2 py-1 text-xs bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded"
                          >
                            {addingUri === retriever.uri ? '...' : '+ Add'}
                          </button>
                        </div>
                        {retriever.score !== null && (
                          <div className="mt-1.5 flex items-center gap-2 text-xs text-neutral-400">
                            <span>Score: {retriever.score.toFixed(2)}</span>
                            {retriever.confidence !== null && (
                              <span>({(retriever.confidence * 100).toFixed(0)}% conf)</span>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Empty state */}
              {result.retrievers.length === 0 && result.items.length === 0 && (
                <div className="text-center text-neutral-500 py-12">
                  <p>No results found</p>
                  <p className="text-sm mt-1">Try a different topic or explore randomly</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    );
  }

  // Modal layout (original)
  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
      <div className="bg-neutral-900 rounded-lg w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-4 border-b border-neutral-800 flex items-center justify-between">
          <h2 className="text-xl font-semibold">Explore</h2>
          <button
            onClick={onClose}
            className="text-neutral-400 hover:text-neutral-200 text-2xl"
          >
            &times;
          </button>
        </div>

        {/* Search bar */}
        <div className="p-4 border-b border-neutral-800">
          <div className="flex gap-2">
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="Enter a topic (or leave blank for random)"
              className="flex-1 px-3 py-2 bg-neutral-800 border border-neutral-700 rounded text-neutral-200 placeholder-neutral-500"
              onKeyDown={(e) => e.key === 'Enter' && handleExplore()}
            />
            <button
              onClick={handleExplore}
              disabled={loading}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded transition-colors"
            >
              {loading ? 'Exploring...' : 'Explore'}
            </button>
          </div>
          {result?.topic && (
            <p className="mt-2 text-sm text-neutral-400">
              Exploring: <span className="text-neutral-200">{result.topic}</span>
            </p>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="p-4 bg-red-900/20 border-b border-red-800 text-red-400">
            {error}
          </div>
        )}

        {/* Progress Display (Modal) */}
        {loading && progressEvents.length > 0 && (
          <div className="px-4 py-3 border-b border-neutral-800 bg-neutral-800/50">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
              <span className="text-sm text-neutral-300">
                {currentStrategy ? `Running: ${currentStrategy}` : 'Starting...'}
              </span>
            </div>
            <div className="space-y-1 max-h-32 overflow-y-auto text-xs font-mono text-neutral-500">
              {progressEvents.map((evt, i) => (
                <div key={i} className="flex gap-2">
                  <span className="text-neutral-600">[{evt.event}]</span>
                  <span>
                    {evt.event === 'start' && `Strategies: ${evt.strategies?.join(', ')}`}
                    {evt.event === 'strategy_start' && evt.display_name}
                    {evt.event === 'strategy_complete' && `${evt.strategy_id}: ${evt.retrievers || 0} sources, ${evt.items || 0} items`}
                    {evt.event === 'complete' && `Done: ${evt.total_retrievers} sources, ${evt.total_items} items`}
                    {evt.event === 'error' && <span className="text-red-400">{evt.message}</span>}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Results */}
        <div className="flex-1 overflow-y-auto">
          {!result && !loading && (
            <div className="text-center text-neutral-500 py-12">
              <p className="text-lg mb-2">Discover new sources</p>
              <p className="text-sm">Click "Explore" to discover content based on a topic or random exploration</p>
            </div>
          )}

          {result && (
            <div>
              {/* Content Items - using shared FeedItem component */}
              {result.items.length > 0 && (
                <div>
                  <div className="px-4 py-2 text-sm text-neutral-400 border-b border-neutral-800">
                    Discovered Content ({result.items.filter(i => !dismissedItems.has(i.id)).length} remaining)
                  </div>
                  {result.items
                    .filter(item => !dismissedItems.has(item.id))
                    .map((item) => (
                      <FeedItem
                        key={item.id}
                        item={item}
                        onOpen={() => handleOpenItem(item)}
                        actions={getActionsForItem(item)}
                        isSaved={savedItems.has(item.id)}
                      />
                    ))}

                  {/* All items dismissed */}
                  {result.items.filter(i => !dismissedItems.has(i.id)).length === 0 && (
                    <div className="text-center py-8 text-neutral-500">
                      <p>All items reviewed!</p>
                      <button
                        onClick={handleExplore}
                        className="mt-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-white text-sm"
                      >
                        Explore More
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Discovered Sources - shown below content */}
              {result.retrievers.length > 0 && (
                <div className="p-4 border-t border-neutral-800">
                  <h3 className="text-lg font-medium mb-3">Discovered Sources</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {result.retrievers.map((retriever) => (
                      <div
                        key={retriever.id}
                        className="bg-neutral-800 rounded-lg p-4 border border-neutral-700"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <h4 className="font-medium truncate">{retriever.display_name}</h4>
                            <p className="text-xs text-neutral-500 truncate mt-1">
                              {retriever.handler_type}
                            </p>
                          </div>
                          <button
                            onClick={() => handleAddRetriever(retriever)}
                            disabled={addingUri === retriever.uri}
                            className="px-2 py-1 text-xs bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded"
                          >
                            {addingUri === retriever.uri ? '...' : '+ Add'}
                          </button>
                        </div>
                        {retriever.score !== null && (
                          <div className="mt-2 flex items-center gap-2 text-xs text-neutral-400">
                            <span>Score: {retriever.score.toFixed(2)}</span>
                            {retriever.confidence !== null && (
                              <span>({(retriever.confidence * 100).toFixed(0)}% conf)</span>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Empty state */}
              {result.retrievers.length === 0 && result.items.length === 0 && (
                <div className="text-center text-neutral-500 py-12">
                  <p>No results found</p>
                  <p className="text-sm mt-1">Try a different topic or explore randomly</p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-neutral-800 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-neutral-700 hover:bg-neutral-600 rounded transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
