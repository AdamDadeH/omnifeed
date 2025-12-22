"""Command-line interface for OmniFeed."""

import sys
import uuid
import webbrowser
from datetime import datetime

import click
from rich.console import Console
from rich.table import Table

from omnifeed.config import Config
from omnifeed.models import Item, ContentType, ConsumptionType
from omnifeed.store import Store
from omnifeed.adapters import create_default_registry
from omnifeed.ranking.pipeline import create_default_pipeline


console = Console()


def get_store() -> Store:
    """Get the configured store."""
    config = Config.load()
    return config.create_store()


def format_age(dt: datetime) -> str:
    """Format a datetime as a human-readable age."""
    delta = datetime.utcnow() - dt
    seconds = delta.total_seconds()

    if seconds < 60:
        return "now"
    elif seconds < 3600:
        mins = int(seconds / 60)
        return f"{mins}m"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours}h"
    elif seconds < 604800:
        days = int(seconds / 86400)
        return f"{days}d"
    else:
        weeks = int(seconds / 604800)
        return f"{weeks}w"


@click.group()
@click.version_option()
def main() -> None:
    """OmniFeed - Unified content feed aggregator."""
    pass


# =============================================================================
# Sources commands
# =============================================================================


@main.group()
def sources() -> None:
    """Manage content sources."""
    pass


@sources.command("add")
@click.argument("url")
def sources_add(url: str) -> None:
    """Add a new source by URL."""
    registry = create_default_registry()
    adapter = registry.find_adapter(url)

    if not adapter:
        console.print(f"[red]No adapter found for URL: {url}[/red]")
        sys.exit(1)

    console.print(f"[dim]Resolving {url}...[/dim]")

    try:
        info = adapter.resolve(url)
    except ValueError as e:
        console.print(f"[red]Failed to resolve URL: {e}[/red]")
        sys.exit(1)

    # Check if already exists
    with get_store() as store:
        existing = store.get_source_by_uri(info.uri)
        if existing:
            console.print(f"[yellow]Source already exists: {existing.display_name}[/yellow]")
            sys.exit(1)

        # Show preview
        console.print()
        console.print(f"[bold]Name:[/bold] {info.display_name}")
        console.print(f"[bold]Type:[/bold] {info.source_type}")
        console.print(f"[bold]URI:[/bold] {info.uri}")
        if info.metadata.get("description"):
            desc = info.metadata["description"][:100]
            console.print(f"[bold]Description:[/bold] {desc}...")
        console.print()

        # Confirm
        if not click.confirm("Add this source?", default=True):
            console.print("[dim]Cancelled.[/dim]")
            return

        source = store.add_source(info)
        console.print(f"[green]Added source: {source.display_name} ({source.id})[/green]")

        # Offer to poll immediately
        if click.confirm("Poll for items now?", default=True):
            _poll_source(store, source.id, registry)


@sources.command("list")
def sources_list() -> None:
    """List all sources."""
    with get_store() as store:
        sources_list = store.list_sources()

        if not sources_list:
            console.print("[dim]No sources configured. Use 'omni-feed sources add <url>' to add one.[/dim]")
            return

        table = Table(show_header=True)
        table.add_column("ID", style="dim")
        table.add_column("Name")
        table.add_column("Type")
        table.add_column("Status")
        table.add_column("Last Polled")
        table.add_column("Items", justify="right")

        for source in sources_list:
            item_count = store.count_items(source_id=source.id)
            last_polled = format_age(source.last_polled_at) if source.last_polled_at else "never"

            status_color = "green" if source.status.value == "active" else "yellow"
            status = f"[{status_color}]{source.status.value}[/{status_color}]"

            table.add_row(
                source.id,
                source.display_name,
                source.source_type,
                status,
                last_polled,
                str(item_count),
            )

        console.print(table)


@sources.command("poll")
@click.argument("source_id", required=False)
def sources_poll(source_id: str | None) -> None:
    """Poll sources for new items."""
    registry = create_default_registry()

    with get_store() as store:
        if source_id:
            source = store.get_source(source_id)
            if not source:
                console.print(f"[red]Source not found: {source_id}[/red]")
                sys.exit(1)
            _poll_source(store, source.id, registry)
        else:
            # Poll all active sources
            sources_list = store.list_sources()
            active_sources = [s for s in sources_list if s.status.value == "active"]

            if not active_sources:
                console.print("[dim]No active sources to poll.[/dim]")
                return

            for source in active_sources:
                _poll_source(store, source.id, registry)


