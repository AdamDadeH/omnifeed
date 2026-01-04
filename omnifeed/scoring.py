"""Source and content scoring.

Tracks quality scores for sources based on user feedback on their content.
Uses exponential moving average (EMA) to balance recent ratings with history.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omnifeed.store.base import Store

logger = logging.getLogger(__name__)

# EMA smoothing factor (higher = more weight to recent ratings)
EMA_ALPHA = 0.3

# Confidence thresholds
MIN_CONFIDENCE_SAMPLES = 3
MAX_CONFIDENCE_SAMPLES = 30


@dataclass
class SourceScore:
    """Score for a content source."""
    source_id: str
    value: float  # 0.0 - 5.0 scale
    confidence: float  # 0.0 - 1.0
    sample_size: int
    last_updated: datetime


def compute_confidence(sample_size: int) -> float:
    """Compute confidence score based on sample size."""
    if sample_size <= 0:
        return 0.0
    normalized = sample_size / MIN_CONFIDENCE_SAMPLES
    return min(1.0, 1 - math.exp(-0.7 * normalized))


class SourceScorer:
    """Manages source scores based on item feedback.

    Usage:
        scorer = SourceScorer(store)

        # When user rates an item
        scorer.record_item_rating(item.source_id, rating=4.5)

        # Get scored sources for explore
        sources = scorer.get_ranked_sources()
    """

    def __init__(self, store: Store):
        self.store = store
        self._cache: dict[str, SourceScore] = {}

    def record_item_rating(self, source_id: str, rating: float) -> SourceScore | None:
        """Record a rating and update the source's score.

        Args:
            source_id: The source that produced the rated content.
            rating: The rating value (0.0 - 5.0 scale).

        Returns:
            Updated SourceScore, or None if source not found.
        """
        source = self.store.get_source(source_id)
        if not source:
            logger.warning(f"Source not found for scoring: {source_id}")
            return None

        now = datetime.utcnow()
        current = self._get_score(source_id)

        if current is None:
            # First rating
            new_score = SourceScore(
                source_id=source_id,
                value=rating,
                confidence=compute_confidence(1),
                sample_size=1,
                last_updated=now,
            )
        else:
            # EMA update
            new_value = EMA_ALPHA * rating + (1 - EMA_ALPHA) * current.value
            new_sample_size = current.sample_size + 1
            new_score = SourceScore(
                source_id=source_id,
                value=new_value,
                confidence=compute_confidence(new_sample_size),
                sample_size=new_sample_size,
                last_updated=now,
            )

        self._save_score(new_score)
        logger.info(f"Source {source_id} score: {new_score.value:.2f} (n={new_score.sample_size})")
        return new_score

    def get_score(self, source_id: str) -> SourceScore | None:
        """Get the current score for a source."""
        return self._get_score(source_id)

    def get_all_scores(self) -> list[SourceScore]:
        """Get scores for all sources."""
        return self._load_all_scores()

    def get_ranked_sources(
        self,
        min_confidence: float = 0.0,
        limit: int = 50,
    ) -> list[tuple[str, SourceScore]]:
        """Get sources ranked by score.

        Returns:
            List of (source_id, score) tuples, highest first.
        """
        scores = self._load_all_scores()

        # Filter by confidence
        scored = [s for s in scores if s.confidence >= min_confidence]

        # Sort by score descending
        scored.sort(key=lambda s: s.value, reverse=True)

        return [(s.source_id, s) for s in scored[:limit]]

    def recompute_from_feedback(self, source_id: str | None = None) -> int:
        """Recompute scores from all explicit feedback.

        Useful for rebuilding scores after changes.

        Args:
            source_id: Specific source to recompute, or all if None.

        Returns:
            Number of sources updated.
        """
        # Get all items and their feedback
        if source_id:
            items = self.store.get_items(source_id=source_id, limit=10000)
        else:
            items = self.store.get_items(limit=10000)

        # Group by source
        source_ratings: dict[str, list[float]] = {}

        for item in items:
            feedback = self.store.get_item_feedback(item.id)
            if feedback:
                if item.source_id not in source_ratings:
                    source_ratings[item.source_id] = []
                source_ratings[item.source_id].append(feedback.reward_score)

        # Compute scores for each source
        updated = 0
        for sid, ratings in source_ratings.items():
            if not ratings:
                continue

            # Use simple average for recompute (not EMA since we have all data)
            avg = sum(ratings) / len(ratings)
            score = SourceScore(
                source_id=sid,
                value=avg,
                confidence=compute_confidence(len(ratings)),
                sample_size=len(ratings),
                last_updated=datetime.utcnow(),
            )
            self._save_score(score)
            updated += 1

        return updated

    def _get_score(self, source_id: str) -> SourceScore | None:
        """Load score from database."""
        try:
            row = self.store._conn.execute(
                """SELECT value, confidence, sample_size, last_updated
                   FROM source_scores WHERE source_id = ?""",
                (source_id,)
            ).fetchone()

            if row:
                return SourceScore(
                    source_id=source_id,
                    value=row[0],
                    confidence=row[1],
                    sample_size=row[2],
                    last_updated=datetime.fromisoformat(row[3]) if row[3] else datetime.utcnow(),
                )
        except Exception:
            pass  # Table might not exist yet
        return None

    def _save_score(self, score: SourceScore) -> None:
        """Save score to database."""
        self.store._conn.execute(
            """INSERT OR REPLACE INTO source_scores
               (source_id, value, confidence, sample_size, last_updated)
               VALUES (?, ?, ?, ?, ?)""",
            (score.source_id, score.value, score.confidence,
             score.sample_size, score.last_updated.isoformat()),
        )
        self.store._conn.commit()

    def _load_all_scores(self) -> list[SourceScore]:
        """Load all scores from database."""
        try:
            rows = self.store._conn.execute(
                """SELECT source_id, value, confidence, sample_size, last_updated
                   FROM source_scores"""
            ).fetchall()

            return [
                SourceScore(
                    source_id=row[0],
                    value=row[1],
                    confidence=row[2],
                    sample_size=row[3],
                    last_updated=datetime.fromisoformat(row[4]) if row[4] else datetime.utcnow(),
                )
                for row in rows
            ]
        except Exception:
            return []


# Singleton
_scorer: SourceScorer | None = None


def get_source_scorer(store: Store) -> SourceScorer:
    """Get or create the source scorer singleton."""
    global _scorer
    if _scorer is None or _scorer.store is not store:
        _scorer = SourceScorer(store)
    return _scorer
