/**
 * Generic Platform Adapter
 * Fallback adapter for any web page with basic content detection
 */

import { BasePlatformAdapter } from './interface';
import type { ContentMetadata, PlaybackState, ContentType } from '../../core/types';

export class GenericAdapter extends BasePlatformAdapter {
  readonly platformId = 'generic';
  readonly domains = ['*'];

  private video: HTMLVideoElement | null = null;
  private audio: HTMLAudioElement | null = null;
  private mediaObserver: MutationObserver | null = null;

  canHandle(_url: string): boolean {
    // Generic adapter handles everything
    return true;
  }

  async init(context: import('../../core/types').PageContext): Promise<void> {
    await super.init(context);

    // Find any media elements
    this.video = document.querySelector('video');
    this.audio = document.querySelector('audio');

    // Watch for new media elements
    this.observeMedia();

    // Setup listeners if media exists
    if (this.video) {
      this.setupMediaListeners(this.video);
    }
    if (this.audio) {
      this.setupMediaListeners(this.audio);
    }
  }

  destroy(): void {
    this.mediaObserver?.disconnect();
    this.mediaObserver = null;
    super.destroy();
  }

  async extractMetadata(): Promise<ContentMetadata | null> {
    // Strategy 1: JSON-LD structured data
    const jsonLd = this.extractJsonLdMetadata();
    if (jsonLd) return jsonLd;

    // Strategy 2: Open Graph + schema.org
    return this.extractOpenGraphMetadata();
  }

  getPlaybackState(): PlaybackState | null {
    const media = this.video || this.audio;
    if (!media) return null;

    return {
      isPlaying: !media.paused,
      currentTime: media.currentTime,
      duration: media.duration || 0,
      playbackRate: media.playbackRate,
      volume: media.volume,
      isMuted: media.muted,
    };
  }

  // ============================================================================
  // Private: Media handling
  // ============================================================================

  private observeMedia(): void {
    this.mediaObserver = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (node instanceof HTMLVideoElement) {
            this.video = node;
            this.setupMediaListeners(node);
          } else if (node instanceof HTMLAudioElement) {
            this.audio = node;
            this.setupMediaListeners(node);
          }
        }
      }
    });

    this.mediaObserver.observe(document.body, {
      childList: true,
      subtree: true,
    });
  }

  private setupMediaListeners(media: HTMLMediaElement): void {
    media.addEventListener('play', () => {
      this.emit(this.createEvent('play', { currentTime: media.currentTime }));
    });

    media.addEventListener('pause', () => {
      this.emit(this.createEvent('pause', { currentTime: media.currentTime }));
    });

    media.addEventListener('ended', () => {
      this.emit(this.createEvent('complete', { duration: media.duration }));
    });
  }

  // ============================================================================
  // Private: Metadata extraction
  // ============================================================================

  private extractJsonLdMetadata(): ContentMetadata | null {
    const jsonLd = this.extractJsonLd();
    if (!jsonLd) return null;

    const type = jsonLd['@type'];
    const contentType = this.mapSchemaTypeToContentType(String(type || ''));

    return {
      contentId: this.generateContentId(),
      title: String(jsonLd.headline || jsonLd.name || document.title),
      creatorName: this.extractAuthor(jsonLd),
      creatorId: null,
      contentType,
      durationSeconds: this.extractDuration(jsonLd),
      thumbnailUrl: this.extractImage(jsonLd),
      canonicalUrl: String(jsonLd.url || window.location.href),
      platform: null,
      metadata: {
        domain: window.location.hostname,
        type: String(type || 'WebPage'),
        datePublished: jsonLd.datePublished,
        description: jsonLd.description,
      },
    };
  }

  private extractOpenGraphMetadata(): ContentMetadata {
    const og = this.extractOpenGraph();
    const contentType = this.detectContentType();

    return {
      contentId: this.generateContentId(),
      title: og.title || document.title,
      creatorName: this.getMetaContent('author') || null,
      creatorId: null,
      contentType,
      durationSeconds: this.video?.duration || this.audio?.duration || null,
      thumbnailUrl: og.thumbnailUrl || null,
      canonicalUrl: og.canonicalUrl || window.location.href,
      platform: null,
      metadata: {
        domain: window.location.hostname,
        path: window.location.pathname,
        description: this.getMetaContent('description'),
      },
    };
  }

  private extractAuthor(jsonLd: Record<string, unknown>): string | null {
    const author = jsonLd.author;
    if (!author) return null;

    if (typeof author === 'string') return author;
    if (typeof author === 'object' && author !== null) {
      const authorObj = author as Record<string, unknown>;
      return String(authorObj.name || '');
    }
    return null;
  }

  private extractDuration(jsonLd: Record<string, unknown>): number | null {
    const duration = jsonLd.duration;
    if (!duration) return null;

    if (typeof duration === 'number') return duration;
    if (typeof duration === 'string') {
      // Parse ISO 8601 duration
      const match = duration.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/);
      if (match) {
        const hours = parseInt(match[1] || '0', 10);
        const minutes = parseInt(match[2] || '0', 10);
        const seconds = parseInt(match[3] || '0', 10);
        return hours * 3600 + minutes * 60 + seconds;
      }
    }
    return null;
  }

  private extractImage(jsonLd: Record<string, unknown>): string | null {
    const image = jsonLd.image || jsonLd.thumbnailUrl;
    if (!image) return null;

    if (typeof image === 'string') return image;
    if (Array.isArray(image) && image.length > 0) {
      const first = image[0];
      if (typeof first === 'string') return first;
      if (typeof first === 'object' && first !== null) {
        return String((first as Record<string, unknown>).url || '');
      }
    }
    if (typeof image === 'object' && image !== null) {
      return String((image as Record<string, unknown>).url || '');
    }
    return null;
  }

  // ============================================================================
  // Private: Content type detection
  // ============================================================================

  private detectContentType(): ContentType {
    // Check for video elements
    if (document.querySelector('video')) return 'video';

    // Check for audio elements
    if (document.querySelector('audio')) return 'audio';

    // Check for article structure
    if (document.querySelector('article')) return 'article';

    // Check meta type
    const ogType = this.getMetaContent('og:type');
    if (ogType) {
      if (ogType.includes('video')) return 'video';
      if (ogType.includes('music') || ogType.includes('audio')) return 'audio';
      if (ogType.includes('article')) return 'article';
    }

    // Check for image galleries
    const images = document.querySelectorAll('article img, main img');
    if (images.length > 5) return 'image';

    return 'other';
  }

  private mapSchemaTypeToContentType(schemaType: string): ContentType {
    const type = schemaType.toLowerCase();

    if (type.includes('video')) return 'video';
    if (type.includes('audio') || type.includes('music') || type.includes('podcast')) {
      return 'audio';
    }
    if (
      type.includes('article') ||
      type.includes('news') ||
      type.includes('blog') ||
      type.includes('review')
    ) {
      return 'article';
    }
    if (type.includes('image') || type.includes('photo')) return 'image';

    return 'other';
  }

  // ============================================================================
  // Private: ID generation
  // ============================================================================

  private generateContentId(): string {
    // Create deterministic ID from URL
    const url = new URL(window.location.href);
    const canonical = `${url.hostname}${url.pathname}`;

    // Simple hash
    let hash = 0;
    for (let i = 0; i < canonical.length; i++) {
      const char = canonical.charCodeAt(i);
      hash = (hash << 5) - hash + char;
      hash = hash & hash;
    }

    return `generic_${Math.abs(hash).toString(36)}`;
  }
}
