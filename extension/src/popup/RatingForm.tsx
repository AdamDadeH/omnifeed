/**
 * Rating Form Component
 */

import React, { useState } from 'react';
import { FEEDBACK_DIMENSIONS } from '../core/config';
import type { ContentInfo } from '../core/types';

interface Props {
  content: ContentInfo | null;
  error: string | null;
  onSubmit: (rating: {
    rewardScore: number;
    selections: Record<string, string[]>;
    notes?: string;
  }) => Promise<void>;
  onRetry: () => void;
}

export function RatingForm({ content, error, onSubmit, onRetry }: Props) {
  const [score, setScore] = useState(3);
  const [selections, setSelections] = useState<Record<string, string[]>>({});
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (error) {
    return (
      <div className="rating-form empty">
        <p className="error-message">{error}</p>
        <button onClick={onRetry} style={{ marginTop: '12px' }}>
          Retry
        </button>
      </div>
    );
  }

  if (!content) {
    return (
      <div className="rating-form empty">
        <p>No content detected on this page.</p>
        <p className="hint" style={{ fontSize: '12px', color: '#666', marginTop: '8px' }}>
          Navigate to a video, article, or audio content to rate it.
        </p>
      </div>
    );
  }

  async function handleSubmit() {
    setSubmitting(true);
    try {
      await onSubmit({
        rewardScore: score,
        selections,
        notes: notes || undefined,
      });
    } catch (e) {
      console.error('Rating failed:', e);
      setSubmitting(false);
    }
  }

  function toggleSelection(
    dimensionId: string,
    optionId: string,
    allowMultiple: boolean
  ) {
    setSelections((prev) => {
      const current = prev[dimensionId] || [];

      if (allowMultiple) {
        if (current.includes(optionId)) {
          return { ...prev, [dimensionId]: current.filter((id) => id !== optionId) };
        } else {
          return { ...prev, [dimensionId]: [...current, optionId] };
        }
      } else {
        if (current.includes(optionId)) {
          return { ...prev, [dimensionId]: [] };
        } else {
          return { ...prev, [dimensionId]: [optionId] };
        }
      }
    });
  }

  const dimensions = Object.values(FEEDBACK_DIMENSIONS);

  return (
    <div className="rating-form">
      {/* Content preview */}
      <div className="content-preview">
        {content.thumbnailUrl && (
          <img src={content.thumbnailUrl} alt="" className="thumbnail" />
        )}
        <div className="content-info">
          <h3 className="title">{content.title}</h3>
          {content.creatorName && <p className="creator">{content.creatorName}</p>}
          <p className="platform">{content.platform || 'Web'}</p>
        </div>
      </div>

      {/* Score slider */}
      <div className="score-section">
        <label>
          Rating: <span className="score-value">{score}/5</span>
        </label>
        <input
          type="range"
          min="0"
          max="5"
          step="0.5"
          value={score}
          onChange={(e) => setScore(parseFloat(e.target.value))}
          className="score-slider"
        />
        <div className="score-labels">
          <span>Not worth it</span>
          <span>Highly valuable</span>
        </div>
      </div>

      {/* Dimension selections */}
      {dimensions.map((dim) => (
        <div key={dim.id} className="dimension-section">
          <label>{dim.name}</label>
          <div className="option-grid">
            {dim.options.map((opt) => {
              const isSelected = (selections[dim.id] || []).includes(opt.id);
              return (
                <button
                  key={opt.id}
                  className={`option-button ${isSelected ? 'selected' : ''}`}
                  onClick={() => toggleSelection(dim.id, opt.id, dim.allowMultiple)}
                >
                  <span className="emoji">{opt.emoji}</span>
                  <span className="label">{opt.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      ))}

      {/* Notes */}
      <div className="form-field">
        <label>Notes (optional)</label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Any thoughts..."
          rows={2}
        />
      </div>

      {/* Submit */}
      <button
        className="submit-button"
        onClick={handleSubmit}
        disabled={submitting}
      >
        {submitting ? 'Saving...' : 'Save Rating'}
      </button>
    </div>
  );
}
