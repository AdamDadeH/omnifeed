import { useState, useCallback, useEffect, useRef } from 'react';
import type { RendererProps } from './types';
import type { FeedItem } from '../../api/types';
import { fetchProxiedContent } from '../../api/client';

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
  const [html, setHtml] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Fetch content via proxy
  useEffect(() => {
    let cancelled = false;

    async function fetchContent() {
      try {
        const result = await fetchProxiedContent(item.url);

        if (cancelled) return;

        if (result.error) {
          setError(result.error);
          setLoading(false);
          return;
        }

        if (result.html) {
          // Rewrite relative URLs to absolute URLs
          const baseUrl = new URL(result.url);
          let processedHtml = result.html;

          // Rewrite src and href attributes to use absolute URLs
          processedHtml = processedHtml.replace(
            /(src|href)="(?!https?:\/\/|data:|#|javascript:)([^"]+)"/gi,
            (match, attr, path) => {
              try {
                const absoluteUrl = new URL(path, baseUrl).href;
                return `${attr}="${absoluteUrl}"`;
              } catch {
                return match;
              }
            }
          );

          // Also handle single-quoted attributes
          processedHtml = processedHtml.replace(
            /(src|href)='(?!https?:\/\/|data:|#|javascript:)([^']+)'/gi,
            (match, attr, path) => {
              try {
                const absoluteUrl = new URL(path, baseUrl).href;
                return `${attr}='${absoluteUrl}'`;
              } catch {
                return match;
              }
            }
          );

          setHtml(processedHtml);
        } else if (result.text) {
          // Wrap plain text in basic HTML
          setHtml(`<pre style="white-space: pre-wrap; font-family: inherit;">${result.text}</pre>`);
        } else {
          setError('No content available');
        }

        setLoading(false);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load content');
          setLoading(false);
        }
      }
    }

    fetchContent();

    return () => {
      cancelled = true;
    };
  }, [item.url]);

  // Handle scroll progress
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

  // Report initial scroll on content load
  useEffect(() => {
    if (html && !loading) {
      // Small delay to let content render
      setTimeout(() => handleScroll(), 100);
    }
  }, [html, loading, handleScroll]);

  return (
    <div className="h-full flex flex-col">
      {/* Loading state */}
      {loading && (
        <div className="flex-1 flex items-center justify-center bg-neutral-950">
          <div className="text-center">
            <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            <p className="text-neutral-400 text-sm">Loading page...</p>
          </div>
        </div>
      )}

      {/* Error state */}
      {error && !loading && (
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

      {/* Content via sandboxed iframe with srcdoc */}
      {html && !loading && !error && (
        <div ref={containerRef} className="flex-1 overflow-auto">
          <iframe
            srcDoc={html}
            title={item.title}
            className="w-full border-0"
            style={{ minHeight: '100%', height: 'auto' }}
            sandbox="allow-same-origin allow-popups"
            onLoad={(e) => {
              // Adjust iframe height to content
              const iframe = e.target as HTMLIFrameElement;
              try {
                const doc = iframe.contentDocument || iframe.contentWindow?.document;
                if (doc) {
                  const height = doc.body.scrollHeight;
                  iframe.style.height = `${height}px`;
                }
              } catch {
                // Cross-origin content, can't access
              }
            }}
          />
        </div>
      )}
    </div>
  );
}
