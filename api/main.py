"""FastAPI server exposing OmniFeed functionality."""

import uuid
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from omnifeed.config import Config
from omnifeed.models import Item, ContentType, ConsumptionType, SourceStatus
from omnifeed.store import Store
from omnifeed.adapters import create_default_registry
from omnifeed.ranking.pipeline import create_default_pipeline


# =============================================================================
# Pydantic models for API
# =============================================================================


class SourceResponse(BaseModel):
    id: str
    source_type: str
    uri: str
    display_name: str
    avatar_url: str | None
    status: str
    created_at: datetime
    last_polled_at: datetime | None
    item_count: int


class SourcePreview(BaseModel):
    source_type: str
    uri: str
    display_name: str
    avatar_url: str | None
    description: str | None


class AddSourceRequest(BaseModel):
    url: str


class ItemResponse(BaseModel):
    id: str
    source_id: str
    source_name: str
    url: str
    title: str
    creator_name: str
    published_at: datetime
    content_type: str
    seen: bool
    hidden: bool
    metadata: dict[str, Any]


class FeedResponse(BaseModel):
    items: list[ItemResponse]
    total_count: int
    unseen_count: int


class StatsResponse(BaseModel):
    source_count: int
    total_items: int
    unseen_items: int
    hidden_items: int


class PollResult(BaseModel):
    source_id: str
    source_name: str
    new_items: int


class FeedbackEventRequest(BaseModel):
    item_id: str
    event_type: str  # "reading_complete", "click", "hover", "hide", etc.
    payload: dict[str, Any] = {}


class FeedbackEventResponse(BaseModel):
    id: str
    item_id: str
    event_type: str
    timestamp: datetime
    payload: dict[str, Any]


class StatsFilter(BaseModel):
    """Defines the slice of data an aggregation covers."""
    source_id: str | None = None
    source_name: str | None = None
    content_type: str | None = None
    # Future: time_period, creator, etc.


class EngagementStats(BaseModel):
    """Aggregated engagement metrics."""
    total_events: int
    total_engagements: int
    avg_time_spent_ms: float
    avg_progress_pct: float
    completion_rate: float
    total_time_spent_ms: float


class StatsSlice(BaseModel):
    """A slice of data with its filter and stats."""
    filter: StatsFilter
    stats: EngagementStats


class FeedbackStatsResponse(BaseModel):
    total_events: int
    slices: list[StatsSlice]
    recent_events: list[FeedbackEventResponse]


# =============================================================================
# Application state
# =============================================================================


