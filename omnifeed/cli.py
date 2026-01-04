"""Command-line interface for OmniFeed."""

import sys
import uuid
import webbrowser
from datetime import datetime

import click
from rich.console import Console
from rich.table import Table

from omnifeed.config import Config
from omnifeed.models import Content, ContentType, ConsumptionType
from omnifeed.store import Store
from omnifeed.adapters import create_default_registry
from omnifeed.ranking.pipeline import create_default_pipeline, ContentRetriever


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
@click.option("--source", "source_type", help="Filter by source type (e.g., youtube, rss)")
def feed(show_all: bool, limit: int, source_type: str | None) -> None:
    """Show the feed."""
    pipeline = create_default_pipeline()
    retriever = ContentRetriever()

    with get_store() as store:
        seen_filter = None if show_all else False
        contents, _ = retriever.retrieve(
            store=store,
            seen=seen_filter,
            hidden=False,
            source_type=source_type,
            limit=limit * 2,
        )

        if not contents:
            if show_all:
                console.print("[dim]No content in feed. Add sources and poll them.[/dim]")
            else:
                console.print("[dim]No unread content. Use --all to see all content.[/dim]")
            return

        # Score and sort
        scored = [(c, pipeline.score(c)) for c in contents]
        scored.sort(key=lambda x: x[1], reverse=True)
        ranked = [c for c, _ in scored[:limit]]

        # Display
        table = Table(show_header=True, show_lines=False)
        table.add_column("#", style="dim", width=3)
        table.add_column("Age", width=4)
        table.add_column("Source", width=20, no_wrap=True)
        table.add_column("Title")

        for i, content in enumerate(ranked, 1):
            primary = store.get_primary_encoding(content.id)
            source_display = primary.source_type if primary else "unknown"

            title = content.title
            if len(title) > 60:
                title = title[:57] + "..."

            style = "dim" if content.seen else ""

            table.add_row(
                str(i),
                format_age(content.published_at),
                source_display[:20],
                title,
                style=style,
            )

        console.print(table)
        console.print()
        console.print("[dim]Commands: open <#>, seen <#>, show <#>[/dim]")

        _store_feed_cache(ranked)


# Simple cache for last displayed feed
_last_feed: list[Content] = []


def _store_feed_cache(contents: list[Content]) -> None:
    global _last_feed
    _last_feed = contents


def _get_cached_content(index: int) -> Content | None:
    if 0 < index <= len(_last_feed):
        return _last_feed[index - 1]
    return None


def _resolve_content(store: Store, ref: str) -> Content | None:
    """Resolve a content reference (# from feed or ID)."""
    if ref.isdigit():
        index = int(ref)
        cached = _get_cached_content(index)
        if cached:
            return store.get_content(cached.id)
    return store.get_content(ref)


# =============================================================================
# Content commands
# =============================================================================


@main.command("open")
@click.argument("ref")
def open_content(ref: str) -> None:
    """Open content in browser and mark as seen."""
    with get_store() as store:
        content = _resolve_content(store, ref)
        if not content:
            console.print(f"[red]Content not found: {ref}[/red]")
            sys.exit(1)

        primary = store.get_primary_encoding(content.id)
        if not primary:
            console.print(f"[red]No URL found for content[/red]")
            sys.exit(1)

        webbrowser.open(primary.uri)
        console.print(f"[dim]Opening: {content.title}[/dim]")

        store.mark_content_seen(content.id)


@main.command("seen")
@click.argument("ref")
def mark_seen(ref: str) -> None:
    """Mark content as seen without opening."""
    with get_store() as store:
        content = _resolve_content(store, ref)
        if not content:
            console.print(f"[red]Content not found: {ref}[/red]")
            sys.exit(1)

        store.mark_content_seen(content.id)
        console.print(f"[green]Marked as seen: {content.title}[/green]")


@main.command("unseen")
@click.argument("ref")
def mark_unseen(ref: str) -> None:
    """Mark content as unseen."""
    with get_store() as store:
        content = _resolve_content(store, ref)
        if not content:
            console.print(f"[red]Content not found: {ref}[/red]")
            sys.exit(1)

        store.mark_content_seen(content.id, seen=False)
        console.print(f"[green]Marked as unseen: {content.title}[/green]")


@main.command("hide")
@click.argument("ref")
def hide_content(ref: str) -> None:
    """Hide content permanently."""
    with get_store() as store:
        content = _resolve_content(store, ref)
        if not content:
            console.print(f"[red]Content not found: {ref}[/red]")
            sys.exit(1)

        store.mark_content_hidden(content.id)
        console.print(f"[yellow]Hidden: {content.title}[/yellow]")


@main.command("show")
@click.argument("ref")
def show_detail(ref: str) -> None:
    """Show details for content."""
    with get_store() as store:
        content = _resolve_content(store, ref)
        if not content:
            console.print(f"[red]Content not found: {ref}[/red]")
            sys.exit(1)

        encodings = store.get_encodings_for_content(content.id)
        primary = next((e for e in encodings if e.is_primary), encodings[0] if encodings else None)

        console.print()
        console.print(f"[bold]{content.title}[/bold]")
        console.print()
        console.print(f"[dim]ID:[/dim] {content.id}")
        console.print(f"[dim]Type:[/dim] {content.content_type.value}")
        console.print(f"[dim]Published:[/dim] {content.published_at.strftime('%Y-%m-%d %H:%M')}")
        console.print(f"[dim]Seen:[/dim] {content.seen}")

        if encodings:
            console.print()
            console.print("[bold]Available from:[/bold]")
            for enc in encodings:
                tag = " (primary)" if enc.is_primary else ""
                console.print(f"  - {enc.source_type}: {enc.uri}{tag}")

        if content.metadata.get("content_text"):
            desc = content.metadata["content_text"][:500]
            console.print()
            console.print("[dim]Preview:[/dim]")
            console.print(desc)
            if len(content.metadata["content_text"]) > 500:
                console.print("[dim]...[/dim]")


# =============================================================================
# Stats command
# =============================================================================


@main.command("stats")
def show_stats() -> None:
    """Show feed statistics."""
    with get_store() as store:
        sources_list = store.list_sources()
        total_content = store.count_content(hidden=False)
        unseen_content = store.count_content(seen=False, hidden=False)
        hidden_content = store.count_content(hidden=True)

        console.print()
        console.print(f"[bold]Sources:[/bold] {len(sources_list)}")
        console.print(f"[bold]Total content:[/bold] {total_content}")
        console.print(f"[bold]Unread:[/bold] {unseen_content}")
        console.print(f"[bold]Hidden:[/bold] {hidden_content}")
        console.print()


if __name__ == "__main__":
    main()
