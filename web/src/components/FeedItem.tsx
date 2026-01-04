import { formatDistanceToNow } from '../utils/time';
import type { FeedItem as FeedItemType } from '../api/types';

function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }
  return `${minutes}:${secs.toString().padStart(2, '0')}`;
}

interface ActionButton {
  label: string;
  onClick: () => void;
  variant?: 'default' | 'primary' | 'danger' | 'success';
  disabled?: boolean;
}

interface Props {
  item: FeedItemType;
  onOpen: () => void;
  /** Custom actions to show. If not provided, uses default feed actions */
  actions?: ActionButton[];
  /** Default action callbacks (used when actions prop not provided) */
  onMarkSeen?: (id: string) => void;
  onHide?: (id: string) => void;
  /** Show saved state indicator */
  isSaved?: boolean;
}

export function FeedItem({ item, onOpen, actions, onMarkSeen, onHide, isSaved }: Props) {
  const handleClick = () => {
    onOpen();
  };

  return (
    <div
      className={`group border-b border-neutral-800 hover:bg-neutral-900 transition-colors ${
        item.seen ? 'opacity-60' : ''
      } ${isSaved ? 'border-l-2 border-l-green-600' : ''}`}
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

            {/* Creator line */}
            <div className="flex items-center gap-2 mt-1 text-sm">
              <span className="text-neutral-400">{item.creator_name}</span>
              {item.metadata.extracted_creators && item.metadata.extracted_creators.length > 0 && (
                <span className="text-neutral-500">
                  {item.metadata.extracted_creators.slice(0, 3).map((ec, idx) => (
                    <span key={ec.creator_id}>
                      {idx === 0 ? ' · ' : ', '}
                      <span className="text-neutral-500">
                        {ec.role === 'guest' ? 'w/' : ec.role === 'featuring' ? 'ft.' : `${ec.role}:`}
                      </span>{' '}
                      <span className="text-neutral-400">{ec.name}</span>
                    </span>
                  ))}
                  {item.metadata.extracted_creators.length > 3 && (
                    <span className="text-neutral-600"> +{item.metadata.extracted_creators.length - 3}</span>
                  )}
                </span>
              )}
            </div>

            {/* Meta line */}
            <div className="flex items-center gap-2 mt-0.5 text-sm text-neutral-500">
              <span className="truncate max-w-[200px]">{item.source_name}</span>
              <span>·</span>
              <a
                href={item.url}
                className="text-blue-400 hover:underline"
              >
                link
              </a>
              <span>·</span>
              <span>{formatDistanceToNow(item.published_at)}</span>
              {item.content_type !== 'article' && (
                <>
                  <span>·</span>
                  <span className="capitalize">{item.content_type}</span>
                </>
              )}
              {item.metadata.duration_seconds && item.metadata.duration_seconds > 0 && (
                <>
                  <span>·</span>
                  <span>{formatDuration(item.metadata.duration_seconds)}</span>
                </>
              )}
              {item.score !== null && (
                <>
                  <span>·</span>
                  <span
                    className={
                      item.score >= 2.0
                        ? 'text-green-500'
                        : item.score >= 1.0
                        ? 'text-yellow-500'
                        : 'text-neutral-500'
                    }
                    title="ML ranking score"
                  >
                    {item.score.toFixed(2)}
                  </span>
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
        <div className="flex items-center gap-2 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
          {isSaved && (
            <span className="text-xs text-green-400 flex items-center gap-1">
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
              </svg>
              Saved
            </span>
          )}
          {actions ? (
            // Custom actions
            actions.map((action, idx) => (
              <button
                key={idx}
                onClick={action.onClick}
                disabled={action.disabled}
                className={`text-xs transition-colors ${
                  action.variant === 'primary'
                    ? 'text-blue-400 hover:text-blue-300'
                    : action.variant === 'danger'
                    ? 'text-red-400 hover:text-red-300'
                    : action.variant === 'success'
                    ? 'text-green-400 hover:text-green-300'
                    : 'text-neutral-500 hover:text-neutral-300'
                } disabled:opacity-50`}
              >
                {action.label}
              </button>
            ))
          ) : (
            // Default feed actions
            <>
              {!item.seen && onMarkSeen && (
                <button
                  onClick={() => onMarkSeen(item.id)}
                  className="text-xs text-neutral-500 hover:text-neutral-300 transition-colors"
                >
                  Mark read
                </button>
              )}
              {onHide && (
                <button
                  onClick={() => onHide(item.id)}
                  className="text-xs text-neutral-500 hover:text-red-400 transition-colors"
                >
                  Hide
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
