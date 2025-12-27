/**
 * Browser adapter abstraction
 * Provides a unified interface for Chrome (MV3) and Firefox (MV2/3) APIs
 */

export interface BrowserAdapter {
  // Identity
  isChrome(): boolean;
  isFirefox(): boolean;
  getBrowserName(): string;

  // Storage
  storage: {
    get<T>(key: string): Promise<T | null>;
    set<T>(key: string, value: T): Promise<void>;
    remove(key: string): Promise<void>;
    clear(): Promise<void>;
  };

  // Tabs
  tabs: {
    query(options: TabQueryOptions): Promise<Tab[]>;
    sendMessage<T, R>(tabId: number, message: T): Promise<R>;
    captureVisibleTab(windowId?: number, options?: CaptureOptions): Promise<string>;
    getCurrent(): Promise<Tab | null>;
  };

  // Runtime
  runtime: {
    sendMessage<T, R>(message: T): Promise<R>;
    onMessage: {
      addListener(callback: MessageListener): void;
      removeListener(callback: MessageListener): void;
    };
    getURL(path: string): string;
  };

  // Tab capture (for audio)
  tabCapture?: {
    getMediaStreamId(options: MediaStreamOptions): Promise<string>;
  };

  // Offscreen (Chrome MV3 only)
  offscreen?: {
    createDocument(options: OffscreenOptions): Promise<void>;
    closeDocument(): Promise<void>;
    hasDocument(): Promise<boolean>;
  };
}

// Types for browser APIs
export interface Tab {
  id?: number;
  url?: string;
  title?: string;
  active: boolean;
  windowId: number;
}

export interface TabQueryOptions {
  active?: boolean;
  currentWindow?: boolean;
  url?: string | string[];
}

export interface CaptureOptions {
  format?: 'jpeg' | 'png';
  quality?: number;
}

export interface MediaStreamOptions {
  targetTabId?: number;
}

export interface OffscreenOptions {
  url: string;
  reasons: string[];
  justification: string;
}

export type MessageListener = (
  message: unknown,
  sender: MessageSender,
  sendResponse: (response: unknown) => void
) => boolean | void | Promise<unknown>;

export interface MessageSender {
  tab?: Tab;
  frameId?: number;
  id?: string;
  url?: string;
}

// Detect browser environment
function detectBrowser(): 'chrome' | 'firefox' | 'unknown' {
  if (typeof chrome !== 'undefined' && chrome.runtime?.id) {
    // Check if it's actually Firefox using Chrome API polyfill
    if (typeof browser !== 'undefined' && browser.runtime?.id) {
      return 'firefox';
    }
    return 'chrome';
  }
  if (typeof browser !== 'undefined' && browser.runtime?.id) {
    return 'firefox';
  }
  return 'unknown';
}

const browserType = detectBrowser();

