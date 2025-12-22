import { useEffect, useState, useCallback } from 'react';
import { getFeed, markSeen, hideItem } from '../api/client';
import type { FeedResponse, FeedItem as FeedItemType } from '../api/types';
import { FeedItem } from './FeedItem';

interface Props {
  sourceFilter?: string;
  showSeen: boolean;
  refreshKey: number;
  onOpenItem: (item: FeedItemType) => void;
}

export function FeedList({ sourceFilter, showSeen, refreshKey, onOpenItem }: Props) {
  const [feed, setFeed] = useState<FeedResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadFeed = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getFeed({
        showSeen,
        sourceId: sourceFilter,
        limit: 50,
      });
      setFeed(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load feed');
    } finally {
      setLoading(false);
    }
  }, [showSeen, sourceFilter]);

  useEffect(() => {
    loadFeed();
  }, [loadFeed, refreshKey]);

  const handleMarkSeen = async (id: string) => {
    try {
      await markSeen(id);
      setFeed((prev) =>
        prev
          ? {
              ...prev,
              items: prev.items.map((item) =>
                item.id === id ? { ...item, seen: true } : item
              ),
              unseen_count: prev.unseen_count - 1,
            }
          : null
      );
    } catch (err) {
      console.error('Failed to mark seen:', err);
    }
  };

  const handleHide = async (id: string) => {
    try {
      await hideItem(id);
      setFeed((prev) =>
        prev
          ? {
              ...prev,
              items: prev.items.filter((item) => item.id !== id),
              total_count: prev.total_count - 1,
            }
          : null
      );
    } catch (err) {
      console.error('Failed to hide:', err);
    }
  };

  if (loading && !feed) {
    return (
      <div className="flex items-center justify-center h-64 text-neutral-500">
        Loading...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-neutral-500">
        <p>{error}</p>
        <button
          onClick={loadFeed}
          className="mt-4 px-4 py-2 bg-neutral-800 hover:bg-neutral-700 rounded transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!feed || feed.items.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-neutral-500">
        {showSeen ? 'No items in feed' : 'No unread items'}
      </div>
    );
  }

  return (
    <div>
      {/* Stats bar */}
      <div className="px-4 py-2 border-b border-neutral-800 text-sm text-neutral-500">
        {feed.unseen_count} unread · {feed.total_count} total
      </div>

      {/* Items */}
      <div>
        {feed.items.map((item) => (
          <FeedItem
            key={item.id}
            item={item}
            onOpen={() => onOpenItem(item)}
            onMarkSeen={handleMarkSeen}
            onHide={handleHide}
          />
        ))}
      </div>
    </div>
  );
}