class AppState:
    store: Store
    registry: Any
    pipeline: Any


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup application state."""
    config = Config.load()
    state.store = config.create_store()
    state.registry = create_default_registry()
    state.pipeline = create_default_pipeline()
    yield
    state.store.close()


# =============================================================================
# FastAPI app
# =============================================================================


app = FastAPI(
    title="OmniFeed API",
    description="Unified content feed aggregator",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Routes: Sources
# =============================================================================


@app.get("/api/sources", response_model=list[SourceResponse])
def list_sources():
    """List all sources."""
    sources = state.store.list_sources()
    return [
        SourceResponse(
            id=s.id,
            source_type=s.source_type,
            uri=s.uri,
            display_name=s.display_name,
            avatar_url=s.avatar_url,
            status=s.status.value,
            created_at=s.created_at,
            last_polled_at=s.last_polled_at,
            item_count=state.store.count_items(source_id=s.id),
        )
        for s in sources
    ]


@app.post("/api/sources/preview", response_model=SourcePreview)
def preview_source(request: AddSourceRequest):
    """Preview a source before adding it."""
    adapter = state.registry.find_adapter(request.url)
    if not adapter:
        raise HTTPException(status_code=400, detail="No adapter found for this URL")

    try:
        info = adapter.resolve(request.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return SourcePreview(
        source_type=info.source_type,
        uri=info.uri,
        display_name=info.display_name,
        avatar_url=info.avatar_url,
        description=info.metadata.get("description"),
    )


@app.post("/api/sources", response_model=SourceResponse)
def add_source(request: AddSourceRequest):
    """Add a new source."""
    adapter = state.registry.find_adapter(request.url)
    if not adapter:
        raise HTTPException(status_code=400, detail="No adapter found for this URL")

    try:
        info = adapter.resolve(request.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Check if already exists
    existing = state.store.get_source_by_uri(info.uri)
    if existing:
        raise HTTPException(status_code=409, detail="Source already exists")

    source = state.store.add_source(info)

    return SourceResponse(
        id=source.id,
        source_type=source.source_type,
        uri=source.uri,
        display_name=source.display_name,
        avatar_url=source.avatar_url,
        status=source.status.value,
        created_at=source.created_at,
        last_polled_at=source.last_polled_at,
        item_count=0,
    )


@app.post("/api/sources/{source_id}/poll", response_model=PollResult)
def poll_source(source_id: str):
    """Poll a source for new items."""
    source = state.store.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    adapter = state.registry.get_adapter_by_type(source.source_type)
    if not adapter:
        raise HTTPException(status_code=500, detail=f"No adapter for {source.source_type}")

    try:
        raw_items = adapter.poll(source.to_info(), since=source.last_polled_at)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    new_count = 0
    for raw in raw_items:
        existing = state.store.get_item_by_external_id(source_id, raw.external_id)
        if existing:
            continue

        # Determine content type
        content_type = ContentType.ARTICLE
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
        state.store.upsert_item(item)
        new_count += 1

    state.store.update_source_poll_time(source_id, datetime.utcnow())

    return PollResult(
        source_id=source_id,
        source_name=source.display_name,
        new_items=new_count,
    )


@app.post("/api/sources/poll-all", response_model=list[PollResult])
def poll_all_sources():
    """Poll all active sources."""
    sources = state.store.list_sources()
    results = []

    for source in sources:
        if source.status != SourceStatus.ACTIVE:
            continue

        try:
            result = poll_source(source.id)
            results.append(result)
        except HTTPException:
            # Skip failed sources
            pass

    return results


@app.delete("/api/sources/{source_id}")
def disable_source(source_id: str):
    """Disable a source."""
    source = state.store.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    state.store.disable_source(source_id)
    return {"status": "disabled"}


# =============================================================================
# Routes: Feed
# =============================================================================


@app.get("/api/feed", response_model=FeedResponse)
def get_feed(
    show_seen: bool = Query(False, description="Include seen items"),
    source_id: str | None = Query(None, description="Filter by source"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Get the ranked feed."""
    seen_filter = None if show_seen else False

    items = state.store.get_items(
        seen=seen_filter,
        hidden=False,
        source_id=source_id,
        limit=limit * 2,  # Get more for ranking
        offset=offset,
    )

    # Rank items
    ranked = state.pipeline.rank(items)[:limit]

    # Get source names
    sources_map = {s.id: s for s in state.store.list_sources()}

    item_responses = [
        ItemResponse(
            id=item.id,
            source_id=item.source_id,
            source_name=sources_map.get(item.source_id, type("", (), {"display_name": "Unknown"})).display_name,
            url=item.url,
            title=item.title,
            creator_name=item.creator_name,
            published_at=item.published_at,
            content_type=item.content_type.value,
            seen=item.seen,
            hidden=item.hidden,
            metadata=item.metadata,
        )
        for item in ranked
    ]

    return FeedResponse(
        items=item_responses,
        total_count=state.store.count_items(hidden=False),
        unseen_count=state.store.count_items(seen=False, hidden=False),
    )


@app.get("/api/items/{item_id}", response_model=ItemResponse)
def get_item(item_id: str):
    """Get a single item."""
    item = state.store.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    sources_map = {s.id: s for s in state.store.list_sources()}
    source = sources_map.get(item.source_id)

    return ItemResponse(
        id=item.id,
        source_id=item.source_id,
        source_name=source.display_name if source else "Unknown",
        url=item.url,
        title=item.title,
        creator_name=item.creator_name,
        published_at=item.published_at,
        content_type=item.content_type.value,
        seen=item.seen,
        hidden=item.hidden,
        metadata=item.metadata,
    )


@app.post("/api/items/{item_id}/seen")
def mark_item_seen(item_id: str):
    """Mark an item as seen."""
    item = state.store.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    state.store.mark_seen(item_id, seen=True)
    return {"status": "seen"}


@app.delete("/api/items/{item_id}/seen")
def mark_item_unseen(item_id: str):
    """Mark an item as unseen."""
    item = state.store.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    state.store.mark_seen(item_id, seen=False)
    return {"status": "unseen"}


@app.post("/api/items/{item_id}/hide")
def hide_item(item_id: str):
    """Hide an item."""
    item = state.store.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    state.store.mark_hidden(item_id, hidden=True)
    return {"status": "hidden"}


# =============================================================================
# Routes: Stats
# =============================================================================


