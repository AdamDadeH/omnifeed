/**
 * OmniFeed API client for extension
 */

import { API_ENDPOINT, EXTENSION_VERSION } from './config';
import { storage, STORAGE_KEYS } from './storage';
import { getPlatformInfo } from '../adapters/browser';
import type {
  BatchEventRequest,
  BatchEventResponse,
  ExtensionAuthRequest,
  ExtensionAuthResponse,
  ExtensionItemRequest,
  ExtensionItemResponse,
  MediaUploadRequest,
  MediaUploadResponse,
  ExplicitRating,
} from './types';

export class ApiClient {
  private baseUrl: string;
  private sessionToken: string | null = null;

  constructor(baseUrl = API_ENDPOINT) {
    this.baseUrl = baseUrl;
  }

  private async getHeaders(): Promise<HeadersInit> {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    };

    if (!this.sessionToken) {
      this.sessionToken = await storage.get<string>(STORAGE_KEYS.SESSION_TOKEN);
    }

    if (this.sessionToken) {
      headers['Authorization'] = `Bearer ${this.sessionToken}`;
    }

    return headers;
  }

  private async request<T>(
    method: string,
    endpoint: string,
    body?: unknown
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers = await this.getHeaders();

    const response = await fetch(url, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`API error ${response.status}: ${error}`);
    }

    return response.json();
  }

  // ============================================================================
  // Authentication
  // ============================================================================

  async authenticate(): Promise<ExtensionAuthResponse> {
    const { browser, os } = getPlatformInfo();

    const request: ExtensionAuthRequest = {
      extension_version: EXTENSION_VERSION,
      browser,
      platform: os,
    };

    const response = await this.request<ExtensionAuthResponse>(
      'POST',
      '/extension/auth',
      request
    );

    // Store session token
    this.sessionToken = response.session_token;
    await storage.set(STORAGE_KEYS.SESSION_TOKEN, response.session_token);
    await storage.set(STORAGE_KEYS.SESSION_TIMESTAMP, Date.now().toString());
    await storage.set(STORAGE_KEYS.CAPTURE_CONFIG, response.capture_config);

    return response;
  }

  // ============================================================================
  // Events
  // ============================================================================

  async submitEvents(request: BatchEventRequest): Promise<BatchEventResponse> {
    return this.request<BatchEventResponse>('POST', '/extension/events', request);
  }

  // ============================================================================
  // Media (Layer 3)
  // ============================================================================

  async uploadMedia(request: MediaUploadRequest): Promise<MediaUploadResponse> {
    return this.request<MediaUploadResponse>('POST', '/extension/media', request);
  }

  // ============================================================================
  // Items
  // ============================================================================

  async createItem(request: ExtensionItemRequest): Promise<ExtensionItemResponse> {
    return this.request<ExtensionItemResponse>('POST', '/extension/items', request);
  }

  async findItem(query: {
    url?: string;
    external_id?: string;
    platform?: string;
  }): Promise<ExtensionItemResponse | null> {
    const params = new URLSearchParams();
    if (query.url) params.append('url', query.url);
    if (query.external_id) params.append('external_id', query.external_id);
    if (query.platform) params.append('platform', query.platform);

    try {
      return await this.request<ExtensionItemResponse>(
        'GET',
        `/extension/items/find?${params.toString()}`
      );
    } catch {
      return null;
    }
  }

  // ============================================================================
  // Feedback
  // ============================================================================

  async submitExplicitFeedback(
    itemId: string,
    rating: ExplicitRating
  ): Promise<void> {
    await this.request('POST', '/feedback/explicit', {
      item_id: itemId,
      reward_score: rating.rewardScore,
      selections: rating.selections,
      notes: rating.notes,
      completion_pct: rating.completionPct,
      is_checkpoint: false,
    });
  }

  // ============================================================================
  // Fingerprint Matching
  // ============================================================================

  async matchAudioFingerprint(fingerprint: {
    hash: string;
    duration: number;
    sample_rate: number;
    peak_count: number;
  }): Promise<{ matches: Array<{ item_id: string; score: number; title: string }> }> {
    return this.request('POST', '/fingerprint/audio', fingerprint);
  }

  async matchVisualSignature(signature: {
    hash: string;
    width: number;
    height: number;
  }): Promise<{ matches: Array<{ item_id: string; score: number; title: string }> }> {
    return this.request('POST', '/fingerprint/visual', signature);
  }

  // ============================================================================
  // Health check
  // ============================================================================

  async ping(): Promise<boolean> {
    try {
      await fetch(`${this.baseUrl.replace('/api', '')}/health`);
      return true;
    } catch {
      return false;
    }
  }
}

// Singleton instance
export const apiClient = new ApiClient();
