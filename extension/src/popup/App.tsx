/**
 * Popup App Component
 */

import React, { useState, useEffect } from 'react';
import { RatingForm } from './RatingForm';
import { QuickCapture } from './QuickCapture';
import { Settings } from './Settings';
import { browserAdapter } from '../adapters/browser';
import type { ContentInfo } from '../core/types';

type View = 'rating' | 'capture' | 'settings';

export function App() {
  const [view, setView] = useState<View>('rating');
  const [content, setContent] = useState<ContentInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadContent();
  }, []);

  async function loadContent() {
    try {
      setLoading(true);
      setError(null);

      // Get active tab in current window (not the popup itself)
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab?.id) {
        setError('No active tab found');
        setLoading(false);
        return;
      }

      console.log('[OmniFeed Popup] Querying tab:', tab.id, tab.url);

      // Request content info from content script
      const response = await chrome.tabs.sendMessage(tab.id, { type: 'GET_CONTENT_INFO' });

      console.log('[OmniFeed Popup] Response:', response);

      if (response?.success && response?.data) {
        setContent(response.data);
      } else {
        setError(response?.error || 'Could not detect content');
      }
    } catch (e: any) {
      console.error('[OmniFeed Popup] Error:', e);
      setError(`Extension not active: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleRating(rating: {
    rewardScore: number;
    selections: Record<string, string[]>;
    notes?: string;
  }) {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) return;

    await chrome.tabs.sendMessage(tab.id, {
      type: 'SUBMIT_RATING',
      payload: rating,
    });

    window.close();
  }

  async function handleCapture(data: {
    url: string;
    title: string;
    creatorName?: string;
    contentType: string;
  }) {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) return;

    // Trigger capture
    await chrome.tabs.sendMessage(tab.id, {
      type: 'CAPTURE_NOW',
    });

    window.close();
  }

  if (loading) {
    return (
      <div className="popup-container loading">
        <div className="spinner" />
        <p>Loading...</p>
      </div>
    );
  }

  return (
    <div className="popup-container">
      <nav className="popup-nav">
        <button
          className={view === 'rating' ? 'active' : ''}
          onClick={() => setView('rating')}
        >
          Rate
        </button>
        <button
          className={view === 'capture' ? 'active' : ''}
          onClick={() => setView('capture')}
        >
          Capture
        </button>
        <button
          className={view === 'settings' ? 'active' : ''}
          onClick={() => setView('settings')}
        >
          Settings
        </button>
      </nav>

      <main className="popup-content">
        {view === 'rating' && (
          <RatingForm
            content={content}
            error={error}
            onSubmit={handleRating}
            onRetry={loadContent}
          />
        )}
        {view === 'capture' && (
          <QuickCapture content={content} onCapture={handleCapture} />
        )}
        {view === 'settings' && <Settings />}
      </main>
    </div>
  );
}
