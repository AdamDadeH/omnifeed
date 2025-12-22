"""Abstract base class for source adapters."""

from abc import ABC, abstractmethod
from datetime import datetime

from omnifeed.models import SourceInfo, RawItem


class SourceAdapter(ABC):
    """Interface for pulling content from a source type."""

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Return the source type identifier (e.g., 'rss', 'youtube_channel')."""
        pass

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Return True if this adapter can handle the given URL."""
        pass

    @abstractmethod
    def resolve(self, url: str) -> SourceInfo:
        """Resolve a URL to source metadata.

        Called when adding a source. Should fetch enough information
        to display the source to the user for confirmation.

        Args:
            url: The URL provided by the user.

        Returns:
            SourceInfo with resolved metadata.

        Raises:
            ValueError: If the URL cannot be resolved.
        """
        pass

    @abstractmethod
    def poll(self, source: SourceInfo, since: datetime | None = None) -> list[RawItem]:
        """Fetch new items from the source.

        Args:
            source: The source to poll.
            since: If provided, only return items published after this time.

        Returns:
            List of RawItem objects representing new content.
        """
        pass
