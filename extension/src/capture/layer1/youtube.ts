/**
 * YouTube Platform Adapter
 * Captures video playback events and metadata from YouTube
 */

import { BasePlatformAdapter } from './interface';
import type { ContentMetadata, PlaybackState } from '../../core/types';

export class YouTubeAdapter extends BasePlatformAdapter {
  readonly platformId = 'youtube';
  readonly domains = ['youtube.com', 'youtu.be'];

  private video: HTMLVideoElement | null = null;
  private observer: MutationObserver | null = null;
  private lastTime = 0;
  private seekThreshold = 2; // seconds
  private boundHandlers: Map<string, EventListener> = new Map();

  canHandle(url: string): boolean {
    if (!super.canHandle(url)) return false;

    // Only handle watch pages and shorts
    return (
      url.includes('/watch') ||
      url.includes('/shorts/') ||
      url.includes('youtu.be/')
    );
  }

  async init(context: import('../../core/types').PageContext): Promise<void> {
    await super.init(context);

    // Wait for video element
    this.video = (await this.waitForElement('video')) as HTMLVideoElement;

    if (this.video) {
      this.setupVideoListeners();
    }

    // Watch for SPA navigation (YouTube is an SPA)
    this.observeNavigation();
  }

  destroy(): void {
    this.removeVideoListeners();
    this.observer?.disconnect();
    this.observer = null;
    this.video = null;
    super.destroy();
  }

  async extractMetadata(): Promise<ContentMetadata | null> {
    // Strategy 1: JSON-LD (most reliable)
    const jsonLd = this.extractJsonLdMetadata();
    if (jsonLd) return jsonLd;

    // Strategy 2: ytInitialPlayerResponse (embedded in page)
    const playerResponse = this.extractPlayerResponse();
    if (playerResponse) return playerResponse;

    // Strategy 3: DOM scraping (fallback)
    return this.scrapeMetadata();
  }

  getPlaybackState(): PlaybackState | null {
    if (!this.video) return null;

    return {
      isPlaying: !this.video.paused,
      currentTime: this.video.currentTime,
      duration: this.video.duration || 0,
      playbackRate: this.video.playbackRate,
      volume: this.video.volume,
      isMuted: this.video.muted,
    };
  }

  startCapture(): void {
    super.startCapture();
    if (this.video) {
      this.lastTime = this.video.currentTime;
    }
  }

  // ============================================================================
  // Private: Event handling
  // ============================================================================

  private setupVideoListeners(): void {
    if (!this.video) return;

    const handlers: Record<string, EventListener> = {
      play: this.handlePlay.bind(this),
      pause: this.handlePause.bind(this),
      seeking: this.handleSeeking.bind(this),
      seeked: this.handleSeeked.bind(this),
      timeupdate: this.handleTimeUpdate.bind(this),
      ended: this.handleEnded.bind(this),
      volumechange: this.handleVolumeChange.bind(this),
      ratechange: this.handleRateChange.bind(this),
    };

    for (const [event, handler] of Object.entries(handlers)) {
      this.video.addEventListener(event, handler);
      this.boundHandlers.set(event, handler);
    }
  }

  private removeVideoListeners(): void {
    if (!this.video) return;

    for (const [event, handler] of this.boundHandlers.entries()) {
      this.video.removeEventListener(event, handler);
    }
    this.boundHandlers.clear();
  }

  private handlePlay(): void {
    this.emit(
      this.createEvent('play', {
        currentTime: this.video?.currentTime || 0,
      })
    );
  }

  private handlePause(): void {
    this.emit(
      this.createEvent('pause', {
        currentTime: this.video?.currentTime || 0,
      })
    );
  }

  private handleSeeking(): void {
    // Seeking started - record the time we're seeking from
    if (this.video) {
      this.lastTime = this.video.currentTime;
    }
  }

  private handleSeeked(): void {
    if (!this.video) return;

    const currentTime = this.video.currentTime;
    const seekDelta = currentTime - this.lastTime;

    if (Math.abs(seekDelta) > this.seekThreshold) {
      this.emit(
        this.createEvent('seek', {
          from: this.lastTime,
          to: currentTime,
          delta: seekDelta,
        })
      );
    }

    this.lastTime = currentTime;
  }

  private handleTimeUpdate(): void {
    if (this.video) {
      this.lastTime = this.video.currentTime;
    }
  }

  private handleEnded(): void {
    this.emit(
      this.createEvent('complete', {
        duration: this.video?.duration || 0,
      })
    );
  }

  private handleVolumeChange(): void {
    this.emit(
      this.createEvent('volume_change', {
        volume: this.video?.volume || 0,
        muted: this.video?.muted || false,
      })
    );
  }

  private handleRateChange(): void {
    this.emit(
      this.createEvent('playback_rate_change', {
        rate: this.video?.playbackRate || 1,
      })
    );
  }

  // ============================================================================
  // Private: Metadata extraction
  // ============================================================================

  private extractJsonLdMetadata(): ContentMetadata | null {
    const jsonLd = this.extractJsonLd();
    if (!jsonLd || jsonLd['@type'] !== 'VideoObject') return null;

    const videoId = this.getVideoId();

    return {
      contentId: videoId,
      title: String(jsonLd.name || ''),
      creatorName: this.extractCreatorFromJsonLd(jsonLd),
      creatorId: this.extractCreatorIdFromUrl(),
      contentType: 'video',
      durationSeconds: this.parseDuration(String(jsonLd.duration || '')),
      thumbnailUrl: String(jsonLd.thumbnailUrl || ''),
      canonicalUrl: `https://www.youtube.com/watch?v=${videoId}`,
      platform: 'youtube',
      metadata: {
        uploadDate: jsonLd.uploadDate,
        description: jsonLd.description,
        interactionCount: jsonLd.interactionCount,
      },
    };
  }

