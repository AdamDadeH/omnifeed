import { useEffect, useRef, useCallback, useState } from 'react';
import type { RendererProps } from './types';
import type { FeedItem } from '../../api/types';

function extractTikTokId(url: string): string | null {
  const patterns = [
    /tiktok\.com\/@[^/]+\/video\/(\d+)/,
    /tiktok\.com\/t\/([A-Za-z0-9]+)/,
    /vm\.tiktok\.com\/([A-Za-z0-9]+)/,
  ];

  for (const pattern of patterns) {
    const match = url.match(pattern);
    if (match) return match[1];
  }
  return null;
}

export function canHandleTikTok(item: FeedItem): boolean {
  const url = item.url.toLowerCase();
  return url.includes('tiktok.com') || url.includes('vm.tiktok.com');
}

export function TikTokRenderer({ item, onScrollProgress }: RendererProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [embedLoaded, setEmbedLoaded] = useState(false);
  const [markedComplete, setMarkedComplete] = useState(false);

  const videoId = item.metadata.video_id as string || extractTikTokId(item.url);
  const author = item.metadata.author as string | undefined;
  const thumbnail = item.metadata.thumbnail as string | undefined;
  const description = item.metadata.content_text as string | undefined;

  // Load TikTok embed script
  useEffect(() => {
    const existingScript = document.querySelector('script[src*="tiktok.com/embed"]');
    if (!existingScript) {
      const script = document.createElement('script');
      script.src = 'https://www.tiktok.com/embed.js';
      script.async = true;
      document.body.appendChild(script);
    } else {
      // Re-process embeds if script already loaded
      if ((window as any).tiktokEmbed) {
        (window as any).tiktokEmbed.lib.render();
      }
    }
  }, [item.url]);

  // Re-render embed when component mounts
  useEffect(() => {
    const timer = setTimeout(() => {
      if ((window as any).tiktokEmbed) {
        (window as any).tiktokEmbed.lib.render();
        setEmbedLoaded(true);
      }
    }, 500);
    return () => clearTimeout(timer);
  }, []);

  const handleScroll = useCallback(() => {
    if (!containerRef.current || !onScrollProgress) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const maxScroll = scrollHeight - clientHeight;
    const pct = maxScroll > 0 ? (scrollTop / maxScroll) * 100 : 100;
    onScrollProgress(markedComplete ? 100 : pct);
  }, [onScrollProgress, markedComplete]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    container.addEventListener('scroll', handleScroll);
    return () => container.removeEventListener('scroll', handleScroll);
  }, [handleScroll]);

  const handleMarkComplete = useCallback(() => {
    setMarkedComplete(true);
    onScrollProgress?.(100);
  }, [onScrollProgress]);

  return (
    <div ref={containerRef} className="h-full overflow-y-auto">
      <div className="max-w-lg mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-6">
          {author && (
            <p className="text-lg text-neutral-300 mb-2">@{author.replace('@', '')}</p>
          )}
          {description && (
            <p className="text-neutral-400 text-sm line-clamp-3">{description}</p>
          )}
        </div>

        {/* TikTok embed */}
        <div className="flex justify-center mb-6">
          <blockquote
            className="tiktok-embed"
            cite={item.url}
            data-video-id={videoId}
            style={{ maxWidth: '605px', minWidth: '325px' }}
          >
            <section>
              {/* Fallback content while loading */}
              {!embedLoaded && thumbnail && (
                <div className="relative aspect-[9/16] bg-neutral-900 rounded-lg overflow-hidden">
                  <img
                    src={thumbnail}
                    alt={item.title}
                    className="w-full h-full object-cover opacity-50"
                  />
                  <div className="absolute inset-0 flex items-center justify-center">
                    <div className="w-12 h-12 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  </div>
                </div>
              )}
            </section>
          </blockquote>
        </div>

        {/* Mark complete button */}
        <div className="flex justify-center mb-6">
          {!markedComplete ? (
            <button
              onClick={handleMarkComplete}
              className="px-4 py-2 bg-neutral-700 hover:bg-neutral-600 rounded-lg transition-colors"
            >
              Mark as Watched
            </button>
          ) : (
            <span className="text-green-500 flex items-center gap-2">
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
              </svg>
              Watched
            </span>
          )}
        </div>

        {/* Open in TikTok */}
        <div className="flex justify-center">
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2 text-sm text-neutral-400 hover:text-neutral-200 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
            Open in TikTok
          </a>
        </div>
      </div>
    </div>
  );
}
