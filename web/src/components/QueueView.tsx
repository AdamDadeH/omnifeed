import { useState, useEffect, useCallback } from 'react';
import { FeedItem } from './FeedItem';
import type { FeedItem as FeedItemType } from '../api/types';

interface Props {
  onClose: () => void;
  onOpenItem: (item: FeedItemType) => void;
  isFullPage?: boolean;
}

interface QueueResponse {
  items: FeedItemType[];
  total_count: number;
}

export function QueueView({ onClose, onOpenItem, isFullPage }: Props) {
  const [items, setItems] = useState<FeedItemType[]>([]);
  const [loading, setLoading] = useState(true);
  const [totalCount, setTotalCount] = useState(0);

  const loadQueue = useCallback(async () => {
    try {
      const response = await fetch('/api/feed/queue?limit=100');
      if (response.ok) {
        const data: QueueResponse = await response.json();
        setItems(data.items);
        setTotalCount(data.total_count);
      }
    } catch (err) {
      console.error('Failed to load queue:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadQueue();
  }, [loadQueue]);

  const handleRemoveFromQueue = useCallback(async (itemId: string) => {
    try {
      await fetch(`/api/feed/queue/${itemId}`, { method: 'DELETE' });
      setItems(prev => prev.filter(item => item.id !== itemId));
      setTotalCount(prev => prev - 1);
    } catch (err) {
      console.error('Failed to remove from queue:', err);
    }
  }, []);

  const getActionsForItem = useCallback((item: FeedItemType) => {
    return [
      {
        label: 'Remove',
        onClick: () => handleRemoveFromQueue(item.id),
        variant: 'danger' as const,
      },
    ];
  }, [handleRemoveFromQueue]);

  const content = (
    <>
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : items.length === 0 ? (
        <div className="text-center text-neutral-500 py-12">
          <p>No saved items yet.</p>
          <p className="text-sm mt-2">Save items from Explore to add them to your queue.</p>
        </div>
      ) : (
        <div>
          {items.map((item) => (
            <FeedItem
              key={item.id}
              item={item}
              onOpen={() => onOpenItem(item)}
              actions={getActionsForItem(item)}
            />
          ))}
        </div>
      )}
    </>
  );

  if (isFullPage) {
    return (
      <div className="flex-1 flex flex-col overflow-hidden">
        <header className="px-4 pt-3 pb-2 border-b border-neutral-800">
          <h2 className="text-lg font-medium">Queue</h2>
          <p className="text-sm text-neutral-500 mt-1">
            {totalCount} saved items
          </p>
        </header>
        <div className="flex-1 overflow-y-auto">
          {content}
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-neutral-950 z-50 flex flex-col">
      <header className="flex-shrink-0 px-6 py-4 border-b border-neutral-800 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Queue</h1>
          <p className="text-sm text-neutral-400 mt-1">
            {totalCount} saved items
          </p>
        </div>
        <button
          onClick={onClose}
          className="px-4 py-2 text-sm bg-neutral-800 hover:bg-neutral-700 rounded transition-colors"
        >
          Close
        </button>
      </header>
      <div className="flex-1 overflow-y-auto">
        {content}
      </div>
    </div>
  );
}
