import { useEffect, useRef, useState, useCallback } from 'react';
import type { FeedItem } from '../api/types';
import { formatDistanceToNow } from '../utils/time';

interface Props {
  item: FeedItem;
  onClose: () => void;
  onFeedback: (feedback: ReadingFeedback) => void;
}

export interface ReadingFeedback {
  item_id: string;
  time_spent_ms: number;
  max_scroll_pct: number;
  completed: boolean;
  scroll_events: number;
}

export function ReaderPane({ item, onClose, onFeedback }: Props) {
  const contentRef = useRef<HTMLDivElement>(null);
  const startTimeRef = useRef<number>(Date.now());
  const maxScrollRef = useRef<number>(0);
  const scrollEventsRef = useRef<number>(0);
  const [scrollPct, setScrollPct] = useState(0);

  // Track scroll position
  const handleScroll = useCallback(() => {
    if (!contentRef.current) return;

    const { scrollTop, scrollHeight, clientHeight } = contentRef.current;
    const maxScroll = scrollHeight - clientHeight;
    const currentPct = maxScroll > 0 ? (scrollTop / maxScroll) * 100 : 0;

    setScrollPct(currentPct);
    scrollEventsRef.current += 1;

    if (currentPct > maxScrollRef.current) {
      maxScrollRef.current = currentPct;
    }
  }, []);

  // Send feedback on close
  const handleClose = useCallback(() => {
    const feedback: ReadingFeedback = {
      item_id: item.id,
      time_spent_ms: Date.now() - startTimeRef.current,
      max_scroll_pct: maxScrollRef.current,
      completed: maxScrollRef.current >= 90,
      scroll_events: scrollEventsRef.current,
    };
    onFeedback(feedback);
    onClose();
  }, [item.id, onClose, onFeedback]);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        handleClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleClose]);

  // Get content to display
  const contentHtml = item.metadata.content_html as string | undefined;
  const contentText = item.metadata.content_text as string | undefined;

  // Check if it's a YouTube video
  const youtubeId = extractYouTubeId(item.url);

  // Format time spent
  const formatTimeSpent = (ms: number) => {
    const seconds = Math.floor(ms / 1000);
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds}s`;
  };

  const [timeSpent, setTimeSpent] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setTimeSpent(Date.now() - startTimeRef.current);
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="fixed inset-0 bg-neutral-950 z-50 flex flex-col">
      {/* Header */}
      <header className="flex-shrink-0 px-4 py-3 border-b border-neutral-800 flex items-center justify-between bg-neutral-900">
        <div className="flex-1 min-w-0 mr-4">
          <h1 className="text-lg font-medium truncate">{item.title}</h1>
          <div className="text-sm text-neutral-500">
            {item.source_name} · {item.creator_name} · {formatDistanceToNow(item.published_at)}
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* Reading stats */}
          <div className="text-sm text-neutral-500 flex items-center gap-3">
            <span>⏱️ {formatTimeSpent(timeSpent)}</span>
            <span>📖 {Math.round(scrollPct)}%</span>
          </div>

          {/* Open external */}
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 text-sm text-neutral-400 hover:text-neutral-200 transition-colors"
          >
            Open original ↗
          </a>

          {/* Close button */}
          <button
            onClick={handleClose}
            className="px-3 py-1.5 text-sm bg-neutral-800 hover:bg-neutral-700 rounded transition-colors"
          >
            Close (Esc)
          </button>
        </div>
      </header>

      {/* Content */}
      <div
        ref={contentRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto"
      >
        <div className="max-w-3xl mx-auto px-6 py-8">
          {youtubeId ? (
            // YouTube embed
            <div className="aspect-video mb-8">
              <iframe
                src={`https://www.youtube.com/embed/${youtubeId}`}
                title={item.title}
                className="w-full h-full rounded-lg"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            </div>
          ) : null}

          {contentHtml ? (
            // Render HTML content
            <article
              className="prose prose-invert prose-neutral max-w-none
                prose-headings:text-neutral-100
                prose-p:text-neutral-300
                prose-a:text-blue-400 prose-a:no-underline hover:prose-a:underline
                prose-strong:text-neutral-200
                prose-code:text-neutral-300 prose-code:bg-neutral-800 prose-code:px-1 prose-code:rounded
                prose-pre:bg-neutral-900 prose-pre:border prose-pre:border-neutral-800
                prose-blockquote:border-neutral-700 prose-blockquote:text-neutral-400
                prose-img:rounded-lg"
              dangerouslySetInnerHTML={{ __html: sanitizeHtml(contentHtml) }}
            />
          ) : contentText ? (
            // Render plain text
            <article className="text-neutral-300 whitespace-pre-wrap leading-relaxed">
              {contentText}
            </article>
          ) : (
            // No content available
            <div className="text-center py-12 text-neutral-500">
              <p className="mb-4">Full content not available in feed.</p>
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-white transition-colors"
              >
                Read on original site ↗
              </a>
            </div>
          )}
        </div>
      </div>

      {/* Progress bar */}
      <div className="flex-shrink-0 h-1 bg-neutral-800">
        <div
          className="h-full bg-blue-500 transition-all duration-150"
          style={{ width: `${scrollPct}%` }}
        />
      </div>
    </div>
  );
}

function extractYouTubeId(url: string): string | null {
  const patterns = [
    /youtube\.com\/watch\?v=([^&]+)/,
    /youtube\.com\/embed\/([^?]+)/,
    /youtu\.be\/([^?]+)/,
  ];

  for (const pattern of patterns) {
    const match = url.match(pattern);
    if (match) return match[1];
  }
  return null;
}

function sanitizeHtml(html: string): string {
  // Basic sanitization - remove script tags and event handlers
  // In production, use a proper sanitizer like DOMPurify
  return html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/\s*on\w+="[^"]*"/gi, '')
    .replace(/\s*on\w+='[^']*'/gi, '');
}
