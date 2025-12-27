/**
 * Layer 3: Audio/Visual Fallback Capture
 * Provides resilient content identification when platform adapters fail
 */

import { AudioCaptureService, AudioFingerprintGenerator } from './audio-capture';
import { VisualCaptureService } from './visual-capture';
import type { AudioFingerprint, VisualSignature, Layer3Signals } from '../../core/types';

export class Layer3Tracker {
  readonly audio: AudioCaptureService;
  readonly visual: VisualCaptureService;
  readonly fingerprint: AudioFingerprintGenerator;

  private active = false;
  private lastAudioFingerprint: AudioFingerprint | null = null;
  private lastVisualSignature: VisualSignature | null = null;

  constructor(audioBufferSeconds = 10) {
    this.audio = new AudioCaptureService(audioBufferSeconds * 1000);
    this.visual = new VisualCaptureService();
    this.fingerprint = new AudioFingerprintGenerator();
  }

  async init(): Promise<void> {
    if (this.active) return;
    this.active = true;

    // Start audio capture if media is present
    const hasMedia = document.querySelector('video, audio') !== null;
    if (hasMedia) {
      await this.audio.startCapture();
    }
  }

  async destroy(): Promise<void> {
    this.active = false;
    await this.audio.stopCapture();
    this.lastAudioFingerprint = null;
    this.lastVisualSignature = null;
  }

  /**
   * Capture and generate fingerprints for current content
   */
  async captureSignals(): Promise<Layer3Signals> {
    const [audioFingerprint, visualCapture] = await Promise.all([
      this.captureAudioFingerprint(),
      this.captureVisualSignature(),
    ]);

    return {
      audioFingerprint,
      visualCapture,
    };
  }

  /**
   * Capture audio fingerprint from current buffer
   */
  async captureAudioFingerprint(): Promise<AudioFingerprint | null> {
    if (!this.audio.isActive()) {
      return null;
    }

    const audioBuffer = await this.audio.getAudioBuffer();
    if (!audioBuffer) {
      return null;
    }

    const fingerprint = await this.fingerprint.generateFingerprint(audioBuffer);
    if (fingerprint) {
      this.lastAudioFingerprint = fingerprint;
    }

    return fingerprint;
  }

  /**
   * Capture visual signature from current content
   */
  async captureVisualSignature(): Promise<VisualSignature | null> {
    const signature = await this.visual.captureVisual();
    if (signature) {
      this.lastVisualSignature = signature;
    }
    return signature;
  }

  /**
   * Get most recent fingerprints without re-capturing
   */
  getLastSignals(): Layer3Signals {
    return {
      audioFingerprint: this.lastAudioFingerprint,
      visualCapture: this.lastVisualSignature,
    };
  }

  isActive(): boolean {
    return this.active;
  }

  hasAudioCapture(): boolean {
    return this.audio.isActive();
  }

  /**
   * Compare current content with a known fingerprint
   */
  async matchAudio(knownHash: string): Promise<number> {
    const current = await this.captureAudioFingerprint();
    if (!current) return 0;

    // Simple string comparison for now
    // In production, would use LSH or similar for approximate matching
    return current.hash === knownHash ? 1 : 0;
  }

  /**
   * Compare current visual with a known signature
   */
  async matchVisual(knownHash: string): Promise<number> {
    const current = await this.captureVisualSignature();
    if (!current) return 0;

    return VisualCaptureService.compareSimilarity(current.hash, knownHash);
  }
}

// Re-export components
export { AudioCaptureService, AudioFingerprintGenerator } from './audio-capture';
export { VisualCaptureService } from './visual-capture';
