"""Base protocols for source plugins.

A source plugin provides:
1. SourceAdapter - polls content from a source (required)
2. SearchProvider - discovers new sources to add (optional)

To create a new source plugin:
1. Create a new directory under omnifeed/sources/
2. Implement SourceAdapter in adapter.py
3. Optionally implement SearchProvider in search.py
4. Export from __init__.py

See omnifeed/sources/_template/ for a complete example.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# =============================================================================
# Data Models
# =============================================================================


@dataclass
class SourceInfo:
    """Metadata about a source, returned by adapter.resolve()."""

    source_type: str  # e.g., "youtube_channel", "rss", "bandcamp"
    uri: str  # Unique identifier, e.g., "youtube:channel:UC..."
    display_name: str  # Human-readable name
    avatar_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawItem:
    """A content item fetched from a source, returned by adapter.poll()."""

    external_id: str  # Unique ID within the source
    url: str  # Link to the content
    title: str
    published_at: datetime
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    # Common metadata fields:
    # - author: str - creator name
    # - content_text: str - text content for embeddings
    # - content_html: str - HTML content for display
    # - thumbnail: str - thumbnail URL
    # - duration_seconds: int - for video/audio
    # - enclosures: list[dict] - media attachments


@dataclass
class SourceSuggestion:
    """A suggested source from search, returned by search.search()."""

    url: str  # URL to add this source
    name: str  # Display name
    source_type: str  # Which adapter handles this

    # Optional display info
    description: str = ""
    thumbnail_url: str | None = None
    subscriber_count: int | None = None

    # Additional metadata for the adapter
    metadata: dict[str, Any] = field(default_factory=dict)

    # Which search provider found this
    provider: str = ""


# =============================================================================
# Protocols
# =============================================================================


class SourceAdapter(ABC):
    """Interface for fetching content from a source type.

    Every source plugin MUST implement this class.

    Example:
        class MyAdapter(SourceAdapter):
            @property
            def source_type(self) -> str:
                return "my_source"

            def can_handle(self, url: str) -> bool:
                return "mysite.com" in url

            def resolve(self, url: str) -> SourceInfo:
                # Fetch metadata about the source
                return SourceInfo(...)

            def poll(self, source: SourceInfo, since: datetime | None) -> list[RawItem]:
                # Fetch new items
                return [RawItem(...), ...]
    """

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Unique identifier for this source type.

        Examples: "rss", "youtube_channel", "bandcamp", "qobuz_artist"
        """
        pass

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Return True if this adapter can handle the given URL.

        Called when a user tries to add a source by URL.
        """
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

        Called periodically to check for new content.

        Args:
            source: The source to poll (from resolve()).
            since: If provided, only return items published after this time.

        Returns:
            List of RawItem objects representing new content.
        """
        pass


class SearchProvider(ABC):
    """Interface for discovering sources via search.

    This is OPTIONAL - not all source types support search.
    If implemented, enables users to search for sources to add.

    Example:
        class MySearchProvider(SearchProvider):
            @property
            def provider_id(self) -> str:
                return "my_source"

            @property
            def source_types(self) -> list[str]:
                return ["my_source"]

            async def search(self, query: str, limit: int = 10) -> list[SourceSuggestion]:
                # Search for sources matching the query
                return [SourceSuggestion(...), ...]
    """

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier for this search provider.

        Usually matches the source_type, but could be different
        (e.g., "feedly" provides search for "rss" sources).
        """
        pass

    @property
    @abstractmethod
    def source_types(self) -> list[str]:
        """Source types this provider can discover.

        Examples: ["rss"], ["youtube_channel"], ["bandcamp"]
        """
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


# =============================================================================
# Plugin Definition
# =============================================================================


@dataclass
class SourcePlugin:
    """A complete source plugin with adapter and optional search."""

    adapter: SourceAdapter
    search: SearchProvider | None = None

    @property
    def source_type(self) -> str:
        return self.adapter.source_type
