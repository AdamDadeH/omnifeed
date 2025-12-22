"""Tests for storage backends."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from omnifeed.models import SourceInfo, Item, ContentType, ConsumptionType
from omnifeed.store import SQLiteStore, FileStore


@pytest.fixture
def sqlite_store():
    """Create a temporary SQLite store."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SQLiteStore(f"{tmpdir}/test.db")
        yield store
        store.close()


@pytest.fixture
def file_store():
    """Create a temporary file store."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = FileStore(tmpdir)
        yield store
        store.close()


@pytest.fixture(params=["sqlite", "file"])
def store(request, sqlite_store, file_store):
    """Parameterized fixture that runs tests against both stores."""
    if request.param == "sqlite":
        return sqlite_store
    return file_store


class TestStore:
    """Tests that run against both store implementations."""

    def test_add_and_get_source(self, store):
        """Test adding and retrieving a source."""
        info = SourceInfo(
            source_type="rss",
            uri="https://example.com/feed.xml",
            display_name="Example Feed",
            avatar_url=None,
            metadata={"description": "A test feed"},
        )

        source = store.add_source(info)
        assert source.id is not None
        assert source.display_name == "Example Feed"
        assert source.source_type == "rss"

        # Retrieve by ID
        retrieved = store.get_source(source.id)
        assert retrieved is not None
        assert retrieved.display_name == "Example Feed"

        # Retrieve by URI
        by_uri = store.get_source_by_uri("https://example.com/feed.xml")
        assert by_uri is not None
        assert by_uri.id == source.id

    def test_list_sources(self, store):
        """Test listing sources."""
        # Add two sources
        store.add_source(SourceInfo(
            source_type="rss",
            uri="https://example1.com/feed.xml",
            display_name="Feed 1",
        ))
        store.add_source(SourceInfo(
            source_type="rss",
            uri="https://example2.com/feed.xml",
            display_name="Feed 2",
        ))

        sources = store.list_sources()
        assert len(sources) == 2

    def test_add_and_get_item(self, store):
        """Test adding and retrieving an item."""
        # First add a source
        source = store.add_source(SourceInfo(
            source_type="rss",
            uri="https://example.com/feed.xml",
            display_name="Example Feed",
        ))

        # Add an item
        item = Item(
            id="item123",
            source_id=source.id,
            external_id="ext123",
            url="https://example.com/post/1",
            title="Test Post",
            creator_name="Test Author",
            published_at=datetime(2024, 1, 15, 12, 0, 0),
            ingested_at=datetime.utcnow(),
            content_type=ContentType.ARTICLE,
            consumption_type=ConsumptionType.ONE_SHOT,
            metadata={"tags": ["test"]},
        )
        store.upsert_item(item)

        # Retrieve by ID
        retrieved = store.get_item("item123")
        assert retrieved is not None
        assert retrieved.title == "Test Post"
        assert retrieved.content_type == ContentType.ARTICLE

        # Retrieve by external ID
        by_ext = store.get_item_by_external_id(source.id, "ext123")
        assert by_ext is not None
        assert by_ext.id == "item123"

    def test_item_seen_hidden_state(self, store):
        """Test marking items as seen and hidden."""
        source = store.add_source(SourceInfo(
            source_type="rss",
            uri="https://example.com/feed.xml",
            display_name="Example Feed",
        ))

        item = Item(
            id="item456",
            source_id=source.id,
            external_id="ext456",
            url="https://example.com/post/2",
            title="Another Post",
            creator_name="Author",
            published_at=datetime.utcnow(),
            ingested_at=datetime.utcnow(),
            content_type=ContentType.ARTICLE,
        )
        store.upsert_item(item)

        # Initially unseen
        retrieved = store.get_item("item456")
        assert not retrieved.seen
        assert not retrieved.hidden

        # Mark as seen
        store.mark_seen("item456")
        retrieved = store.get_item("item456")
        assert retrieved.seen

        # Mark as hidden
        store.mark_hidden("item456")
        retrieved = store.get_item("item456")
        assert retrieved.hidden

    def test_get_items_filters(self, store):
        """Test filtering items."""
        source = store.add_source(SourceInfo(
            source_type="rss",
            uri="https://example.com/feed.xml",
            display_name="Example Feed",
        ))

        # Add several items
        for i in range(5):
            item = Item(
                id=f"item{i}",
                source_id=source.id,
                external_id=f"ext{i}",
                url=f"https://example.com/post/{i}",
                title=f"Post {i}",
                creator_name="Author",
                published_at=datetime(2024, 1, i + 1),
                ingested_at=datetime.utcnow(),
                content_type=ContentType.ARTICLE,
            )
            store.upsert_item(item)

        # Mark some as seen
        store.mark_seen("item0")
        store.mark_seen("item1")

        # Mark one as hidden
        store.mark_hidden("item2")

        # Test filters
        all_visible = store.get_items(hidden=False)
        assert len(all_visible) == 4  # item2 is hidden

        unseen = store.get_items(seen=False, hidden=False)
        assert len(unseen) == 2  # item3, item4

        seen = store.get_items(seen=True, hidden=False)
        assert len(seen) == 2  # item0, item1

    def test_count_items(self, store):
        """Test counting items."""
        source = store.add_source(SourceInfo(
            source_type="rss",
            uri="https://example.com/feed.xml",
            display_name="Example Feed",
        ))

        for i in range(3):
            item = Item(
                id=f"count{i}",
                source_id=source.id,
                external_id=f"count_ext{i}",
                url=f"https://example.com/count/{i}",
                title=f"Count {i}",
                creator_name="Author",
                published_at=datetime.utcnow(),
                ingested_at=datetime.utcnow(),
                content_type=ContentType.ARTICLE,
            )
            store.upsert_item(item)

        store.mark_seen("count0")

        assert store.count_items() == 3
        assert store.count_items(seen=False) == 2
        assert store.count_items(seen=True) == 1