@app.get("/api/stats", response_model=StatsResponse)
def get_stats():
    """Get feed statistics."""
    return StatsResponse(
        source_count=len(state.store.list_sources()),
        total_items=state.store.count_items(hidden=False),
        unseen_items=state.store.count_items(seen=False, hidden=False),
        hidden_items=state.store.count_items(hidden=True),
    )


# =============================================================================
# Routes: Feedback
# =============================================================================


@app.post("/api/feedback", response_model=FeedbackEventResponse)
def record_feedback(request: FeedbackEventRequest):
    """Record a feedback event for training."""
    from omnifeed.models import FeedbackEvent

    # Verify item exists
    item = state.store.get_item(request.item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    event = FeedbackEvent(
        id=uuid.uuid4().hex[:12],
        item_id=request.item_id,
        timestamp=datetime.utcnow(),
        event_type=request.event_type,
        payload=request.payload,
    )

    state.store.add_feedback_event(event)

    return FeedbackEventResponse(
        id=event.id,
        item_id=event.item_id,
        event_type=event.event_type,
        timestamp=event.timestamp,
        payload=event.payload,
    )


@app.get("/api/feedback", response_model=list[FeedbackEventResponse])
def list_feedback(
    item_id: str | None = Query(None),
    event_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    """List feedback events."""
    events = state.store.get_feedback_events(
        item_id=item_id,
        event_type=event_type,
        limit=limit,
    )

    return [
        FeedbackEventResponse(
            id=e.id,
            item_id=e.item_id,
            event_type=e.event_type,
            timestamp=e.timestamp,
            payload=e.payload,
        )
        for e in events
    ]


@app.get("/api/feedback/stats", response_model=FeedbackStatsResponse)
def get_feedback_stats(
    source_id: str | None = Query(None, description="Filter stats to a specific source"),
):
    """Get feedback statistics, optionally filtered by source."""
    # Get all events (up to 10000 for stats)
    all_events = state.store.get_feedback_events(limit=10000)

    # Build item -> source mapping
    item_to_source: dict[str, str] = {}
    for e in all_events:
        if e.item_id not in item_to_source:
            item = state.store.get_item(e.item_id)
            if item:
                item_to_source[e.item_id] = item.source_id

    # Get source names
    sources_map = {s.id: s for s in state.store.list_sources()}

    # Filter events by source if specified
    if source_id:
        all_events = [e for e in all_events if item_to_source.get(e.item_id) == source_id]

    # Group events by source
    events_by_source: dict[str, list] = {}
    for e in all_events:
        src_id = item_to_source.get(e.item_id)
        if src_id:
            if src_id not in events_by_source:
                events_by_source[src_id] = []
            events_by_source[src_id].append(e)

    # Calculate per-source stats
    engagement_types = ("reading_complete", "watching_complete", "listening_complete", "engagement_complete")
    slices: list[StatsSlice] = []

    for source_id, events in events_by_source.items():
        source = sources_map.get(source_id)
        source_name = source.display_name if source else "Unknown"

        engagement_events = [e for e in events if e.event_type in engagement_types]

        avg_time = 0.0
        avg_progress = 0.0
        completion_rate = 0.0
        total_time = 0.0

        if engagement_events:
            times = [e.payload.get("time_spent_ms", 0) for e in engagement_events]
            progress = [e.payload.get("max_scroll_pct", e.payload.get("progress_pct", 0)) for e in engagement_events]
            completions = [1 if e.payload.get("completed", False) else 0 for e in engagement_events]

            avg_time = sum(times) / len(times)
            avg_progress = sum(progress) / len(progress)
            completion_rate = sum(completions) / len(completions) * 100
            total_time = sum(times)

        slices.append(StatsSlice(
            filter=StatsFilter(
                source_id=source_id,
                source_name=source_name,
            ),
            stats=EngagementStats(
                total_events=len(events),
                total_engagements=len(engagement_events),
                avg_time_spent_ms=avg_time,
                avg_progress_pct=avg_progress,
                completion_rate=completion_rate,
                total_time_spent_ms=total_time,
            ),
        ))

    # Sort by total engagements descending
    slices.sort(key=lambda s: s.stats.total_engagements, reverse=True)

    # Get recent events
    recent = all_events[:20]

    return FeedbackStatsResponse(
        total_events=len(all_events),
        slices=slices,
        recent_events=[
            FeedbackEventResponse(
                id=e.id,
                item_id=e.item_id,
                event_type=e.event_type,
                timestamp=e.timestamp,
                payload=e.payload,
            )
            for e in recent
        ],
    )


# =============================================================================
# Health check
# =============================================================================


@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
