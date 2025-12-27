"""Migration script to backfill Creator entities from existing item creator_names."""

import uuid
from datetime import datetime

from omnifeed.config import Config
from omnifeed.store import create_store
from omnifeed.models import Creator, CreatorType


def generate_id() -> str:
    """Generate a short unique ID."""
    return uuid.uuid4().hex[:12]


def migrate_creators(dry_run: bool = False, verbose: bool = True) -> dict:
    """
    Migrate existing items to use Creator entities.

    1. Extract unique creator_name values from items
    2. Create Creator entities for each unique name
    3. Update items with creator_id references

    Args:
        dry_run: If True, don't make changes, just report what would happen
        verbose: If True, print progress

    Returns:
        dict with migration statistics
    """
    config = Config.load()
    store = create_store(config.store_type, config.store_path)

    stats = {
        "total_items": 0,
        "unique_creators": 0,
        "creators_created": 0,
        "creators_existing": 0,
        "items_updated": 0,
        "items_skipped": 0,
    }

    try:
        # Get all items (we need to get all, not just limited)
        # Using a high limit since we need to process all
        items = store.get_items(limit=100000, hidden=None, seen=None)
        stats["total_items"] = len(items)

        if verbose:
            print(f"Found {len(items)} items to process")

        # Extract unique creator names
        creator_names: dict[str, list] = {}  # name -> list of item_ids
        for item in items:
            if item.creator_name and item.creator_name.strip():
                name = item.creator_name.strip()
                if name not in creator_names:
                    creator_names[name] = []
                creator_names[name].append(item.id)

        stats["unique_creators"] = len(creator_names)

        if verbose:
            print(f"Found {len(creator_names)} unique creator names")

        # Create or find creators and update items
        name_to_creator_id: dict[str, str] = {}

        for name, item_ids in creator_names.items():
            # Check if creator already exists (by exact name match)
            existing = store.get_creator_by_name(name)

            if existing:
                name_to_creator_id[name] = existing.id
                stats["creators_existing"] += 1
                if verbose:
                    print(f"  Found existing creator: {name} ({existing.id})")
            else:
                # Create new creator
                if dry_run:
                    creator_id = f"<would_create_{generate_id()}>"
                    stats["creators_created"] += 1
                    if verbose:
                        print(f"  Would create creator: {name}")
                else:
                    creator = Creator(
                        id=generate_id(),
                        name=name,
                        creator_type=CreatorType.UNKNOWN,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                    store.add_creator(creator)
                    name_to_creator_id[name] = creator.id
                    stats["creators_created"] += 1
                    if verbose:
                        print(f"  Created creator: {name} ({creator.id})")

        # Update items with creator_id
        for item in items:
            if item.creator_id:
                # Already has creator_id
                stats["items_skipped"] += 1
                continue

            if item.creator_name and item.creator_name.strip():
                name = item.creator_name.strip()
                creator_id = name_to_creator_id.get(name)

                if creator_id and not creator_id.startswith("<would_create"):
                    if not dry_run:
                        item.creator_id = creator_id
                        store.upsert_item(item)
                    stats["items_updated"] += 1
            else:
                stats["items_skipped"] += 1

        if verbose:
            print("\nMigration complete!")
            print(f"  Total items: {stats['total_items']}")
            print(f"  Unique creator names: {stats['unique_creators']}")
            print(f"  Creators created: {stats['creators_created']}")
            print(f"  Creators already existing: {stats['creators_existing']}")
            print(f"  Items updated: {stats['items_updated']}")
            print(f"  Items skipped: {stats['items_skipped']}")

            if dry_run:
                print("\n(Dry run - no changes made)")

        return stats

    finally:
        store.close()


def main():
    """Run the migration from command line."""
    import argparse

    parser = argparse.ArgumentParser(description="Migrate items to use Creator entities")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't make changes, just report what would happen",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )

    args = parser.parse_args()

    migrate_creators(dry_run=args.dry_run, verbose=not args.quiet)


if __name__ == "__main__":
    main()
