/**
 * Visual Capture Service
 * Captures video frames and viewport screenshots for fingerprinting
 */

import type { VisualSignature } from '../../core/types';

export class VisualCaptureService {
  private hashSize = 8; // 8x8 = 64-bit hash

  /**
   * Capture current visual content
   */
  async captureVisual(): Promise<VisualSignature | null> {
    // Try video frame capture first (for media content)
    const videoCapture = await this.captureVideoFrame();
    if (videoCapture) return videoCapture;

    // Fall back to viewport capture
    return this.captureViewport();
  }

  /**
   * Capture frame from video element
   */
  async captureVideoFrame(): Promise<VisualSignature | null> {
    const video = document.querySelector('video') as HTMLVideoElement;
    if (!video || video.paused || video.videoWidth === 0) {
      return null;
    }

    try {
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;

      const ctx = canvas.getContext('2d');
      if (!ctx) return null;

      ctx.drawImage(video, 0, 0);

      // Generate perceptual hash
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const hash = this.generatePerceptualHash(imageData);

      // Generate low-quality thumbnail for debugging/display
      const thumbnailCanvas = document.createElement('canvas');
      thumbnailCanvas.width = 160;
      thumbnailCanvas.height = 90;
      const thumbCtx = thumbnailCanvas.getContext('2d');
      if (thumbCtx) {
        thumbCtx.drawImage(video, 0, 0, 160, 90);
      }

      return {
        type: 'video_frame',
        timestamp: Date.now(),
        width: video.videoWidth,
        height: video.videoHeight,
        hash,
        thumbnail: thumbnailCanvas.toDataURL('image/jpeg', 0.3),
      };
    } catch (e) {
      console.error('Video frame capture failed:', e);
      return null;
    }
  }

  /**
   * Capture viewport screenshot
   */
  async captureViewport(): Promise<VisualSignature | null> {
    try {
      // Use html2canvas-like approach with canvas
      // For a simpler implementation, we'll capture the main content area

      const mainContent =
        document.querySelector('main, article, #content, .content') ||
        document.body;

      // Create a canvas from the content
      const canvas = await this.elementToCanvas(mainContent as HTMLElement);
      if (!canvas) return null;

      const ctx = canvas.getContext('2d');
      if (!ctx) return null;

      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const hash = this.generatePerceptualHash(imageData);

      return {
        type: 'viewport',
        timestamp: Date.now(),
        width: canvas.width,
        height: canvas.height,
        hash,
        thumbnail: canvas.toDataURL('image/jpeg', 0.3),
      };
    } catch (e) {
      console.error('Viewport capture failed:', e);
      return null;
    }
  }

  /**
   * Generate perceptual hash (pHash) from image data
   *
   * Algorithm:
   * 1. Resize to small size (8x8)
   * 2. Convert to grayscale
   * 3. Compute mean
   * 4. Generate hash: 1 if pixel > mean, 0 otherwise
   */
  generatePerceptualHash(imageData: ImageData): string {
    // Step 1: Resize to hashSize x hashSize
    const resized = this.resizeImageData(
      imageData,
      this.hashSize,
      this.hashSize
    );

    // Step 2: Convert to grayscale
    const grayscale = this.toGrayscale(resized);

    // Step 3: Compute mean
    const mean =
      grayscale.reduce((sum, val) => sum + val, 0) / grayscale.length;

    // Step 4: Generate hash
    let hash = '';
    for (const pixel of grayscale) {
      hash += pixel >= mean ? '1' : '0';
    }

    // Convert binary to hex
    return this.binaryToHex(hash);
  }

  /**
   * Resize image data using bilinear interpolation
   */
  private resizeImageData(
    imageData: ImageData,
    width: number,
    height: number
  ): ImageData {
    const canvas = document.createElement('canvas');
    canvas.width = imageData.width;
    canvas.height = imageData.height;

    const ctx = canvas.getContext('2d')!;
    ctx.putImageData(imageData, 0, 0);

    // Create destination canvas
    const destCanvas = document.createElement('canvas');
    destCanvas.width = width;
    destCanvas.height = height;

    const destCtx = destCanvas.getContext('2d')!;

    // Use smooth scaling
    destCtx.imageSmoothingEnabled = true;
    destCtx.imageSmoothingQuality = 'high';
    destCtx.drawImage(canvas, 0, 0, width, height);

    return destCtx.getImageData(0, 0, width, height);
  }

  /**
   * Convert image data to grayscale values
   */
  private toGrayscale(imageData: ImageData): number[] {
    const data = imageData.data;
    const grayscale: number[] = [];

    for (let i = 0; i < data.length; i += 4) {
      // Weighted grayscale conversion (ITU-R BT.709)
      const gray = data[i] * 0.2126 + data[i + 1] * 0.7152 + data[i + 2] * 0.0722;
      grayscale.push(gray);
    }

    return grayscale;
  }

  /**
   * Convert binary string to hexadecimal
   */
  private binaryToHex(binary: string): string {
    let hex = '';
    for (let i = 0; i < binary.length; i += 4) {
      const chunk = binary.slice(i, i + 4).padEnd(4, '0');
      hex += parseInt(chunk, 2).toString(16);
    }
    return hex;
  }

  /**
   * Calculate Hamming distance between two hashes
   */
  static hammingDistance(hash1: string, hash2: string): number {
    // Convert hex to binary
    const bin1 = VisualCaptureService.hexToBinary(hash1);
    const bin2 = VisualCaptureService.hexToBinary(hash2);

    let distance = 0;
    const maxLen = Math.max(bin1.length, bin2.length);

    for (let i = 0; i < maxLen; i++) {
      if (bin1[i] !== bin2[i]) {
        distance++;
      }
    }

    return distance;
  }

  private static hexToBinary(hex: string): string {
    return hex
      .split('')
      .map((h) => parseInt(h, 16).toString(2).padStart(4, '0'))
      .join('');
  }

  /**
   * Compare two hashes and return similarity score (0-1)
   */
  static compareSimilarity(hash1: string, hash2: string): number {
    const distance = VisualCaptureService.hammingDistance(hash1, hash2);
    const maxDistance = hash1.length * 4; // 4 bits per hex char
    return 1 - distance / maxDistance;
  }

  /**
   * Convert DOM element to canvas
   */
  private async elementToCanvas(
    element: HTMLElement
  ): Promise<HTMLCanvasElement | null> {
    try {
      const rect = element.getBoundingClientRect();
      const width = Math.min(rect.width, 1280);
      const height = Math.min(rect.height, 720);

      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;

      const ctx = canvas.getContext('2d');
      if (!ctx) return null;

      // Simple approach: draw a representative color for the content
      // In production, would use html2canvas or similar
      ctx.fillStyle = this.getElementColor(element);
      ctx.fillRect(0, 0, width, height);

      // Draw visible images
      const images = element.querySelectorAll('img');
      for (const img of Array.from(images).slice(0, 5)) {
        try {
          if (img.complete && img.naturalWidth > 0) {
            const imgRect = img.getBoundingClientRect();
            const x = imgRect.left - rect.left;
            const y = imgRect.top - rect.top;
            ctx.drawImage(
              img,
              x,
              y,
              Math.min(imgRect.width, 200),
              Math.min(imgRect.height, 200)
            );
          }
        } catch {
          // Ignore cross-origin images
        }
      }

      return canvas;
    } catch (e) {
      console.error('Element to canvas failed:', e);
      return null;
    }
  }

  private getElementColor(element: HTMLElement): string {
    const style = window.getComputedStyle(element);
    return style.backgroundColor || '#ffffff';
  }
}
