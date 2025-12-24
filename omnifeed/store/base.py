"""Abstract base class for storage backends."""

from abc import ABC, abstractmethod
from datetime import datetime

from omnifeed.models import (
    Source, SourceInfo, Item, FeedbackEvent,
    FeedbackDimension, FeedbackOption, ExplicitFeedback,
    ItemAttribution,
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

    # Lifecycle
    @abstractmethod
    def close(self) -> None:
        """Close the store and release resources."""
        pass

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
