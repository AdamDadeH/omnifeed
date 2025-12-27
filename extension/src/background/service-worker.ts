/**
 * Background Service Worker
 * Handles extension lifecycle, message routing, and periodic tasks
 */

import { browserAdapter } from '../adapters/browser';
import { sessionManager } from '../core/session';
import { eventQueue } from '../core/queue';
import { privacyManager } from '../core/privacy';
import { apiClient } from '../core/api';
import type { Message, MessageResponse } from '../core/types';

console.log('[OmniFeed] Service worker starting...');

/**
 * Initialize background services
 */
async function init(): Promise<void> {
  try {
    await privacyManager.init();
    await sessionManager.init();
    await eventQueue.init();

    console.log('[OmniFeed] Background services initialized');
  } catch (e) {
    console.error('[OmniFeed] Background init failed:', e);
  }
}

// Initialize on startup
init();

/**
 * Message listener for popup and content scripts
 */
browserAdapter.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const msg = message as Message;

  handleMessage(msg, sender)
    .then(sendResponse)
    .catch((e) => {
      console.error('[OmniFeed] Message handler error:', e);
      sendResponse({ success: false, error: String(e) });
    });

  return true; // Keep channel open for async response
});

/**
 * Handle incoming messages
 */
async function handleMessage(
  message: Message,
  _sender: chrome.runtime.MessageSender
): Promise<MessageResponse> {
  switch (message.type) {
    case 'SYNC_NOW':
      return handleSyncNow();

    case 'UPDATE_CONFIG':
      return handleUpdateConfig(message.payload as any);

    case 'GET_STATE':
      return handleGetState();

    default:
      return { success: false, error: 'Unknown message type' };
  }
}

/**
 * Force sync event queue
 */
async function handleSyncNow(): Promise<MessageResponse> {
  try {
    const result = await eventQueue.sync();
    return {
      success: true,
      data: result,
    };
  } catch (e) {
    return { success: false, error: String(e) };
  }
}

/**
 * Update capture configuration
 */
async function handleUpdateConfig(
  config: Record<string, unknown>
): Promise<MessageResponse> {
  try {
    await sessionManager.updateConfig(config as any);
    return { success: true };
  } catch (e) {
    return { success: false, error: String(e) };
  }
}

/**
 * Get current background state
 */
async function handleGetState(): Promise<MessageResponse> {
  const isOnline = await apiClient.ping();

  return {
    success: true,
    data: {
      sessionInitialized: sessionManager.isInitialized(),
      queueLength: eventQueue.getQueueLength(),
      isSyncing: eventQueue.isSyncing(),
      apiOnline: isOnline,
      hasConsent: privacyManager.hasConsent(),
    },
  };
}

/**
 * Handle extension install/update
 */
chrome.runtime.onInstalled?.addListener((details) => {
  console.log('[OmniFeed] Extension installed/updated:', details.reason);

  if (details.reason === 'install') {
    // Open welcome/consent page on first install
    chrome.tabs.create({
      url: chrome.runtime.getURL('popup/index.html') + '?welcome=true',
    });
  }
});

/**
 * Handle browser action click (if no popup)
 */
chrome.action?.onClicked?.addListener(async (tab) => {
  if (!tab.id) return;

  try {
    // Try to get content info from active tab
    const response = await browserAdapter.tabs.sendMessage(tab.id, {
      type: 'GET_CONTENT_INFO',
    });
    console.log('[OmniFeed] Content info:', response);
  } catch (e) {
    console.log('[OmniFeed] No content script on this page');
  }
});

/**
 * Periodic alarm for queue sync
 */
chrome.alarms?.create?.('sync', { periodInMinutes: 1 });

chrome.alarms?.onAlarm?.addListener(async (alarm) => {
  if (alarm.name === 'sync') {
    await eventQueue.sync();
  }
});