  private extractPlayerResponse(): ContentMetadata | null {
    // YouTube embeds player data in script tags
    const scripts = document.querySelectorAll('script');
    for (const script of scripts) {
      const match = script.textContent?.match(
        /var ytInitialPlayerResponse\s*=\s*({.+?});/
      );
      if (match) {
        try {
          const data = JSON.parse(match[1]);
          return this.parsePlayerResponse(data);
        } catch {
          continue;
        }
      }
    }
    return null;
  }

  private parsePlayerResponse(data: Record<string, unknown>): ContentMetadata | null {
    const videoDetails = data.videoDetails as Record<string, unknown> | undefined;
    if (!videoDetails) return null;

    const videoId = String(videoDetails.videoId || '');

    return {
      contentId: videoId,
      title: String(videoDetails.title || ''),
      creatorName: String(videoDetails.author || ''),
      creatorId: String(videoDetails.channelId || ''),
      contentType: 'video',
      durationSeconds: parseInt(String(videoDetails.lengthSeconds || '0'), 10),
      thumbnailUrl: this.extractThumbnail(videoDetails),
      canonicalUrl: `https://www.youtube.com/watch?v=${videoId}`,
      platform: 'youtube',
      metadata: {
        viewCount: videoDetails.viewCount,
        isLiveContent: videoDetails.isLiveContent,
        keywords: videoDetails.keywords,
      },
    };
  }

  private scrapeMetadata(): ContentMetadata | null {
    const videoId = this.getVideoId();
    if (!videoId) return null;

    // Get title from various possible locations
    const title =
      document.querySelector('h1.ytd-video-primary-info-renderer')?.textContent ||
      document.querySelector('meta[name="title"]')?.getAttribute('content') ||
      document.title.replace(' - YouTube', '');

    // Get channel name
    const creatorName =
      document.querySelector('#channel-name a')?.textContent ||
      document.querySelector('ytd-channel-name a')?.textContent ||
      null;

    // Get channel ID from link
    const channelLink = document.querySelector('#channel-name a, ytd-channel-name a');
    const creatorId = channelLink?.getAttribute('href')?.split('/').pop() || null;

    return {
      contentId: videoId,
      title: title?.trim() || '',
      creatorName: creatorName?.trim() || null,
      creatorId,
      contentType: 'video',
      durationSeconds: this.video?.duration || null,
      thumbnailUrl: `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`,
      canonicalUrl: `https://www.youtube.com/watch?v=${videoId}`,
      platform: 'youtube',
      metadata: {},
    };
  }

  // ============================================================================
  // Private: Helpers
  // ============================================================================

  private getVideoId(): string {
    const url = new URL(window.location.href);

    // Standard watch page
    const v = url.searchParams.get('v');
    if (v) return v;

    // Shorts
    const shortsMatch = url.pathname.match(/\/shorts\/([^/?]+)/);
    if (shortsMatch) return shortsMatch[1];

    // youtu.be
    if (url.hostname === 'youtu.be') {
      return url.pathname.slice(1).split('/')[0];
    }

    return '';
  }

  private extractCreatorFromJsonLd(jsonLd: Record<string, unknown>): string | null {
    const author = jsonLd.author as Record<string, unknown> | undefined;
    if (author?.name) return String(author.name);

    // Try publication field
    const publication = jsonLd.publication as Record<string, unknown> | undefined;
    if (publication?.name) return String(publication.name);

    return null;
  }

  private extractCreatorIdFromUrl(): string | null {
    const channelLink = document.querySelector(
      'a[href*="/channel/"], a[href*="/@"]'
    );
    if (!channelLink) return null;

    const href = channelLink.getAttribute('href') || '';
    const match = href.match(/\/(channel\/[^/?]+|@[^/?]+)/);
    return match ? match[1] : null;
  }

  private extractThumbnail(videoDetails: Record<string, unknown>): string | null {
    const thumbnail = videoDetails.thumbnail as Record<string, unknown> | undefined;
    const thumbnails = thumbnail?.thumbnails as Array<{ url: string }> | undefined;
    if (thumbnails?.length) {
      // Get highest quality
      return thumbnails[thumbnails.length - 1].url;
    }
    return null;
  }

  private parseDuration(isoDuration: string): number | null {
    // Parse ISO 8601 duration (PT1H2M3S)
    const match = isoDuration.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/);
    if (!match) return null;

    const hours = parseInt(match[1] || '0', 10);
    const minutes = parseInt(match[2] || '0', 10);
    const seconds = parseInt(match[3] || '0', 10);

    return hours * 3600 + minutes * 60 + seconds;
  }

  private observeNavigation(): void {
    // YouTube uses SPA navigation - watch for URL changes
    let lastUrl = window.location.href;

    this.observer = new MutationObserver(() => {
      if (window.location.href !== lastUrl) {
        lastUrl = window.location.href;
        this.handleNavigation();
      }
    });

    this.observer.observe(document.body, {
      childList: true,
      subtree: true,
    });
  }

  private async handleNavigation(): Promise<void> {
    // Re-initialize on navigation
    this.removeVideoListeners();

    if (this.canHandle(window.location.href)) {
      this.video = (await this.waitForElement('video')) as HTMLVideoElement;
      if (this.video) {
        this.setupVideoListeners();
      }
    }
  }
}
