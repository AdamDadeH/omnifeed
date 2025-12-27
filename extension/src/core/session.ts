/**
 * Session management for extension authentication
 */

import { storage, STORAGE_KEYS } from './storage';
import { apiClient } from './api';
import { SESSION_CONFIG, DEFAULT_CAPTURE_CONFIG } from './config';
import type { CaptureConfig } from './types';

export class SessionManager {
  private sessionToken: string | null = null;
  private config: CaptureConfig | null = null;
  private initialized = false;

  async init(): Promise<void> {
    if (this.initialized) return;

    // Check for existing session
    this.sessionToken = await storage.get<string>(STORAGE_KEYS.SESSION_TOKEN);

    if (!this.sessionToken || (await this.isSessionExpired())) {
      await this.authenticate();
    } else {
      // Load existing config
      this.config = await storage.get<CaptureConfig>(STORAGE_KEYS.CAPTURE_CONFIG);
    }

    this.initialized = true;
  }

  private async authenticate(): Promise<void> {
    try {
      const response = await apiClient.authenticate();
      this.sessionToken = response.session_token;
      this.config = response.capture_config;
    } catch (e) {
      console.error('Authentication failed:', e);
      // Use default config if auth fails
      this.config = DEFAULT_CAPTURE_CONFIG;
    }
  }

  private async isSessionExpired(): Promise<boolean> {
    const timestampStr = await storage.get<string>(STORAGE_KEYS.SESSION_TIMESTAMP);
    if (!timestampStr) return true;

    const timestamp = parseInt(timestampStr, 10);
    if (isNaN(timestamp)) return true;

    const age = Date.now() - timestamp;
    return age > SESSION_CONFIG.maxAgeMs;
  }

  async refresh(): Promise<void> {
    await this.authenticate();
  }

  getToken(): string | null {
    return this.sessionToken;
  }

  getConfig(): CaptureConfig {
    return this.config ?? DEFAULT_CAPTURE_CONFIG;
  }

  async updateConfig(updates: Partial<CaptureConfig>): Promise<void> {
    this.config = { ...this.getConfig(), ...updates };
    await storage.set(STORAGE_KEYS.CAPTURE_CONFIG, this.config);
  }

  isInitialized(): boolean {
    return this.initialized;
  }
}

// Singleton instance
export const sessionManager = new SessionManager();
