"""SQLite storage backend."""

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from omnifeed.models import Source, SourceInfo, SourceStatus, Item, ContentType, ConsumptionType, FeedbackEvent
from omnifeed.store.base import Store


SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    uri TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    avatar_url TEXT,
    metadata JSON,
    created_at TEXT NOT NULL,
    last_polled_at TEXT,
    poll_interval_seconds INTEGER DEFAULT 3600,
    status TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id),
    external_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    creator_name TEXT NOT NULL,
    published_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    content_type TEXT NOT NULL,
    consumption_type TEXT DEFAULT 'one_shot',
    metadata JSON,
    seen INTEGER DEFAULT 0,
    hidden INTEGER DEFAULT 0,
    series_id TEXT,
    series_position INTEGER,
    UNIQUE(source_id, external_id)
);

CREATE INDEX IF NOT EXISTS idx_items_published ON items(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_source ON items(source_id);
CREATE INDEX IF NOT EXISTS idx_items_seen ON items(seen);
CREATE INDEX IF NOT EXISTS idx_items_hidden ON items(hidden);

CREATE TABLE IF NOT EXISTS feedback_events (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL REFERENCES items(id),
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSON
);

CREATE INDEX IF NOT EXISTS idx_feedback_item ON feedback_events(item_id);
CREATE INDEX IF NOT EXISTS idx_feedback_type ON feedback_events(event_type);
CREATE INDEX IF NOT EXISTS idx_feedback_timestamp ON feedback_events(timestamp DESC);
"""


def _generate_id() -> str:
    """Generate a short unique ID."""
    return uuid.uuid4().hex[:12]


def _datetime_to_str(dt: datetime) -> str:
    """Convert datetime to ISO format string."""
    return dt.isoformat()


def _str_to_datetime(s: str) -> datetime:
    """Parse ISO format string to datetime."""
    return datetime.fromisoformat(s)


def _row_to_source(row: sqlite3.Row) -> Source:
    """Convert a database row to a Source."""
    return Source(
        id=row["id"],
        source_type=row["source_type"],
        uri=row["uri"],
        display_name=row["display_name"],
        avatar_url=row["avatar_url"],
        metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        created_at=_str_to_datetime(row["created_at"]),
        last_polled_at=_str_to_datetime(row["last_polled_at"]) if row["last_polled_at"] else None,
        poll_interval_seconds=row["poll_interval_seconds"],
        status=SourceStatus(row["status"]),
    )


def _row_to_item(row: sqlite3.Row) -> Item:
    """Convert a database row to an Item."""
    return Item(
        id=row["id"],
        source_id=row["source_id"],
        external_id=row["external_id"],
        url=row["url"],
        title=row["title"],
        creator_name=row["creator_name"],
        published_at=_str_to_datetime(row["published_at"]),
        ingested_at=_str_to_datetime(row["ingested_at"]),
        content_type=ContentType(row["content_type"]),
        consumption_type=ConsumptionType(row["consumption_type"]),
        metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        seen=bool(row["seen"]),
        hidden=bool(row["hidden"]),
        series_id=row["series_id"],
        series_position=row["series_position"],
    )


class SQLiteStore(Store):
    """SQLite-backed store. Good for production single-user."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False allows use from multiple threads (FastAPI)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        """Create tables if not exist."""
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # Sources

    def add_source(self, info: SourceInfo) -> Source:
        """Add a new source. Returns the created Source with ID."""
        source_id = _generate_id()
        now = datetime.utcnow()

        self._conn.execute(
            """
            INSERT INTO sources (id, source_type, uri, display_name, avatar_url, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                info.source_type,
                info.uri,
                info.display_name,
                info.avatar_url,
                json.dumps(info.metadata),
                _datetime_to_str(now),
            ),
        )
        self._conn.commit()

        return Source.from_info(source_id, info, now)

    def list_sources(self) -> list[Source]:
        """List all sources."""
        cursor = self._conn.execute("SELECT * FROM sources ORDER BY created_at DESC")
        return [_row_to_source(row) for row in cursor.fetchall()]

    def get_source(self, source_id: str) -> Source | None:
        """Get a source by ID."""
        cursor = self._conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,))
        row = cursor.fetchone()
        return _row_to_source(row) if row else None

    def get_source_by_uri(self, uri: str) -> Source | None:
        """Get a source by its URI."""
        cursor = self._conn.execute("SELECT * FROM sources WHERE uri = ?", (uri,))
        row = cursor.fetchone()
        return _row_to_source(row) if row else None

    def update_source_poll_time(self, source_id: str, polled_at: datetime) -> None:
        """Update the last polled timestamp for a source."""
        self._conn.execute(
            "UPDATE sources SET last_polled_at = ? WHERE id = ?",
            (_datetime_to_str(polled_at), source_id),
        )
        self._conn.commit()

    def disable_source(self, source_id: str) -> None:
        """Disable (soft delete) a source."""
        self._conn.execute(
            "UPDATE sources SET status = ? WHERE id = ?",
            (SourceStatus.PAUSED.value, source_id),
        )
        self._conn.commit()

    # Items

    def upsert_item(self, item: Item) -> None:
        """Insert or update an item by source_id + external_id."""
        self._conn.execute(
            """
            INSERT INTO items (
                id, source_id, external_id, url, title, creator_name,
                published_at, ingested_at, content_type, consumption_type,
                metadata, seen, hidden, series_id, series_position
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, external_id) DO UPDATE SET
                url = excluded.url,
                title = excluded.title,
                creator_name = excluded.creator_name,
                published_at = excluded.published_at,
                content_type = excluded.content_type,
                consumption_type = excluded.consumption_type,
                metadata = excluded.metadata,
                series_id = excluded.series_id,
                series_position = excluded.series_position
            """,
            (
                item.id,
                item.source_id,
                item.external_id,
                item.url,
                item.title,
                item.creator_name,
                _datetime_to_str(item.published_at),
                _datetime_to_str(item.ingested_at),
                item.content_type.value,
                item.consumption_type.value,
                json.dumps(item.metadata),
                int(item.seen),
                int(item.hidden),
                item.series_id,
                item.series_position,
            ),
        )
        self._conn.commit()

    def get_items(
        self,
        seen: bool | None = None,
        hidden: bool = False,
        source_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Item]:
        """Get items with optional filters."""
        conditions = []
        params: list = []

        if seen is not None:
            conditions.append("seen = ?")
            params.append(int(seen))

        if hidden is not None:
            conditions.append("hidden = ?")
            params.append(int(hidden))

        if source_id is not None:
            conditions.append("source_id = ?")
            params.append(source_id)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        query = f"""
            SELECT * FROM items
            {where}
            ORDER BY published_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        cursor = self._conn.execute(query, params)
        return [_row_to_item(row) for row in cursor.fetchall()]

    def get_item(self, item_id: str) -> Item | None:
        """Get a single item by ID."""
        cursor = self._conn.execute("SELECT * FROM items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        return _row_to_item(row) if row else None

    def get_item_by_external_id(self, source_id: str, external_id: str) -> Item | None:
        """Get an item by source_id and external_id."""
        cursor = self._conn.execute(
            "SELECT * FROM items WHERE source_id = ? AND external_id = ?",
            (source_id, external_id),
        )
        row = cursor.fetchone()
        return _row_to_item(row) if row else None

    def mark_seen(self, item_id: str, seen: bool = True) -> None:
        """Mark an item as seen or unseen."""
        self._conn.execute("UPDATE items SET seen = ? WHERE id = ?", (int(seen), item_id))
        self._conn.commit()

    def mark_hidden(self, item_id: str, hidden: bool = True) -> None:
        """Mark an item as hidden or unhidden."""
        self._conn.execute("UPDATE items SET hidden = ? WHERE id = ?", (int(hidden), item_id))
        self._conn.commit()

    def count_items(
        self,
        seen: bool | None = None,
        hidden: bool | None = None,
        source_id: str | None = None,
    ) -> int:
        """Count items matching the filters."""
        conditions = []
        params: list = []

        if seen is not None:
            conditions.append("seen = ?")
            params.append(int(seen))

        if hidden is not None:
            conditions.append("hidden = ?")
            params.append(int(hidden))

        if source_id is not None:
            conditions.append("source_id = ?")
            params.append(source_id)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        cursor = self._conn.execute(f"SELECT COUNT(*) FROM items {where}", params)
        return cursor.fetchone()[0]

    # Feedback events

    def add_feedback_event(self, event: FeedbackEvent) -> None:
        """Store a feedback event."""
        self._conn.execute(
            """
            INSERT INTO feedback_events (id, item_id, timestamp, event_type, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.item_id,
                _datetime_to_str(event.timestamp),
                event.event_type,
                json.dumps(event.payload),
            ),
        )
        self._conn.commit()

    def get_feedback_events(
        self,
        item_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[FeedbackEvent]:
        """Get feedback events with optional filters."""
        conditions = []
        params: list = []

        if item_id is not None:
            conditions.append("item_id = ?")
            params.append(item_id)

        if event_type is not None:
            conditions.append("event_type = ?")
            params.append(event_type)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        query = f"""
            SELECT * FROM feedback_events
            {where}
            ORDER BY timestamp DESC
            LIMIT ?
        """
        params.append(limit)

        cursor = self._conn.execute(query, params)
        return [
            FeedbackEvent(
                id=row["id"],
                item_id=row["item_id"],
                timestamp=_str_to_datetime(row["timestamp"]),
                event_type=row["event_type"],
                payload=json.loads(row["payload"]) if row["payload"] else {},
            )
            for row in cursor.fetchall()
        ]

    # Lifecycle

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
