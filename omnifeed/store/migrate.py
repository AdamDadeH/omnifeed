"""Migration utilities for moving data between stores."""

from omnifeed.store.base import Store


def migrate_store(source: Store, target: Store) -> tuple[int, int]:
    """Copy all data from source store to target store.

    Args:
        source: The store to read from.
        target: The store to write to.

    Returns:
        Tuple of (sources_migrated, items_migrated).
    """
    sources_count = 0
    items_count = 0

    # Migrate sources
    for src in source.list_sources():
        target.add_source(src.to_info())
        sources_count += 1

    # Migrate items - need to get all, including seen and hidden
    items = source.get_items(seen=None, hidden=None, limit=100000)
    for item in items:
        target.upsert_item(item)
        items_count += 1

    return sources_count, items_count
