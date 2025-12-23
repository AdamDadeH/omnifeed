import { useEffect, useRef, useCallback } from 'react';
import type { RendererProps } from './types';

function sanitizeHtml(html: string): string {
  // Basic sanitization - remove script tags and event handlers
  // In production, use a proper sanitizer like DOMPurify
  return html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/\s*on\w+="[^"]*"/gi, '')
    .replace(/\s*on\w+='[^']*'/gi, '');
}

export function HtmlRenderer({ item, onScrollProgress }: RendererProps) {
  const containerRef = useRef<HTMLDivElement>(null);

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

  const contentHtml = item.metadata.content_html as string | undefined;

  if (!contentHtml) {
    return (
      <div className="text-center py-12 text-neutral-500">
        <p>No HTML content available.</p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto px-6 py-8">
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
      </div>
    </div>
  );
}
