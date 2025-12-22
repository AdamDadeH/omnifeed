"""JSON file-based storage backend."""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from omnifeed.models import Source, SourceInfo, SourceStatus, Item, ContentType, ConsumptionType, FeedbackEvent
from omnifeed.store.base import Store


def _generate_id() -> str:
    """Generate a short unique ID."""
    return uuid.uuid4().hex[:12]


def _datetime_to_str(dt: datetime) -> str:
    """Convert datetime to ISO format string."""
    return dt.isoformat()


def _str_to_datetime(s: str) -> datetime:
    """Parse ISO format string to datetime."""
    return datetime.fromisoformat(s)


def _source_to_dict(source: Source) -> dict[str, Any]:
    """Serialize a Source to a dictionary."""
    return {
        "id": source.id,
        "source_type": source.source_type,
        "uri": source.uri,
        "display_name": source.display_name,
        "avatar_url": source.avatar_url,
        "metadata": source.metadata,
        "created_at": _datetime_to_str(source.created_at),
        "last_polled_at": _datetime_to_str(source.last_polled_at) if source.last_polled_at else None,
        "poll_interval_seconds": source.poll_interval_seconds,
        "status": source.status.value,
    }


def _dict_to_source(d: dict[str, Any]) -> Source:
    """Deserialize a dictionary to a Source."""
    return Source(
        id=d["id"],
        source_type=d["source_type"],
        uri=d["uri"],
        display_name=d["display_name"],
        avatar_url=d.get("avatar_url"),
        metadata=d.get("metadata", {}),
        created_at=_str_to_datetime(d["created_at"]),
        last_polled_at=_str_to_datetime(d["last_polled_at"]) if d.get("last_polled_at") else None,
        poll_interval_seconds=d.get("poll_interval_seconds", 3600),
        status=SourceStatus(d.get("status", "active")),
    )


def _item_to_dict(item: Item) -> dict[str, Any]:
    """Serialize an Item to a dictionary."""
    return {
        "id": item.id,
        "source_id": item.source_id,
        "external_id": item.external_id,
        "url": item.url,
        "title": item.title,
        "creator_name": item.creator_name,
        "published_at": _datetime_to_str(item.published_at),
        "ingested_at": _datetime_to_str(item.ingested_at),
        "content_type": item.content_type.value,
        "consumption_type": item.consumption_type.value,
        "metadata": item.metadata,
        "seen": item.seen,
        "hidden": item.hidden,
        "series_id": item.series_id,
        "series_position": item.series_position,
    }


def _dict_to_item(d: dict[str, Any]) -> Item:
    """Deserialize a dictionary to an Item."""
    return Item(
        id=d["id"],
        source_id=d["source_id"],
        external_id=d["external_id"],
        url=d["url"],
        title=d["title"],
        creator_name=d["creator_name"],
        published_at=_str_to_datetime(d["published_at"]),
        ingested_at=_str_to_datetime(d["ingested_at"]),
        content_type=ContentType(d["content_type"]),
        consumption_type=ConsumptionType(d.get("consumption_type", "one_shot")),
        metadata=d.get("metadata", {}),
        seen=d.get("seen", False),
        hidden=d.get("hidden", False),
        series_id=d.get("series_id"),
        series_position=d.get("series_position"),
    )


def _feedback_to_dict(event: FeedbackEvent) -> dict[str, Any]:
    """Serialize a FeedbackEvent to a dictionary."""
    return {
        "id": event.id,
        "item_id": event.item_id,
        "timestamp": _datetime_to_str(event.timestamp),
        "event_type": event.event_type,
        "payload": event.payload,
    }


def _dict_to_feedback(d: dict[str, Any]) -> FeedbackEvent:
    """Deserialize a dictionary to a FeedbackEvent."""
    return FeedbackEvent(
        id=d["id"],
        item_id=d["item_id"],
        timestamp=_str_to_datetime(d["timestamp"]),
        event_type=d["event_type"],
        payload=d.get("payload", {}),
    )


