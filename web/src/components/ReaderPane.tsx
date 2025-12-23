import { useEffect, useRef, useState, useCallback } from 'react';
import type { FeedItem, FeedbackDimension, ExplicitFeedback, ExplicitFeedbackPayload } from '../api/types';
import { formatDistanceToNow } from '../utils/time';
import { getFeedbackDimensions, submitExplicitFeedback, getItemExplicitFeedback } from '../api/client';
import { getRendererForItem } from './renderers';

interface Props {
  item: FeedItem;
  onClose: () => void;
  onFeedback: (feedback: ReadingFeedback) => void;
}

export interface ReadingFeedback {
  item_id: string;
  time_spent_ms: number;
  max_scroll_pct: number;
  completed: boolean;
  scroll_events: number;
}

export function ReaderPane({ item, onClose, onFeedback }: Props) {
  const startTimeRef = useRef<number>(Date.now());
  const maxScrollRef = useRef<number>(0);
  const scrollEventsRef = useRef<number>(0);
  const [scrollPct, setScrollPct] = useState(0);
  const [showFeedbackPrompt, setShowFeedbackPrompt] = useState(false);
  const [dimensions, setDimensions] = useState<FeedbackDimension[]>([]);

  // Feedback form state
  const [rewardScore, setRewardScore] = useState(2.5);
  const [selections, setSelections] = useState<Record<string, string[]>>({});
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [existingFeedback, setExistingFeedback] = useState<ExplicitFeedback | null>(null);

  // Time tracking
  const [timeSpent, setTimeSpent] = useState(0);

  // Get the appropriate renderer for this item
  const rendererInfo = getRendererForItem(item);
  const hasInlineRenderer = rendererInfo !== null;

  // Load dimensions and existing feedback on mount
  useEffect(() => {
    getFeedbackDimensions().then(setDimensions).catch(console.error);

    // Load existing feedback for this item
    getItemExplicitFeedback(item.id).then(fb => {
      if (fb) {
        setExistingFeedback(fb);
        setRewardScore(fb.reward_score);
        setSelections(fb.selections || {});
        setNotes(fb.notes || '');
      }
    }).catch(console.error);
  }, [item.id]);

  // Time spent counter
  useEffect(() => {
    const interval = setInterval(() => {
      setTimeSpent(Date.now() - startTimeRef.current);
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  // Handle scroll progress from renderer
  const handleScrollProgress = useCallback((pct: number) => {
    setScrollPct(pct);
    scrollEventsRef.current += 1;
    if (pct > maxScrollRef.current) {
      maxScrollRef.current = pct;
    }
  }, []);

  // Handle close - show feedback prompt first
  const handleCloseClick = useCallback(() => {
    setShowFeedbackPrompt(true);
  }, []);

  // Actually close and send feedback
  const finalizeClose = useCallback(() => {
    const feedback: ReadingFeedback = {
      item_id: item.id,
      time_spent_ms: Date.now() - startTimeRef.current,
      max_scroll_pct: maxScrollRef.current,
      completed: maxScrollRef.current >= 90,
      scroll_events: scrollEventsRef.current,
    };
    onFeedback(feedback);
    onClose();
  }, [item.id, onClose, onFeedback]);

  // Skip feedback and close
  const handleSkipFeedback = useCallback(() => {
    finalizeClose();
  }, [finalizeClose]);

  // Submit feedback and close
  const handleSubmitFeedback = useCallback(async () => {
    setSubmitting(true);
    try {
      const payload: ExplicitFeedbackPayload = {
        item_id: item.id,
        reward_score: rewardScore,
        selections,
        notes: notes || undefined,
        completion_pct: maxScrollRef.current,
        is_checkpoint: false,
      };
      await submitExplicitFeedback(payload);
      finalizeClose();
    } catch (err) {
      console.error('Failed to submit feedback:', err);
      setSubmitting(false);
    }
  }, [item.id, rewardScore, selections, notes, finalizeClose]);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (showFeedbackPrompt) {
          handleSkipFeedback();
        } else {
          handleCloseClick();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleCloseClick, handleSkipFeedback, showFeedbackPrompt]);

  // Toggle option selection
  const toggleOption = (dimensionId: string, optionId: string, allowMultiple: boolean) => {
    setSelections(prev => {
      const current = prev[dimensionId] || [];
      if (allowMultiple) {
        if (current.includes(optionId)) {
          return { ...prev, [dimensionId]: current.filter(id => id !== optionId) };
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
  };

  // Format time spent
  const formatTimeSpent = (ms: number) => {
    const seconds = Math.floor(ms / 1000);
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds}s`;
  };

  // Feedback prompt modal
  if (showFeedbackPrompt) {
    return (
      <div className="fixed inset-0 bg-neutral-950 z-50 flex items-center justify-center">
        <div className="bg-neutral-900 rounded-lg w-full max-w-lg p-6">
          <h2 className="text-lg font-medium mb-4">
            {existingFeedback ? 'Update your rating' : 'Rate this content'}
          </h2>
          {existingFeedback && (
            <p className="text-sm text-neutral-500 mb-4">
              Previously rated {existingFeedback.reward_score.toFixed(1)}/5 on {new Date(existingFeedback.timestamp).toLocaleDateString()}
            </p>
          )}

          {/* Reward score slider */}
          <div className="mb-6">
            <label className="block text-sm text-neutral-400 mb-2">
              Reward per unit time: {rewardScore.toFixed(1)} / 5
            </label>
            <input
              type="range"
              min="0"
              max="5"
              step="0.1"
              value={rewardScore}
              onChange={(e) => setRewardScore(parseFloat(e.target.value))}
              className="w-full h-2 bg-neutral-700 rounded-lg appearance-none cursor-pointer"
            />
            <div className="flex justify-between text-xs text-neutral-500 mt-1">
              <span>Not worth it</span>
              <span>Highly valuable</span>
            </div>
          </div>

          {/* Dimensions */}
          {dimensions.map(dim => (
            <div key={dim.id} className="mb-4">
              <label className="block text-sm text-neutral-400 mb-2">
                {dim.description || dim.name}
                {dim.allow_multiple && <span className="text-neutral-500 ml-1">(select multiple)</span>}
              </label>
              <div className="flex flex-wrap gap-2">
                {dim.options.map(opt => {
                  const isSelected = (selections[dim.id] || []).includes(opt.id);
                  return (
                    <button
                      key={opt.id}
                      onClick={() => toggleOption(dim.id, opt.id, dim.allow_multiple)}
                      className={`px-3 py-1.5 text-sm rounded transition-colors ${
                        isSelected
                          ? 'bg-blue-600 text-white'
                          : 'bg-neutral-800 text-neutral-300 hover:bg-neutral-700'
                      }`}
                      title={opt.description || undefined}
                    >
                      {opt.label}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}

          {/* Notes */}
          <div className="mb-6">
            <label className="block text-sm text-neutral-400 mb-2">
              Notes (optional)
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Any thoughts on this content..."
              className="w-full px-3 py-2 bg-neutral-800 border border-neutral-700 rounded text-sm resize-none h-20"
            />
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3">
            <button
              onClick={handleSkipFeedback}
              className="px-4 py-2 text-sm text-neutral-400 hover:text-neutral-200 transition-colors"
              disabled={submitting}
            >
              {existingFeedback ? 'Keep existing' : 'Skip rating'}
            </button>
            <button
              onClick={handleSubmitFeedback}
              disabled={submitting}
              className="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-500 rounded transition-colors disabled:opacity-50"
            >
              {submitting ? 'Saving...' : existingFeedback ? 'Update' : 'Save'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Render the content using the appropriate renderer
  const ContentRenderer = rendererInfo?.component;

  return (
    <div className="fixed inset-0 bg-neutral-950 z-50 flex flex-col">
      {/* Header */}
      <header className="flex-shrink-0 px-4 py-3 border-b border-neutral-800 flex items-center justify-between bg-neutral-900">
        <div className="flex-1 min-w-0 mr-4">
          <h1 className="text-lg font-medium truncate">{item.title}</h1>
          <div className="text-sm text-neutral-500">
            {item.source_name} · {item.creator_name} · {formatDistanceToNow(item.published_at)}
            {rendererInfo && (
              <span className="ml-2 px-1.5 py-0.5 bg-neutral-800 rounded text-xs">
                {rendererInfo.name}
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* Reading stats */}
          <div className="text-sm text-neutral-500 flex items-center gap-3">
            <span>{formatTimeSpent(timeSpent)}</span>
            <span>{Math.round(scrollPct)}%</span>
          </div>

          {/* Show existing rating if present */}
          {existingFeedback && (
            <span className="text-sm text-yellow-500" title="Previously rated">
              Rated {existingFeedback.reward_score.toFixed(1)}/5
            </span>
          )}

          {/* Open external - only show if no inline renderer or as secondary option */}
          {!hasInlineRenderer && (
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 rounded transition-colors"
            >
              Open original
            </a>
          )}

          {/* Back - close without recording anything */}
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm text-neutral-500 hover:text-neutral-300 transition-colors"
            title="Go back without recording engagement"
          >
            Back
          </button>

          {/* Rate - records engagement and prompts for rating */}
          <button
            onClick={handleCloseClick}
            className="px-3 py-1.5 text-sm bg-neutral-800 hover:bg-neutral-700 rounded transition-colors"
            title="Record engagement and rate this content"
          >
            {existingFeedback ? 'Update Rating' : 'Rate'} (Esc)
          </button>
        </div>
      </header>

      {/* Content area */}
      <div className="flex-1 overflow-hidden">
        {ContentRenderer ? (
          <ContentRenderer item={item} onScrollProgress={handleScrollProgress} />
        ) : (
          // Fallback when no renderer available
          <div className="h-full flex items-center justify-center">
            <div className="text-center py-12 text-neutral-500">
              <p className="mb-4">No inline viewer available for this content type.</p>
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-white transition-colors"
              >
                Open original
              </a>
            </div>
          </div>
        )}
      </div>

      {/* Progress bar */}
      <div className="flex-shrink-0 h-1 bg-neutral-800">
        <div
          className={`h-full transition-all duration-150 ${scrollPct >= 90 ? 'bg-green-500' : 'bg-blue-500'}`}
          style={{ width: `${scrollPct}%` }}
        />
      </div>
    </div>
  );
}
