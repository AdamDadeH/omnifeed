"""Registry for feature extractors."""

from omnifeed.models import Item
from omnifeed.ranking.base import FeatureExtractor


class FeatureRegistry:
    """Registry of feature extractors."""

    def __init__(self) -> None:
        self._extractors: list[FeatureExtractor] = []

    def register(self, extractor: FeatureExtractor) -> None:
        """Register a feature extractor."""
        self._extractors.append(extractor)

    def extract_all(self, item: Item) -> dict[str, float]:
        """Run all extractors, return combined feature dict."""
        features: dict[str, float] = {}
        for ext in self._extractors:
            features.update(ext.extract(item))
        return features

    def list_extractors(self) -> list[FeatureExtractor]:
        """List all registered extractors."""
        return list(self._extractors)
