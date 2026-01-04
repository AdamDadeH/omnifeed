import { useState, useEffect } from 'react';
import type { FeedItem } from '../api/types';
import { formatDistanceToNow } from '../utils/time';

interface RatedItem {
  item: FeedItem;
  rating: number;
  rated_at: string;
  selections: Record<string, string[]>;
}

interface RatedItemsResponse {
  items: RatedItem[];
  total_count: number;
}

interface Props {
  onClose: () => void;
  onOpenItem: (item: FeedItem) => void;
  isFullPage?: boolean;
}

export function RatedView({ onClose, onOpenItem, isFullPage }: Props) {
  const [items, setItems] = useState<RatedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [totalCount, setTotalCount] = useState(0);

  useEffect(() => {
    async function loadRated() {
      try {
        const response = await fetch('/api/feed/rated?limit=100');
        const data: RatedItemsResponse = await response.json();
        setItems(data.items);
        setTotalCount(data.total_count);
      } catch (err) {
        console.error('Failed to load rated items:', err);
      } finally {
        setLoading(false);
      }
    }
    loadRated();
  }, []);

  const formatRating = (rating: number) => {
    return '★'.repeat(Math.round(rating)) + '☆'.repeat(5 - Math.round(rating));
  };

  const formatSelections = (selections: Record<string, string[]>) => {
    const tags: string[] = [];
    for (const [, values] of Object.entries(selections)) {
      tags.push(...values);
    }
    return tags;
  };

  const content = (
    <>
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : items.length === 0 ? (
        <div className="text-center text-neutral-500 py-12">
          <p>No rated items yet.</p>
          <p className="text-sm mt-2">Rate items in the reader to see them here.</p>
        </div>
      ) : (
        <div className={isFullPage ? "space-y-1" : "space-y-3 max-w-4xl mx-auto"}>
          {items.map(({ item, rating, rated_at, selections }) => {
            const tags = formatSelections(selections);
            return (
              <div
                key={`${item.id}-${rated_at}`}
                className={`${isFullPage ? 'border-b border-neutral-800 px-4 py-3' : 'bg-neutral-900 rounded-lg p-4'} hover:bg-neutral-800/50 transition-colors cursor-pointer`}
                onClick={() => onOpenItem(item)}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium truncate">{item.title}</h3>
                    <div className="flex items-center gap-2 mt-1 text-sm text-neutral-400">
                      <span>{item.creator_name}</span>
                      <span>·</span>
                      <span>{item.source_name}</span>
                    </div>
                  </div>

                  <div className="flex-shrink-0 text-right">
                    <div className="text-yellow-500 text-lg" title={`${rating.toFixed(1)}/5`}>
                      {formatRating(rating)}
                    </div>
                    <div className="text-xs text-neutral-500 mt-1">
                      {formatDistanceToNow(rated_at)}
                    </div>
                  </div>
                </div>

                {tags.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-3">
                    {tags.map((tag) => (
                      <span
                        key={tag}
                        className="px-2 py-0.5 text-xs bg-neutral-800 text-neutral-300 rounded"
                      >
                        {tag.replace(/_/g, ' ')}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </>
  );

  if (isFullPage) {
    return (
      <div className="flex-1 flex flex-col overflow-hidden">
        <header className="px-4 pt-3 pb-2 border-b border-neutral-800">
          <h2 className="text-lg font-medium">Rated Items</h2>
          <p className="text-sm text-neutral-500 mt-1">
            {totalCount} items with explicit ratings
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
          <h1 className="text-xl font-semibold">Rated Items</h1>
          <p className="text-sm text-neutral-400 mt-1">
            {totalCount} items with explicit ratings
          </p>
        </div>
        <button
          onClick={onClose}
          className="px-4 py-2 text-sm bg-neutral-800 hover:bg-neutral-700 rounded transition-colors"
        >
          Close
        </button>
      </header>
      <div className="flex-1 overflow-y-auto p-6">
        {content}
      </div>
    </div>
  );
}
