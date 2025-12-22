"""Ranking pipeline for scoring and ordering items."""

from datetime import datetime

from omnifeed.models import Item
from omnifeed.ranking.registry import FeatureRegistry


class RankingPipeline:
    """Scores and ranks items for the feed.

    MVP implementation uses chronological ordering.
    Feature extraction is wired up for logging/future use.
    """

    def __init__(self, feature_registry: FeatureRegistry | None = None):
        self.feature_registry = feature_registry or FeatureRegistry()

    def score(self, item: Item) -> float:
        """Score a single item.

        MVP: Just use recency (newer = higher score).
        Features are extracted but not used in scoring yet.
        """
        # Extract features (for logging/future use)
        if self.feature_registry:
            _features = self.feature_registry.extract_all(item)

        # MVP scoring: newer = higher score
        age_seconds = (datetime.utcnow() - item.published_at).total_seconds()
        return -age_seconds  # Negative so newer = higher

    def rank(self, items: list[Item]) -> list[Item]:
        """Return items sorted by score descending."""
        return sorted(items, key=lambda i: self.score(i), reverse=True)


def create_default_pipeline() -> RankingPipeline:
    """Create a ranking pipeline with default extractors."""
    from omnifeed.ranking.extractors import FreshnessExtractor, ContentTypeExtractor

    registry = FeatureRegistry()
    registry.register(FreshnessExtractor())
    registry.register(ContentTypeExtractor())

    return RankingPipeline(registry)
