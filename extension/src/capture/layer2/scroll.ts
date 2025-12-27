/**
 * Scroll Tracker
 * Tracks scroll depth and behavior on pages
 */

import type { ScrollStats } from '../../core/types';

// Throttle function
function throttle<T extends (...args: unknown[]) => void>(
  fn: T,
  delay: number
): T {
  let lastCall = 0;
  return ((...args: unknown[]) => {
    const now = Date.now();
    if (now - lastCall >= delay) {
      lastCall = now;
      fn(...args);
    }
  }) as T;
}

export class ScrollTracker {
  private maxScroll = 0;
  private scrollEvents = 0;
  private lastScrollTime = 0;
  private scrollVelocities: number[] = [];
  private lastScrollPct = 0;
  private boundHandler: EventListener;
  private active = false;

  constructor() {
    this.boundHandler = throttle(this.handleScroll.bind(this), 100);
  }

  init(): void {
    if (this.active) return;
    this.active = true;
    window.addEventListener('scroll', this.boundHandler, { passive: true });

    // Record initial scroll position
    this.maxScroll = this.getScrollPercentage();
    this.lastScrollPct = this.maxScroll;
  }

  destroy(): void {
    this.active = false;
    window.removeEventListener('scroll', this.boundHandler);
  }

  reset(): void {
    this.maxScroll = 0;
    this.scrollEvents = 0;
    this.lastScrollTime = 0;
    this.scrollVelocities = [];
    this.lastScrollPct = 0;
  }

  private handleScroll(): void {
    const scrollPct = this.getScrollPercentage();
    const now = Date.now();

    // Track max scroll
    if (scrollPct > this.maxScroll) {
      this.maxScroll = scrollPct;
    }

    // Track velocity
    if (this.lastScrollTime > 0) {
      const timeDelta = (now - this.lastScrollTime) / 1000; // seconds
      const scrollDelta = Math.abs(scrollPct - this.lastScrollPct);

      if (timeDelta > 0) {
        const velocity = scrollDelta / timeDelta; // % per second
        this.scrollVelocities.push(velocity);

        // Keep only last 100 velocities
        if (this.scrollVelocities.length > 100) {
          this.scrollVelocities.shift();
        }
      }
    }

    this.scrollEvents++;
    this.lastScrollTime = now;
    this.lastScrollPct = scrollPct;
  }

  private getScrollPercentage(): number {
    const docHeight = Math.max(
      document.body.scrollHeight,
      document.documentElement.scrollHeight,
      document.body.offsetHeight,
      document.documentElement.offsetHeight
    );
    const viewHeight = window.innerHeight;
    const scrollTop = window.scrollY || document.documentElement.scrollTop;

    const scrollable = docHeight - viewHeight;
    if (scrollable <= 0) return 100;

    return Math.min(100, (scrollTop / scrollable) * 100);
  }

  getStats(): ScrollStats {
    const avgVelocity =
      this.scrollVelocities.length > 0
        ? this.scrollVelocities.reduce((a, b) => a + b, 0) /
          this.scrollVelocities.length
        : 0;

    return {
      maxScrollPct: Math.round(this.maxScroll * 100) / 100,
      scrollEvents: this.scrollEvents,
      avgVelocity: Math.round(avgVelocity * 100) / 100,
    };
  }

  getCurrentScroll(): number {
    return this.getScrollPercentage();
  }
}
