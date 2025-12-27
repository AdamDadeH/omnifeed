/**
 * Content Script - Main Entry Point
 * Runs on matched pages to capture signals
 */

import { CaptureManager } from '../capture/manager';
import { sessionManager } from '../core/session';
import { eventQueue } from '../core/queue';
import { privacyManager } from '../core/privacy';
import { browserAdapter } from '../adapters/browser';
import { DEFAULT_CAPTURE_CONFIG } from '../core/config';
import type { Message, MessageResponse, ContentInfo } from '../core/types';

let captureManager: CaptureManager | null = null;
let initError: string | null = null;

/**
 * Initialize the content script
 */
async function init(): Promise<void> {
  console.log('[OmniFeed] Content script loading on:', window.location.href);

  // Setup message listener FIRST so popup can always communicate
  setupMessageListener();
  console.log('[OmniFeed] Message listener ready');

  try {
    // Initialize privacy manager first
    await privacyManager.init();

    // Auto-grant consent in development (TODO: proper consent flow)
    if (!privacyManager.hasConsent()) {
      console.log('[OmniFeed] Auto-granting consent for development');
      await privacyManager.recordConsent({
        implicitFeedback: true,
        explicitFeedback: true,
        audioCapture: true,
        visualCapture: true,
        sendToServer: true,
      });
    }

    // Initialize session
    await sessionManager.init();

    // Initialize event queue
    await eventQueue.init();

    // Get capture config
    const config = sessionManager.getConfig();

    // Create and initialize capture manager
    captureManager = new CaptureManager(config);
    await captureManager.init(window.location.href);

    console.log('[OmniFeed] Capture initialized for:', window.location.href);

    // Setup unload handler
    setupUnloadHandler();

    // Watch for SPA navigation
    setupNavigationObserver();
  } catch (e: any) {
    console.error('[OmniFeed] Init failed:', e);
    initError = e.message || String(e);
  }
}

/**
 * Setup message listener for popup/background communication
 */
function setupMessageListener(): void {
  browserAdapter.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    const msg = message as Message;

    handleMessage(msg)
      .then(sendResponse)
      .catch((e) => {
        sendResponse({ success: false, error: String(e) });
      });

    return true; // Keep channel open for async response
  });
}

/**
 * Handle incoming messages
 */
async function handleMessage(message: Message): Promise<MessageResponse> {
  switch (message.type) {
    case 'GET_CONTENT_INFO':
      return getContentInfo();

    case 'SUBMIT_RATING':
      return submitRating(message.payload as any);

    case 'CAPTURE_NOW':
      return captureNow();

    case 'GET_STATE':
      return getState();

    default:
      return { success: false, error: 'Unknown message type' };
  }
}

/**
 * Get current content info for popup
 */
async function getContentInfo(): Promise<MessageResponse<ContentInfo>> {
  // Return basic info even if capture manager isn't ready
  if (!captureManager) {
    if (initError) {
      return { success: false, error: `Init error: ${initError}` };
    }
    // Still initializing or failed - return basic page info
    return {
      success: true,
      data: {
        itemId: null,
        title: document.title,
        creatorName: null,
        platform: null,
        contentType: 'other',
        thumbnailUrl: null,
        url: window.location.href,
        confidence: 0.1,
      },
    };
  }

  const metadata = await captureManager.getContentInfo();
  const context = captureManager.getContext();

  return {
    success: true,
    data: {
      itemId: context?.contentId ?? null,
      title: metadata?.title ?? context?.title ?? document.title,
      creatorName: metadata?.creatorName ?? null,
      platform: context?.platform ?? null,
      contentType: metadata?.contentType ?? 'other',
      thumbnailUrl: metadata?.thumbnailUrl ?? null,
      url: window.location.href,
      confidence: metadata ? 0.5 : 0.2,
    },
  };
}

/**
 * Submit rating from popup
 */
async function submitRating(
  rating: { rewardScore: number; selections: Record<string, string[]>; notes?: string }
): Promise<MessageResponse> {
  if (!captureManager) {
    return { success: false, error: 'Capture manager not initialized' };
  }

  try {
    const context = captureManager.getContext();

    await eventQueue.enqueue({
      type: 'rating',
      timestamp: Date.now(),
      url: window.location.href,
      itemId: context?.contentId ?? null,
      payload: {
        rewardScore: rating.rewardScore,
        selections: rating.selections,
        notes: rating.notes,
      },
    });

    return { success: true };
  } catch (e) {
    return { success: false, error: String(e) };
  }
}

/**
 * Trigger manual capture
 */
async function captureNow(): Promise<MessageResponse> {
  if (!captureManager) {
    return { success: false, error: 'Capture manager not initialized' };
  }

  try {
    const signals = await captureManager.collectSignals();
    return {
      success: true,
      data: {
        hasAudio: !!signals.layer3?.audioFingerprint,
        hasVisual: !!signals.layer3?.visualCapture,
        confidence: signals.confidence,
      },
    };
  } catch (e) {
    return { success: false, error: String(e) };
  }
}

/**
 * Get current state for popup
 */
async function getState(): Promise<MessageResponse> {
  return {
    success: true,
    data: {
      initialized: captureManager?.isInitialized() ?? false,
      context: captureManager?.getContext() ?? null,
      config: captureManager?.getConfig() ?? DEFAULT_CAPTURE_CONFIG,
      queueLength: eventQueue.getQueueLength(),
    },
  };
}

/**
 * Handle page unload
 */
function setupUnloadHandler(): void {
  window.addEventListener('beforeunload', async () => {
    if (captureManager) {
      await captureManager.destroy();
    }
  });

  window.addEventListener('pagehide', async () => {
    if (captureManager) {
      await captureManager.destroy();
    }
  });
}

/**
 * Watch for SPA navigation
 */
function setupNavigationObserver(): void {
  let lastUrl = window.location.href;

  // Use History API interception
  const originalPushState = history.pushState;
  const originalReplaceState = history.replaceState;

  history.pushState = function (...args) {
    originalPushState.apply(this, args);
    handleNavigation();
  };

  history.replaceState = function (...args) {
    originalReplaceState.apply(this, args);
    handleNavigation();
  };

  window.addEventListener('popstate', () => {
    handleNavigation();
  });

  async function handleNavigation(): Promise<void> {
    const newUrl = window.location.href;
    if (newUrl !== lastUrl) {
      lastUrl = newUrl;

      // Destroy old manager
      if (captureManager) {
        await captureManager.destroy();
      }

      // Reinitialize for new page
      const config = sessionManager.getConfig();
      captureManager = new CaptureManager(config);
      await captureManager.init(newUrl);

      console.log('[OmniFeed] Reinitialized for:', newUrl);
    }
  }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
