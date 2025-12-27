/**
 * Visibility Tracker
 * Tracks when page is visible vs hidden (tab switches, minimized, etc.)
 */

import type { VisibilityStats } from '../../core/types';

export class VisibilityTracker {
  private visibleTime = 0;
  private hiddenTime = 0;
  private lastStateChange = Date.now();
  private isVisible = !document.hidden;
  private boundHandler: EventListener;
  private active = false;

  constructor() {
    this.boundHandler = this.handleVisibilityChange.bind(this);
  }

  init(): void {
    if (this.active) return;
    this.active = true;
    this.lastStateChange = Date.now();
    this.isVisible = !document.hidden;
    document.addEventListener('visibilitychange', this.boundHandler);
  }

  destroy(): void {
    this.updateTimers();
    this.active = false;
    document.removeEventListener('visibilitychange', this.boundHandler);
  }

  reset(): void {
    this.visibleTime = 0;
    this.hiddenTime = 0;
    this.lastStateChange = Date.now();
    this.isVisible = !document.hidden;
  }

  private handleVisibilityChange(): void {
    this.updateTimers();
    this.isVisible = !document.hidden;
    this.lastStateChange = Date.now();
  }

  private updateTimers(): void {
    const elapsed = Date.now() - this.lastStateChange;
    if (this.isVisible) {
      this.visibleTime += elapsed;
    } else {
      this.hiddenTime += elapsed;
    }
  }

  getStats(): VisibilityStats {
    // Update timers before returning stats
    const now = Date.now();
    const elapsed = now - this.lastStateChange;

    let visibleMs = this.visibleTime;
    let hiddenMs = this.hiddenTime;

    // Add current period
    if (this.isVisible) {
      visibleMs += elapsed;
    } else {
      hiddenMs += elapsed;
    }

    const total = visibleMs + hiddenMs;
    const visibilityRatio = total > 0 ? visibleMs / total : 1;

    return {
      visibleMs,
      hiddenMs,
      visibilityRatio: Math.round(visibilityRatio * 1000) / 1000,
    };
  }

  isPageVisible(): boolean {
    return this.isVisible;
  }

  getVisibleTime(): number {
    const elapsed = Date.now() - this.lastStateChange;
    return this.visibleTime + (this.isVisible ? elapsed : 0);
  }
}
