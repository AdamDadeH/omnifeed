import type { FeedItem } from '../../api/types';

/**
 * Props passed to all content renderers
 */
export interface RendererProps {
  item: FeedItem;
  onScrollProgress?: (pct: number) => void;
}

/**
 * Renderer registration info
 */
export interface RendererInfo {
  /** Unique identifier for this renderer */
  id: string;
  /** Human-readable name */
  name: string;
  /** React component to render content */
  component: React.ComponentType<RendererProps>;
  /**
   * Check if this renderer can handle the given item.
   * Higher priority renderers are checked first.
   * Return true if this renderer should be used.
   */
  canHandle: (item: FeedItem) => boolean;
  /** Priority (higher = checked first). Default: 0 */
  priority?: number;
}
