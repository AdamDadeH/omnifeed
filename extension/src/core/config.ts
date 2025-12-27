/**
 * Extension configuration and constants
 */

import type { CaptureConfig, PrivacyConfig } from './types';

export const EXTENSION_VERSION = '0.1.0';

// API endpoint - configurable for development
export const API_ENDPOINT =
  process.env.NODE_ENV === 'development'
    ? 'http://localhost:8000/api'
    : 'http://localhost:8000/api'; // Update for production

// Default capture configuration
export const DEFAULT_CAPTURE_CONFIG: CaptureConfig = {
  enabled: true,
  layer1Enabled: true,
  layer2Enabled: true,
  layer3Enabled: true,
  audioBufferSeconds: 10,
  visualCaptureInterval: 30, // seconds
  batchIntervalMs: 5000, // 5 seconds
};

// Default privacy configuration
export const DEFAULT_PRIVACY_CONFIG: PrivacyConfig = {
  captureOnlyKnownPlatforms: true,
  excludedDomains: [],
  localProcessingOnly: false,
  sendRawMedia: false,
  retentionDays: 30,
};

// Supported platforms with their domains
export const SUPPORTED_PLATFORMS = {
  youtube: ['youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'],
  netflix: ['netflix.com', 'www.netflix.com'],
  spotify: ['open.spotify.com'],
  medium: ['medium.com', '*.medium.com'],
  substack: ['*.substack.com', 'substack.com'],
} as const;

// Flatten to get all supported domains
export const ALL_SUPPORTED_DOMAINS = Object.values(SUPPORTED_PLATFORMS).flat();

// Feedback dimensions (matches backend)
export const FEEDBACK_DIMENSIONS = {
  reward_type: {
    id: 'reward_type',
    name: 'Content Value',
    allowMultiple: true,
    options: [
      { id: 'entertainment', label: 'Entertainment', emoji: '🎬' },
      { id: 'curiosity', label: 'Curiosity', emoji: '🧠' },
      { id: 'foundational', label: 'Foundational', emoji: '📚' },
      { id: 'expertise', label: 'Expertise', emoji: '🎯' },
    ],
  },
  emotional: {
    id: 'emotional',
    name: 'Feeling',
    allowMultiple: true,
    options: [
      { id: 'nostalgic', label: 'Nostalgic', emoji: '💭' },
      { id: 'inspiring', label: 'Inspiring', emoji: '✨' },
      { id: 'relaxing', label: 'Relaxing', emoji: '😌' },
    ],
  },
  replayability: {
    id: 'replayability',
    name: 'Replayability',
    allowMultiple: false,
    options: [
      { id: 'one_and_done', label: 'One and done', emoji: '✓' },
      { id: 'might_revisit', label: 'Might revisit', emoji: '🔄' },
      { id: 'will_revisit', label: 'Will revisit', emoji: '⭐' },
      { id: 'reference', label: 'Reference', emoji: '📑' },
    ],
  },
} as const;

// Event types
export const EVENT_TYPES = {
  // Layer 1: Platform specific
  PLAY: 'play',
  PAUSE: 'pause',
  SEEK: 'seek',
  COMPLETE: 'complete',
  LIKE: 'like',
  DISLIKE: 'dislike',

  // Layer 2: Generic
  PAGE_VIEW: 'page_view',
  PAGE_LEAVE: 'page_leave',
  SCROLL: 'scroll',
  VISIBILITY_CHANGE: 'visibility_change',

  // Explicit
  RATING: 'rating',
  CAPTURE: 'capture',
} as const;

// Queue settings
export const QUEUE_CONFIG = {
  maxQueueSize: 1000,
  maxRetries: 3,
  retryDelayMs: 30000,
  batchSize: 50,
} as const;

// Session settings
export const SESSION_CONFIG = {
  maxAgeMs: 7 * 24 * 60 * 60 * 1000, // 7 days
} as const;
