/**
 * Settings Component
 * Privacy controls and extension configuration
 */

import React, { useState, useEffect } from 'react';
import { browserAdapter } from '../adapters/browser';
import { privacyManager } from '../core/privacy';
import { storage, STORAGE_KEYS } from '../core/storage';
import type { CaptureConfig, PrivacyConfig } from '../core/types';
import { DEFAULT_CAPTURE_CONFIG, DEFAULT_PRIVACY_CONFIG } from '../core/config';

export function Settings() {
  const [captureConfig, setCaptureConfig] = useState<CaptureConfig>(
    DEFAULT_CAPTURE_CONFIG
  );
  const [privacyConfig, setPrivacyConfig] = useState<PrivacyConfig>(
    DEFAULT_PRIVACY_CONFIG
  );
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<{ synced: number; pending: number } | null>(
    null
  );

  useEffect(() => {
    loadSettings();
    loadStatus();
  }, []);

  async function loadSettings() {
    try {
      const capture = await storage.get<CaptureConfig>(STORAGE_KEYS.CAPTURE_CONFIG);
      const privacy = await storage.get<PrivacyConfig>(STORAGE_KEYS.PRIVACY_CONFIG);

      if (capture) setCaptureConfig(capture);
      if (privacy) setPrivacyConfig(privacy);
    } catch (e) {
      console.error('Failed to load settings:', e);
    } finally {
      setLoading(false);
    }
  }

  async function loadStatus() {
    try {
      const response = await browserAdapter.runtime.sendMessage<
        { type: string },
        { success: boolean; data?: { queueLength: number } }
      >({ type: 'GET_STATE' });

      if (response.success && response.data) {
        setStatus({
          synced: 0, // TODO: Track synced count
          pending: response.data.queueLength,
        });
      }
    } catch (e) {
      console.error('Failed to load status:', e);
    }
  }

  async function saveSettings() {
    setSaving(true);
    try {
      await storage.set(STORAGE_KEYS.CAPTURE_CONFIG, captureConfig);
      await storage.set(STORAGE_KEYS.PRIVACY_CONFIG, privacyConfig);

      // Notify background
      await browserAdapter.runtime.sendMessage({
        type: 'UPDATE_CONFIG',
        payload: captureConfig,
      });
    } catch (e) {
      console.error('Failed to save settings:', e);
    } finally {
      setSaving(false);
    }
  }

  async function handleSync() {
    try {
      await browserAdapter.runtime.sendMessage({ type: 'SYNC_NOW' });
      await loadStatus();
    } catch (e) {
      console.error('Sync failed:', e);
    }
  }

  if (loading) {
    return (
      <div className="settings loading">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="settings">
      {/* Status */}
      <div className="settings-section">
        <h3>Status</h3>
        {status && (
          <div style={{ fontSize: '13px', color: '#666' }}>
            <p>Pending events: {status.pending}</p>
            <button
              onClick={handleSync}
              style={{
                marginTop: '8px',
                padding: '6px 12px',
                fontSize: '12px',
              }}
            >
              Sync Now
            </button>
          </div>
        )}
      </div>

      {/* Capture Settings */}
      <div className="settings-section">
        <h3>Capture</h3>

        <div className="setting-row">
          <label>Enable capture</label>
          <label className="toggle">
            <input
              type="checkbox"
              checked={captureConfig.enabled}
              onChange={(e) =>
                setCaptureConfig({ ...captureConfig, enabled: e.target.checked })
              }
            />
            <span className="toggle-slider" />
          </label>
        </div>

        <div className="setting-row">
          <label>Platform-specific (Layer 1)</label>
          <label className="toggle">
            <input
              type="checkbox"
              checked={captureConfig.layer1Enabled}
              onChange={(e) =>
                setCaptureConfig({
                  ...captureConfig,
                  layer1Enabled: e.target.checked,
                })
              }
            />
            <span className="toggle-slider" />
          </label>
        </div>

        <div className="setting-row">
          <label>Generic signals (Layer 2)</label>
          <label className="toggle">
            <input
              type="checkbox"
              checked={captureConfig.layer2Enabled}
              onChange={(e) =>
                setCaptureConfig({
                  ...captureConfig,
                  layer2Enabled: e.target.checked,
                })
              }
            />
            <span className="toggle-slider" />
          </label>
        </div>

        <div className="setting-row">
          <label>Audio/visual capture (Layer 3)</label>
          <label className="toggle">
            <input
              type="checkbox"
              checked={captureConfig.layer3Enabled}
              onChange={(e) =>
                setCaptureConfig({
                  ...captureConfig,
                  layer3Enabled: e.target.checked,
                })
              }
            />
            <span className="toggle-slider" />
          </label>
        </div>
      </div>

      {/* Privacy Settings */}
      <div className="settings-section">
        <h3>Privacy</h3>

        <div className="setting-row">
          <label>Known platforms only</label>
          <label className="toggle">
            <input
              type="checkbox"
              checked={privacyConfig.captureOnlyKnownPlatforms}
              onChange={(e) =>
                setPrivacyConfig({
                  ...privacyConfig,
                  captureOnlyKnownPlatforms: e.target.checked,
                })
              }
            />
            <span className="toggle-slider" />
          </label>
        </div>

        <div className="setting-row">
          <label>Local processing only</label>
          <label className="toggle">
            <input
              type="checkbox"
              checked={privacyConfig.localProcessingOnly}
              onChange={(e) =>
                setPrivacyConfig({
                  ...privacyConfig,
                  localProcessingOnly: e.target.checked,
                })
              }
            />
            <span className="toggle-slider" />
          </label>
        </div>
      </div>

      {/* Save button */}
      <button
        className="submit-button"
        onClick={saveSettings}
        disabled={saving}
        style={{ marginTop: '16px' }}
      >
        {saving ? 'Saving...' : 'Save Settings'}
      </button>
    </div>
  );
}
