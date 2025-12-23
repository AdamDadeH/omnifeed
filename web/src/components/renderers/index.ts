import type { FeedItem } from '../../api/types';
import type { RendererInfo } from './types';

// Import renderers
import { HtmlRenderer } from './HtmlRenderer';
import { TextRenderer } from './TextRenderer';
import { YouTubeRenderer, canHandleYouTube } from './YouTubeRenderer';
import { QobuzRenderer, canHandleQobuz } from './QobuzRenderer';
import { WebPageRenderer, canHandleWebPage } from './WebPageRenderer';
import { TikTokRenderer, canHandleTikTok } from './TikTokRenderer';

// Re-export types
export type { RendererProps, RendererInfo } from './types';

/**
 * Registry of all available renderers.
 * Higher priority renderers are checked first.
 * The first renderer whose canHandle returns true is used.
 */
const renderers: RendererInfo[] = [
  // Custom renderers (high priority)
  {
    id: 'youtube',
    name: 'YouTube',
    component: YouTubeRenderer,
    canHandle: canHandleYouTube,
    priority: 100,
  },
  {
    id: 'qobuz',
    name: 'Qobuz',
    component: QobuzRenderer,
    canHandle: canHandleQobuz,
    priority: 100,
  },
  {
    id: 'tiktok',
    name: 'TikTok',
    component: TikTokRenderer,
    canHandle: canHandleTikTok,
    priority: 100,
  },

  // Base renderers (lower priority, act as fallbacks)
  {
    id: 'html',
    name: 'HTML Article',
    component: HtmlRenderer,
    canHandle: (item) => !!item.metadata.content_html,
    priority: 10,
  },
  {
    id: 'text',
    name: 'Plain Text',
    component: TextRenderer,
    canHandle: (item) => !!item.metadata.content_text,
    priority: 5,
  },
  {
    id: 'webpage',
    name: 'Web Page',
    component: WebPageRenderer,
    canHandle: canHandleWebPage,
    priority: 1,  // Lowest priority - fallback for direct page loading
  },
];

// Sort by priority (descending)
renderers.sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0));

/**
 * Find the appropriate renderer for a feed item.
 * Returns the first renderer whose canHandle returns true.
 */
export function getRendererForItem(item: FeedItem): RendererInfo | null {
  for (const renderer of renderers) {
    if (renderer.canHandle(item)) {
      return renderer;
    }
  }
  return null;
}

/**
 * Get all registered renderers.
 */
export function getAllRenderers(): RendererInfo[] {
  return [...renderers];
}

/**
 * Register a custom renderer.
 * Use this to add renderers dynamically (e.g., from plugins).
 */
export function registerRenderer(renderer: RendererInfo): void {
  renderers.push(renderer);
  renderers.sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0));
}

/**
 * Check if there's a renderer that can handle inline display for this item.
 * If false, the item can only be viewed via "Open original".
 */
export function canRenderInline(item: FeedItem): boolean {
  return getRendererForItem(item) !== null;
}

// Export individual renderers for direct use if needed
export { HtmlRenderer } from './HtmlRenderer';
export { TextRenderer } from './TextRenderer';
export { YouTubeRenderer } from './YouTubeRenderer';
export { QobuzRenderer } from './QobuzRenderer';
export { WebPageRenderer } from './WebPageRenderer';
export { TikTokRenderer } from './TikTokRenderer';
