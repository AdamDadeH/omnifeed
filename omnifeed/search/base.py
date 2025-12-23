"""Base classes for source search/discovery."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceSuggestion:
    """A suggested source from search results."""

    # Core identifiers
    url: str
    name: str
    source_type: str  # e.g., "youtube_channel", "rss", "bandcamp_artist"

    # Display info
    description: str = ""
    thumbnail_url: str | None = None
    subscriber_count: int | None = None

    # Metadata for the adapter
    metadata: dict[str, Any] = field(default_factory=dict)

    # Which provider found this
    provider: str = ""


class SearchProvider(ABC):
    """Interface for searching/discovering sources."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier for this provider (e.g., 'youtube', 'feedly')."""
        pass

    @property
    @abstractmethod
    def source_types(self) -> list[str]:
        """Source types this provider can find (e.g., ['youtube_channel'])."""
        pass

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[SourceSuggestion]:
        """Search for sources matching the query.

        Args:
            query: Search terms (creator name, topic, etc.)
            limit: Maximum results to return.

        Returns:
            List of SourceSuggestion objects.
        """
        pass
