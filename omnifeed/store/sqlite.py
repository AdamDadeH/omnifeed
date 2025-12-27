"""SQLite storage backend."""

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from omnifeed.models import (
    Source, SourceInfo, SourceStatus, Item, ContentType, ConsumptionType,
    FeedbackEvent, FeedbackDimension, FeedbackOption, ExplicitFeedback,
    ItemAttribution, Creator, CreatorType, CreatorStats, SourceStats,
    Platform, PlatformCapability, DiscoverySource, DiscoverySignal,
    PlatformInstance, ContentInfo, SignalType,
)
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
    canonical_ids JSON,
    seen INTEGER DEFAULT 0,
    hidden INTEGER DEFAULT 0,
    series_id TEXT,
    series_position INTEGER,
    embedding JSON,
    embeddings JSON,
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

CREATE TABLE IF NOT EXISTS feedback_dimensions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    allow_multiple INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback_options (
    id TEXT PRIMARY KEY,
    dimension_id TEXT NOT NULL REFERENCES feedback_dimensions(id),
    label TEXT NOT NULL,
    description TEXT,
    sort_order INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_options_dimension ON feedback_options(dimension_id);

CREATE TABLE IF NOT EXISTS explicit_feedback (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL REFERENCES items(id),
    timestamp TEXT NOT NULL,
    reward_score REAL NOT NULL,
    selections JSON,
    notes TEXT,
    completion_pct REAL,
    is_checkpoint INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_explicit_feedback_item ON explicit_feedback(item_id);
CREATE INDEX IF NOT EXISTS idx_explicit_feedback_timestamp ON explicit_feedback(timestamp DESC);

CREATE TABLE IF NOT EXISTS item_attributions (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL REFERENCES items(id),
    source_id TEXT NOT NULL REFERENCES sources(id),
    discovered_at TEXT NOT NULL,
    rank INTEGER,
    context TEXT,
    metadata JSON,
    UNIQUE(item_id, source_id)
);

CREATE INDEX IF NOT EXISTS idx_attributions_item ON item_attributions(item_id);
CREATE INDEX IF NOT EXISTS idx_attributions_source ON item_attributions(source_id);

CREATE TABLE IF NOT EXISTS creators (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_variants JSON,
    creator_type TEXT DEFAULT 'unknown',
    external_ids JSON,
    avatar_url TEXT,
    bio TEXT,
    url TEXT,
    metadata JSON,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_creators_name ON creators(name COLLATE NOCASE);

-- Platform vs Discovery Source Architecture

CREATE TABLE IF NOT EXISTS platforms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    platform_type TEXT NOT NULL,
    content_types JSON NOT NULL,
    capabilities JSON NOT NULL,
    auth_required INTEGER DEFAULT 0,
    api_available INTEGER DEFAULT 0,
    base_url TEXT,
    url_patterns JSON,
    metadata JSON,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS discovery_sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    content_types JSON NOT NULL,
    typical_platforms JSON,
    poll_url TEXT,
    poll_interval_seconds INTEGER DEFAULT 86400,
    metadata JSON,
    created_at TEXT NOT NULL,
    last_polled_at TEXT
);

CREATE TABLE IF NOT EXISTS discovery_signals (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES discovery_sources(id),
    item_id TEXT REFERENCES items(id),
    content_info JSON,
    signal_type TEXT NOT NULL DEFAULT 'curated',
    rank INTEGER,
    rating REAL,
    context TEXT,
    recommender TEXT,
    url TEXT,
    discovered_at TEXT NOT NULL,
    metadata JSON
);

CREATE INDEX IF NOT EXISTS idx_discovery_signals_source ON discovery_signals(source_id);
CREATE INDEX IF NOT EXISTS idx_discovery_signals_item ON discovery_signals(item_id);
CREATE INDEX IF NOT EXISTS idx_discovery_signals_unresolved ON discovery_signals(item_id) WHERE item_id IS NULL;

CREATE TABLE IF NOT EXISTS platform_instances (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL REFERENCES items(id),
    platform_id TEXT NOT NULL REFERENCES platforms(id),
    platform_item_id TEXT NOT NULL,
    url TEXT NOT NULL,
    availability TEXT DEFAULT 'available',
    quality_tiers JSON,
    price REAL,
    currency TEXT,
    region_locks JSON,
    match_confidence REAL DEFAULT 1.0,
    discovered_at TEXT NOT NULL,
    metadata JSON,
    UNIQUE(item_id, platform_id)
);

CREATE INDEX IF NOT EXISTS idx_platform_instances_item ON platform_instances(item_id);
CREATE INDEX IF NOT EXISTS idx_platform_instances_platform ON platform_instances(platform_id);
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
    # Handle embeddings - try new format first, fall back to legacy
    embeddings = []
    try:
        if row["embeddings"]:
            embeddings = json.loads(row["embeddings"])
    except (KeyError, IndexError):
        # Column might not exist in older DBs
        pass

    # Handle canonical_ids
    canonical_ids = {}
    try:
        if row["canonical_ids"]:
            canonical_ids = json.loads(row["canonical_ids"])
    except (KeyError, IndexError):
        # Column might not exist in older DBs
        pass

    # Handle creator_id
    creator_id = None
    try:
        creator_id = row["creator_id"]
    except (KeyError, IndexError):
        pass

    return Item(
        id=row["id"],
        source_id=row["source_id"],
        external_id=row["external_id"],
        url=row["url"],
        title=row["title"],
        creator_id=creator_id,
        creator_name=row["creator_name"],
        published_at=_str_to_datetime(row["published_at"]),
        ingested_at=_str_to_datetime(row["ingested_at"]),
        content_type=ContentType(row["content_type"]),
        consumption_type=ConsumptionType(row["consumption_type"]),
        metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        canonical_ids=canonical_ids,
        seen=bool(row["seen"]),
        hidden=bool(row["hidden"]),
        series_id=row["series_id"],
        series_position=row["series_position"],
        embeddings=embeddings,
    )


def _row_to_creator(row: sqlite3.Row) -> Creator:
    """Convert a database row to a Creator."""
    name_variants = []
    try:
        if row["name_variants"]:
            name_variants = json.loads(row["name_variants"])
    except (KeyError, IndexError):
        pass

    external_ids = {}
    try:
        if row["external_ids"]:
            external_ids = json.loads(row["external_ids"])
    except (KeyError, IndexError):
        pass

    metadata = {}
    try:
        if row["metadata"]:
            metadata = json.loads(row["metadata"])
    except (KeyError, IndexError):
        pass

    return Creator(
        id=row["id"],
        name=row["name"],
        name_variants=name_variants,
        creator_type=CreatorType(row["creator_type"]) if row["creator_type"] else CreatorType.UNKNOWN,
        external_ids=external_ids,
        avatar_url=row["avatar_url"],
        bio=row["bio"],
        url=row["url"],
        metadata=metadata,
        created_at=_str_to_datetime(row["created_at"]),
        updated_at=_str_to_datetime(row["updated_at"]),
    )


def _row_to_platform(row: sqlite3.Row) -> Platform:
    """Convert a database row to a Platform."""
    content_types = []
    if row["content_types"]:
        content_types = [ContentType(ct) for ct in json.loads(row["content_types"])]

    capabilities = []
    if row["capabilities"]:
        capabilities = [PlatformCapability(c) for c in json.loads(row["capabilities"])]

    url_patterns = []
    if row["url_patterns"]:
        url_patterns = json.loads(row["url_patterns"])

    metadata = {}
    if row["metadata"]:
        metadata = json.loads(row["metadata"])

    return Platform(
        id=row["id"],
        name=row["name"],
        platform_type=row["platform_type"],
        content_types=content_types,
        capabilities=capabilities,
        auth_required=bool(row["auth_required"]),
        api_available=bool(row["api_available"]),
        base_url=row["base_url"],
        url_patterns=url_patterns,
        metadata=metadata,
        created_at=_str_to_datetime(row["created_at"]),
    )


def _row_to_discovery_source(row: sqlite3.Row) -> DiscoverySource:
    """Convert a database row to a DiscoverySource."""
    content_types = []
    if row["content_types"]:
        content_types = [ContentType(ct) for ct in json.loads(row["content_types"])]

    typical_platforms = []
    if row["typical_platforms"]:
        typical_platforms = json.loads(row["typical_platforms"])

    metadata = {}
    if row["metadata"]:
        metadata = json.loads(row["metadata"])

    return DiscoverySource(
        id=row["id"],
        name=row["name"],
        source_type=row["source_type"],
        content_types=content_types,
        typical_platforms=typical_platforms,
        poll_url=row["poll_url"],
        poll_interval_seconds=row["poll_interval_seconds"],
        metadata=metadata,
        created_at=_str_to_datetime(row["created_at"]),
        last_polled_at=_str_to_datetime(row["last_polled_at"]) if row["last_polled_at"] else None,
    )


def _row_to_discovery_signal(row: sqlite3.Row) -> DiscoverySignal:
    """Convert a database row to a DiscoverySignal."""
    content_info = None
    if row["content_info"]:
        ci_data = json.loads(row["content_info"])
        content_info = ContentInfo(
            content_type=ContentType(ci_data["content_type"]),
            title=ci_data["title"],
            creators=ci_data.get("creators", []),
            year=ci_data.get("year"),
            external_ids=ci_data.get("external_ids", {}),
        )

    metadata = {}
    if row["metadata"]:
        metadata = json.loads(row["metadata"])

    return DiscoverySignal(
        id=row["id"],
        source_id=row["source_id"],
        item_id=row["item_id"],
        content_info=content_info,
        signal_type=SignalType(row["signal_type"]) if row["signal_type"] else SignalType.CURATED,
        rank=row["rank"],
        rating=row["rating"],
        context=row["context"],
        recommender=row["recommender"],
        url=row["url"],
        discovered_at=_str_to_datetime(row["discovered_at"]),
        metadata=metadata,
    )


def _row_to_platform_instance(row: sqlite3.Row) -> PlatformInstance:
    """Convert a database row to a PlatformInstance."""
    quality_tiers = []
    if row["quality_tiers"]:
        quality_tiers = json.loads(row["quality_tiers"])

    region_locks = []
    if row["region_locks"]:
        region_locks = json.loads(row["region_locks"])

    metadata = {}
    if row["metadata"]:
        metadata = json.loads(row["metadata"])

    return PlatformInstance(
        id=row["id"],
        item_id=row["item_id"],
        platform_id=row["platform_id"],
        platform_item_id=row["platform_item_id"],
        url=row["url"],
        availability=row["availability"],
        quality_tiers=quality_tiers,
        price=row["price"],
        currency=row["currency"],
        region_locks=region_locks,
        match_confidence=row["match_confidence"],
        discovered_at=_str_to_datetime(row["discovered_at"]),
        metadata=metadata,
    )


def _row_to_attribution(row: sqlite3.Row) -> ItemAttribution:
    """Convert a database row to an ItemAttribution."""
    # Handle new columns that may not exist in older DBs
    external_id = ""
    is_primary = False
    try:
        external_id = row["external_id"] or ""
    except (KeyError, IndexError):
        pass
    try:
        is_primary = bool(row["is_primary"])
    except (KeyError, IndexError):
        pass

    return ItemAttribution(
        id=row["id"],
        item_id=row["item_id"],
        source_id=row["source_id"],
        discovered_at=_str_to_datetime(row["discovered_at"]),
        external_id=external_id,
        is_primary=is_primary,
        rank=row["rank"],
        context=row["context"],
        metadata=json.loads(row["metadata"]) if row["metadata"] else {},
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
        self._migrate_schema()

    def _migrate_schema(self) -> None:
        """Apply any necessary schema migrations."""
        cursor = self._conn.execute("PRAGMA table_info(items)")
        columns = {row[1] for row in cursor.fetchall()}

        # Add embeddings column if missing
        if "embeddings" not in columns:
            self._conn.execute("ALTER TABLE items ADD COLUMN embeddings JSON")
            self._conn.commit()

        # Add canonical_ids column if missing
        if "canonical_ids" not in columns:
            self._conn.execute("ALTER TABLE items ADD COLUMN canonical_ids JSON")
            self._conn.commit()

        # Migrate legacy embedding to embeddings list
        if "embedding" in columns:
            # Convert old single embedding to list format
            cursor = self._conn.execute(
                "SELECT id, embedding FROM items WHERE embedding IS NOT NULL AND embeddings IS NULL"
            )
            for row in cursor.fetchall():
                item_id, old_embedding = row
                if old_embedding:
                    import json as json_mod
                    try:
                        vector = json_mod.loads(old_embedding) if isinstance(old_embedding, str) else old_embedding
                        new_embeddings = [{
                            "type": "text",
                            "model": "all-MiniLM-L6-v2",
                            "vector": vector,
                        }]
                        self._conn.execute(
                            "UPDATE items SET embeddings = ? WHERE id = ?",
                            (json_mod.dumps(new_embeddings), item_id)
                        )
                    except Exception:
                        pass
            self._conn.commit()

        # Add creator_id column if missing
        if "creator_id" not in columns:
            self._conn.execute("ALTER TABLE items ADD COLUMN creator_id TEXT REFERENCES creators(id)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_items_creator ON items(creator_id)")
            self._conn.commit()

        # Migrate item_attributions table for new columns
        cursor = self._conn.execute("PRAGMA table_info(item_attributions)")
        attr_columns = {row[1] for row in cursor.fetchall()}

        if "is_primary" not in attr_columns:
            self._conn.execute("ALTER TABLE item_attributions ADD COLUMN is_primary INTEGER DEFAULT 0")
            self._conn.commit()

        if "external_id" not in attr_columns:
            self._conn.execute("ALTER TABLE item_attributions ADD COLUMN external_id TEXT")
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

    def delete_source(self, source_id: str, delete_items: bool = True) -> int:
        """Permanently delete a source and optionally its items.

        Returns the number of items deleted.
        """
        items_deleted = 0
        if delete_items:
            cursor = self._conn.execute(
                "DELETE FROM items WHERE source_id = ?", (source_id,)
            )
            items_deleted = cursor.rowcount
        self._conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        self._conn.commit()
        return items_deleted

    def get_source_stats(self, source_id: str) -> SourceStats:
        """Get aggregated stats for a source from content feedback."""
        # Count items from this source
        cursor = self._conn.execute(
            "SELECT COUNT(*) FROM items WHERE source_id = ?", (source_id,)
        )
        total_items = cursor.fetchone()[0]

        # Get item IDs for this source
        cursor = self._conn.execute(
            "SELECT id FROM items WHERE source_id = ?", (source_id,)
        )
        item_ids = [row[0] for row in cursor.fetchall()]

        if not item_ids:
            return SourceStats(source_id=source_id, total_items=0)

        placeholders = ",".join("?" * len(item_ids))

        # Count feedback events
        cursor = self._conn.execute(
            f"SELECT COUNT(*) FROM feedback_events WHERE item_id IN ({placeholders})",
            item_ids
        )
        total_feedback = cursor.fetchone()[0]

        # Get average reward score
        cursor = self._conn.execute(
            f"SELECT AVG(reward_score) FROM explicit_feedback WHERE item_id IN ({placeholders})",
            item_ids
        )
        avg_reward = cursor.fetchone()[0]

        # Count unique creators
        cursor = self._conn.execute(
            f"SELECT COUNT(DISTINCT creator_id) FROM items WHERE source_id = ? AND creator_id IS NOT NULL",
            (source_id,)
        )
        unique_creators = cursor.fetchone()[0]

        return SourceStats(
            source_id=source_id,
            total_items=total_items,
            total_feedback_events=total_feedback,
            avg_reward_score=avg_reward,
            unique_creators=unique_creators,
        )

    # Creators

    def add_creator(self, creator: Creator) -> Creator:
        """Add a new creator. Returns the created Creator with ID."""
        if not creator.id:
            creator.id = _generate_id()

        self._conn.execute(
            """
            INSERT INTO creators (
                id, name, name_variants, creator_type, external_ids,
                avatar_url, bio, url, metadata, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                creator.id,
                creator.name,
                json.dumps(creator.name_variants) if creator.name_variants else None,
                creator.creator_type.value,
                json.dumps(creator.external_ids) if creator.external_ids else None,
                creator.avatar_url,
                creator.bio,
                creator.url,
                json.dumps(creator.metadata) if creator.metadata else None,
                _datetime_to_str(creator.created_at),
                _datetime_to_str(creator.updated_at),
            ),
        )
        self._conn.commit()
        return creator

    def get_creator(self, creator_id: str) -> Creator | None:
        """Get a creator by ID."""
        cursor = self._conn.execute("SELECT * FROM creators WHERE id = ?", (creator_id,))
        row = cursor.fetchone()
        return _row_to_creator(row) if row else None

    def get_creator_by_name(self, name: str) -> Creator | None:
        """Find a creator by exact name match (case-insensitive)."""
        cursor = self._conn.execute(
            "SELECT * FROM creators WHERE name = ? COLLATE NOCASE",
            (name.strip(),)
        )
        row = cursor.fetchone()
        return _row_to_creator(row) if row else None

    def find_creator_by_external_id(self, id_type: str, id_value: str) -> Creator | None:
        """Find a creator by external ID (e.g., YouTube channel ID)."""
        cursor = self._conn.execute(
            "SELECT * FROM creators WHERE json_extract(external_ids, ?) = ?",
            (f"$.{id_type}", id_value)
        )
        row = cursor.fetchone()
        return _row_to_creator(row) if row else None

    def update_creator(self, creator: Creator) -> None:
        """Update creator metadata."""
        creator.updated_at = datetime.utcnow()
        self._conn.execute(
            """
            UPDATE creators SET
                name = ?,
                name_variants = ?,
                creator_type = ?,
                external_ids = ?,
                avatar_url = ?,
                bio = ?,
                url = ?,
                metadata = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                creator.name,
                json.dumps(creator.name_variants) if creator.name_variants else None,
                creator.creator_type.value,
                json.dumps(creator.external_ids) if creator.external_ids else None,
                creator.avatar_url,
                creator.bio,
                creator.url,
                json.dumps(creator.metadata) if creator.metadata else None,
                _datetime_to_str(creator.updated_at),
                creator.id,
            ),
        )
        self._conn.commit()

    def list_creators(self, limit: int = 100, offset: int = 0) -> list[Creator]:
        """List all creators."""
        cursor = self._conn.execute(
            "SELECT * FROM creators ORDER BY name COLLATE NOCASE LIMIT ? OFFSET ?",
            (limit, offset)
        )
        return [_row_to_creator(row) for row in cursor.fetchall()]

    def get_creator_stats(self, creator_id: str) -> CreatorStats:
        """Get aggregated stats for a creator from content feedback."""
        # Count items by this creator
        cursor = self._conn.execute(
            "SELECT COUNT(*) FROM items WHERE creator_id = ?", (creator_id,)
        )
        total_items = cursor.fetchone()[0]

        # Get item IDs for this creator
        cursor = self._conn.execute(
            "SELECT id, content_type FROM items WHERE creator_id = ?", (creator_id,)
        )
        rows = cursor.fetchall()
        item_ids = [row[0] for row in rows]

        # Count content types
        content_types: dict[str, int] = {}
        for row in rows:
            ct = row[1]
            content_types[ct] = content_types.get(ct, 0) + 1

        if not item_ids:
            return CreatorStats(creator_id=creator_id, total_items=0)

        placeholders = ",".join("?" * len(item_ids))

        # Count feedback events
        cursor = self._conn.execute(
            f"SELECT COUNT(*) FROM feedback_events WHERE item_id IN ({placeholders})",
            item_ids
        )
        total_feedback = cursor.fetchone()[0]

        # Get average reward score
        cursor = self._conn.execute(
            f"SELECT AVG(reward_score) FROM explicit_feedback WHERE item_id IN ({placeholders})",
            item_ids
        )
        avg_reward = cursor.fetchone()[0]

        return CreatorStats(
            creator_id=creator_id,
            total_items=total_items,
            total_feedback_events=total_feedback,
            avg_reward_score=avg_reward,
            content_types=content_types,
        )

    def get_items_by_creator(self, creator_id: str, limit: int = 50, offset: int = 0) -> list[Item]:
        """Get items created by a specific creator."""
        cursor = self._conn.execute(
            """
            SELECT * FROM items
            WHERE creator_id = ?
            ORDER BY published_at DESC
            LIMIT ? OFFSET ?
            """,
            (creator_id, limit, offset)
        )
        return [_row_to_item(row) for row in cursor.fetchall()]

    # Items

    def upsert_item(self, item: Item) -> None:
        """Insert or update an item by source_id + external_id."""
        self._conn.execute(
            """
            INSERT INTO items (
                id, source_id, external_id, url, title, creator_id, creator_name,
                published_at, ingested_at, content_type, consumption_type,
                metadata, canonical_ids, seen, hidden, series_id, series_position, embeddings
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, external_id) DO UPDATE SET
                url = excluded.url,
                title = excluded.title,
                creator_id = excluded.creator_id,
                creator_name = excluded.creator_name,
                published_at = excluded.published_at,
                content_type = excluded.content_type,
                consumption_type = excluded.consumption_type,
                metadata = excluded.metadata,
                canonical_ids = excluded.canonical_ids,
                series_id = excluded.series_id,
                series_position = excluded.series_position,
                embeddings = excluded.embeddings
            """,
            (
                item.id,
                item.source_id,
                item.external_id,
                item.url,
                item.title,
                item.creator_id,
                item.creator_name,
                _datetime_to_str(item.published_at),
                _datetime_to_str(item.ingested_at),
                item.content_type.value,
                item.consumption_type.value,
                json.dumps(item.metadata),
                json.dumps(item.canonical_ids) if item.canonical_ids else None,
                int(item.seen),
                int(item.hidden),
                item.series_id,
                item.series_position,
                json.dumps(item.embeddings) if item.embeddings else None,
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

    def get_item_by_url(self, url: str) -> Item | None:
        """Get an item by URL (deduplication fallback)."""
        cursor = self._conn.execute(
            "SELECT * FROM items WHERE url = ?",
            (url,),
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

    # Feedback dimensions and options

    def add_dimension(self, dimension: FeedbackDimension) -> None:
        """Add a feedback dimension."""
        self._conn.execute(
            """
            INSERT INTO feedback_dimensions (id, name, description, allow_multiple, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                dimension.id,
                dimension.name,
                dimension.description,
                int(dimension.allow_multiple),
                int(dimension.active),
                _datetime_to_str(dimension.created_at),
            ),
        )
        self._conn.commit()

    def get_dimensions(self, active_only: bool = True) -> list[FeedbackDimension]:
        """Get all feedback dimensions."""
        if active_only:
            cursor = self._conn.execute(
                "SELECT * FROM feedback_dimensions WHERE active = 1 ORDER BY name"
            )
        else:
            cursor = self._conn.execute("SELECT * FROM feedback_dimensions ORDER BY name")

        return [
            FeedbackDimension(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                allow_multiple=bool(row["allow_multiple"]),
                active=bool(row["active"]),
                created_at=_str_to_datetime(row["created_at"]),
            )
            for row in cursor.fetchall()
        ]

    def get_dimension(self, dimension_id: str) -> FeedbackDimension | None:
        """Get a dimension by ID."""
        cursor = self._conn.execute(
            "SELECT * FROM feedback_dimensions WHERE id = ?", (dimension_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        return FeedbackDimension(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            allow_multiple=bool(row["allow_multiple"]),
            active=bool(row["active"]),
            created_at=_str_to_datetime(row["created_at"]),
        )

    def add_option(self, option: FeedbackOption) -> None:
        """Add an option to a dimension."""
        self._conn.execute(
            """
            INSERT INTO feedback_options (id, dimension_id, label, description, sort_order, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                option.id,
                option.dimension_id,
                option.label,
                option.description,
                option.sort_order,
                int(option.active),
                _datetime_to_str(option.created_at),
            ),
        )
        self._conn.commit()

    def get_options(
        self,
        dimension_id: str | None = None,
        active_only: bool = True,
    ) -> list[FeedbackOption]:
        """Get options, optionally filtered by dimension."""
        conditions = []
        params: list = []

        if dimension_id is not None:
            conditions.append("dimension_id = ?")
            params.append(dimension_id)

        if active_only:
            conditions.append("active = 1")

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        cursor = self._conn.execute(
            f"SELECT * FROM feedback_options {where} ORDER BY sort_order, label",
            params,
        )

        return [
            FeedbackOption(
                id=row["id"],
                dimension_id=row["dimension_id"],
                label=row["label"],
                description=row["description"],
                sort_order=row["sort_order"],
                active=bool(row["active"]),
                created_at=_str_to_datetime(row["created_at"]),
            )
            for row in cursor.fetchall()
        ]

    def update_option(self, option_id: str, active: bool) -> None:
        """Update an option's active status."""
        self._conn.execute(
            "UPDATE feedback_options SET active = ? WHERE id = ?",
            (int(active), option_id),
        )
        self._conn.commit()

    # Explicit feedback

    def add_explicit_feedback(self, feedback: ExplicitFeedback) -> None:
        """Store explicit user feedback."""
        self._conn.execute(
            """
            INSERT INTO explicit_feedback (
                id, item_id, timestamp, reward_score, selections, notes, completion_pct, is_checkpoint
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feedback.id,
                feedback.item_id,
                _datetime_to_str(feedback.timestamp),
                feedback.reward_score,
                json.dumps(feedback.selections),
                feedback.notes,
                feedback.completion_pct,
                int(feedback.is_checkpoint),
            ),
        )
        self._conn.commit()

    def get_explicit_feedback(
        self,
        item_id: str | None = None,
        limit: int = 100,
    ) -> list[ExplicitFeedback]:
        """Get explicit feedback, optionally filtered by item."""
        conditions = []
        params: list = []

        if item_id is not None:
            conditions.append("item_id = ?")
            params.append(item_id)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        query = f"""
            SELECT * FROM explicit_feedback
            {where}
            ORDER BY timestamp DESC
            LIMIT ?
        """
        params.append(limit)

        cursor = self._conn.execute(query, params)
        return [
            ExplicitFeedback(
                id=row["id"],
                item_id=row["item_id"],
                timestamp=_str_to_datetime(row["timestamp"]),
                reward_score=row["reward_score"],
                selections=json.loads(row["selections"]) if row["selections"] else {},
                notes=row["notes"],
                completion_pct=row["completion_pct"],
                is_checkpoint=bool(row["is_checkpoint"]),
            )
            for row in cursor.fetchall()
        ]

    def get_item_feedback(self, item_id: str) -> ExplicitFeedback | None:
        """Get the most recent explicit feedback for an item."""
        cursor = self._conn.execute(
            """
            SELECT * FROM explicit_feedback
            WHERE item_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (item_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return ExplicitFeedback(
            id=row["id"],
            item_id=row["item_id"],
            timestamp=_str_to_datetime(row["timestamp"]),
            reward_score=row["reward_score"],
            selections=json.loads(row["selections"]) if row["selections"] else {},
            notes=row["notes"],
            completion_pct=row["completion_pct"],
            is_checkpoint=bool(row["is_checkpoint"]),
        )

    # Canonical ID lookup for deduplication

    def get_item_by_canonical_id(self, id_type: str, id_value: str) -> Item | None:
        """Find an item by canonical ID (ISBN, IMDB, etc.)."""
        # Use JSON query to search within canonical_ids
        cursor = self._conn.execute(
            """
            SELECT * FROM items
            WHERE json_extract(canonical_ids, ?) = ?
            """,
            (f"$.{id_type}", id_value),
        )
        row = cursor.fetchone()
        return _row_to_item(row) if row else None

    def find_items_by_canonical_ids(self, canonical_ids: dict[str, str]) -> Item | None:
        """Find an existing item that matches any of the provided canonical IDs.

        Returns the first matching item, or None if no match found.
        Useful for deduplication when ingesting items from multiple sources.
        """
        for id_type, id_value in canonical_ids.items():
            item = self.get_item_by_canonical_id(id_type, id_value)
            if item:
                return item
        return None

    # Item attributions

    def add_attribution(self, attribution: ItemAttribution) -> None:
        """Add an attribution linking an item to a source."""
        self._conn.execute(
            """
            INSERT INTO item_attributions (
                id, item_id, source_id, discovered_at, external_id, is_primary,
                rank, context, metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_id, source_id) DO UPDATE SET
                external_id = excluded.external_id,
                is_primary = excluded.is_primary,
                rank = excluded.rank,
                context = excluded.context,
                metadata = excluded.metadata
            """,
            (
                attribution.id,
                attribution.item_id,
                attribution.source_id,
                _datetime_to_str(attribution.discovered_at),
                attribution.external_id,
                int(attribution.is_primary),
                attribution.rank,
                attribution.context,
                json.dumps(attribution.metadata) if attribution.metadata else None,
            ),
        )
        self._conn.commit()

    def get_attributions(self, item_id: str) -> list[ItemAttribution]:
        """Get all attributions for an item."""
        cursor = self._conn.execute(
            "SELECT * FROM item_attributions WHERE item_id = ? ORDER BY is_primary DESC, discovered_at",
            (item_id,),
        )
        return [_row_to_attribution(row) for row in cursor.fetchall()]

    def get_attribution(self, item_id: str, source_id: str) -> ItemAttribution | None:
        """Get a specific attribution for an item from a source."""
        cursor = self._conn.execute(
            "SELECT * FROM item_attributions WHERE item_id = ? AND source_id = ?",
            (item_id, source_id),
        )
        row = cursor.fetchone()
        return _row_to_attribution(row) if row else None

    def upsert_attribution(self, attribution: ItemAttribution) -> None:
        """Add or update an attribution (upsert by item_id + source_id)."""
        # Same as add_attribution - the ON CONFLICT handles upsert
        self.add_attribution(attribution)

    def get_items_by_source_attribution(self, source_id: str, limit: int = 50) -> list[Item]:
        """Get items attributed to a source (even if not the primary source)."""
        cursor = self._conn.execute(
            """
            SELECT i.* FROM items i
            JOIN item_attributions a ON i.id = a.item_id
            WHERE a.source_id = ?
            ORDER BY a.rank ASC NULLS LAST, a.discovered_at DESC
            LIMIT ?
            """,
            (source_id, limit),
        )
        return [_row_to_item(row) for row in cursor.fetchall()]

    # Lifecycle

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
