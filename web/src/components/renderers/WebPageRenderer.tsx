import { useState, useCallback, useEffect } from 'react';
import type { RendererProps } from './types';
import type { FeedItem } from '../../api/types';

export function canHandleWebPage(item: FeedItem): boolean {
  // Handle sitemap items or items that need direct page loading
  if (item.metadata.needs_content_fetch) {
    return true;
  }
  // Handle generic web URLs without content
  if (!item.metadata.content_html && !item.metadata.content_text) {
    const url = item.url.toLowerCase();
    return url.startsWith('http://') || url.startsWith('https://');
  }
  return false;
}

export function WebPageRenderer({ item, onScrollProgress }: RendererProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const handleLoad = useCallback(() => {
    setLoading(false);
    // Mark as complete when page loads
    onScrollProgress?.(100);
  }, [onScrollProgress]);

  const handleError = useCallback(() => {
    setLoading(false);
    setError('Page could not be loaded in frame. Some sites block embedding.');
  }, []);

  // Some sites block iframes - detect and show fallback
  useEffect(() => {
    // Give iframe a chance to load, then check
    const timeout = setTimeout(() => {
      if (loading) {
        // Still loading after 10s - might be blocked
        setLoading(false);
      }
    }, 10000);
    return () => clearTimeout(timeout);
  }, [loading]);

  return (
    <div className="h-full flex flex-col">
      {/* Loading state */}
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-neutral-950 z-10">
          <div className="text-center">
            <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            <p className="text-neutral-400 text-sm">Loading page...</p>
          </div>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center max-w-md px-6">
            <div className="w-12 h-12 rounded-full bg-neutral-800 flex items-center justify-center mx-auto mb-4">
              <svg className="w-6 h-6 text-neutral-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <p className="text-neutral-400 mb-4">{error}</p>
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-white transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
              Open in new tab
            </a>
          </div>
        </div>
      )}

      {/* Iframe */}
      {!error && (
        <iframe
          src={item.url}
          title={item.title}
          className="flex-1 w-full border-0"
          onLoad={handleLoad}
          onError={handleError}
          sandbox="allow-same-origin allow-scripts allow-popups allow-forms"
          referrerPolicy="no-referrer"
        />
      )}
    </div>
  );
}
