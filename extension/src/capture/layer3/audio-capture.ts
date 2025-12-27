/**
 * Audio Capture Service
 * Captures audio from tabs for fingerprinting
 *
 * Chrome: Uses tabCapture API with offscreen document
 * Firefox: Uses browser.tabs.captureTab
 */

import { browserAdapter } from '../../adapters/browser';
import type { AudioFingerprint } from '../../core/types';

export class AudioCaptureService {
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private bufferDuration: number;
  private isCapturing = false;
  private stream: MediaStream | null = null;

  constructor(bufferDuration = 10000) {
    // Buffer duration in milliseconds
    this.bufferDuration = bufferDuration;
  }

  async startCapture(): Promise<boolean> {
    if (this.isCapturing) return true;

    try {
      if (browserAdapter.isChrome()) {
        return await this.startChromeCapture();
      } else {
        return await this.startFirefoxCapture();
      }
    } catch (e) {
      console.error('Audio capture failed:', e);
      return false;
    }
  }

  private async startChromeCapture(): Promise<boolean> {
    // Chrome requires offscreen document for audio processing
    // For now, we'll use a simpler approach with the Web Audio API
    // This captures audio from video/audio elements on the page

    const media = document.querySelector('video, audio') as HTMLMediaElement;
    if (!media) {
      console.warn('No media element found for audio capture');
      return false;
    }

    try {
      // Create audio context and capture from media element
      const audioContext = new AudioContext();
      const source = audioContext.createMediaElementSource(media);

      // Create destination for recording
      const dest = audioContext.createMediaStreamDestination();
      source.connect(dest);
      source.connect(audioContext.destination); // Also output to speakers

      this.stream = dest.stream;
      return this.startRecording(this.stream);
    } catch (e) {
      console.error('Chrome audio capture error:', e);
      return false;
    }
  }

  private async startFirefoxCapture(): Promise<boolean> {
    // Firefox can capture tab audio more directly
    // For now, use the same media element approach
    return this.startChromeCapture();
  }

  private startRecording(stream: MediaStream): boolean {
    try {
      // Check supported MIME types
      const mimeType = this.getSupportedMimeType();

      this.mediaRecorder = new MediaRecorder(stream, {
        mimeType,
        audioBitsPerSecond: 128000,
      });

      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          this.audioChunks.push(event.data);
          this.trimBuffer();
        }
      };

      this.mediaRecorder.onerror = (e) => {
        console.error('MediaRecorder error:', e);
        this.stopCapture();
      };

      // Record in 1-second chunks
      this.mediaRecorder.start(1000);
      this.isCapturing = true;

      return true;
    } catch (e) {
      console.error('Failed to start recording:', e);
      return false;
    }
  }

  private getSupportedMimeType(): string {
    const types = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/mp4',
    ];

    for (const type of types) {
      if (MediaRecorder.isTypeSupported(type)) {
        return type;
      }
    }

    return 'audio/webm';
  }

  private trimBuffer(): void {
    // Keep approximately bufferDuration of audio
    // Assuming 1-second chunks
    const maxChunks = Math.ceil(this.bufferDuration / 1000);
    while (this.audioChunks.length > maxChunks) {
      this.audioChunks.shift();
    }
  }

  async getAudioBuffer(): Promise<Blob | null> {
    if (this.audioChunks.length === 0) return null;

    const mimeType = this.mediaRecorder?.mimeType || 'audio/webm';
    return new Blob(this.audioChunks, { type: mimeType });
  }

  async stopCapture(): Promise<void> {
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop();
    }

    if (this.stream) {
      for (const track of this.stream.getTracks()) {
        track.stop();
      }
    }

    this.mediaRecorder = null;
    this.stream = null;
    this.audioChunks = [];
    this.isCapturing = false;
  }

  isActive(): boolean {
    return this.isCapturing;
  }

  getBufferLength(): number {
    return this.audioChunks.length;
  }
}

/**
 * Audio Fingerprint Generator
 * Generates fingerprints from audio data using spectral analysis
 */
export class AudioFingerprintGenerator {
  private fftSize = 4096;
  private hopSize = 2048;

