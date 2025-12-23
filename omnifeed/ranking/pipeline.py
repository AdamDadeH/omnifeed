"""Ranking pipeline for scoring and ordering items."""

import logging
from datetime import datetime

from omnifeed.models import Item
from omnifeed.ranking.embeddings import get_embedding_by_type
from omnifeed.ranking.registry import FeatureRegistry

logger = logging.getLogger(__name__)


class RankingPipeline:
    """Scores and ranks items for the feed.

    Uses trained ML model when available, falls back to chronological.
    """

    def __init__(
        self,
        feature_registry: FeatureRegistry | None = None,
        use_ml_model: bool = True,
    ):
        self.feature_registry = feature_registry or FeatureRegistry()
        self.use_ml_model = use_ml_model
        self._ranking_model = None

    def _get_ranking_model(self):
        """Get the trained ranking model (lazy load)."""
        if self._ranking_model is None and self.use_ml_model:
            try:
                from omnifeed.ranking.model import get_ranking_model
                self._ranking_model = get_ranking_model()
            except Exception as e:
                logger.warning(f"Failed to load ranking model: {e}")
                self._ranking_model = False  # Marker for failed load
        return self._ranking_model if self._ranking_model else None

    def score(self, item: Item) -> float:
        """Score a single item.

        Uses ML model if trained, otherwise falls back to recency.
        """
        # Try ML model first
        model = self._get_ranking_model()
        if model and model.is_trained and get_embedding_by_type(item.embeddings, "text"):
            try:
                return model.score(item)
            except Exception as e:
                logger.warning(f"ML scoring failed: {e}")

        # Fallback: recency-based scoring
        age_seconds = (datetime.utcnow() - item.published_at).total_seconds()
        # Normalize to roughly 0-5 range (1 day old = ~2.5)
        recency_score = max(0, 5 - (age_seconds / 86400))
        return recency_score

    def rank(self, items: list[Item]) -> list[Item]:
        """Return items sorted by score descending."""
        return sorted(items, key=lambda i: self.score(i), reverse=True)

    def rank_with_diversity(
        self,
        items: list[Item],
        max_per_source: int = 3,
    ) -> list[Item]:
        """Rank items with diversity injection.

        Limits consecutive items from same source.
        """
        scored = [(item, self.score(item)) for item in items]
        scored.sort(key=lambda x: x[1], reverse=True)

        result = []
        source_counts: dict[str, int] = {}
        deferred: list[tuple[Item, float]] = []

        for item, score in scored:
            count = source_counts.get(item.source_id, 0)
            if count < max_per_source:
                result.append(item)
                source_counts[item.source_id] = count + 1
            else:
                deferred.append((item, score))

        # Add deferred items at the end
        for item, _ in deferred:
            result.append(item)

        return result


def create_default_pipeline() -> RankingPipeline:
    """Create a ranking pipeline with default extractors."""
    from omnifeed.ranking.extractors import FreshnessExtractor, ContentTypeExtractor

    registry = FeatureRegistry()
    registry.register(FreshnessExtractor())
    registry.register(ContentTypeExtractor())

    return RankingPipeline(registry)