def _poll_source(store: Store, source_id: str, registry) -> None:
    """Poll a single source for new items."""
    source = store.get_source(source_id)
    if not source:
        return

    adapter = registry.get_adapter_by_type(source.source_type)
    if not adapter:
        console.print(f"[red]No adapter for source type: {source.source_type}[/red]")
        return

    console.print(f"[dim]Polling {source.display_name}...[/dim]")

    try:
        raw_items = adapter.poll(source.to_info(), since=source.last_polled_at)
    except ValueError as e:
        console.print(f"[red]Failed to poll: {e}[/red]")
        return

    new_count = 0
    for raw in raw_items:
        # Check if item already exists
        existing = store.get_item_by_external_id(source_id, raw.external_id)
        if existing:
            continue

        # Determine content type from metadata
        content_type = ContentType.ARTICLE  # Default for RSS
        enclosures = raw.raw_metadata.get("enclosures", [])
        for enc in enclosures:
            if enc.get("type", "").startswith("audio"):
                content_type = ContentType.AUDIO
                break
            elif enc.get("type", "").startswith("video"):
                content_type = ContentType.VIDEO
                break

        item = Item(
            id=uuid.uuid4().hex[:12],
            source_id=source_id,
            external_id=raw.external_id,
            url=raw.url,
            title=raw.title,
            creator_name=raw.raw_metadata.get("author", source.display_name),
            published_at=raw.published_at,
            ingested_at=datetime.utcnow(),
            content_type=content_type,
            consumption_type=ConsumptionType.ONE_SHOT,
            metadata=raw.raw_metadata,
        )
        store.upsert_item(item)
        new_count += 1

    store.update_source_poll_time(source_id, datetime.utcnow())
    console.print(f"[green]Added {new_count} new items from {source.display_name}[/green]")


@sources.command("disable")
@click.argument("source_id")
def sources_disable(source_id: str) -> None:
    """Disable a source (stop polling)."""
    with get_store() as store:
        source = store.get_source(source_id)
        if not source:
            console.print(f"[red]Source not found: {source_id}[/red]")
            sys.exit(1)

        store.disable_source(source_id)
        console.print(f"[yellow]Disabled source: {source.display_name}[/yellow]")


# =============================================================================
# Feed commands
# =============================================================================


@main.command("feed")
@click.option("--all", "show_all", is_flag=True, help="Include seen items")
@click.option("--limit", default=20, help="Number of items to show")
@click.option("--source", "source_id", help="Filter by source ID")
def feed(show_all: bool, limit: int, source_id: str | None) -> None:
    """Show the feed."""
    pipeline = create_default_pipeline()

    with get_store() as store:
        # Get items
        seen_filter = None if show_all else False
        items = store.get_items(
            seen=seen_filter,
            hidden=False,
            source_id=source_id,
            limit=limit * 2,  # Get more than needed for ranking
        )

        if not items:
            if show_all:
                console.print("[dim]No items in feed. Add sources and poll them.[/dim]")
            else:
                console.print("[dim]No unread items. Use --all to see all items.[/dim]")
            return

        # Rank items
        ranked = pipeline.rank(items)[:limit]

        # Get sources for display names
        sources_map = {s.id: s for s in store.list_sources()}

        # Display
        table = Table(show_header=True, show_lines=False)
        table.add_column("#", style="dim", width=3)
        table.add_column("Age", width=4)
        table.add_column("Source", width=20, no_wrap=True)
        table.add_column("Title")

        for i, item in enumerate(ranked, 1):
            source = sources_map.get(item.source_id)
            source_name = source.display_name if source else "Unknown"

            # Truncate title if needed
            title = item.title
            if len(title) > 60:
                title = title[:57] + "..."

            # Dim seen items
            style = "dim" if item.seen else ""

            table.add_row(
                str(i),
                format_age(item.published_at),
                source_name[:20],
                title,
                style=style,
            )

        console.print(table)
        console.print()
        console.print("[dim]Commands: open <#>, seen <#>, hide <#>[/dim]")

        # Store the ranked items for quick access
        _store_feed_cache(ranked)


# Simple cache for last displayed feed
_last_feed: list[Item] = []


def _store_feed_cache(items: list[Item]) -> None:
    global _last_feed
    _last_feed = items


