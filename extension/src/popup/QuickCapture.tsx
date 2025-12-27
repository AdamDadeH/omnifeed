/**
 * Quick Capture Component
 * For manually capturing content when auto-detection fails
 */

import React, { useState } from 'react';
import type { ContentInfo } from '../core/types';

interface Props {
  content: ContentInfo | null;
  onCapture: (data: {
    url: string;
    title: string;
    creatorName?: string;
    contentType: string;
  }) => Promise<void>;
}

export function QuickCapture({ content, onCapture }: Props) {
  const [title, setTitle] = useState(content?.title || document.title);
  const [creator, setCreator] = useState(content?.creatorName || '');
  const [contentType, setContentType] = useState<string>(
    content?.contentType || 'other'
  );
  const [capturing, setCapturing] = useState(false);

  async function handleCapture() {
    setCapturing(true);
    try {
      await onCapture({
        url: window.location.href,
        title,
        creatorName: creator || undefined,
        contentType,
      });
    } catch (e) {
      console.error('Capture failed:', e);
      setCapturing(false);
    }
  }

  return (
    <div className="quick-capture">
      <h3 style={{ marginBottom: '8px' }}>Capture Content</h3>

      <p
        style={{
          fontSize: '12px',
          color: '#666',
          marginBottom: '16px',
        }}
      >
        Manually capture this content for your feed. Useful when the extension
        doesn't automatically detect the content.
      </p>

      <div className="form-field">
        <label>Title</label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Content title"
        />
      </div>

      <div className="form-field">
        <label>Creator (optional)</label>
        <input
          type="text"
          value={creator}
          onChange={(e) => setCreator(e.target.value)}
          placeholder="Creator name"
        />
      </div>

      <div className="form-field">
        <label>Content Type</label>
        <select
          value={contentType}
          onChange={(e) => setContentType(e.target.value)}
        >
          <option value="video">Video</option>
          <option value="audio">Audio</option>
          <option value="article">Article</option>
          <option value="other">Other</option>
        </select>
      </div>

      <button
        className="submit-button"
        onClick={handleCapture}
        disabled={capturing || !title}
      >
        {capturing ? 'Capturing...' : 'Capture & Add to Feed'}
      </button>
    </div>
  );
}
