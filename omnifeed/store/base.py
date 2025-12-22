"""Abstract base class for storage backends."""

from abc import ABC, abstractmethod
from datetime import datetime

from omnifeed.models import Source, SourceInfo, Item, FeedbackEvent


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

    # Lifecycle
    @abstractmethod
    def close(self) -> None:
        """Close the store and release resources."""
        pass

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
