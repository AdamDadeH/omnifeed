import { useEffect, useRef, useCallback, useState } from 'react';
import type { RendererProps } from './types';
import type { FeedItem } from '../../api/types';

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

export function canHandleYouTube(item: FeedItem): boolean {
  // Check source type
  if (item.metadata.source_type === 'youtube_channel' ||
      item.metadata.source_type === 'youtube_playlist') {
    return true;
  }
  // Check URL
  return extractYouTubeId(item.url) !== null;
}

export function YouTubeRenderer({ item, onScrollProgress }: RendererProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [manuallyCompleted, setManuallyCompleted] = useState(false);

  const videoId = item.metadata.video_id as string || extractYouTubeId(item.url);
  const description = item.metadata.content_text as string | undefined;
  const duration = item.metadata.duration_seconds as number | undefined;
  const viewCount = item.metadata.view_count as number | undefined;

  const handleScroll = useCallback(() => {
    if (!containerRef.current || !onScrollProgress) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const maxScroll = scrollHeight - clientHeight;
    const pct = maxScroll > 0 ? (scrollTop / maxScroll) * 100 : 100;
    onScrollProgress(manuallyCompleted ? 100 : pct);
  }, [onScrollProgress, manuallyCompleted]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    container.addEventListener('scroll', handleScroll);
    return () => container.removeEventListener('scroll', handleScroll);
  }, [handleScroll]);

  const handleMarkComplete = useCallback(() => {
    setManuallyCompleted(true);
    onScrollProgress?.(100);
  }, [onScrollProgress]);

  const formatDuration = (seconds: number) => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  const formatViews = (count: number) => {
    if (count >= 1000000) return `${(count / 1000000).toFixed(1)}M views`;
    if (count >= 1000) return `${(count / 1000).toFixed(1)}K views`;
    return `${count} views`;
  };

  if (!videoId) {
    return (
      <div className="text-center py-12 text-neutral-500">
        <p>Could not extract YouTube video ID.</p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto px-6 py-8">
        {/* Video embed */}
        <div className="aspect-video mb-6 bg-black rounded-lg overflow-hidden">
          <iframe
            src={`https://www.youtube.com/embed/${videoId}?autoplay=0&rel=0`}
            title={item.title}
            className="w-full h-full"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        </div>

        {/* Video info */}
        <div className="mb-6">
          <div className="flex items-center gap-4 text-sm text-neutral-400 mb-4">
            {duration && <span>{formatDuration(duration)}</span>}
            {viewCount && <span>{formatViews(viewCount)}</span>}
            {!manuallyCompleted ? (
              <button
                onClick={handleMarkComplete}
                className="px-3 py-1 bg-neutral-700 hover:bg-neutral-600 rounded transition-colors"
              >
                Mark as Watched
              </button>
            ) : (
              <span className="text-green-500">Watched</span>
            )}
          </div>
        </div>

        {/* Description */}
        {description && (
          <div className="border-t border-neutral-800 pt-6">
            <h3 className="text-sm font-medium text-neutral-400 mb-3">Description</h3>
            <p className="text-neutral-300 whitespace-pre-wrap leading-relaxed">
              {description}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
