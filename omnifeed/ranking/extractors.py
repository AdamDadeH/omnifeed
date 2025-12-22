"""Built-in feature extractors."""

from datetime import datetime

from omnifeed.models import Item
from omnifeed.ranking.base import FeatureExtractor


class FreshnessExtractor(FeatureExtractor):
    """Extract freshness feature based on publish time."""

    @property
    def name(self) -> str:
        return "freshness"

    def extract(self, item: Item) -> dict[str, float]:
        """Extract age in hours as a feature."""
        age_seconds = (datetime.utcnow() - item.published_at).total_seconds()
        age_hours = age_seconds / 3600

        return {
            "age_hours": age_hours,
            "age_days": age_hours / 24,
        }


class ContentTypeExtractor(FeatureExtractor):
    """One-hot encoding of content type."""

    @property
    def name(self) -> str:
        return "content_type"

    def extract(self, item: Item) -> dict[str, float]:
        """Return one-hot encoding of content type."""
        features = {
            "is_video": 0.0,
            "is_audio": 0.0,
            "is_article": 0.0,
            "is_paper": 0.0,
        }

        key = f"is_{item.content_type.value}"
        if key in features:
            features[key] = 1.0

        return features
