// Core types for OmniFeed extension

// ============================================================================
// Extension State
// ============================================================================

export interface ExtensionState {
  auth: AuthState;
  capture: CaptureConfig;
  context: PageContext | null;
  queue: QueueState;
  privacy: PrivacyConfig;
}

export interface AuthState {
  apiEndpoint: string;
  sessionToken: string | null;
  userId: string | null;
}

export interface CaptureConfig {
  enabled: boolean;
  layer1Enabled: boolean;
  layer2Enabled: boolean;
  layer3Enabled: boolean;
  audioBufferSeconds: number;
  visualCaptureInterval: number;
  batchIntervalMs: number;
}

export interface QueueState {
  pendingEvents: number;
  lastSync: string | null;
  syncInProgress: boolean;
}

export interface PrivacyConfig {
  captureOnlyKnownPlatforms: boolean;
  excludedDomains: string[];
  localProcessingOnly: boolean;
  sendRawMedia: boolean;
  retentionDays: number;
}

// ============================================================================
// Page Context
// ============================================================================

export interface PageContext {
  url: string;
  domain: string;
  platform: string | null;
  contentId: string | null;
  title: string;
  startTime: number;
  sessionId: string;
  adapter: string;
  signals: CapturedSignals;
}

export interface CapturedSignals {
  platformEvents: PlatformEvent[];
  scrollDepth: number;
  timeVisible: number;
  interactionCount: number;
  audioFingerprints: AudioFingerprint[];
  visualSignatures: VisualSignature[];
}

// ============================================================================
// Content Metadata
// ============================================================================

export interface ContentMetadata {
  contentId: string;
  title: string;
  creatorName: string | null;
  creatorId: string | null;
  contentType: ContentType;
  durationSeconds: number | null;
  thumbnailUrl: string | null;
  canonicalUrl: string;
  platform?: string;
  metadata: Record<string, unknown>;
}

export type ContentType = 'video' | 'audio' | 'article' | 'image' | 'other';

// ============================================================================
// Platform Events (Layer 1)
// ============================================================================

export interface PlatformEvent {
  type: string;
  timestamp: number;
  platform: string;
  contentId: string;
  data: Record<string, unknown>;
}

export interface PlaybackState {
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  playbackRate: number;
  volume: number;
  isMuted: boolean;
}

// ============================================================================
// Layer 2 Signals
// ============================================================================

export interface ScrollStats {
  maxScrollPct: number;
  scrollEvents: number;
  avgVelocity: number;
}

export interface VisibilityStats {
  visibleMs: number;
  hiddenMs: number;
  visibilityRatio: number;
}

export interface InteractionStats {
  clicks: number;
  keystrokes: number;
  mouseMovements: number;
  touches: number;
  interactionScore: number;
}

export interface Layer2Signals {
  scroll: ScrollStats;
  visibility: VisibilityStats;
  interaction: InteractionStats;
  timeOnPage: number;
}

// ============================================================================
// Layer 3: Audio/Visual
// ============================================================================

export interface AudioFingerprint {
  hash: string;
  duration: number;
  sampleRate: number;
  peakCount: number;
  timestamp: number;
}

export interface VisualSignature {
  type: 'video_frame' | 'viewport';
  timestamp: number;
  width: number;
  height: number;
  hash: string;
  thumbnail?: string;
}

export interface Layer3Signals {
  audioFingerprint: AudioFingerprint | null;
  visualCapture: VisualSignature | null;
}

// ============================================================================
// Collected Signals (all layers)
// ============================================================================

export interface CollectedSignals {
  timestamp: number;
  url: string;
  layer1: Layer1Signals | null;
  layer2: Layer2Signals | null;
  layer3: Layer3Signals | null;
  metadata: ContentMetadata | null;
  confidence: number;
}

export interface Layer1Signals {
  platform: string;
  events: PlatformEvent[];
  playbackState: PlaybackState | null;
}

// ============================================================================
// Event Queue
// ============================================================================

export interface QueuedEvent {
  id: string;
  event: CapturedEvent;
  timestamp: number;
  retries: number;
}

export interface CapturedEvent {
  type: string;
  timestamp: number;
  url: string;
  itemId: string | null;
  payload: Record<string, unknown>;
}

// ============================================================================
// API Types
// ============================================================================

export interface ExtensionEventRequest {
  event_type: string;
  timestamp: number;
  url: string;
  item_id: string | null;
  payload: Record<string, unknown>;
}

export interface BatchEventRequest {
  events: ExtensionEventRequest[];
  session_id: string;
  client_version: string;
}

export interface BatchEventResponse {
  accepted: number;
  rejected: number;
  created_items: string[];
}

export interface ExtensionAuthRequest {
  extension_version: string;
  browser: string;
  platform: string;
}

export interface ExtensionAuthResponse {
  session_token: string;
  api_version: string;
  supported_platforms: string[];
  capture_config: CaptureConfig;
}

export interface MediaUploadRequest {
  media_type: 'audio' | 'visual';
  data: string; // base64
  context: Record<string, unknown>;
}

export interface MediaUploadResponse {
  fingerprint_id: string;
  identified_item_id: string | null;
  confidence: number;
  embedding_generated: boolean;
}

export interface ExtensionItemRequest {
  url: string;
  title: string;
  creator_name?: string;
  content_type: string;
  platform?: string;
  external_id?: string;
  metadata: Record<string, unknown>;
  thumbnail_url?: string;
  fingerprint_id?: string;
}

export interface ExtensionItemResponse {
  item_id: string;
  created: boolean;
  matched_by: string | null;
}

// ============================================================================
// Content Info (for popup)
// ============================================================================

export interface ContentInfo {
  itemId: string | null;
  title: string;
  creatorName: string | null;
  platform: string | null;
  contentType: ContentType;
  thumbnailUrl: string | null;
  url: string;
  confidence: number;
}

// ============================================================================
// Explicit Feedback
// ============================================================================

export interface ExplicitRating {
  itemId: string | null;
  rewardScore: number;
  selections: Record<string, string[]>;
  notes?: string;
  completionPct?: number;
}

// ============================================================================
// Messages between content script and background
// ============================================================================

export type MessageType =
  | 'GET_CONTENT_INFO'
  | 'SUBMIT_RATING'
  | 'CAPTURE_NOW'
  | 'GET_STATE'
  | 'UPDATE_CONFIG'
  | 'SYNC_NOW';

export interface Message<T = unknown> {
  type: MessageType;
  payload?: T;
}

export interface MessageResponse<T = unknown> {
  success: boolean;
  data?: T;
  error?: string;
}
