import { useEffect, useRef, useCallback } from 'react';
import type { RendererProps } from './types';

export function TextRenderer({ item, onScrollProgress }: RendererProps) {
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

  const contentText = item.metadata.content_text as string | undefined;

  if (!contentText) {
    return (
      <div className="text-center py-12 text-neutral-500">
        <p>No text content available.</p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto px-6 py-8">
        <article className="text-neutral-300 whitespace-pre-wrap leading-relaxed">
          {contentText}
        </article>
      </div>
    </div>
  );
}
