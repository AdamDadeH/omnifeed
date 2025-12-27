/**
 * Capture Manager
 * Orchestrates all three capture layers and manages signal collection
 */

import { getAdapterRegistry, initializeRegistry } from './layer1/registry';
import { Layer2Tracker } from './layer2';
import { Layer3Tracker } from './layer3';
import type { PlatformAdapter } from './layer1/interface';
import type {
  PageContext,
  CollectedSignals,
  CaptureConfig,
  ContentMetadata,
  PlatformEvent,
  CapturedEvent,
} from '../core/types';
import { eventQueue } from '../core/queue';
import { privacyManager } from '../core/privacy';

// Generate unique ID
function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

export class CaptureManager {
  private layer1: PlatformAdapter | null = null;
  private layer2: Layer2Tracker;
  private layer3: Layer3Tracker;
  private context: PageContext | null = null;
  private config: CaptureConfig;
  private initialized = false;
  private eventBuffer: PlatformEvent[] = [];

  constructor(config: CaptureConfig) {
    this.config = config;
    this.layer2 = new Layer2Tracker();
    this.layer3 = new Layer3Tracker(config.audioBufferSeconds);
  }

  /**
   * Initialize capture for current page
   */
  async init(url: string): Promise<void> {
    if (this.initialized) return;

    // Create page context
    this.context = {
      url,
      domain: new URL(url).hostname,
      platform: null,
      contentId: null,
      title: document.title,
      startTime: Date.now(),
      sessionId: generateId(),
      adapter: 'none',
      signals: {
        platformEvents: [],
        scrollDepth: 0,
        timeVisible: 0,
        interactionCount: 0,
        audioFingerprints: [],
        visualSignatures: [],
      },
    };

    // Initialize adapter registry
    await initializeRegistry();

    // Layer 1: Select appropriate platform adapter
    if (this.config.layer1Enabled) {
      const registry = getAdapterRegistry();
      this.layer1 = registry.findAdapter(url);

      if (this.layer1) {
        this.context.platform = this.layer1.platformId;
        this.context.adapter = this.layer1.platformId;

        await this.layer1.init(this.context);

        // Subscribe to platform events
        this.layer1.onEvent((event) => {
          this.handlePlatformEvent(event);
        });

        // Extract metadata
        const metadata = await this.layer1.extractMetadata();
        if (metadata) {
          this.context.contentId = metadata.contentId;
          this.context.title = metadata.title;
        }

        // Start capturing
        this.layer1.startCapture();
      }
    }

    // Layer 2: Always initialize generic signals
    if (this.config.layer2Enabled) {
      this.layer2.init();
    }

    // Layer 3: Initialize if enabled and confidence is low
    if (this.config.layer3Enabled && this.shouldEnableLayer3()) {
      await this.layer3.init();
    }

    this.initialized = true;

    // Emit page view event
    await this.emitEvent('page_view', {
      platform: this.context.platform,
      contentId: this.context.contentId,
      title: this.context.title,
    });
  }

  /**
   * Determine if Layer 3 should be activated
   */
  private shouldEnableLayer3(): boolean {
    // Enable Layer 3 when:
    // 1. No platform adapter found
    // 2. Platform adapter failed to extract content ID
    // 3. Explicitly enabled for this domain

    if (!this.layer1) return true;
    if (!this.context?.contentId) return true;

    return false;
  }

  /**
   * Handle platform event from Layer 1
   */
  private async handlePlatformEvent(event: PlatformEvent): Promise<void> {
    this.eventBuffer.push(event);

    // Emit to queue
    await this.emitEvent(event.type, {
      platform: event.platform,
      contentId: event.contentId,
      ...event.data,
    });
  }

  /**
   * Collect all signals from all layers
   */
  async collectSignals(): Promise<CollectedSignals> {
    const signals: CollectedSignals = {
      timestamp: Date.now(),
      url: window.location.href,
      layer1: null,
      layer2: null,
      layer3: null,
      metadata: null,
      confidence: 0,
    };

    // Layer 1: Platform-specific
    if (this.layer1) {
      try {
        signals.metadata = await this.layer1.extractMetadata();
        signals.layer1 = {
          platform: this.layer1.platformId,
          events: [...this.eventBuffer],
          playbackState: this.layer1.getPlaybackState?.() || null,
        };
        signals.confidence += 0.4;
      } catch (e) {
        console.warn('Layer 1 capture failed:', e);
      }
    }

    // Layer 2: Generic signals
    if (this.config.layer2Enabled) {
      signals.layer2 = this.layer2.getStats();
      signals.confidence += 0.2;
    }

    // Layer 3: Fallback capture (only if needed)
    if (this.config.layer3Enabled && signals.confidence < 0.5) {
      try {
        signals.layer3 = await this.layer3.captureSignals();
        if (signals.layer3.audioFingerprint || signals.layer3.visualCapture) {
          signals.confidence += 0.3;
        }
      } catch (e) {
        console.warn('Layer 3 capture failed:', e);
      }
    }

    return signals;
  }

  /**
   * Finalize capture when leaving page
   */
  async finalize(): Promise<CollectedSignals> {
    const signals = await this.collectSignals();

    // Emit page leave event with all collected data
    await this.emitEvent('page_leave', {
      platform: this.context?.platform,
      contentId: this.context?.contentId,
      timeOnPage: this.layer2.getTimeOnPage(),
      visibleTime: this.layer2.getVisibleTime(),
      scrollDepth: signals.layer2?.scroll.maxScrollPct,
      engagementScore: this.layer2.getEngagementScore(),
    });

    return signals;
  }

  /**
   * Clean up resources
   */
  async destroy(): Promise<void> {
    if (!this.initialized) return;

    // Finalize before destroying
    await this.finalize();

    this.layer1?.destroy();
    this.layer2.destroy();
    await this.layer3.destroy();

    this.layer1 = null;
    this.context = null;
    this.eventBuffer = [];
    this.initialized = false;
  }

  /**
   * Emit event to queue
   */
  private async emitEvent(
    type: string,
    payload: Record<string, unknown>
  ): Promise<void> {
    const event: CapturedEvent = {
      type,
      timestamp: Date.now(),
      url: window.location.href,
      itemId: this.context?.contentId ?? null,
      payload: privacyManager.redactEvent({
        type,
        timestamp: Date.now(),
        url: window.location.href,
        itemId: null,
        payload,
      }).payload,
    };

    await eventQueue.enqueue(event);
  }

  // ============================================================================
  // Public API for content script
  // ============================================================================

  getContext(): PageContext | null {
    return this.context;
  }

  async getContentInfo(): Promise<ContentMetadata | null> {
    if (this.layer1) {
      return this.layer1.extractMetadata();
    }
    return null;
  }

  isInitialized(): boolean {
    return this.initialized;
  }

  getConfig(): CaptureConfig {
    return this.config;
  }

  updateConfig(updates: Partial<CaptureConfig>): void {
    this.config = { ...this.config, ...updates };
  }
}