// Chrome adapter implementation
const chromeAdapter: BrowserAdapter = {
  isChrome: () => true,
  isFirefox: () => false,
  getBrowserName: () => 'chrome',

  storage: {
    async get<T>(key: string): Promise<T | null> {
      return new Promise((resolve) => {
        chrome.storage.local.get([key], (result) => {
          resolve(result[key] ?? null);
        });
      });
    },
    async set<T>(key: string, value: T): Promise<void> {
      return new Promise((resolve) => {
        chrome.storage.local.set({ [key]: value }, resolve);
      });
    },
    async remove(key: string): Promise<void> {
      return new Promise((resolve) => {
        chrome.storage.local.remove(key, resolve);
      });
    },
    async clear(): Promise<void> {
      return new Promise((resolve) => {
        chrome.storage.local.clear(resolve);
      });
    },
  },

  tabs: {
    async query(options: TabQueryOptions): Promise<Tab[]> {
      return new Promise((resolve) => {
        chrome.tabs.query(options, resolve);
      });
    },
    async sendMessage<T, R>(tabId: number, message: T): Promise<R> {
      return new Promise((resolve, reject) => {
        chrome.tabs.sendMessage(tabId, message, (response) => {
          if (chrome.runtime.lastError) {
            reject(new Error(chrome.runtime.lastError.message));
          } else {
            resolve(response);
          }
        });
      });
    },
    async captureVisibleTab(windowId?: number, options?: CaptureOptions): Promise<string> {
      return new Promise((resolve, reject) => {
        chrome.tabs.captureVisibleTab(windowId ?? null!, options ?? {}, (dataUrl) => {
          if (chrome.runtime.lastError) {
            reject(new Error(chrome.runtime.lastError.message));
          } else {
            resolve(dataUrl);
          }
        });
      });
    },
    async getCurrent(): Promise<Tab | null> {
      const [tab] = await chromeAdapter.tabs.query({ active: true, currentWindow: true });
      return tab ?? null;
    },
  },

  runtime: {
    async sendMessage<T, R>(message: T): Promise<R> {
      return new Promise((resolve, reject) => {
        chrome.runtime.sendMessage(message, (response) => {
          if (chrome.runtime.lastError) {
            reject(new Error(chrome.runtime.lastError.message));
          } else {
            resolve(response);
          }
        });
      });
    },
    onMessage: {
      addListener(callback: MessageListener) {
        chrome.runtime.onMessage.addListener(callback);
      },
      removeListener(callback: MessageListener) {
        chrome.runtime.onMessage.removeListener(callback);
      },
    },
    getURL(path: string): string {
      return chrome.runtime.getURL(path);
    },
  },

  tabCapture: {
    async getMediaStreamId(options: MediaStreamOptions): Promise<string> {
      return new Promise((resolve, reject) => {
        chrome.tabCapture.getMediaStreamId(options, (streamId) => {
          if (chrome.runtime.lastError) {
            reject(new Error(chrome.runtime.lastError.message));
          } else {
            resolve(streamId);
          }
        });
      });
    },
  },

  offscreen: {
    async createDocument(options: OffscreenOptions): Promise<void> {
      try {
        await (chrome as any).offscreen.createDocument({
          url: options.url,
          reasons: options.reasons,
          justification: options.justification,
        });
      } catch (e: any) {
        // Document may already exist
        if (!e.message?.includes('already exists')) {
          throw e;
        }
      }
    },
    async closeDocument(): Promise<void> {
      try {
        await (chrome as any).offscreen.closeDocument();
      } catch {
        // Document may not exist
      }
    },
    async hasDocument(): Promise<boolean> {
      try {
        const contexts = await (chrome as any).runtime.getContexts({
          contextTypes: ['OFFSCREEN_DOCUMENT'],
        });
        return contexts.length > 0;
      } catch {
        return false;
      }
    },
  },
};

// Firefox adapter implementation
const firefoxAdapter: BrowserAdapter = {
  isChrome: () => false,
  isFirefox: () => true,
  getBrowserName: () => 'firefox',

  storage: {
    async get<T>(key: string): Promise<T | null> {
      const result = await browser.storage.local.get(key);
      return result[key] ?? null;
    },
    async set<T>(key: string, value: T): Promise<void> {
      await browser.storage.local.set({ [key]: value });
    },
    async remove(key: string): Promise<void> {
      await browser.storage.local.remove(key);
    },
    async clear(): Promise<void> {
      await browser.storage.local.clear();
    },
  },

  tabs: {
    async query(options: TabQueryOptions): Promise<Tab[]> {
      return browser.tabs.query(options);
    },
    async sendMessage<T, R>(tabId: number, message: T): Promise<R> {
      return browser.tabs.sendMessage(tabId, message);
    },
    async captureVisibleTab(windowId?: number, options?: CaptureOptions): Promise<string> {
      return browser.tabs.captureVisibleTab(windowId, options);
    },
    async getCurrent(): Promise<Tab | null> {
      const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
      return tab ?? null;
    },
  },

  runtime: {
    async sendMessage<T, R>(message: T): Promise<R> {
      return browser.runtime.sendMessage(message);
    },
    onMessage: {
      addListener(callback: MessageListener) {
        browser.runtime.onMessage.addListener(callback);
      },
      removeListener(callback: MessageListener) {
        browser.runtime.onMessage.removeListener(callback);
      },
    },
    getURL(path: string): string {
      return browser.runtime.getURL(path);
    },
  },

  // Firefox has different tab capture API
  // We'll implement this differently in the audio capture module
};

// Export the appropriate adapter based on detected browser
export const browserAdapter: BrowserAdapter =
  browserType === 'firefox' ? firefoxAdapter : chromeAdapter;

// Also export for explicit access
export { chromeAdapter, firefoxAdapter };

// Utility to get platform info
export function getPlatformInfo(): { browser: string; os: string } {
  const browser = browserAdapter.getBrowserName();
  const platform = navigator.platform.toLowerCase();

  let os = 'unknown';
  if (platform.includes('mac')) os = 'macos';
  else if (platform.includes('win')) os = 'windows';
  else if (platform.includes('linux')) os = 'linux';

  return { browser, os };
}
