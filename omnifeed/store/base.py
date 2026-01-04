"""Abstract base class for storage backends."""

from abc import ABC, abstractmethod
from datetime import datetime

from omnifeed.models import (
    Source, SourceInfo, Item, FeedbackEvent,
    FeedbackDimension, FeedbackOption, ExplicitFeedback,
    ItemAttribution, Creator, CreatorStats, SourceStats,
    DiscoverySignal, Content, Encoding,
)
from omnifeed.retriever.types import Retriever, RetrieverScore


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

    # Content (new model - abstract content independent of access method)
    @abstractmethod
    def upsert_content(self, content: Content) -> None:
        """Insert or update content by ID."""
        pass

    @abstractmethod
    def get_content(self, content_id: str) -> Content | None:
        """Get content by ID."""
        pass

    @abstractmethod
    def get_contents(
        self,
        seen: bool | None = None,
        hidden: bool | None = None,
        source_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Content]:
        """Get content with optional filters.

        Args:
            seen: Filter by seen status
            hidden: Filter by hidden status
            source_type: Filter by encoding source type (joins with encodings table)
            limit: Max results
            offset: Pagination offset
        """
        pass

    @abstractmethod
    def get_content_by_canonical_id(self, id_type: str, id_value: str) -> Content | None:
        """Find content by canonical ID (ISBN, IMDB, etc.)."""
        pass

    @abstractmethod
    def find_content_by_canonical_ids(self, canonical_ids: dict[str, str]) -> Content | None:
        """Find existing content that matches any of the provided canonical IDs."""
        pass

    @abstractmethod
    def mark_content_seen(self, content_id: str, seen: bool = True) -> None:
        """Mark content as seen or unseen."""
        pass

    @abstractmethod
    def mark_content_hidden(self, content_id: str, hidden: bool = True) -> None:
        """Mark content as hidden or unhidden."""
        pass

    @abstractmethod
    def count_content(
        self,
        seen: bool | None = None,
        hidden: bool | None = None,
    ) -> int:
        """Count content matching the filters."""
        pass

    # Encodings (how to access content - URLs, deep links, etc.)
    @abstractmethod
    def add_encoding(self, encoding: Encoding) -> None:
        """Add a new encoding for content."""
        pass

    @abstractmethod
    def get_encoding(self, encoding_id: str) -> Encoding | None:
        """Get an encoding by ID."""
        pass

    @abstractmethod
    def get_encoding_by_external_id(self, source_type: str, external_id: str) -> Encoding | None:
        """Get an encoding by source type and external ID."""
        pass

    @abstractmethod
    def get_encoding_by_uri(self, uri: str) -> Encoding | None:
        """Get an encoding by URI (URL or deep link)."""
        pass

    @abstractmethod
    def get_encodings_for_content(self, content_id: str) -> list[Encoding]:
        """Get all encodings for a piece of content."""
        pass

    @abstractmethod
    def get_primary_encoding(self, content_id: str) -> Encoding | None:
        """Get the primary (first discovered) encoding for content."""
        pass

    # Convenience methods for Content + Encoding
    @abstractmethod
    def get_content_with_encodings(
        self, content_id: str
    ) -> tuple[Content, list[Encoding]] | None:
        """Get content along with all its encodings."""
        pass

    @abstractmethod
    def migrate_items_to_content(self) -> int:
        """Migrate existing Item records to Content + Encoding. Returns count migrated."""
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

    # Retrievers
    @abstractmethod
    def add_retriever(self, retriever: Retriever) -> Retriever:
        """Add a new retriever. Returns the created Retriever with ID."""
        pass

    @abstractmethod
    def get_retriever(self, retriever_id: str) -> Retriever | None:
        """Get a retriever by ID."""
        pass

    @abstractmethod
    def get_retriever_by_uri(self, uri: str) -> Retriever | None:
        """Get a retriever by its URI."""
        pass

    @abstractmethod
    def list_retrievers(
        self,
        parent_id: str | None = None,
        kind: str | None = None,
        enabled_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Retriever]:
        """List retrievers with optional filters."""
        pass

    @abstractmethod
    def get_children(self, parent_id: str) -> list[Retriever]:
        """Get child retrievers of a parent."""
        pass

    @abstractmethod
    def update_retriever(self, retriever: Retriever) -> None:
        """Update retriever metadata and config."""
        pass

    @abstractmethod
    def update_retriever_invoked(self, retriever_id: str, invoked_at: datetime) -> None:
        """Update the last_invoked_at timestamp."""
        pass

    @abstractmethod
    def update_retriever_score(self, retriever_id: str, score: RetrieverScore) -> None:
        """Update a retriever's quality score."""
        pass

    @abstractmethod
    def enable_retriever(self, retriever_id: str, enabled: bool = True) -> None:
        """Enable or disable a retriever."""
        pass

    @abstractmethod
    def delete_retriever(self, retriever_id: str, delete_children: bool = True) -> int:
        """Delete a retriever and optionally its children. Returns count deleted."""
        pass

    @abstractmethod
    def get_retrievers_needing_poll(self, limit: int = 10) -> list[Retriever]:
        """Get POLL retrievers that are due for polling."""
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
