"""Abstract base class for feature extractors."""

from abc import ABC, abstractmethod

from omnifeed.models import Content


class FeatureExtractor(ABC):
    """Interface for extracting ranking features from content."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this feature extractor."""
        pass

    @abstractmethod
    def extract(self, content: Content) -> dict[str, float]:
        """Extract feature(s) from content.

        Returns:
            Dictionary mapping feature names to values.
        """
        pass
