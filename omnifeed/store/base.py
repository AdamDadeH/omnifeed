"""Abstract base class for storage backends."""

from abc import ABC, abstractmethod
from datetime import datetime

from omnifeed.models import (
    Source, SourceInfo, Item, FeedbackEvent,
    FeedbackDimension, FeedbackOption, ExplicitFeedback,
    ItemAttribution, Creator, CreatorStats, SourceStats,
    Platform, DiscoverySource, DiscoverySignal, PlatformInstance,
)


class Store(ABC):
    """Abstract persistence layer for sources and items."""

    # Sources
    @abstractmethod
    def add_source(self, info: SourceInfo) -> Source:
        """Add a new source. Returns the created Source with ID."""
        pass

    @abstractmethod
    def list_sources(self) -> list[Source]:
        """List all sources."""
        pass

    @abstractmethod
    def get_source(self, source_id: str) -> Source | None:
        """Get a source by ID."""
        pass

    @abstractmethod
    def get_source_by_uri(self, uri: str) -> Source | None:
        """Get a source by its URI."""
        pass

    @abstractmethod
    def update_source_poll_time(self, source_id: str, polled_at: datetime) -> None:
        """Update the last polled timestamp for a source."""
        pass

    @abstractmethod
    def disable_source(self, source_id: str) -> None:
        """Disable (soft delete) a source."""
        pass

    @abstractmethod
    def delete_source(self, source_id: str, delete_items: bool = True) -> int:
        """Permanently delete a source and optionally its items."""
        pass

    @abstractmethod
    def get_source_stats(self, source_id: str) -> SourceStats:
        """Get aggregated stats for a source from content feedback."""
        pass

    # Creators
    @abstractmethod
    def add_creator(self, creator: Creator) -> Creator:
        """Add a new creator. Returns the created Creator with ID."""
        pass

    @abstractmethod
    def get_creator(self, creator_id: str) -> Creator | None:
        """Get a creator by ID."""
        pass

    @abstractmethod
    def get_creator_by_name(self, name: str) -> Creator | None:
        """Find a creator by exact name match (case-insensitive)."""
        pass

    @abstractmethod
    def find_creator_by_external_id(self, id_type: str, id_value: str) -> Creator | None:
        """Find a creator by external ID (e.g., YouTube channel ID)."""
        pass

    @abstractmethod
    def update_creator(self, creator: Creator) -> None:
        """Update creator metadata."""
        pass

    @abstractmethod
    def list_creators(self, limit: int = 100, offset: int = 0) -> list[Creator]:
        """List all creators."""
        pass

    @abstractmethod
    def get_creator_stats(self, creator_id: str) -> CreatorStats:
        """Get aggregated stats for a creator from content feedback."""
        pass

    @abstractmethod
    def get_items_by_creator(self, creator_id: str, limit: int = 50, offset: int = 0) -> list[Item]:
        """Get items created by a specific creator."""
        pass

    # Items
    @abstractmethod
    def upsert_item(self, item: Item) -> None:
        """Insert or update an item by source_id + external_id."""
        pass

    @abstractmethod
    def get_items(
        self,
        seen: bool | None = None,
        hidden: bool = False,
        source_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Item]:
        """Get items with optional filters."""
        pass

    @abstractmethod
    def get_item(self, item_id: str) -> Item | None:
        """Get a single item by ID."""
        pass

    @abstractmethod
    def get_item_by_external_id(self, source_id: str, external_id: str) -> Item | None:
        """Get an item by source_id and external_id."""
        pass

    @abstractmethod
    def get_item_by_url(self, url: str) -> Item | None:
        """Get an item by URL (deduplication fallback)."""
        pass

    @abstractmethod
    def get_item_by_canonical_id(self, id_type: str, id_value: str) -> Item | None:
        """Find an item by canonical ID (ISBN, IMDB, etc.)."""
        pass

    @abstractmethod
    def find_items_by_canonical_ids(self, canonical_ids: dict[str, str]) -> Item | None:
        """Find an existing item that matches any of the provided canonical IDs."""
        pass

    @abstractmethod
    def mark_seen(self, item_id: str, seen: bool = True) -> None:
        """Mark an item as seen or unseen."""
        pass

    @abstractmethod
    def mark_hidden(self, item_id: str, hidden: bool = True) -> None:
        """Mark an item as hidden or unhidden."""
        pass

    @abstractmethod
    def count_items(
        self,
        seen: bool | None = None,
        hidden: bool | None = None,
        source_id: str | None = None,
    ) -> int:
        """Count items matching the filters."""
        pass

    # Feedback events
    @abstractmethod
    def add_feedback_event(self, event: FeedbackEvent) -> None:
        """Store a feedback event."""
        pass

    @abstractmethod
    def get_feedback_events(
        self,
        item_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[FeedbackEvent]:
        """Get feedback events with optional filters."""
        pass

    # Feedback dimensions and options
    @abstractmethod
    def add_dimension(self, dimension: FeedbackDimension) -> None:
        """Add a feedback dimension."""
        pass

    @abstractmethod
    def get_dimensions(self, active_only: bool = True) -> list[FeedbackDimension]:
        """Get all feedback dimensions."""
        pass

    @abstractmethod
    def get_dimension(self, dimension_id: str) -> FeedbackDimension | None:
        """Get a dimension by ID."""
        pass

    @abstractmethod
    def add_option(self, option: FeedbackOption) -> None:
        """Add an option to a dimension."""
        pass

    @abstractmethod
    def get_options(
        self,
        dimension_id: str | None = None,
        active_only: bool = True,
    ) -> list[FeedbackOption]:
        """Get options, optionally filtered by dimension."""
        pass

    @abstractmethod
    def update_option(self, option_id: str, active: bool) -> None:
        """Update an option's active status."""
        pass

    # Explicit feedback
    @abstractmethod
    def add_explicit_feedback(self, feedback: ExplicitFeedback) -> None:
        """Store explicit user feedback."""
        pass

    @abstractmethod
    def get_explicit_feedback(
        self,
        item_id: str | None = None,
        limit: int = 100,
    ) -> list[ExplicitFeedback]:
        """Get explicit feedback, optionally filtered by item."""
        pass

    @abstractmethod
    def get_item_feedback(self, item_id: str) -> ExplicitFeedback | None:
        """Get the most recent explicit feedback for an item."""
        pass

    # Item attributions
    @abstractmethod
    def add_attribution(self, attribution: ItemAttribution) -> None:
        """Add an attribution linking an item to a source."""
        pass

    @abstractmethod
    def get_attributions(self, item_id: str) -> list[ItemAttribution]:
        """Get all attributions for an item."""
        pass

    @abstractmethod
    def get_attribution(self, item_id: str, source_id: str) -> ItemAttribution | None:
        """Get a specific attribution for an item from a source."""
        pass

    @abstractmethod
    def get_items_by_source_attribution(self, source_id: str, limit: int = 50) -> list[Item]:
        """Get items attributed to a source (even if not the primary source)."""
        pass

    @abstractmethod
    def upsert_attribution(self, attribution: ItemAttribution) -> None:
        """Add or update an attribution (upsert by item_id + source_id)."""
        pass

    # Platforms
    @abstractmethod
    def add_platform(self, platform: Platform) -> Platform:
        """Add a new platform. Returns the created Platform."""
        pass

    @abstractmethod
    def get_platform(self, platform_id: str) -> Platform | None:
        """Get a platform by ID."""
        pass

    @abstractmethod
    def get_platform_by_url(self, url: str) -> Platform | None:
        """Find a platform that matches the given URL pattern."""
        pass

    @abstractmethod
    def list_platforms(self) -> list[Platform]:
        """List all platforms."""
        pass

    # Discovery sources
    @abstractmethod
    def add_discovery_source(self, source: DiscoverySource) -> DiscoverySource:
        """Add a new discovery source. Returns the created DiscoverySource."""
        pass

    @abstractmethod
    def get_discovery_source(self, source_id: str) -> DiscoverySource | None:
        """Get a discovery source by ID."""
        pass

    @abstractmethod
    def list_discovery_sources(self) -> list[DiscoverySource]:
        """List all discovery sources."""
        pass

    @abstractmethod
    def update_discovery_source_poll_time(
        self, source_id: str, polled_at: datetime
    ) -> None:
        """Update the last polled timestamp for a discovery source."""
        pass

    # Discovery signals
    @abstractmethod
    def add_discovery_signal(self, signal: DiscoverySignal) -> DiscoverySignal:
        """Add a discovery signal. Returns the created signal."""
        pass

    @abstractmethod
    def get_discovery_signals(
        self,
        item_id: str | None = None,
        source_id: str | None = None,
        limit: int = 100,
    ) -> list[DiscoverySignal]:
        """Get discovery signals with optional filters."""
        pass

    @abstractmethod
    def get_unresolved_signals(self, limit: int = 100) -> list[DiscoverySignal]:
        """Get signals that haven't been matched to items yet."""
        pass

    @abstractmethod
    def resolve_signal(self, signal_id: str, item_id: str) -> None:
        """Link a discovery signal to a resolved item."""
        pass

    # Platform instances
    @abstractmethod
    def add_platform_instance(self, instance: PlatformInstance) -> PlatformInstance:
        """Add a platform instance for content. Returns the created instance."""
        pass

    @abstractmethod
    def get_platform_instances(
        self,
        item_id: str | None = None,
        platform_id: str | None = None,
    ) -> list[PlatformInstance]:
        """Get platform instances with optional filters."""
        pass

    @abstractmethod
    def get_platform_instance(
        self, item_id: str, platform_id: str
    ) -> PlatformInstance | None:
        """Get a specific platform instance for an item on a platform."""
        pass

    # Lifecycle
    @abstractmethod
    def close(self) -> None:
        """Close the store and release resources."""
        pass

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
