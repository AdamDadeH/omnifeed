/**
 * Layer 2 Signal Tracker
 * Combines all generic web signals into a unified interface
 */

import { ScrollTracker } from './scroll';
import { VisibilityTracker } from './visibility';
import { InteractionTracker } from './interaction';
import type { Layer2Signals } from '../../core/types';

export class Layer2Tracker {
  readonly scroll: ScrollTracker;
  readonly visibility: VisibilityTracker;
  readonly interaction: InteractionTracker;

  private startTime: number = 0;
  private active = false;

  constructor() {
    this.scroll = new ScrollTracker();
    this.visibility = new VisibilityTracker();
    this.interaction = new InteractionTracker();
  }

  init(): void {
    if (this.active) return;
    this.active = true;
    this.startTime = Date.now();

    this.scroll.init();
    this.visibility.init();
    this.interaction.init();
  }

  destroy(): void {
    this.active = false;
    this.scroll.destroy();
    this.visibility.destroy();
    this.interaction.destroy();
  }

  reset(): void {
    this.startTime = Date.now();
    this.scroll.reset();
    this.visibility.reset();
    this.interaction.reset();
  }

  getStats(): Layer2Signals {
    return {
      scroll: this.scroll.getStats(),
      visibility: this.visibility.getStats(),
      interaction: this.interaction.getStats(),
      timeOnPage: this.getTimeOnPage(),
    };
  }

  getTimeOnPage(): number {
    if (this.startTime === 0) return 0;
    return Date.now() - this.startTime;
  }

  getVisibleTime(): number {
    return this.visibility.getVisibleTime();
  }

  isActive(): boolean {
    return this.active;
  }

  /**
   * Calculate an engagement score based on all signals
   */
  getEngagementScore(): number {
    const stats = this.getStats();

    // Weights for different signals
    const weights = {
      scrollDepth: 0.3,
      timeOnPage: 0.3,
      visibility: 0.2,
      interaction: 0.2,
    };

    // Normalize scroll (0-100 -> 0-1)
    const scrollScore = stats.scroll.maxScrollPct / 100;

    // Normalize time (cap at 10 minutes for full score)
    const timeScore = Math.min(stats.timeOnPage / (10 * 60 * 1000), 1);

    // Visibility ratio is already 0-1
    const visibilityScore = stats.visibility.visibilityRatio;

    // Normalize interaction (cap at score of 100)
    const interactionScore = Math.min(stats.interaction.interactionScore / 100, 1);

    return (
      scrollScore * weights.scrollDepth +
      timeScore * weights.timeOnPage +
      visibilityScore * weights.visibility +
      interactionScore * weights.interaction
    );
  }

  /**
   * Check if user has meaningfully engaged with the page
   */
  hasEngaged(): boolean {
    const stats = this.getStats();

    // Consider engaged if:
    // - Scrolled more than 10%
    // - Or spent more than 30 seconds visibly
    // - Or had significant interactions
    return (
      stats.scroll.maxScrollPct > 10 ||
      stats.visibility.visibleMs > 30000 ||
      stats.interaction.interactionScore > 10
    );
  }
}

// Re-export individual trackers
export { ScrollTracker } from './scroll';
export { VisibilityTracker } from './visibility';
export { InteractionTracker } from './interaction';
