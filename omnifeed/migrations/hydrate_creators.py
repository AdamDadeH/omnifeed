"""Hydrate existing items with extracted creators from descriptions.

This migration:
1. Scans all items for creator information in descriptions
2. Creates Creator entities for high-confidence extractions
3. Updates item metadata with extracted_creators array
4. Links items to primary creators where missing
"""

import json
import uuid
from datetime import datetime

from omnifeed.config import Config
from omnifeed.store.sqlite import SQLiteStore
from omnifeed.models import Creator, CreatorType, Source
from omnifeed.creators import extract_from_item


def hydrate_creators(
    dry_run: bool = False,
    min_confidence: float = 0.7,
    verbose: bool = True,
) -> dict:
    """Hydrate items with extracted creator information.

    Args:
        dry_run: If True, don't make any changes
        min_confidence: Minimum confidence threshold for creator extraction
        verbose: Print progress information

    Returns:
        Stats about the hydration process
    """
    config = Config.load()
    store = SQLiteStore(config.store_path)

    # Get all sources for source_type lookup
    sources = {s.id: s for s in store.list_sources()}

    # Stats
    stats = {
        "items_processed": 0,
        "items_updated": 0,
        "creators_created": 0,
        "creators_linked": 0,
        "primary_creators_set": 0,
    }

    # Process items in batches
    offset = 0
    batch_size = 100

    while True:
        items = store.get_items(limit=batch_size, offset=offset, seen=None, hidden=None)
        if not items:
            break

        for item in items:
            stats["items_processed"] += 1
            source = sources.get(item.source_id)
            source_type = source.source_type if source else "unknown"

            # Extract creators from description
            extracted = extract_from_item(item.metadata, item.title, source_type)
            high_conf = [e for e in extracted if e.confidence >= min_confidence]

            if not high_conf:
                continue

            # Build extracted_creators list
            extracted_creator_data = []
            for ec in high_conf:
                # Find or create creator
                creator = _find_or_create_creator(store, ec.name, dry_run, stats)
                if creator:
                    extracted_creator_data.append({
                        "creator_id": creator.id,
                        "name": ec.name,
                        "role": ec.role,
                        "confidence": ec.confidence,
                    })

            if not extracted_creator_data:
                continue

            # Check if item already has extracted_creators
            existing = item.metadata.get("extracted_creators", [])
            if existing:
                # Skip if already hydrated
                continue

            # Update item metadata
            new_metadata = dict(item.metadata)
            new_metadata["extracted_creators"] = extracted_creator_data

            if verbose:
                print(f"  {item.title[:50]}...")
                for ec in extracted_creator_data:
                    print(f"    + {ec['name']} ({ec['role']})")

            if not dry_run:
                # Update the item in the database
                store._conn.execute(
                    "UPDATE items SET metadata = ? WHERE id = ?",
                    (json.dumps(new_metadata), item.id)
                )
                store._conn.commit()

            stats["items_updated"] += 1

            # Set primary creator if missing
            if not item.creator_id and item.creator_name:
                primary_creator = _find_or_create_creator(store, item.creator_name, dry_run, stats)
                if primary_creator and not dry_run:
                    store._conn.execute(
                        "UPDATE items SET creator_id = ? WHERE id = ?",
                        (primary_creator.id, item.id)
                    )
                    store._conn.commit()
                    stats["primary_creators_set"] += 1

        offset += batch_size

        if verbose and offset % 500 == 0:
            print(f"Processed {offset} items...")

    if verbose:
        print(f"\nHydration complete:")
        print(f"  Items processed: {stats['items_processed']}")
        print(f"  Items updated: {stats['items_updated']}")
        print(f"  Creators created: {stats['creators_created']}")
        print(f"  Primary creators set: {stats['primary_creators_set']}")
        if dry_run:
            print("  (DRY RUN - no changes made)")

    store.close()
    return stats


def _find_or_create_creator(
    store: SQLiteStore,
    name: str,
    dry_run: bool,
    stats: dict,
) -> Creator | None:
    """Find or create a creator by name."""
    name = name.strip()
    if not name:
        return None

    # Try exact name match first
    existing = store.get_creator_by_name(name)
    if existing:
        return existing

    if dry_run:
        # In dry run, pretend we created it
        stats["creators_created"] += 1
        return Creator(
            id=f"dry_{uuid.uuid4().hex[:8]}",
            name=name,
            creator_type=CreatorType.UNKNOWN,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

    # Create new creator
    creator = Creator(
        id=uuid.uuid4().hex[:12],
        name=name,
        creator_type=CreatorType.UNKNOWN,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    store.add_creator(creator)
    stats["creators_created"] += 1
    return creator


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Hydrate items with extracted creators")
    parser.add_argument("--dry-run", action="store_true", help="Don't make changes")
    parser.add_argument("--confidence", type=float, default=0.7, help="Min confidence threshold")
    parser.add_argument("--quiet", action="store_true", help="Suppress output")
    args = parser.parse_args()

    hydrate_creators(
        dry_run=args.dry_run,
        min_confidence=args.confidence,
        verbose=not args.quiet,
    )