def _get_cached_item(index: int) -> Item | None:
    if 0 < index <= len(_last_feed):
        return _last_feed[index - 1]
    return None


# =============================================================================
# Item commands
# =============================================================================


@main.command("open")
@click.argument("item_ref")
def open_item(item_ref: str) -> None:
    """Open an item in browser and mark as seen."""
    with get_store() as store:
        item = _resolve_item(store, item_ref)
        if not item:
            console.print(f"[red]Item not found: {item_ref}[/red]")
            sys.exit(1)

        # Open in browser
        webbrowser.open(item.url)
        console.print(f"[dim]Opening: {item.title}[/dim]")

        # Mark as seen
        store.mark_seen(item.id)


@main.command("seen")
@click.argument("item_ref")
def mark_seen(item_ref: str) -> None:
    """Mark an item as seen without opening."""
    with get_store() as store:
        item = _resolve_item(store, item_ref)
        if not item:
            console.print(f"[red]Item not found: {item_ref}[/red]")
            sys.exit(1)

        store.mark_seen(item.id)
        console.print(f"[green]Marked as seen: {item.title}[/green]")


@main.command("unseen")
@click.argument("item_ref")
def mark_unseen(item_ref: str) -> None:
    """Mark an item as unseen."""
    with get_store() as store:
        item = _resolve_item(store, item_ref)
        if not item:
            console.print(f"[red]Item not found: {item_ref}[/red]")
            sys.exit(1)

        store.mark_seen(item.id, seen=False)
        console.print(f"[green]Marked as unseen: {item.title}[/green]")


@main.command("hide")
@click.argument("item_ref")
def hide_item(item_ref: str) -> None:
    """Hide an item permanently."""
    with get_store() as store:
        item = _resolve_item(store, item_ref)
        if not item:
            console.print(f"[red]Item not found: {item_ref}[/red]")
            sys.exit(1)

        store.mark_hidden(item.id)
        console.print(f"[yellow]Hidden: {item.title}[/yellow]")


@main.command("show")
@click.argument("item_ref")
def show_item_detail(item_ref: str) -> None:
    """Show details for an item."""
    with get_store() as store:
        item = _resolve_item(store, item_ref)
        if not item:
            console.print(f"[red]Item not found: {item_ref}[/red]")
            sys.exit(1)

        sources_map = {s.id: s for s in store.list_sources()}
        source = sources_map.get(item.source_id)

        console.print()
        console.print(f"[bold]{item.title}[/bold]")
        console.print()
        console.print(f"[dim]ID:[/dim] {item.id}")
        console.print(f"[dim]Source:[/dim] {source.display_name if source else 'Unknown'}")
        console.print(f"[dim]Author:[/dim] {item.creator_name}")
        console.print(f"[dim]Published:[/dim] {item.published_at.strftime('%Y-%m-%d %H:%M')}")
        console.print(f"[dim]Type:[/dim] {item.content_type.value}")
        console.print(f"[dim]URL:[/dim] {item.url}")
        console.print()

        # Show description if available
        if item.metadata.get("content_text"):
            desc = item.metadata["content_text"][:500]
            console.print(f"[dim]Preview:[/dim]")
            console.print(desc)
            if len(item.metadata["content_text"]) > 500:
                console.print("[dim]...[/dim]")


def _resolve_item(store: Store, item_ref: str) -> Item | None:
    """Resolve an item reference (# from feed or ID)."""
    # Try as feed index first
    if item_ref.isdigit():
        index = int(item_ref)
        cached = _get_cached_item(index)
        if cached:
            return store.get_item(cached.id)

    # Try as item ID
    return store.get_item(item_ref)


# =============================================================================
# Stats command
# =============================================================================


@main.command("stats")
def show_stats() -> None:
    """Show feed statistics."""
    with get_store() as store:
        sources_list = store.list_sources()
        total_items = store.count_items(hidden=False)
        unseen_items = store.count_items(seen=False, hidden=False)
        hidden_items = store.count_items(hidden=True)

        console.print()
        console.print(f"[bold]Sources:[/bold] {len(sources_list)}")
        console.print(f"[bold]Total items:[/bold] {total_items}")
        console.print(f"[bold]Unread:[/bold] {unseen_items}")
        console.print(f"[bold]Hidden:[/bold] {hidden_items}")
        console.print()


if __name__ == "__main__":
    main()
