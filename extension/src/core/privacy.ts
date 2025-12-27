/**
 * Privacy controls and consent management
 */

import { storage, STORAGE_KEYS } from './storage';
import { DEFAULT_PRIVACY_CONFIG, ALL_SUPPORTED_DOMAINS } from './config';
import type { PrivacyConfig, CapturedEvent } from './types';

const CONSENT_VERSION = '1.0';

export interface ConsentOptions {
  implicitFeedback: boolean;
  explicitFeedback: boolean;
  audioCapture: boolean;
  visualCapture: boolean;
  sendToServer: boolean;
}

export interface UserConsent {
  version: string;
  timestamp: number;
  options: ConsentOptions;
}

export class PrivacyManager {
  private config: PrivacyConfig = DEFAULT_PRIVACY_CONFIG;
  private consent: UserConsent | null = null;

  async init(): Promise<void> {
    // Load privacy config
    const storedConfig = await storage.get<PrivacyConfig>(STORAGE_KEYS.PRIVACY_CONFIG);
    if (storedConfig) {
      this.config = { ...DEFAULT_PRIVACY_CONFIG, ...storedConfig };
    }

    // Load consent
    this.consent = await storage.get<UserConsent>(STORAGE_KEYS.USER_CONSENT);
  }

  async saveConfig(): Promise<void> {
    await storage.set(STORAGE_KEYS.PRIVACY_CONFIG, this.config);
  }

  getConfig(): PrivacyConfig {
    return this.config;
  }

  async updateConfig(updates: Partial<PrivacyConfig>): Promise<void> {
    this.config = { ...this.config, ...updates };
    await this.saveConfig();
  }

  // ============================================================================
  // Consent
  // ============================================================================

  hasConsent(): boolean {
    return this.consent?.version === CONSENT_VERSION;
  }

  getConsent(): UserConsent | null {
    return this.consent;
  }

  async recordConsent(options: ConsentOptions): Promise<void> {
    this.consent = {
      version: CONSENT_VERSION,
      timestamp: Date.now(),
      options,
    };
    await storage.set(STORAGE_KEYS.USER_CONSENT, this.consent);
  }

  async revokeConsent(): Promise<void> {
    this.consent = null;
    await storage.remove(STORAGE_KEYS.USER_CONSENT);
    await this.clearAllData();
  }

  private async clearAllData(): Promise<void> {
    await storage.remove(STORAGE_KEYS.EVENT_QUEUE);
    await storage.remove(STORAGE_KEYS.SESSION_TOKEN);
    await storage.remove(STORAGE_KEYS.AUDIO_FINGERPRINTS);
    await storage.remove(STORAGE_KEYS.VISUAL_SIGNATURES);
    await storage.remove(STORAGE_KEYS.CAPTURE_CONFIG);
  }

  // ============================================================================
  // Capture permissions
  // ============================================================================

  isCaptureAllowed(url: string): boolean {
    if (!this.hasConsent()) return false;
    if (!this.consent?.options.implicitFeedback) return false;

    try {
      const urlObj = new URL(url);
      const domain = urlObj.hostname.replace(/^www\./, '');

      // Check exclusion list
      if (this.config.excludedDomains.some((d) => domain.includes(d))) {
        return false;
      }

      // Check known platforms only mode
      if (this.config.captureOnlyKnownPlatforms) {
        const isKnown = ALL_SUPPORTED_DOMAINS.some((supported) => {
          // Handle wildcard patterns
          if (supported.startsWith('*.')) {
            const suffix = supported.slice(2);
            return domain.endsWith(suffix);
          }
          return domain === supported || domain.endsWith(`.${supported}`);
        });

        if (!isKnown) return false;
      }

      return true;
    } catch {
      return false;
    }
  }

  isAudioCaptureAllowed(): boolean {
    return (
      this.hasConsent() &&
      !!this.consent?.options.audioCapture &&
      !this.config.localProcessingOnly
    );
  }

  isVisualCaptureAllowed(): boolean {
    return (
      this.hasConsent() &&
      !!this.consent?.options.visualCapture &&
      !this.config.localProcessingOnly
    );
  }

  canSendRawMedia(): boolean {
    return (
      this.hasConsent() &&
      !!this.consent?.options.sendToServer &&
      this.config.sendRawMedia
    );
  }

  // ============================================================================
  // Data redaction
  // ============================================================================

  redactEvent(event: CapturedEvent): CapturedEvent {
    return {
      ...event,
      payload: this.redactPayload(event.payload),
    };
  }

  private redactPayload(
    payload: Record<string, unknown>
  ): Record<string, unknown> {
    const sensitiveKeys = [
      'email',
      'password',
      'token',
      'key',
      'secret',
      'auth',
      'credential',
      'ssn',
      'credit',
      'card',
    ];

    const result = { ...payload };

    for (const key of Object.keys(result)) {
      const lowerKey = key.toLowerCase();
      if (sensitiveKeys.some((s) => lowerKey.includes(s))) {
        result[key] = '[REDACTED]';
      }
    }

    return result;
  }

  // ============================================================================
  // Domain management
  // ============================================================================

  async addExcludedDomain(domain: string): Promise<void> {
    if (!this.config.excludedDomains.includes(domain)) {
      this.config.excludedDomains.push(domain);
      await this.saveConfig();
    }
  }

  async removeExcludedDomain(domain: string): Promise<void> {
    this.config.excludedDomains = this.config.excludedDomains.filter(
      (d) => d !== domain
    );
    await this.saveConfig();
  }

  getExcludedDomains(): string[] {
    return this.config.excludedDomains;
  }
}

// Singleton instance
export const privacyManager = new PrivacyManager();