class FileStore(Store):
    """JSON file-backed store. Simple, inspectable, good for testing."""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir).expanduser()
        self.sources_file = self.data_dir / "sources.json"
        self.items_file = self.data_dir / "items.json"
        self.feedback_file = self.data_dir / "feedback.json"

        self._sources: dict[str, Source] = {}
        self._items: dict[str, Item] = {}
        self._feedback: list[FeedbackEvent] = []
        self._load()

    def _load(self) -> None:
        """Load data from JSON files."""
        if self.sources_file.exists():
            data = json.loads(self.sources_file.read_text())
            self._sources = {s["id"]: _dict_to_source(s) for s in data}

        if self.items_file.exists():
            data = json.loads(self.items_file.read_text())
            self._items = {i["id"]: _dict_to_item(i) for i in data}

        if self.feedback_file.exists():
            data = json.loads(self.feedback_file.read_text())
            self._feedback = [_dict_to_feedback(f) for f in data]

    def _save(self) -> None:
        """Persist data to JSON files."""
        self.data_dir.mkdir(parents=True, exist_ok=True)

        sources_data = [_source_to_dict(s) for s in self._sources.values()]
        self.sources_file.write_text(json.dumps(sources_data, indent=2))

        items_data = [_item_to_dict(i) for i in self._items.values()]
        self.items_file.write_text(json.dumps(items_data, indent=2))

        feedback_data = [_feedback_to_dict(f) for f in self._feedback]
        self.feedback_file.write_text(json.dumps(feedback_data, indent=2))

    # Sources

    def add_source(self, info: SourceInfo) -> Source:
        """Add a new source. Returns the created Source with ID."""
        # Check for duplicate URI
        for source in self._sources.values():
            if source.uri == info.uri:
                raise ValueError(f"Source with URI {info.uri} already exists")

        source_id = _generate_id()
        now = datetime.utcnow()
        source = Source.from_info(source_id, info, now)

        self._sources[source_id] = source
        self._save()
        return source

    def list_sources(self) -> list[Source]:
        """List all sources."""
        return sorted(self._sources.values(), key=lambda s: s.created_at, reverse=True)

    def get_source(self, source_id: str) -> Source | None:
        """Get a source by ID."""
        return self._sources.get(source_id)

    def get_source_by_uri(self, uri: str) -> Source | None:
        """Get a source by its URI."""
        for source in self._sources.values():
            if source.uri == uri:
                return source
        return None

    def update_source_poll_time(self, source_id: str, polled_at: datetime) -> None:
        """Update the last polled timestamp for a source."""
        if source_id in self._sources:
            self._sources[source_id].last_polled_at = polled_at
            self._save()

    def disable_source(self, source_id: str) -> None:
        """Disable (soft delete) a source."""
        if source_id in self._sources:
            self._sources[source_id].status = SourceStatus.PAUSED
            self._save()

    # Items

    def upsert_item(self, item: Item) -> None:
        """Insert or update an item by source_id + external_id."""
        # Check if item with same source_id + external_id exists
        existing = self.get_item_by_external_id(item.source_id, item.external_id)
        if existing:
            # Update existing - preserve seen/hidden state
            item.seen = existing.seen
            item.hidden = existing.hidden
            self._items[existing.id] = item
            # Also update the item's ID to match existing
            item.id = existing.id
        else:
            self._items[item.id] = item

        self._save()

    def get_items(
        self,
        seen: bool | None = None,
        hidden: bool = False,
        source_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Item]:
        """Get items with optional filters."""
        items = list(self._items.values())

        # Apply filters
        if seen is not None:
            items = [i for i in items if i.seen == seen]

        if hidden is not None:
            items = [i for i in items if i.hidden == hidden]

        if source_id is not None:
            items = [i for i in items if i.source_id == source_id]

        # Sort by published_at descending
        items.sort(key=lambda i: i.published_at, reverse=True)

        # Apply pagination
        return items[offset : offset + limit]

    def get_item(self, item_id: str) -> Item | None:
        """Get a single item by ID."""
        return self._items.get(item_id)

    def get_item_by_external_id(self, source_id: str, external_id: str) -> Item | None:
        """Get an item by source_id and external_id."""
        for item in self._items.values():
            if item.source_id == source_id and item.external_id == external_id:
                return item
        return None

    def mark_seen(self, item_id: str, seen: bool = True) -> None:
        """Mark an item as seen or unseen."""
        if item_id in self._items:
            self._items[item_id].seen = seen
            self._save()

    def mark_hidden(self, item_id: str, hidden: bool = True) -> None:
        """Mark an item as hidden or unhidden."""
        if item_id in self._items:
            self._items[item_id].hidden = hidden
            self._save()

    def count_items(
        self,
        seen: bool | None = None,
        hidden: bool | None = None,
        source_id: str | None = None,
    ) -> int:
        """Count items matching the filters."""
        items = list(self._items.values())

        if seen is not None:
            items = [i for i in items if i.seen == seen]

        if hidden is not None:
            items = [i for i in items if i.hidden == hidden]

        if source_id is not None:
            items = [i for i in items if i.source_id == source_id]

        return len(items)

    # Feedback events

    def add_feedback_event(self, event: FeedbackEvent) -> None:
        """Store a feedback event."""
        self._feedback.append(event)
        self._save()

    def get_feedback_events(
        self,
        item_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[FeedbackEvent]:
        """Get feedback events with optional filters."""
        events = self._feedback

        if item_id is not None:
            events = [e for e in events if e.item_id == item_id]

        if event_type is not None:
            events = [e for e in events if e.event_type == event_type]

        # Sort by timestamp descending
        events = sorted(events, key=lambda e: e.timestamp, reverse=True)

        return events[:limit]

    # Lifecycle

    def close(self) -> None:
        """No-op for file store (data is saved on each mutation)."""
        pass