  /**
   * Generate fingerprint from audio blob
   */
  async generateFingerprint(audioBlob: Blob): Promise<AudioFingerprint | null> {
    try {
      const arrayBuffer = await audioBlob.arrayBuffer();
      const audioContext = new OfflineAudioContext(1, 44100 * 10, 44100);

      const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);

      // Extract spectral peaks
      const peaks = this.extractSpectralPeaks(audioBuffer);

      // Create constellation and generate hash
      const hash = this.createFingerprintHash(peaks);

      return {
        hash,
        duration: audioBuffer.duration,
        sampleRate: audioBuffer.sampleRate,
        peakCount: peaks.length,
        timestamp: Date.now(),
      };
    } catch (e) {
      console.error('Fingerprint generation failed:', e);
      return null;
    }
  }

  private extractSpectralPeaks(buffer: AudioBuffer): SpectralPeak[] {
    const data = buffer.getChannelData(0);
    const peaks: SpectralPeak[] = [];

    // Simple peak extraction using energy
    // In production, would use proper FFT and peak finding
    const windowSize = this.fftSize;
    const hopSize = this.hopSize;

    for (let i = 0; i < data.length - windowSize; i += hopSize) {
      const frame = data.slice(i, i + windowSize);
      const time = i / buffer.sampleRate;

      // Calculate energy in different frequency bands
      const bands = this.calculateBandEnergies(frame);

      // Find peaks in each band
      for (let band = 0; band < bands.length; band++) {
        if (bands[band] > 0.1) {
          // Threshold
          peaks.push({
            time,
            frequency: this.bandToFrequency(band),
            magnitude: bands[band],
          });
        }
      }
    }

    // Limit to strongest peaks
    peaks.sort((a, b) => b.magnitude - a.magnitude);
    return peaks.slice(0, 500);
  }

  private calculateBandEnergies(frame: Float32Array): number[] {
    // Simplified band energy calculation
    // In production, would use proper FFT
    const numBands = 32;
    const bands = new Array(numBands).fill(0);
    const samplesPerBand = Math.floor(frame.length / numBands);

    for (let band = 0; band < numBands; band++) {
      const start = band * samplesPerBand;
      const end = start + samplesPerBand;
      let energy = 0;

      for (let i = start; i < end; i++) {
        energy += frame[i] * frame[i];
      }

      bands[band] = Math.sqrt(energy / samplesPerBand);
    }

    return bands;
  }

  private bandToFrequency(band: number): number {
    // Map band index to approximate frequency
    const minFreq = 300;
    const maxFreq = 5000;
    const numBands = 32;

    return minFreq + (band / numBands) * (maxFreq - minFreq);
  }

  private createFingerprintHash(peaks: SpectralPeak[]): string {
    // Create constellation pairs and hash them
    // This is a simplified version of the Shazam algorithm

    const pairs: string[] = [];
    const targetZone = 5; // Number of forward peaks to pair with

    // Sort by time
    peaks.sort((a, b) => a.time - b.time);

    for (let i = 0; i < peaks.length - targetZone; i++) {
      const anchor = peaks[i];

      for (let j = 1; j <= targetZone && i + j < peaks.length; j++) {
        const target = peaks[i + j];
        const timeDelta = target.time - anchor.time;

        // Only pair if within reasonable time window
        if (timeDelta > 0 && timeDelta < 2) {
          // Quantize and create pair identifier
          const f1 = Math.round(anchor.frequency / 10);
          const f2 = Math.round(target.frequency / 10);
          const dt = Math.round(timeDelta * 100);

          pairs.push(`${f1}:${f2}:${dt}`);
        }
      }
    }

    // Hash the pairs
    return this.hashString(pairs.join('|'));
  }

  private hashString(str: string): string {
    // Simple hash function
    // In production, would use a proper hash like SHA-256
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = (hash << 5) - hash + char;
      hash = hash & hash; // Convert to 32-bit integer
    }

    return Math.abs(hash).toString(36).padStart(16, '0').slice(0, 16);
  }
}

interface SpectralPeak {
  time: number;
  frequency: number;
  magnitude: number;
}
