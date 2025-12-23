import { useEffect, useRef, useCallback } from 'react';
import type { RendererProps } from './types';
import type { FeedItem } from '../../api/types';

export function canHandleQobuz(item: FeedItem): boolean {
  return item.url.includes('qobuz.com') || item.metadata.album_id !== undefined;
}

export function QobuzRenderer({ item, onScrollProgress }: RendererProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  const albumId = item.metadata.album_id as string | undefined;
  const author = item.metadata.author as string | undefined;
  const tracksCount = item.metadata.tracks_count as number | undefined;
  const durationSeconds = item.metadata.duration_seconds as number | undefined;
  const genre = item.metadata.genre as string | undefined;
  const label = item.metadata.label as string | undefined;
  const hiresAvailable = item.metadata.hires_available as boolean | undefined;
  const albumType = item.metadata.album_type as string | undefined;
  const thumbnail = item.metadata.thumbnail as string | undefined;
  const description = item.metadata.content_text as string | undefined;

  const handleScroll = useCallback(() => {
    if (!containerRef.current || !onScrollProgress) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const maxScroll = scrollHeight - clientHeight;
    const pct = maxScroll > 0 ? (scrollTop / maxScroll) * 100 : 100;
    onScrollProgress(pct);
  }, [onScrollProgress]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    container.addEventListener('scroll', handleScroll);
    return () => container.removeEventListener('scroll', handleScroll);
  }, [handleScroll]);

  const formatDuration = (seconds: number) => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m} min`;
  };

  const effectiveAlbumId = albumId || extractAlbumId(item.url);

  // Qobuz app deep link (opens in Qobuz app if installed, otherwise web)
  const qobuzAppLink = `qobuz://album/${effectiveAlbumId}`;
  const qobuzWebLink = item.url;

  return (
    <div ref={containerRef} className="h-full overflow-y-auto">
      <div className="max-w-2xl mx-auto px-6 py-8">
        {/* Album card */}
        <div className="bg-neutral-900 rounded-xl overflow-hidden shadow-2xl">
          {/* Large album art */}
          {thumbnail && (
            <div className="aspect-square w-full max-w-md mx-auto">
              <img
                src={thumbnail.replace('/small/', '/large/').replace('/medium/', '/large/')}
                alt={item.title}
                className="w-full h-full object-cover"
                onError={(e) => {
                  // Fallback to original thumbnail if large version fails
                  (e.target as HTMLImageElement).src = thumbnail;
                }}
              />
            </div>
          )}

          {/* Album info */}
          <div className="p-6">
            {/* Type badge */}
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs uppercase tracking-wide text-neutral-500">
                {albumType || 'Album'}
              </span>
              {hiresAvailable && (
                <span className="px-2 py-0.5 bg-amber-600/20 text-amber-400 text-xs rounded-full font-medium">
                  Hi-Res
                </span>
              )}
            </div>

            {/* Title & Artist */}
            <h1 className="text-2xl font-bold text-neutral-100 mb-1">{item.title}</h1>
            {author && <p className="text-lg text-neutral-400 mb-4">{author}</p>}

            {/* Metadata row */}
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-neutral-500 mb-6">
              {tracksCount && (
                <span className="flex items-center gap-1">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
                  </svg>
                  {tracksCount} tracks
                </span>
              )}
              {durationSeconds && (
                <span className="flex items-center gap-1">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  {formatDuration(durationSeconds)}
                </span>
              )}
              {genre && <span>{genre}</span>}
              {label && <span className="text-neutral-600">on {label}</span>}
            </div>

            {/* Play button */}
            <a
              href={qobuzWebLink}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-3 w-full py-4 bg-blue-600 hover:bg-blue-500 rounded-lg text-white font-medium transition-colors"
              onClick={() => {
                // Try app link first, fall back to web
                const appWindow = window.open(qobuzAppLink, '_blank');
                if (appWindow) {
                  setTimeout(() => {
                    if (!appWindow.closed) {
                      appWindow.location.href = qobuzWebLink;
                    }
                  }, 500);
                }
              }}
            >
              <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7z" />
              </svg>
              Play on Qobuz
            </a>

            {/* Secondary link */}
            <p className="text-center text-xs text-neutral-600 mt-3">
              Opens in Qobuz app or web player
            </p>
          </div>
        </div>

        {/* Description if available */}
        {description && (
          <div className="mt-8">
            <h3 className="text-sm font-medium text-neutral-400 mb-3">About this release</h3>
            <p className="text-neutral-300 whitespace-pre-wrap leading-relaxed">
              {description}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function extractAlbumId(url: string): string | null {
  const patterns = [
    /qobuz\.com\/[a-z-]+\/album\/[^/]+\/([a-z0-9]+)/i,
    /open\.qobuz\.com\/album\/([a-z0-9]+)/i,
  ];

  for (const pattern of patterns) {
    const match = url.match(pattern);
    if (match) return match[1];
  }
  return null;
}
