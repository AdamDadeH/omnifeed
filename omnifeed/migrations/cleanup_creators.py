"""Clean up garbage creator entries and re-hydrate items.

This script:
1. Removes all extracted_creators from item metadata
2. Deletes creators that have no items linked (creator_id on items)
3. Re-runs hydration with improved extraction
"""

import json

from omnifeed.config import Config
from omnifeed.store.sqlite import SQLiteStore


def cleanup_creators(dry_run: bool = False, verbose: bool = True) -> dict:
    """Clean up garbage creator data.

    Args:
        dry_run: If True, don't make any changes
        verbose: Print progress information

    Returns:
        Stats about the cleanup
    """
    config = Config.load()
    store = SQLiteStore(config.store_path)

    stats = {
        "items_cleaned": 0,
        "creators_deleted": 0,
        "creators_kept": 0,
    }

    # Step 1: Clear extracted_creators from all items
    if verbose:
        print("Step 1: Clearing extracted_creators from items...")

    cursor = store._conn.execute("SELECT id, metadata FROM items")
    items_to_update = []

    for row in cursor.fetchall():
        item_id, metadata_json = row
        try:
            metadata = json.loads(metadata_json) if metadata_json else {}
        except json.JSONDecodeError:
            continue

        if "extracted_creators" in metadata:
            del metadata["extracted_creators"]
            items_to_update.append((json.dumps(metadata), item_id))

    if verbose:
        print(f"  Found {len(items_to_update)} items with extracted_creators")

    if not dry_run and items_to_update:
        store._conn.executemany(
            "UPDATE items SET metadata = ? WHERE id = ?",
            items_to_update
        )
        store._conn.commit()

    stats["items_cleaned"] = len(items_to_update)

    # Step 2: Find creators that are not linked to any items via creator_id
    if verbose:
        print("\nStep 2: Finding orphaned creators...")

    cursor = store._conn.execute("""
        SELECT c.id, c.name
        FROM creators c
        LEFT JOIN items i ON i.creator_id = c.id
        WHERE i.id IS NULL
    """)
    orphaned_creators = cursor.fetchall()

    if verbose:
        print(f"  Found {len(orphaned_creators)} orphaned creators")
        if orphaned_creators and len(orphaned_creators) <= 20:
            for cid, cname in orphaned_creators:
                print(f"    - {cname}")

    if not dry_run and orphaned_creators:
        store._conn.executemany(
            "DELETE FROM creators WHERE id = ?",
            [(cid,) for cid, _ in orphaned_creators]
        )
        store._conn.commit()

    stats["creators_deleted"] = len(orphaned_creators)

    # Count remaining creators
    cursor = store._conn.execute("SELECT COUNT(*) FROM creators")
    stats["creators_kept"] = cursor.fetchone()[0]

    if verbose:
        print(f"\nCleanup complete:")
        print(f"  Items cleaned: {stats['items_cleaned']}")
        print(f"  Creators deleted: {stats['creators_deleted']}")
        print(f"  Creators remaining: {stats['creators_kept']}")
        if dry_run:
            print("  (DRY RUN - no changes made)")

    store.close()
    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Clean up garbage creator data")
    parser.add_argument("--dry-run", action="store_true", help="Don't make changes")
    parser.add_argument("--quiet", action="store_true", help="Suppress output")
    args = parser.parse_args()

    cleanup_creators(dry_run=args.dry_run, verbose=not args.quiet)
