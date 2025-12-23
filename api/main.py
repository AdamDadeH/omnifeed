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
    score: float | None = None  # ML ranking score (click_prob * expected_reward)


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


# Feedback dimensions and explicit feedback models

class FeedbackOptionResponse(BaseModel):
    id: str
    dimension_id: str
    label: str
    description: str | None
    sort_order: int
    active: bool


class FeedbackDimensionResponse(BaseModel):
    id: str
    name: str
    description: str | None
    allow_multiple: bool
    active: bool
    options: list[FeedbackOptionResponse]


class ExplicitFeedbackRequest(BaseModel):
    item_id: str
    reward_score: float  # 0.0 - 5.0
    selections: dict[str, list[str]] = {}  # dimension_id -> option_ids
    notes: str | None = None
    completion_pct: float | None = None
    is_checkpoint: bool = False


class ExplicitFeedbackResponse(BaseModel):
    id: str
    item_id: str
    timestamp: datetime
    reward_score: float
    selections: dict[str, list[str]]
    notes: str | None
    completion_pct: float | None
    is_checkpoint: bool


# =============================================================================
# Application state
# =============================================================================


class AppState:
    store: Store
    registry: Any
    pipeline: Any


state = AppState()


def seed_feedback_dimensions(store: Store) -> None:
    """Seed initial feedback dimensions if they don't exist."""
    from omnifeed.models import FeedbackDimension, FeedbackOption

    existing = store.get_dimensions(active_only=False)
    existing_names = {d.name for d in existing}

    # Seed reward_type dimension
    if "reward_type" not in existing_names:
        dim = FeedbackDimension(
            id="reward_type",
            name="reward_type",
            description="What type of value did this content provide?",
            allow_multiple=True,
        )
        store.add_dimension(dim)

        options = [
            ("entertainment", "Entertainment", "Pure enjoyment or fun", 0),
            ("curiosity", "Curiosity", "Satisfied intellectual curiosity", 1),
            ("foundational", "Foundational Knowledge", "Core knowledge or skills", 2),
            ("expertise", "Targeted Expertise", "Specific expertise I need", 3),
        ]
        for opt_id, label, desc, order in options:
            store.add_option(FeedbackOption(
                id=f"reward_type_{opt_id}",
                dimension_id="reward_type",
                label=label,
                description=desc,
                sort_order=order,
            ))

    # Seed replayability dimension
    if "replayability" not in existing_names:
        dim = FeedbackDimension(
            id="replayability",
            name="replayability",
            description="How likely are you to revisit this content?",
            allow_multiple=False,
        )
        store.add_dimension(dim)

        options = [
            ("one_and_done", "One and Done", "Liked it but won't revisit", 0),
            ("might_revisit", "Might Revisit", "Could see myself coming back", 1),
            ("will_revisit", "Will Definitely Revisit", "So good I'll re-consume", 2),
            ("reference", "Reference Material", "Will come back to look things up", 3),
        ]
        for opt_id, label, desc, order in options:
            store.add_option(FeedbackOption(
                id=f"replayability_{opt_id}",
                dimension_id="replayability",
                label=label,
                description=desc,
                sort_order=order,
            ))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup application state."""
    config = Config.load()
    state.store = config.create_store()
    state.registry = create_default_registry()
    state.pipeline = create_default_pipeline()

    # Seed initial feedback dimensions
    seed_feedback_dimensions(state.store)

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

    # Collect new items first
    new_items: list[Item] = []
    for raw in raw_items:
        # Check by external_id first
        existing = state.store.get_item_by_external_id(source_id, raw.external_id)
        if existing:
            continue

        # Also check by URL as a fallback (prevents dupes from format changes)
        existing_by_url = state.store.get_item_by_url(raw.url)
        if existing_by_url:
            continue

        # Determine content type based on source type or enclosures
        content_type = ContentType.ARTICLE
        if source.source_type in ("youtube_channel", "youtube_playlist"):
            content_type = ContentType.VIDEO
        elif source.source_type in ("bandcamp", "bandcamp_fan", "qobuz_artist", "qobuz_label"):
            content_type = ContentType.AUDIO
        else:
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
        new_items.append(item)

    # Generate embeddings for new items (batched)
    if new_items:
        import logging

        # Text embeddings (title + description)
        try:
            from omnifeed.ranking.embeddings import get_embedding_service
            embedding_service = get_embedding_service()
            text_embeddings = embedding_service.embed_items(new_items)
            for item, emb in zip(new_items, text_embeddings):
                item.embeddings.append(emb)
        except Exception as e:
            logging.warning(f"Failed to generate text embeddings: {e}")

        # Transcript embeddings for YouTube videos
        if source.source_type in ("youtube_channel", "youtube_playlist"):
            try:
                from omnifeed.ranking.transcript_embeddings import embed_youtube_items
                transcript_embeddings = embed_youtube_items(new_items)
                for item in new_items:
                    if item.id in transcript_embeddings:
                        item.embeddings.append(transcript_embeddings[item.id])
                logging.info(f"Generated {len(transcript_embeddings)} transcript embeddings")
            except Exception as e:
                logging.warning(f"Failed to generate transcript embeddings: {e}")

    # Save items
    for item in new_items:
        state.store.upsert_item(item)

    state.store.update_source_poll_time(source_id, datetime.utcnow())

    return PollResult(
        source_id=source_id,
        source_name=source.display_name,
        new_items=len(new_items),
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
# Routes: Search
# =============================================================================


class SearchSuggestionResponse(BaseModel):
    url: str
    name: str
    source_type: str
    description: str
    thumbnail_url: str | None
    subscriber_count: int | None
    provider: str
    metadata: dict[str, Any]


class SearchResponse(BaseModel):
    query: str
    results: list[SearchSuggestionResponse]
    providers_used: list[str]


@app.get("/api/search", response_model=SearchResponse)
async def search_sources(
    q: str = Query(..., min_length=1, description="Search query"),
    providers: str | None = Query(None, description="Comma-separated provider IDs"),
    limit: int = Query(10, ge=1, le=50, description="Max results per provider"),
):
    """Search for sources to add."""
    from omnifeed.search import get_search_service

    service = get_search_service()

    # Parse provider filter
    provider_ids = None
    if providers:
        provider_ids = [p.strip() for p in providers.split(",")]

    # Run search
    suggestions = await service.search(q, limit=limit, provider_ids=provider_ids)

    return SearchResponse(
        query=q,
        results=[
            SearchSuggestionResponse(
                url=s.url,
                name=s.name,
                source_type=s.source_type,
                description=s.description,
                thumbnail_url=s.thumbnail_url,
                subscriber_count=s.subscriber_count,
                provider=s.provider,
                metadata=s.metadata,
            )
            for s in suggestions
        ],
        providers_used=provider_ids or service.provider_ids,
    )


@app.get("/api/search/providers")
def list_search_providers():
    """List available search providers."""
    from omnifeed.search import get_search_service

    service = get_search_service()

    return {
        "providers": [
            {
                "id": p.provider_id,
                "source_types": p.source_types,
            }
            for p in service.providers
        ]
    }


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
    import logging

    seen_filter = None if show_seen else False

    # Use pipeline's retrieve_and_rank to score ALL candidates
    ranked, stats = state.pipeline.retrieve_and_rank(
        store=state.store,
        seen=seen_filter,
        hidden=False,
        source_id=source_id,
        limit=limit + offset,  # Get enough for offset
    )

    # Apply offset
    ranked = ranked[offset:]

    # Log performance for monitoring
    logging.info(
        f"Feed request: {stats.scored_count} candidates, "
        f"{stats.total_time_ms:.0f}ms total"
    )

    # Get source names
    sources_map = {s.id: s for s in state.store.list_sources()}

    # Build response with scores
    item_responses = []
    for item in ranked:
        score = state.pipeline.score(item)
        item_responses.append(ItemResponse(
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
            score=round(score, 3),
        ))

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
# Routes: Feedback Dimensions
# =============================================================================


@app.get("/api/feedback/dimensions", response_model=list[FeedbackDimensionResponse])
def list_dimensions():
    """List all feedback dimensions with their options."""
    dimensions = state.store.get_dimensions(active_only=True)

    result = []
    for dim in dimensions:
        options = state.store.get_options(dimension_id=dim.id, active_only=True)
        result.append(FeedbackDimensionResponse(
            id=dim.id,
            name=dim.name,
            description=dim.description,
            allow_multiple=dim.allow_multiple,
            active=dim.active,
            options=[
                FeedbackOptionResponse(
                    id=opt.id,
                    dimension_id=opt.dimension_id,
                    label=opt.label,
                    description=opt.description,
                    sort_order=opt.sort_order,
                    active=opt.active,
                )
                for opt in options
            ],
        ))

    return result


# =============================================================================
# Routes: Explicit Feedback
# =============================================================================


@app.post("/api/feedback/explicit", response_model=ExplicitFeedbackResponse)
def record_explicit_feedback(request: ExplicitFeedbackRequest):
    """Record explicit user feedback for an item."""
    from omnifeed.models import ExplicitFeedback

    # Verify item exists
    item = state.store.get_item(request.item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Validate reward score range
    if not 0.0 <= request.reward_score <= 5.0:
        raise HTTPException(status_code=400, detail="Reward score must be between 0.0 and 5.0")

    feedback = ExplicitFeedback(
        id=uuid.uuid4().hex[:12],
        item_id=request.item_id,
        timestamp=datetime.utcnow(),
        reward_score=request.reward_score,
        selections=request.selections,
        notes=request.notes,
        completion_pct=request.completion_pct,
        is_checkpoint=request.is_checkpoint,
    )

    state.store.add_explicit_feedback(feedback)

    return ExplicitFeedbackResponse(
        id=feedback.id,
        item_id=feedback.item_id,
        timestamp=feedback.timestamp,
        reward_score=feedback.reward_score,
        selections=feedback.selections,
        notes=feedback.notes,
        completion_pct=feedback.completion_pct,
        is_checkpoint=feedback.is_checkpoint,
    )


@app.get("/api/feedback/explicit/{item_id}", response_model=ExplicitFeedbackResponse | None)
def get_item_explicit_feedback(item_id: str):
    """Get the most recent explicit feedback for an item."""
    feedback = state.store.get_item_feedback(item_id)
    if not feedback:
        return None

    return ExplicitFeedbackResponse(
        id=feedback.id,
        item_id=feedback.item_id,
        timestamp=feedback.timestamp,
        reward_score=feedback.reward_score,
        selections=feedback.selections,
        notes=feedback.notes,
        completion_pct=feedback.completion_pct,
        is_checkpoint=feedback.is_checkpoint,
    )


@app.get("/api/feedback/explicit", response_model=list[ExplicitFeedbackResponse])
def list_explicit_feedback(
    item_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    """List explicit feedback entries."""
    feedbacks = state.store.get_explicit_feedback(item_id=item_id, limit=limit)

    return [
        ExplicitFeedbackResponse(
            id=fb.id,
            item_id=fb.item_id,
            timestamp=fb.timestamp,
            reward_score=fb.reward_score,
            selections=fb.selections,
            notes=fb.notes,
            completion_pct=fb.completion_pct,
            is_checkpoint=fb.is_checkpoint,
        )
        for fb in feedbacks
    ]


# =============================================================================
# Routes: Model Training
# =============================================================================


class TrainResponse(BaseModel):
    status: str
    example_count: int = 0
    click_examples: int = 0
    reward_examples: int = 0
    # Diagnostic fields (when insufficient_data)
    total_items: int | None = None
    items_with_embeddings: int | None = None
    click_events: int | None = None
    explicit_feedbacks: int | None = None
    engaged_items: int | None = None
    missing_embeddings: int | None = None
    issues: list[str] | None = None


@app.post("/api/model/train", response_model=TrainResponse)
def train_ranking_model():
    """Train the ranking model on engagement data."""
    from omnifeed.ranking.model import get_ranking_model, DEFAULT_MODEL_PATH

    model = get_ranking_model()

    try:
        result = model.train(state.store)
        if result["status"] == "success":
            model.save(DEFAULT_MODEL_PATH)
        return TrainResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/model/status")
def get_model_status():
    """Get the current model training status."""
    from omnifeed.ranking.model import get_ranking_model, DEFAULT_MODEL_PATH

    model = get_ranking_model()

    return {
        "is_trained": model.is_trained,
        "source_count": len(model.source_stats),
        "model_path": str(DEFAULT_MODEL_PATH),
        "model_exists": DEFAULT_MODEL_PATH.exists(),
    }


class RefreshEmbeddingsResponse(BaseModel):
    updated_count: int
    skipped_count: int
    failed_count: int


@app.post("/api/model/refresh-embeddings", response_model=RefreshEmbeddingsResponse)
def refresh_embeddings(
    source_id: str | None = Query(None, description="Only refresh items from this source"),
    force: bool = Query(False, description="Regenerate even if embedding exists"),
    embedding_type: str = Query("text", description="Type of embedding to refresh"),
):
    """Regenerate embeddings for items."""
    import logging
    from omnifeed.ranking.embeddings import get_embedding_by_type

    items = state.store.get_items(source_id=source_id, limit=10000)

    # Filter items needing embeddings
    if force:
        to_embed = items
    else:
        to_embed = [
            item for item in items
            if not get_embedding_by_type(item.embeddings, embedding_type)
        ]

    if not to_embed:
        return RefreshEmbeddingsResponse(updated_count=0, skipped_count=len(items), failed_count=0)

    updated = 0
    failed = 0

    try:
        from omnifeed.ranking.embeddings import get_embedding_service
        embedding_service = get_embedding_service()

        # Batch embed
        new_embeddings = embedding_service.embed_items(to_embed)

        for item, emb in zip(to_embed, new_embeddings):
            try:
                # Remove old embedding of same type if exists
                item.embeddings = [e for e in item.embeddings if e.get("type") != embedding_type]
                item.embeddings.append(emb)
                state.store.upsert_item(item)
                updated += 1
            except Exception as e:
                logging.warning(f"Failed to save embedding for {item.id}: {e}")
                failed += 1

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding generation failed: {e}")

    return RefreshEmbeddingsResponse(
        updated_count=updated,
        skipped_count=len(items) - len(to_embed),
        failed_count=failed,
    )


@app.post("/api/model/refresh-transcripts", response_model=RefreshEmbeddingsResponse)
def refresh_transcript_embeddings(
    source_id: str | None = Query(None, description="Only refresh items from this source"),
    force: bool = Query(False, description="Regenerate even if transcript embedding exists"),
):
    """Generate transcript embeddings for YouTube videos."""
    import logging
    from omnifeed.ranking.embeddings import get_embedding_by_type
    from omnifeed.ranking.transcript_embeddings import embed_transcript

    # Get YouTube items
    items = state.store.get_items(source_id=source_id, limit=10000)

    # Filter to YouTube videos only
    youtube_items = [
        item for item in items
        if item.metadata.get("video_id") or "youtube.com" in item.url
    ]

    if not youtube_items:
        return RefreshEmbeddingsResponse(updated_count=0, skipped_count=len(items), failed_count=0)

    # Filter items needing transcript embeddings
    if force:
        to_embed = youtube_items
    else:
        to_embed = [
            item for item in youtube_items
            if not get_embedding_by_type(item.embeddings, "transcript")
        ]

    if not to_embed:
        return RefreshEmbeddingsResponse(
            updated_count=0,
            skipped_count=len(youtube_items),
            failed_count=0,
        )

    updated = 0
    failed = 0
    no_transcript = 0

    for item in to_embed:
        video_id = item.metadata.get("video_id")
        if not video_id:
            # Extract from URL
            import re
            match = re.search(r'youtube\.com/watch\?v=([^&]+)', item.url)
            if match:
                video_id = match.group(1)

        if not video_id:
            failed += 1
            continue

        try:
            emb = embed_transcript(video_id)
            if emb:
                # Remove old transcript embedding if exists
                item.embeddings = [e for e in item.embeddings if e.get("type") != "transcript"]
                item.embeddings.append(emb)
                state.store.upsert_item(item)
                updated += 1
                logging.info(f"Transcript embedding for: {item.title[:40]}")
            else:
                no_transcript += 1
        except Exception as e:
            logging.warning(f"Failed transcript for {item.id}: {e}")
            failed += 1

    logging.info(f"Transcript embeddings: {updated} updated, {no_transcript} no transcript, {failed} failed")

    return RefreshEmbeddingsResponse(
        updated_count=updated,
        skipped_count=len(youtube_items) - len(to_embed) + no_transcript,
        failed_count=failed,
    )


# =============================================================================
# Health check
# =============================================================================


@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
