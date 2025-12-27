/**
 * Storage abstraction for extension data persistence
 */

import { browserAdapter } from '../adapters/browser';

export class Storage {
  private prefix: string;

  constructor(prefix = 'omnifeed_') {
    this.prefix = prefix;
  }

  private key(name: string): string {
    return `${this.prefix}${name}`;
  }

  async get<T>(name: string): Promise<T | null> {
    try {
      const value = await browserAdapter.storage.get<T>(this.key(name));
      return value;
    } catch (e) {
      console.error(`Storage.get failed for ${name}:`, e);
      return null;
    }
  }

  async set<T>(name: string, value: T): Promise<void> {
    try {
      await browserAdapter.storage.set(this.key(name), value);
    } catch (e) {
      console.error(`Storage.set failed for ${name}:`, e);
      throw e;
    }
  }

  async remove(name: string): Promise<void> {
    try {
      await browserAdapter.storage.remove(this.key(name));
    } catch (e) {
      console.error(`Storage.remove failed for ${name}:`, e);
    }
  }

  async clear(): Promise<void> {
    await browserAdapter.storage.clear();
  }

  // Convenience methods for common operations

  async getJSON<T>(name: string, defaultValue: T): Promise<T> {
    const value = await this.get<T>(name);
    return value ?? defaultValue;
  }

  async update<T extends object>(name: string, updates: Partial<T>): Promise<T | null> {
    const current = await this.get<T>(name);
    if (!current) return null;

    const updated = { ...current, ...updates };
    await this.set(name, updated);
    return updated;
  }

  async appendToArray<T>(name: string, items: T[], maxLength?: number): Promise<void> {
    const current = await this.get<T[]>(name) ?? [];
    let updated = [...current, ...items];

    if (maxLength && updated.length > maxLength) {
      updated = updated.slice(-maxLength);
    }

    await this.set(name, updated);
  }
}

// Singleton instance
export const storage = new Storage();

// Storage keys as constants
export const STORAGE_KEYS = {
  SESSION_TOKEN: 'session_token',
  SESSION_TIMESTAMP: 'session_timestamp',
  CAPTURE_CONFIG: 'capture_config',
  PRIVACY_CONFIG: 'privacy_config',
  EVENT_QUEUE: 'event_queue',
  USER_CONSENT: 'user_consent',
  AUDIO_FINGERPRINTS: 'audio_fingerprints',
  VISUAL_SIGNATURES: 'visual_signatures',
  EXCLUDED_DOMAINS: 'excluded_domains',
} as const;
