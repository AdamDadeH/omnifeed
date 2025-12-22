import { formatDistanceToNow } from '../utils/time';
import type { FeedItem as FeedItemType } from '../api/types';

interface Props {
  item: FeedItemType;
  onOpen: () => void;
  onMarkSeen: (id: string) => void;
  onHide: (id: string) => void;
}

export function FeedItem({ item, onOpen, onMarkSeen, onHide }: Props) {
  const handleClick = () => {
    onOpen();
  };

  return (
    <div
      className={`group border-b border-neutral-800 hover:bg-neutral-900 transition-colors ${
        item.seen ? 'opacity-60' : ''
      }`}
    >
      <div className="px-4 py-3">
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            {/* Title */}
            <button
              onClick={handleClick}
              className="text-left w-full font-medium text-neutral-100 hover:text-blue-400 transition-colors line-clamp-2"
            >
              {item.title}
            </button>

            {/* Meta line */}
            <div className="flex items-center gap-2 mt-1 text-sm text-neutral-500">
              <span className="truncate max-w-[200px]">{item.source_name}</span>
              <span>·</span>
              <span>{formatDistanceToNow(item.published_at)}</span>
              {item.content_type !== 'article' && (
                <>
                  <span>·</span>
                  <span className="capitalize">{item.content_type}</span>
                </>
              )}
            </div>

            {/* Description preview */}
            {typeof item.metadata.content_text === 'string' && (
              <p className="mt-2 text-sm text-neutral-400 line-clamp-2">
                {item.metadata.content_text.slice(0, 200)}
              </p>
            )}
          </div>

          {/* Thumbnail */}
          {typeof item.metadata.thumbnail === 'string' && (
            <img
              src={item.metadata.thumbnail}
              alt=""
              className="w-20 h-14 object-cover rounded bg-neutral-800 flex-shrink-0"
            />
          )}
        </div>

        {/* Actions - show on hover */}
        <div className="flex gap-2 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
          {!item.seen && (
            <button
              onClick={() => onMarkSeen(item.id)}
              className="text-xs text-neutral-500 hover:text-neutral-300 transition-colors"
            >
              Mark read
            </button>
          )}
          <button
            onClick={() => onHide(item.id)}
            className="text-xs text-neutral-500 hover:text-red-400 transition-colors"
          >
            Hide
          </button>
        </div>
      </div>
    </div>
  );
}
