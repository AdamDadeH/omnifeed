/**
 * Interaction Tracker
 * Tracks user interactions (clicks, keystrokes, mouse movements, touches)
 */

import type { InteractionStats } from '../../core/types';

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

export class InteractionTracker {
  private clicks = 0;
  private keystrokes = 0;
  private mouseMovements = 0;
  private touches = 0;
  private lastInteractionTime = 0;
  private active = false;

  private handlers: Map<string, EventListener> = new Map();

  init(): void {
    if (this.active) return;
    this.active = true;

    // Click handler
    const clickHandler = () => {
      this.clicks++;
      this.lastInteractionTime = Date.now();
    };
    this.handlers.set('click', clickHandler);
    document.addEventListener('click', clickHandler, { passive: true });

    // Keydown handler
    const keydownHandler = () => {
      this.keystrokes++;
      this.lastInteractionTime = Date.now();
    };
    this.handlers.set('keydown', keydownHandler);
    document.addEventListener('keydown', keydownHandler, { passive: true });

    // Mouse move handler (throttled)
    const mousemoveHandler = throttle(() => {
      this.mouseMovements++;
      this.lastInteractionTime = Date.now();
    }, 200);
    this.handlers.set('mousemove', mousemoveHandler);
    document.addEventListener('mousemove', mousemoveHandler, { passive: true });

    // Touch handler
    const touchHandler = () => {
      this.touches++;
      this.lastInteractionTime = Date.now();
    };
    this.handlers.set('touchstart', touchHandler);
    document.addEventListener('touchstart', touchHandler, { passive: true });
  }

  destroy(): void {
    this.active = false;
    for (const [event, handler] of this.handlers.entries()) {
      document.removeEventListener(event, handler);
    }
    this.handlers.clear();
  }

  reset(): void {
    this.clicks = 0;
    this.keystrokes = 0;
    this.mouseMovements = 0;
    this.touches = 0;
    this.lastInteractionTime = 0;
  }

  getStats(): InteractionStats {
    return {
      clicks: this.clicks,
      keystrokes: this.keystrokes,
      mouseMovements: this.mouseMovements,
      touches: this.touches,
      interactionScore: this.calculateScore(),
    };
  }

  private calculateScore(): number {
    // Weighted interaction score
    // Clicks and keystrokes are stronger signals than mouse movements
    return (
      this.clicks * 3 +
      this.keystrokes * 2 +
      this.mouseMovements * 0.1 +
      this.touches * 2
    );
  }

  getLastInteractionTime(): number {
    return this.lastInteractionTime;
  }

  getTimeSinceLastInteraction(): number {
    if (this.lastInteractionTime === 0) return 0;
    return Date.now() - this.lastInteractionTime;
  }

  hasInteracted(): boolean {
    return (
      this.clicks > 0 ||
      this.keystrokes > 0 ||
      this.mouseMovements > 0 ||
      this.touches > 0
    );
  }
}
