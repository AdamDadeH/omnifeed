"""Score propagation for retrievers.

When users provide feedback on content, scores propagate upward:
- Leaf retrievers: EMA of content ratings from that source
- Parent retrievers: Weighted average of children's scores

This enables ranking and prioritization of sources based on
historical quality.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import TYPE_CHECKING

from omnifeed.retriever.types import Retriever, RetrieverScore

if TYPE_CHECKING:
    from omnifeed.store.base import Store


# EMA smoothing factor (higher = more weight to recent ratings)
EMA_ALPHA = 0.3

# Minimum sample size for confident scoring
MIN_CONFIDENCE_SAMPLES = 5
MAX_CONFIDENCE_SAMPLES = 50


def compute_confidence(sample_size: int) -> float:
    """Compute confidence score based on sample size.

    Returns a value between 0 and 1, approaching 1 as sample
    size increases.

    Args:
        sample_size: Number of feedback events.

    Returns:
        Confidence value between 0 and 1.
    """
    if sample_size <= 0:
        return 0.0

    # Use a logistic-like curve
    # Reaches ~0.5 at MIN_CONFIDENCE_SAMPLES
    # Reaches ~0.9 at MAX_CONFIDENCE_SAMPLES
    normalized = sample_size / MIN_CONFIDENCE_SAMPLES
    return 1 - math.exp(-0.7 * normalized)


class RetrieverScorer:
    """Manages score computation and propagation for retrievers.

    Usage:
        scorer = RetrieverScorer(store)

        # When user rates content from a retriever
        scorer.record_rating(retriever_id, rating=4.5)
    """

    def __init__(self, store: Store):
        self.store = store

    def record_rating(self, retriever_id: str, rating: float) -> list[str]:
        """Record a rating and propagate it up the entire retriever chain.

        The raw rating propagates to all ancestors - each gets an EMA update.
        This lets us measure how good a retriever is at finding good descendants.

        Args:
            retriever_id: The leaf retriever that produced the rated content.
            rating: The rating value (0.0 - 5.0 scale).

        Returns:
            List of retriever IDs that were updated.
        """
        import logging
        logger = logging.getLogger(__name__)

        updated_ids = []
        current = self.store.get_retriever(retriever_id)

        while current:
            # Update this retriever's score with EMA
            new_score = self._ema_update(current.score, rating)
            self.store.update_retriever_score(current.id, new_score)
            updated_ids.append(current.id)

            logger.info(
                f"Retriever '{current.display_name}' score: "
                f"{new_score.value:.2f} (n={new_score.sample_size})"
            )

            # Walk up to parent
            if current.parent_id:
                current = self.store.get_retriever(current.parent_id)
            else:
                break

        return updated_ids

    def record_rating_for_source(self, source_id: str, rating: float) -> list[str]:
        """Record a rating, finding the retriever from source_id.

        Handles both:
        - New path: source_id IS a retriever ID (from retriever system)
        - Old path: source_id is a Source ID (from sources table)

        Args:
            source_id: The source_id from the item (may be retriever or source ID).
            rating: The rating value (0.0 - 5.0 scale).

        Returns:
            List of retriever IDs that were updated.
        """
        import logging
        logger = logging.getLogger(__name__)

        # First try: source_id is actually a retriever ID
        retriever = self.store.get_retriever(source_id)
        if retriever:
            logger.debug(f"Found retriever directly: {source_id}")
            return self.record_rating(retriever.id, rating)

        # Second try: source_id is a Source ID, look up and find matching retriever
        source = self.store.get_source(source_id)
        if not source:
            logger.debug(f"No source or retriever found for: {source_id}")
            return []

        # Try to find retriever by matching URI patterns
        # Retriever URIs are like: source:{type}:{uri}
        retriever_uri = f"source:{source.source_type}:{source.uri}"
        retriever = self.store.get_retriever_by_uri(retriever_uri)

        if not retriever:
            # Also try just the raw URI
            retriever = self.store.get_retriever_by_uri(source.uri)

        if not retriever:
            logger.debug(f"No retriever found for source URI: {source.uri}")
            return []

        return self.record_rating(retriever.id, rating)

    def _ema_update(self, current_score: RetrieverScore | None, rating: float) -> RetrieverScore:
        """Compute new score using EMA update."""
        now = datetime.utcnow()

        if current_score is None:
            return RetrieverScore(
                value=rating,
                confidence=compute_confidence(1),
                sample_size=1,
                last_updated=now,
            )
        else:
            new_value = EMA_ALPHA * rating + (1 - EMA_ALPHA) * current_score.value
            new_sample_size = current_score.sample_size + 1
            return RetrieverScore(
                value=new_value,
                confidence=compute_confidence(new_sample_size),
                sample_size=new_sample_size,
                last_updated=now,
            )

    def propagate_all(self) -> int:
        """Propagate scores from children to parents for all retrievers.

        This recalculates parent scores as weighted averages of their
        children's scores. Useful for batch recalculation.

        Returns:
            Number of parent retrievers updated.
        """
        updated = 0

        # Get all retrievers
        all_retrievers = self.store.list_retrievers(enabled_only=False, limit=1000)

        # Find all unique parent IDs that have scored children
        parent_ids = set()
        for r in all_retrievers:
            if r.parent_id and r.score is not None:
                parent_ids.add(r.parent_id)

        # Propagate to each parent
        for parent_id in parent_ids:
            if self._propagate_to_parent(parent_id, all_retrievers):
                updated += 1

        return updated

    def _propagate_to_parent(
        self,
        parent_id: str,
        all_retrievers: list[Retriever] | None = None,
    ) -> bool:
        """Recalculate a parent's score from its children's scores.

        Parent score = weighted average of children's scores,
        weighted by each child's sample_size (confidence proxy).

        Args:
            parent_id: The parent retriever to update.
            all_retrievers: Optional pre-fetched list to avoid extra queries.

        Returns:
            True if the parent was updated, False otherwise.
        """
        import logging
        logger = logging.getLogger(__name__)

        # Get children
        if all_retrievers:
            children = [r for r in all_retrievers if r.parent_id == parent_id]
        else:
            children = self.store.get_children(parent_id)

        # Filter to scored children only
        scored_children = [c for c in children if c.score is not None]
        if not scored_children:
            return False

        # Calculate weighted average (weight = sample_size)
        total_weight = sum(c.score.sample_size for c in scored_children)
        if total_weight == 0:
            return False

        weighted_sum = sum(
            c.score.value * c.score.sample_size
            for c in scored_children
        )
        avg_score = weighted_sum / total_weight
        total_samples = sum(c.score.sample_size for c in scored_children)

        # Update parent
        new_score = RetrieverScore(
            value=avg_score,
            confidence=compute_confidence(total_samples),
            sample_size=total_samples,
            last_updated=datetime.utcnow(),
        )

        self.store.update_retriever_score(parent_id, new_score)

        parent = self.store.get_retriever(parent_id)
        if parent:
            logger.info(
                f"Parent '{parent.display_name}' score: "
                f"{new_score.value:.2f} (from {len(scored_children)} children, n={total_samples})"
            )

        return True

    def get_top_retrievers(
        self,
        limit: int = 10,
        min_confidence: float = 0.3,
    ) -> list[Retriever]:
        """Get the top-scoring retrievers.

        Args:
            limit: Maximum number of retrievers to return.
            min_confidence: Minimum confidence threshold.

        Returns:
            List of retrievers sorted by score (descending).
        """
        all_retrievers = self.store.list_retrievers(enabled_only=True, limit=100)

        # Filter by confidence and sort by score
        scored = [
            r for r in all_retrievers
            if r.score is not None and r.score.confidence >= min_confidence
        ]
        scored.sort(key=lambda r: r.score.value, reverse=True)

        return scored[:limit]

    def get_exploration_candidates(
        self,
        limit: int = 10,
        max_confidence: float = 0.5,
    ) -> list[Retriever]:
        """Get retrievers that need more exploration.

        Returns retrievers with low confidence (need more data) or
        no score yet.

        Args:
            limit: Maximum number of retrievers to return.
            max_confidence: Maximum confidence threshold.

        Returns:
            List of under-explored retrievers.
        """
        all_retrievers = self.store.list_retrievers(enabled_only=True, limit=100)

        # Find low-confidence or unscored retrievers
        candidates = [
            r for r in all_retrievers
            if r.score is None or r.score.confidence < max_confidence
        ]

        # Prioritize completely unscored retrievers
        candidates.sort(
            key=lambda r: (r.score.confidence if r.score else -1, r.created_at)
        )

        return candidates[:limit]

    def select_retrievers(
        self,
        limit: int = 10,
        explore_ratio: float = 0.3,
        min_exploit_confidence: float = 0.3,
    ) -> tuple[list[Retriever], list[Retriever]]:
        """Select retrievers with explore/exploit balance.

        CRITICAL: Always reserves explore_ratio for exploration to prevent
        the system from only exploiting known-good sources.

        Args:
            limit: Total number of retrievers to return.
            explore_ratio: Fraction reserved for exploration (0.3 = 30%).
            min_exploit_confidence: Minimum confidence for exploitation.

        Returns:
            Tuple of (exploit_retrievers, explore_retrievers).
            Combined length <= limit.
        """
        import random

        explore_count = max(1, int(limit * explore_ratio))  # At least 1 for explore
        exploit_count = limit - explore_count

        # Get exploitation candidates (high-scoring, high-confidence)
        exploit_candidates = self.get_top_retrievers(
            limit=exploit_count * 2,  # Get extra for variety
            min_confidence=min_exploit_confidence,
        )

        # Get exploration candidates (low-confidence or unscored)
        explore_candidates = self.get_exploration_candidates(
            limit=explore_count * 2,
            max_confidence=min_exploit_confidence,
        )

        # Select with some randomization to avoid always picking the same
        if len(exploit_candidates) > exploit_count:
            # Weighted random: higher scores more likely but not guaranteed
            exploit_selected = self._weighted_sample(
                exploit_candidates, exploit_count
            )
        else:
            exploit_selected = exploit_candidates[:exploit_count]

        # Explore: random sample from candidates
        if len(explore_candidates) > explore_count:
            explore_selected = random.sample(explore_candidates, explore_count)
        else:
            explore_selected = explore_candidates[:explore_count]

        return exploit_selected, explore_selected

    def _weighted_sample(
        self,
        retrievers: list[Retriever],
        count: int,
    ) -> list[Retriever]:
        """Sample retrievers weighted by score (higher = more likely).

        Not deterministic - adds variety while favoring high scores.
        """
        import random

        if not retrievers or count <= 0:
            return []

        # Build weights from scores (minimum weight = 1 to give everyone a chance)
        weights = []
        for r in retrievers:
            if r.score:
                # Score 0-5 → weight 1-6
                weights.append(1.0 + r.score.value)
            else:
                weights.append(1.0)

        # Sample without replacement
        selected = []
        remaining = list(retrievers)
        remaining_weights = list(weights)

        for _ in range(min(count, len(remaining))):
            # Weighted random choice
            total = sum(remaining_weights)
            r = random.uniform(0, total)
            cumulative = 0
            for i, w in enumerate(remaining_weights):
                cumulative += w
                if r <= cumulative:
                    selected.append(remaining[i])
                    remaining.pop(i)
                    remaining_weights.pop(i)
                    break

        return selected


def record_content_feedback(
    store: Store,
    source_id: str,
    rating: float,
) -> list[str]:
    """Record feedback for content and propagate to retriever chain.

    Convenience function for recording feedback without instantiating
    a scorer directly.

    Args:
        store: The store instance.
        source_id: The source_id from the rated item.
        rating: The rating value (0.0 - 5.0).

    Returns:
        List of retriever IDs that were updated.
    """
    scorer = RetrieverScorer(store)
    return scorer.record_rating_for_source(source_id, rating)
