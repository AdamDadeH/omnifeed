/**
 * Platform Adapter Interface
 * Defines the contract for platform-specific content capture adapters
 */

import type {
  ContentMetadata,
  PlatformEvent,
  PlaybackState,
  PageContext,
} from '../../core/types';

export interface PlatformAdapter {
  /** Unique identifier for this platform */
  readonly platformId: string;

  /** Domains this adapter handles */
  readonly domains: string[];

  /** Check if adapter can handle current page */
  canHandle(url: string): boolean;

  /** Initialize adapter on page load */
  init(context: PageContext): Promise<void>;

  /** Clean up on page unload */
  destroy(): void;

  /** Extract content metadata from page */
  extractMetadata(): Promise<ContentMetadata | null>;

  /** Start capturing platform-specific events */
  startCapture(): void;

  /** Stop capturing */
  stopCapture(): void;

  /** Get current playback state (for media platforms) */
  getPlaybackState?(): PlaybackState | null;

  /** Subscribe to platform events */
  onEvent(callback: EventCallback): void;

  /** Remove event subscription */
  offEvent(callback: EventCallback): void;
}

export type EventCallback = (event: PlatformEvent) => void;

/**
 * Base class for platform adapters with common functionality
 */
export abstract class BasePlatformAdapter implements PlatformAdapter {
  abstract readonly platformId: string;
  abstract readonly domains: string[];

  protected context: PageContext | null = null;
  protected eventCallbacks: Set<EventCallback> = new Set();
  protected isCapturing = false;

  canHandle(url: string): boolean {
    try {
      const urlObj = new URL(url);
      const hostname = urlObj.hostname.replace(/^www\./, '');
      return this.domains.some(
        (domain) => hostname === domain || hostname.endsWith(`.${domain}`)
      );
    } catch {
      return false;
    }
  }

  async init(context: PageContext): Promise<void> {
    this.context = context;
  }

  destroy(): void {
    this.stopCapture();
    this.eventCallbacks.clear();
    this.context = null;
  }

  abstract extractMetadata(): Promise<ContentMetadata | null>;

  startCapture(): void {
    this.isCapturing = true;
  }

  stopCapture(): void {
    this.isCapturing = false;
  }

  onEvent(callback: EventCallback): void {
    this.eventCallbacks.add(callback);
  }

  offEvent(callback: EventCallback): void {
    this.eventCallbacks.delete(callback);
  }

  protected emit(event: PlatformEvent): void {
    if (!this.isCapturing) return;

    for (const callback of this.eventCallbacks) {
      try {
        callback(event);
      } catch (e) {
        console.error('Event callback error:', e);
      }
    }
  }

  protected createEvent(
    type: string,
    data: Record<string, unknown> = {}
  ): PlatformEvent {
    return {
      type,
      timestamp: Date.now(),
      platform: this.platformId,
      contentId: this.context?.contentId ?? '',
      data,
    };
  }

  // ============================================================================
  // Utility methods for subclasses
  // ============================================================================

  protected waitForElement(
    selector: string,
    timeout = 5000
  ): Promise<Element | null> {
    return new Promise((resolve) => {
      const element = document.querySelector(selector);
      if (element) {
        resolve(element);
        return;
      }

      const observer = new MutationObserver(() => {
        const el = document.querySelector(selector);
        if (el) {
          observer.disconnect();
          resolve(el);
        }
      });

      observer.observe(document.body, {
        childList: true,
        subtree: true,
      });

      setTimeout(() => {
        observer.disconnect();
        resolve(null);
      }, timeout);
    });
  }

  protected extractJsonLd(): Record<string, unknown> | null {
    const script = document.querySelector('script[type="application/ld+json"]');
    if (!script?.textContent) return null;

    try {
      return JSON.parse(script.textContent);
    } catch {
      return null;
    }
  }

  protected getMetaContent(property: string): string | null {
    const meta = document.querySelector(
      `meta[property="${property}"], meta[name="${property}"]`
    );
    return meta?.getAttribute('content') ?? null;
  }

  protected extractOpenGraph(): Partial<ContentMetadata> {
    return {
      title: this.getMetaContent('og:title') ?? document.title,
      thumbnailUrl: this.getMetaContent('og:image') ?? undefined,
      canonicalUrl:
        this.getMetaContent('og:url') ?? window.location.href,
    } as Partial<ContentMetadata>;
  }
}
