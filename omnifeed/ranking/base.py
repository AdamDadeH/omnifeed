"""Abstract base class for feature extractors."""

from abc import ABC, abstractmethod

from omnifeed.models import Item


class FeatureExtractor(ABC):
    """Interface for extracting ranking features from an item."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this feature extractor."""
        pass

    @abstractmethod
    def extract(self, item: Item) -> dict[str, float]:
        """Extract feature(s) from item.

        Returns:
            Dictionary mapping feature names to values.
        """
        pass
