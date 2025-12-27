/**
 * Event queue with offline support and batching
 */

import { storage, STORAGE_KEYS } from './storage';
import { apiClient } from './api';
import { EXTENSION_VERSION, QUEUE_CONFIG } from './config';
import type { CapturedEvent, QueuedEvent, ExtensionEventRequest } from './types';

// Generate unique ID
function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

export class EventQueue {
  private queue: QueuedEvent[] = [];
  private syncInProgress = false;
  private syncIntervalId: number | null = null;
  private sessionId: string;

  constructor() {
    this.sessionId = generateId();
  }

  async init(): Promise<void> {
    // Load persisted queue
    const stored = await storage.get<QueuedEvent[]>(STORAGE_KEYS.EVENT_QUEUE);
    if (stored) {
      this.queue = stored;
    }

    // Set up periodic sync
    this.startPeriodicSync();

    // Sync on network reconnection
    if (typeof window !== 'undefined') {
      window.addEventListener('online', () => this.sync());
    }
  }

  private startPeriodicSync(): void {
    if (this.syncIntervalId) return;

    this.syncIntervalId = setInterval(
      () => this.sync(),
      QUEUE_CONFIG.batchSize * 100 // ~5 seconds
    ) as unknown as number;
  }

  stopPeriodicSync(): void {
    if (this.syncIntervalId) {
      clearInterval(this.syncIntervalId);
      this.syncIntervalId = null;
    }
  }

  async enqueue(event: CapturedEvent): Promise<void> {
    const queuedEvent: QueuedEvent = {
      id: generateId(),
      event,
      timestamp: Date.now(),
      retries: 0,
    };

    this.queue.push(queuedEvent);

    // Persist immediately
    await this.persist();

    // Trim if too large
    if (this.queue.length > QUEUE_CONFIG.maxQueueSize) {
      this.queue = this.queue.slice(-QUEUE_CONFIG.maxQueueSize);
      await this.persist();
    }

    // Try immediate sync if online
    if (this.isOnline() && !this.syncInProgress) {
      // Don't await - fire and forget
      this.sync().catch(console.error);
    }
  }

  async sync(): Promise<SyncResult> {
    if (this.syncInProgress || this.queue.length === 0 || !this.isOnline()) {
      return { synced: 0, failed: 0 };
    }

    this.syncInProgress = true;

    try {
      // Take batch from queue
      const batch = this.queue.slice(0, QUEUE_CONFIG.batchSize);

      // Convert to API format
      const events: ExtensionEventRequest[] = batch.map((q) => ({
        event_type: q.event.type,
        timestamp: q.event.timestamp,
        url: q.event.url,
        item_id: q.event.itemId,
        payload: q.event.payload,
      }));

      // Send to server
      const response = await apiClient.submitEvents({
        events,
        session_id: this.sessionId,
        client_version: EXTENSION_VERSION,
      });

      // Remove successfully synced events
      if (response.accepted > 0) {
        this.queue = this.queue.slice(response.accepted);
        await this.persist();
      }

      // Handle rejected events
      if (response.rejected > 0) {
        await this.handleRejected(batch, response.accepted, response.rejected);
      }

      return {
        synced: response.accepted,
        failed: response.rejected,
        createdItems: response.created_items,
      };
    } catch (e) {
      console.error('Sync failed:', e);
      return { synced: 0, failed: this.queue.length };
    } finally {
      this.syncInProgress = false;
    }
  }

  private async handleRejected(
    batch: QueuedEvent[],
    acceptedCount: number,
    rejectedCount: number
  ): Promise<void> {
    const rejectedStart = acceptedCount;
    const rejectedEnd = rejectedStart + rejectedCount;

    for (let i = rejectedStart; i < rejectedEnd && i < batch.length; i++) {
      const queueIndex = i - acceptedCount; // Index in remaining queue
      if (this.queue[queueIndex]) {
        this.queue[queueIndex].retries++;

        // Drop after max retries
        if (this.queue[queueIndex].retries > QUEUE_CONFIG.maxRetries) {
          this.queue.splice(queueIndex, 1);
        }
      }
    }

    await this.persist();
  }

  private async persist(): Promise<void> {
    await storage.set(STORAGE_KEYS.EVENT_QUEUE, this.queue);
  }

  private isOnline(): boolean {
    return typeof navigator === 'undefined' || navigator.onLine;
  }

  getQueueLength(): number {
    return this.queue.length;
  }

  isSyncing(): boolean {
    return this.syncInProgress;
  }

  async clear(): Promise<void> {
    this.queue = [];
    await this.persist();
  }
}

export interface SyncResult {
  synced: number;
  failed: number;
  createdItems?: string[];
}

// Singleton instance
export const eventQueue = new EventQueue();
