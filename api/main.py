"""FastAPI server exposing OmniFeed functionality."""

import uuid
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Any

import asyncio
import json
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from omnifeed.config import Config
from omnifeed.models import Item, ContentType, ConsumptionType, SourceStatus, Creator, CreatorType, ItemAttribution
from omnifeed.store import Store
from omnifeed.adapters import create_default_registry
from omnifeed.ranking.pipeline import create_default_pipeline
from omnifeed.creators import extract_from_item
import logging

# Configure logging to show INFO level for our modules
logging.basicConfig(level=logging.INFO)
logging.getLogger("omnifeed").setLevel(logging.INFO)
logging.getLogger("api").setLevel(logging.INFO)

logger = logging.getLogger(__name__)


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


class AttributionResponse(BaseModel):
    source_id: str
    source_name: str
    discovered_at: datetime
    rank: int | None
    context: str | None


class ItemResponse(BaseModel):
    id: str
    source_id: str
    source_name: str
    url: str
    title: str
    creator_id: str | None = None
    creator_name: str
    published_at: datetime
    content_type: str
    seen: bool
    hidden: bool
    metadata: dict[str, Any]
    canonical_ids: dict[str, str] = {}
    attributions: list[AttributionResponse] = []
    score: float | None = None  # ML ranking score (click_prob * expected_reward)


class EncodingResponse(BaseModel):
    """Represents a way to access content (URL, deep link, etc.)."""
    id: str
    source_type: str  # "youtube", "rss", "bandcamp", etc.
    external_id: str
    uri: str
    media_type: str | None = None
    metadata: dict[str, Any] = {}
    is_primary: bool = False


class ContentResponse(BaseModel):
    """Content-centric response (new model, replaces ItemResponse)."""
    id: str
    title: str
    content_type: str
    published_at: datetime
    seen: bool
    hidden: bool
    metadata: dict[str, Any] = {}
    canonical_ids: dict[str, str] = {}
    creator_ids: list[str] = []
    # Primary encoding info (convenience fields)
    url: str  # Primary encoding URI
    source_type: str  # Primary encoding source_type
    # All encodings (where this content lives)
    encodings: list[EncodingResponse] = []
    score: float | None = None


class ContentFeedResponse(BaseModel):
    """Feed response using Content model."""
    items: list[ContentResponse]
    total_count: int
    unseen_count: int


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


# Creator models

class CreatorResponse(BaseModel):
    id: str
    name: str
    creator_type: str
    avatar_url: str | None
    bio: str | None
    url: str | None
    item_count: int = 0
    avg_score: float | None = None


class CreatorStatsResponse(BaseModel):
    creator_id: str
    total_items: int
    total_feedback_events: int
    avg_reward_score: float | None
    content_types: dict[str, int]


class SourceStatsResponse(BaseModel):
    source_id: str
    total_items: int
    total_feedback_events: int
    avg_reward_score: float | None
    unique_creators: int


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

# CORS for local development and browser extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for extension support
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


def _find_or_create_creator(
    store: Store,
    name: str,
    source_type: str,
    raw_metadata: dict[str, Any],
) -> Creator | None:
    """Find or create a creator based on available metadata.

    Matching strategy:
    1. External IDs (e.g., YouTube channel_id) - most reliable
    2. Exact name match (case-insensitive)
    3. Create new creator if no match

    Returns None if name is empty/whitespace.
    """
    name = name.strip()
    if not name:
        return None

    # Build external_ids from metadata based on source type
    external_ids: dict[str, str] = {}
    avatar_url: str | None = None

    if source_type in ("youtube_channel", "youtube_playlist"):
        channel_id = raw_metadata.get("channel_id")
        if channel_id:
            external_ids["youtube"] = channel_id
        # Use channel thumbnail as avatar if available
        avatar_url = raw_metadata.get("thumbnail")

    # Try to find by external ID first (most reliable)
    for id_type, id_value in external_ids.items():
        existing = store.find_creator_by_external_id(id_type, id_value)
        if existing:
            logger.debug(f"Found creator by {id_type} ID: {existing.name}")
            return existing

    # Try exact name match (case-insensitive)
    existing = store.get_creator_by_name(name)
    if existing:
        # If we have new external IDs, update the creator
        if external_ids:
            updated = False
            for id_type, id_value in external_ids.items():
                if id_type not in existing.external_ids:
                    existing.external_ids[id_type] = id_value
                    updated = True
            if updated:
                existing.updated_at = datetime.utcnow()
                store.update_creator(existing)
                logger.debug(f"Updated creator with new external IDs: {existing.name}")
        return existing

    # Create new creator
    creator = Creator(
        id=uuid.uuid4().hex[:12],
        name=name,
        creator_type=CreatorType.UNKNOWN,
        external_ids=external_ids,
        avatar_url=avatar_url,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    store.add_creator(creator)
    logger.info(f"Created new creator: {creator.name} (id={creator.id})")
    return creator


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

        # Extract creator info and find or create creator
        creator_name = raw.raw_metadata.get("author", source.display_name)
        creator = _find_or_create_creator(
            store=state.store,
            name=creator_name,
            source_type=source.source_type,
            raw_metadata=raw.raw_metadata,
        )

        # Extract additional creators from description
        extracted_creators = extract_from_item(raw.raw_metadata, raw.title, source.source_type)
        extracted_creator_data = []
        for ec in extracted_creators:
            if ec.confidence >= 0.7:
                # Create or find Creator entity for high-confidence extractions
                extracted_creator = _find_or_create_creator(
                    store=state.store,
                    name=ec.name,
                    source_type=source.source_type,
                    raw_metadata={},  # No additional metadata for extracted creators
                )
                if extracted_creator:
                    extracted_creator_data.append({
                        "creator_id": extracted_creator.id,
                        "name": ec.name,
                        "role": ec.role,
                        "confidence": ec.confidence,
                    })
                    logger.debug(f"Extracted creator: {ec.name} ({ec.role}) -> {extracted_creator.id}")

        # Add extracted creators to metadata
        item_metadata = dict(raw.raw_metadata)
        if extracted_creator_data:
            item_metadata["extracted_creators"] = extracted_creator_data

        item = Item(
            id=uuid.uuid4().hex[:12],
            source_id=source_id,
            external_id=raw.external_id,
            url=raw.url,
            title=raw.title,
            creator_id=creator.id if creator else None,
            creator_name=creator_name,
            published_at=raw.published_at,
            ingested_at=datetime.utcnow(),
            content_type=content_type,
            consumption_type=ConsumptionType.ONE_SHOT,
            metadata=item_metadata,
        )
        new_items.append(item)

    # Ingest items with unified pipeline (embeddings + persistence)
    if new_items:
        from omnifeed.ingestion import get_ingestion_pipeline
        pipeline = get_ingestion_pipeline(state.store)
        pipeline.ingest(new_items, source_type=source.source_type)

        # Create attributions linking items to the source
        for item in new_items:
            attribution = ItemAttribution(
                id=uuid.uuid4().hex[:12],
                item_id=item.id,
                source_id=source_id,
                external_id=item.external_id,
                is_primary=True,  # First source is primary
                discovered_at=datetime.utcnow(),
            )
            state.store.upsert_attribution(attribution)

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
def delete_source(source_id: str, keep_items: bool = Query(False, description="Keep items when deleting source")):
    """Delete a source and its items."""
    source = state.store.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    items_deleted = state.store.delete_source(source_id, delete_items=not keep_items)
    return {"status": "deleted", "items_deleted": items_deleted}


@app.get("/api/sources/{source_id}/stats", response_model=SourceStatsResponse)
def get_source_stats(source_id: str):
    """Get aggregated stats for a source."""
    source = state.store.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    stats = state.store.get_source_stats(source_id)
    return SourceStatsResponse(
        source_id=stats.source_id,
        total_items=stats.total_items,
        total_feedback_events=stats.total_feedback_events,
        avg_reward_score=stats.avg_reward_score,
        unique_creators=stats.unique_creators,
    )


# =============================================================================
# Routes: Creators
# =============================================================================


@app.get("/api/creators", response_model=list[CreatorResponse])
def list_creators(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List all creators."""
    creators = state.store.list_creators(limit=limit, offset=offset)
    result = []
    for creator in creators:
        stats = state.store.get_creator_stats(creator.id)
        result.append(CreatorResponse(
            id=creator.id,
            name=creator.name,
            creator_type=creator.creator_type.value,
            avatar_url=creator.avatar_url,
            bio=creator.bio,
            url=creator.url,
            item_count=stats.total_items,
            avg_score=stats.avg_reward_score,
        ))
    return result


@app.get("/api/creators/{creator_id}", response_model=CreatorResponse)
def get_creator(creator_id: str):
    """Get a creator by ID."""
    creator = state.store.get_creator(creator_id)
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")

    stats = state.store.get_creator_stats(creator_id)
    return CreatorResponse(
        id=creator.id,
        name=creator.name,
        creator_type=creator.creator_type.value,
        avatar_url=creator.avatar_url,
        bio=creator.bio,
        url=creator.url,
        item_count=stats.total_items,
        avg_score=stats.avg_reward_score,
    )


@app.get("/api/creators/{creator_id}/stats", response_model=CreatorStatsResponse)
def get_creator_stats(creator_id: str):
    """Get aggregated stats for a creator."""
    creator = state.store.get_creator(creator_id)
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")

    stats = state.store.get_creator_stats(creator_id)
    return CreatorStatsResponse(
        creator_id=stats.creator_id,
        total_items=stats.total_items,
        total_feedback_events=stats.total_feedback_events,
        avg_reward_score=stats.avg_reward_score,
        content_types=stats.content_types,
    )


@app.get("/api/creators/{creator_id}/items", response_model=list[ItemResponse])
def get_creator_items(
    creator_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Get items by a specific creator."""
    creator = state.store.get_creator(creator_id)
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")

    items = state.store.get_items_by_creator(creator_id, limit=limit, offset=offset)
    result = []
    for item in items:
        source = state.store.get_source(item.source_id)
        result.append(ItemResponse(
            id=item.id,
            source_id=item.source_id,
            source_name=source.display_name if source else "Unknown",
            url=item.url,
            title=item.title,
            creator_id=item.creator_id,
            creator_name=item.creator_name,
            published_at=item.published_at,
            content_type=item.content_type.value,
            seen=item.seen,
            hidden=item.hidden,
            metadata=item.metadata,
            canonical_ids=item.canonical_ids,
        ))
    return result


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
    source_id: str | None = Query(None, description="Filter by source type"),
    objective: str | None = Query(None, description="Ranking objective (entertainment, curiosity, etc.)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Get the ranked feed.

    Sources from Content+Encoding internally, returns ItemResponse for backwards compat.
    """
    import logging
    from omnifeed.ranking.pipeline import ContentRetriever

    seen_filter = None if show_seen else False

    # Use ContentRetriever (new model)
    retriever = ContentRetriever()
    contents, retrieval_stats = retriever.retrieve(
        store=state.store,
        seen=seen_filter,
        hidden=False,
        source_type=source_id,  # source_id param now maps to source_type
        limit=limit + offset,
    )

    # Score and sort
    scored = [(c, state.pipeline.score(c, objective=objective)) for c in contents]
    scored.sort(key=lambda x: x[1], reverse=True)
    scored = scored[offset:offset + limit]

    logging.info(f"Feed request: {len(contents)} candidates scored")

    # Build response (ItemResponse format for backwards compat)
    item_responses = []
    for content, score in scored:
        # Get primary encoding for source info
        primary = state.store.get_primary_encoding(content.id)
        source_type = primary.source_type if primary else ""
        url = primary.uri if primary else ""

        # Get attributions (still works - same IDs)
        attributions = state.store.get_attributions(content.id)
        attr_responses = [
            AttributionResponse(
                source_id=attr.source_id,
                source_name=attr.source_id,  # Use source_type as name
                discovered_at=attr.discovered_at,
                rank=attr.rank,
                context=attr.context,
            )
            for attr in attributions
        ]

        # Map Content fields to ItemResponse
        item_responses.append(ItemResponse(
            id=content.id,
            source_id=source_type,
            source_name=source_type,
            url=url,
            title=content.title,
            creator_id=content.creator_ids[0] if content.creator_ids else None,
            creator_name="",  # Deprecated - use creator_ids
            published_at=content.published_at,
            content_type=content.content_type.value,
            seen=content.seen,
            hidden=content.hidden,
            metadata=content.metadata,
            canonical_ids=content.canonical_ids,
            attributions=attr_responses,
            score=round(score, 3),
        ))

    return FeedResponse(
        items=item_responses,
        total_count=state.store.count_content(hidden=False),
        unseen_count=state.store.count_content(seen=False, hidden=False),
    )


class RatedItemResponse(BaseModel):
    item: ItemResponse
    rating: float
    rated_at: datetime
    selections: dict[str, list[str]] = {}


class RatedItemsResponse(BaseModel):
    items: list[RatedItemResponse]
    total_count: int


@app.get("/api/feed/rated", response_model=RatedItemsResponse)
def get_rated_items(limit: int = 50, offset: int = 0):
    """Get items that have explicit feedback (ratings)."""
    import json
    sources_map = {s.id: s for s in state.store.list_sources()}

    # Query items with explicit feedback using explicit column names
    cursor = state.store._conn.execute("""
        SELECT
            i.id, i.source_id, i.url, i.title, i.creator_id, i.creator_name,
            i.published_at, i.content_type, i.seen, i.hidden, i.metadata, i.canonical_ids,
            ef.reward_score, ef.timestamp as rated_at, ef.selections
        FROM items i
        JOIN explicit_feedback ef ON ef.item_id = i.id
        ORDER BY ef.timestamp DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))

    rated_items = []
    for row in cursor.fetchall():
        (item_id, source_id, url, title, creator_id, creator_name,
         published_at, content_type, seen, hidden, metadata_json, canonical_ids_json,
         reward_score, rated_at, selections_json) = row

        source = sources_map.get(source_id)
        item_response = ItemResponse(
            id=item_id,
            source_id=source_id,
            source_name=source.display_name if source else "Unknown",
            url=url,
            title=title,
            creator_id=creator_id,
            creator_name=creator_name,
            published_at=published_at,
            content_type=content_type,
            seen=bool(seen),
            hidden=bool(hidden),
            metadata=json.loads(metadata_json) if metadata_json else {},
            canonical_ids=json.loads(canonical_ids_json) if canonical_ids_json else {},
        )

        rated_items.append(RatedItemResponse(
            item=item_response,
            rating=reward_score,
            rated_at=rated_at,
            selections=json.loads(selections_json) if selections_json else {},
        ))

    # Get total count
    cursor = state.store._conn.execute("""
        SELECT COUNT(DISTINCT i.id)
        FROM items i
        JOIN explicit_feedback ef ON ef.item_id = i.id
    """)
    total = cursor.fetchone()[0]

    return RatedItemsResponse(items=rated_items, total_count=total)


class QueueItemsResponse(BaseModel):
    items: list[ItemResponse]
    total_count: int


@app.get("/api/feed/queue", response_model=QueueItemsResponse)
def get_queue_items(limit: int = 100, offset: int = 0):
    """Get items that were saved from Explore (explore_save feedback events)."""
    import json
    sources_map = {s.id: s for s in state.store.list_sources()}

    # Query items with explore_save feedback events
    cursor = state.store._conn.execute("""
        SELECT DISTINCT
            i.id, i.source_id, i.url, i.title, i.creator_id, i.creator_name,
            i.published_at, i.content_type, i.seen, i.hidden, i.metadata, i.canonical_ids,
            fe.timestamp as saved_at
        FROM items i
        JOIN feedback_events fe ON fe.item_id = i.id
        WHERE fe.event_type = 'explore_save'
        ORDER BY fe.timestamp DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))

    queue_items = []
    for row in cursor.fetchall():
        (item_id, source_id, url, title, creator_id, creator_name,
         published_at, content_type, seen, hidden, metadata_json, canonical_ids_json,
         saved_at) = row

        source = sources_map.get(source_id)
        item_response = ItemResponse(
            id=item_id,
            source_id=source_id,
            source_name=source.display_name if source else "Discovered",
            url=url,
            title=title,
            creator_id=creator_id,
            creator_name=creator_name,
            published_at=published_at,
            content_type=content_type,
            seen=bool(seen),
            hidden=bool(hidden),
            metadata=json.loads(metadata_json) if metadata_json else {},
            canonical_ids=json.loads(canonical_ids_json) if canonical_ids_json else {},
        )
        queue_items.append(item_response)

    # Get total count
    cursor = state.store._conn.execute("""
        SELECT COUNT(DISTINCT i.id)
        FROM items i
        JOIN feedback_events fe ON fe.item_id = i.id
        WHERE fe.event_type = 'explore_save'
    """)
    total = cursor.fetchone()[0]

    return QueueItemsResponse(items=queue_items, total_count=total)


@app.delete("/api/feed/queue/{item_id}")
def remove_from_queue(item_id: str):
    """Remove an item from the queue (delete the explore_save feedback event)."""
    cursor = state.store._conn.execute("""
        DELETE FROM feedback_events
        WHERE item_id = ? AND event_type = 'explore_save'
    """, (item_id,))
    state.store._conn.commit()

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Item not in queue")

    return {"status": "removed", "item_id": item_id}


@app.get("/api/items/{item_id}", response_model=ItemResponse)
def get_item(item_id: str):
    """Get a single item."""
    item = state.store.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    sources_map = {s.id: s for s in state.store.list_sources()}
    source = sources_map.get(item.source_id)

    # Get attributions
    attributions = state.store.get_attributions(item.id)
    attr_responses = [
        AttributionResponse(
            source_id=attr.source_id,
            source_name=sources_map.get(attr.source_id, type("", (), {"display_name": "Unknown"})).display_name,
            discovered_at=attr.discovered_at,
            rank=attr.rank,
            context=attr.context,
        )
        for attr in attributions
    ]

    return ItemResponse(
        id=item.id,
        source_id=item.source_id,
        source_name=source.display_name if source else "Unknown",
        url=item.url,
        title=item.title,
        creator_id=item.creator_id,
        creator_name=item.creator_name,
        published_at=item.published_at,
        content_type=item.content_type.value,
        seen=item.seen,
        hidden=item.hidden,
        metadata=item.metadata,
        canonical_ids=item.canonical_ids,
        attributions=attr_responses,
    )


@app.post("/api/items/{item_id}/seen")
def mark_item_seen(item_id: str):
    """Mark an item as seen."""
    # Use Content (item_id == content_id after migration)
    content = state.store.get_content(item_id)
    if not content:
        raise HTTPException(status_code=404, detail="Item not found")

    state.store.mark_content_seen(item_id, seen=True)
    return {"status": "seen"}


@app.delete("/api/items/{item_id}/seen")
def mark_item_unseen(item_id: str):
    """Mark an item as unseen."""
    content = state.store.get_content(item_id)
    if not content:
        raise HTTPException(status_code=404, detail="Item not found")

    state.store.mark_content_seen(item_id, seen=False)
    return {"status": "unseen"}


@app.post("/api/items/{item_id}/hide")
def hide_item(item_id: str):
    """Hide an item."""
    content = state.store.get_content(item_id)
    if not content:
        raise HTTPException(status_code=404, detail="Item not found")

    state.store.mark_content_hidden(item_id, hidden=True)
    return {"status": "hidden"}


@app.get("/api/items/{item_id}/attributions", response_model=list[AttributionResponse])
def get_item_attributions(item_id: str):
    """Get all attributions for an item (which sources recommended it)."""
    item = state.store.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    sources_map = {s.id: s for s in state.store.list_sources()}
    attributions = state.store.get_attributions(item_id)

    return [
        AttributionResponse(
            source_id=attr.source_id,
            source_name=sources_map.get(attr.source_id, type("", (), {"display_name": "Unknown"})).display_name,
            discovered_at=attr.discovered_at,
            rank=attr.rank,
            context=attr.context,
        )
        for attr in attributions
    ]


class AddAttributionRequest(BaseModel):
    source_id: str
    rank: int | None = None
    context: str | None = None


@app.post("/api/items/{item_id}/attributions", response_model=AttributionResponse)
def add_item_attribution(item_id: str, request: AddAttributionRequest):
    """Add an attribution to an item (record that a source recommended it)."""
    from omnifeed.models import ItemAttribution

    item = state.store.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    source = state.store.get_source(request.source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    attribution = ItemAttribution(
        id=uuid.uuid4().hex[:12],
        item_id=item_id,
        source_id=request.source_id,
        discovered_at=datetime.utcnow(),
        rank=request.rank,
        context=request.context,
    )

    state.store.add_attribution(attribution)

    return AttributionResponse(
        source_id=attribution.source_id,
        source_name=source.display_name,
        discovered_at=attribution.discovered_at,
        rank=attribution.rank,
        context=attribution.context,
    )


# =============================================================================
# Routes: Content Proxy
# =============================================================================


class ContentProxyResponse(BaseModel):
    url: str
    content_type: str
    html: str | None = None
    text: str | None = None
    title: str | None = None
    error: str | None = None


@app.get("/api/proxy/content", response_model=ContentProxyResponse)
async def proxy_content(url: str = Query(..., description="URL to fetch")):
    """Fetch external page content, bypassing CORS and X-Frame-Options restrictions.

    This endpoint fetches the HTML content of a URL server-side and returns it,
    allowing the frontend to render content that would otherwise be blocked.
    """
    import httpx
    from html.parser import HTMLParser

    class TitleExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_title = False
            self.title = None

        def handle_starttag(self, tag, attrs):
            if tag.lower() == "title":
                self.in_title = True

        def handle_endtag(self, tag):
            if tag.lower() == "title":
                self.in_title = False

        def handle_data(self, data):
            if self.in_title:
                self.title = data.strip()

    # Basic URL validation
    if not url.startswith(("http://", "https://")):
        return ContentProxyResponse(
            url=url,
            content_type="error",
            error="Invalid URL - must start with http:// or https://",
        )

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                },
            )
            response.raise_for_status()

            content_type = response.headers.get("content-type", "").lower()

            # Handle HTML
            if "text/html" in content_type:
                html = response.text

                # Extract title
                extractor = TitleExtractor()
                try:
                    extractor.feed(html)
                except Exception:
                    pass

                return ContentProxyResponse(
                    url=str(response.url),  # Use final URL after redirects
                    content_type="text/html",
                    html=html,
                    title=extractor.title,
                )

            # Handle plain text
            if "text/plain" in content_type:
                return ContentProxyResponse(
                    url=str(response.url),
                    content_type="text/plain",
                    text=response.text,
                )

            # Unsupported content type
            return ContentProxyResponse(
                url=str(response.url),
                content_type=content_type,
                error=f"Unsupported content type: {content_type}",
            )

    except httpx.TimeoutException:
        return ContentProxyResponse(
            url=url,
            content_type="error",
            error="Request timed out",
        )
    except httpx.HTTPStatusError as e:
        return ContentProxyResponse(
            url=url,
            content_type="error",
            error=f"HTTP {e.response.status_code}: {e.response.reason_phrase}",
        )
    except Exception as e:
        return ContentProxyResponse(
            url=url,
            content_type="error",
            error=str(e),
        )


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

    # Propagate rating up the retriever chain
    from omnifeed.retriever.scoring import record_content_feedback
    record_content_feedback(state.store, item.source_id, feedback.reward_score)

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
    click_examples: int | None = None
    reward_examples: int | None = None
    embedding_types: list[str] | None = None
    objective_counts: dict[str, int] | None = None
    # Diagnostic fields (when insufficient_data)
    total_items: int | None = None
    items_with_embeddings: int | None = None
    click_events: int | None = None
    explicit_feedbacks: int | None = None
    engaged_items: int | None = None
    missing_embeddings: int | None = None
    issues: list[str] | None = None


@app.post("/api/model/train", response_model=TrainResponse)
def train_ranking_model(
    model_name: str = Query("default", description="Model to train: default, multi_objective, or all"),
):
    """Train ranking model(s) on engagement data."""
    from omnifeed.ranking.model_registry import get_model_registry

    registry = get_model_registry()
    results = {}

    try:
        models_to_train = []
        if model_name == "all":
            models_to_train = [m["name"] for m in registry.list_models()]
        else:
            models_to_train = [model_name]

        for name in models_to_train:
            result = registry.train_model(name, state.store)
            if "message" in result and result.get("status") == "error":
                raise HTTPException(status_code=400, detail=result["message"])
            results[name] = result

        if not results:
            raise HTTPException(status_code=400, detail=f"Unknown model: {model_name}")

        # Return first result for backwards compat
        first_result = list(results.values())[0]
        return TrainResponse(
            status=first_result.get("status", "error"),
            example_count=first_result.get("example_count", 0),
            click_examples=first_result.get("click_examples"),
            reward_examples=first_result.get("reward_examples"),
            embedding_types=first_result.get("embedding_types"),
            objective_counts=first_result.get("objective_counts"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/model/status")
def get_model_status():
    """Get status of all registered models."""
    from omnifeed.ranking.model_registry import get_model_registry
    from pathlib import Path

    registry = get_model_registry()
    models_info = registry.list_models()

    # Build detailed status per model
    models = {}
    for info in models_info:
        model = registry.get_model(info["name"])
        model_data = {
            "is_trained": model.is_trained if model else False,
            "model_exists": Path(info["path"]).exists(),
            "supports_objectives": info["supports_objectives"],
            "is_default": info["is_default"],
        }
        # Add model-specific stats if available
        if model and hasattr(model, "source_stats"):
            model_data["source_count"] = len(model.source_stats)
        if model and hasattr(model, "training_counts"):
            model_data["objective_counts"] = model.training_counts
        models[info["name"]] = model_data

    return {"models": models}


@app.get("/api/objectives")
def get_objectives():
    """Get available ranking objectives."""
    from omnifeed.ranking.model_registry import get_model_registry
    from omnifeed.ranking.multi_objective import OBJECTIVE_TYPES, OBJECTIVE_LABELS

    registry = get_model_registry()

    # Get training counts from multi-objective model if available
    training_counts = {}
    mo_model = registry.get_model("multi_objective")
    if mo_model and hasattr(mo_model, "training_counts"):
        training_counts = mo_model.training_counts

    # Determine which model would be used for objectives
    active_model = None
    for obj_id in OBJECTIVE_TYPES:
        model, model_name = registry.get_model_for_objective(obj_id)
        if model and model.is_trained:
            active_model = model_name
            break

    return {
        "objectives": [
            {
                "id": obj_id,
                "label": OBJECTIVE_LABELS.get(obj_id, obj_id),
                "training_count": training_counts.get(obj_id, 0),
            }
            for obj_id in OBJECTIVE_TYPES
        ],
        "active_model": active_model or "default",
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
    from omnifeed.ingestion import get_ingestion_pipeline

    pipeline = get_ingestion_pipeline(state.store)
    result = pipeline.refresh_embeddings(
        source_id=source_id,
        embedding_type=embedding_type,
        force=force,
    )

    return RefreshEmbeddingsResponse(
        updated_count=result["updated_count"],
        skipped_count=result["skipped_count"],
        failed_count=result["failed_count"],
    )


@app.post("/api/model/refresh-transcripts", response_model=RefreshEmbeddingsResponse)
def refresh_transcript_embeddings(
    source_id: str | None = Query(None, description="Only refresh items from this source"),
    force: bool = Query(False, description="Regenerate even if content already has transcript"),
):
    """Enrich YouTube items with transcripts and regenerate embeddings.

    This endpoint:
    1. Fetches transcripts for YouTube videos
    2. Adds transcript text to content_text metadata
    3. Regenerates text embeddings to include transcript content
    """
    import logging
    from omnifeed.sources.youtube.adapter import enrich_with_transcript
    from omnifeed.featurization import get_embedding_service

    # Get YouTube items
    items = state.store.get_items(source_id=source_id, limit=10000)

    # Filter to YouTube videos only
    youtube_items = [
        item for item in items
        if item.metadata.get("video_id") or "youtube.com" in item.url
    ]

    if not youtube_items:
        return RefreshEmbeddingsResponse(updated_count=0, skipped_count=len(items), failed_count=0)

    # Filter items needing transcript enrichment
    if force:
        to_enrich = youtube_items
    else:
        # Skip items that already have substantial content_text (likely already enriched)
        to_enrich = [
            item for item in youtube_items
            if len(item.metadata.get("content_text", "")) < 500
        ]

    if not to_enrich:
        return RefreshEmbeddingsResponse(
            updated_count=0,
            skipped_count=len(youtube_items),
            failed_count=0,
        )

    # Enrich with transcripts
    enriched_count = enrich_with_transcript(to_enrich)
    logging.info(f"Enriched {enriched_count} items with transcripts")

    # Regenerate text embeddings for enriched items
    updated = 0
    failed = 0

    if enriched_count > 0:
        embedding_service = get_embedding_service()
        enriched_items = [
            item for item in to_enrich
            if len(item.metadata.get("content_text", "")) >= 500
        ]

        try:
            embeddings = embedding_service.embed_items(enriched_items)
            for item, emb in zip(enriched_items, embeddings):
                # Remove old text embedding and add new one
                item.embeddings = [e for e in item.embeddings if e.get("type") != "text"]
                item.embeddings.append(emb)
                state.store.upsert_item(item)
                updated += 1
        except Exception as e:
            logging.warning(f"Failed to regenerate embeddings: {e}")
            failed = len(enriched_items)

    logging.info(f"Transcript refresh: {updated} updated, {len(to_enrich) - enriched_count} no transcript, {failed} failed")

    return RefreshEmbeddingsResponse(
        updated_count=updated,
        skipped_count=len(youtube_items) - len(to_enrich) + (len(to_enrich) - enriched_count),
        failed_count=failed,
    )


# =============================================================================
# Routes: Discovery
# =============================================================================


class DiscoveryResultResponse(BaseModel):
    url: str
    name: str
    source_type: str
    description: str
    thumbnail_url: str | None
    subscriber_count: int | None
    relevance_score: float
    explanation: str
    matched_interests: list[str]
    from_query: str


class InterestResponse(BaseModel):
    topic: str
    confidence: float
    example_items: list[str]


class InterestProfileResponse(BaseModel):
    interests: list[InterestResponse]
    top_creators: list[str]
    content_types: list[str]
    generated_queries: list[str]


class DiscoveryResponse(BaseModel):
    results: list[DiscoveryResultResponse]
    queries_used: list[str]
    interest_profile: InterestProfileResponse | None
    mode: str


@app.get("/api/discover", response_model=DiscoveryResponse)
async def discover_sources(
    prompt: str | None = Query(None, description="What to search for"),
    limit: int = Query(10, ge=1, le=50),
    platforms: str | None = Query(None, description="Comma-separated platforms"),
):
    """Discover new sources based on prompt or user interests.

    If prompt is provided, searches for matching sources.
    If no prompt, analyzes user's engagement history to suggest sources.
    """
    from omnifeed.discovery import DiscoveryEngine

    engine = DiscoveryEngine(state.store)

    platform_list = None
    if platforms:
        platform_list = [p.strip() for p in platforms.split(",")]

    if prompt:
        response = await engine.discover_from_prompt(
            prompt=prompt,
            limit=limit,
            platforms=platform_list,
        )
    else:
        response = await engine.discover_from_interests(limit=limit)

    # Convert to response model
    results = [
        DiscoveryResultResponse(
            url=r.suggestion.url,
            name=r.suggestion.name,
            source_type=r.suggestion.source_type,
            description=r.suggestion.description,
            thumbnail_url=r.suggestion.thumbnail_url,
            subscriber_count=r.suggestion.subscriber_count,
            relevance_score=r.relevance_score,
            explanation=r.explanation,
            matched_interests=r.matched_interests,
            from_query=r.from_query,
        )
        for r in response.results
    ]

    profile_response = None
    if response.interest_profile:
        profile_response = InterestProfileResponse(
            interests=[
                InterestResponse(
                    topic=i.topic,
                    confidence=i.confidence,
                    example_items=i.example_items,
                )
                for i in response.interest_profile.interests
            ],
            top_creators=response.interest_profile.top_creators,
            content_types=response.interest_profile.content_types,
            generated_queries=response.interest_profile.generated_queries,
        )

    return DiscoveryResponse(
        results=results,
        queries_used=response.queries_used,
        interest_profile=profile_response,
        mode=response.mode,
    )


@app.get("/api/discover/interests", response_model=InterestProfileResponse | None)
def get_interest_profile(min_score: float = Query(3.0, description="Minimum feedback score")):
    """Get user's extracted interest profile from engagement data."""
    from omnifeed.discovery import build_interest_profile

    profile = build_interest_profile(state.store, min_score=min_score)

    if not profile:
        return None

    return InterestProfileResponse(
        interests=[
            InterestResponse(
                topic=i.topic,
                confidence=i.confidence,
                example_items=i.example_items,
            )
            for i in profile.interests
        ],
        top_creators=profile.top_creators,
        content_types=profile.content_types,
        generated_queries=profile.generated_queries,
    )


@app.get("/api/discover/llm-status")
def get_llm_status():
    """Check LLM backend status for discovery."""
    from omnifeed.discovery import get_llm_status as _get_status

    return _get_status()


# =============================================================================
# Routes: Sitemap Config
# =============================================================================


class SitemapSelectorsRequest(BaseModel):
    title: str | None = "og:title"
    description: str | None = "og:description"
    image: str | None = "og:image"
    author: str | None = None


class SitemapConfigRequest(BaseModel):
    selectors: SitemapSelectorsRequest = SitemapSelectorsRequest()
    fetch_content: bool = True
    max_items: int = 1000


class SitemapConfigResponse(BaseModel):
    domain: str
    selectors: dict[str, str | None]
    fetch_content: bool
    max_items: int


@app.get("/api/sitemap/configs", response_model=list[SitemapConfigResponse])
def list_sitemap_configs():
    """List all sitemap configs."""
    from pathlib import Path
    import json

    config_dir = Path("~/.omnifeed/sitemap_configs").expanduser()
    if not config_dir.exists():
        return []

    configs = []
    for config_file in config_dir.glob("*.json"):
        try:
            with open(config_file) as f:
                data = json.load(f)
            configs.append(SitemapConfigResponse(
                domain=config_file.stem,
                selectors=data.get("selectors", {}),
                fetch_content=data.get("fetch_content", True),
                max_items=data.get("max_items", 1000),
            ))
        except Exception:
            pass  # Skip invalid configs

    return configs


@app.get("/api/sitemap/configs/{domain}", response_model=SitemapConfigResponse)
def get_sitemap_config(domain: str):
    """Get sitemap config for a domain."""
    from pathlib import Path
    import json

    config_path = Path("~/.omnifeed/sitemap_configs").expanduser() / f"{domain}.json"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="Config not found")

    with open(config_path) as f:
        data = json.load(f)

    return SitemapConfigResponse(
        domain=domain,
        selectors=data.get("selectors", {}),
        fetch_content=data.get("fetch_content", True),
        max_items=data.get("max_items", 1000),
    )


@app.post("/api/sitemap/configs/{domain}", response_model=SitemapConfigResponse)
def upsert_sitemap_config(domain: str, request: SitemapConfigRequest):
    """Create or update sitemap config for a domain."""
    from pathlib import Path
    import json

    config_dir = Path("~/.omnifeed/sitemap_configs").expanduser()
    config_dir.mkdir(parents=True, exist_ok=True)

    config_path = config_dir / f"{domain}.json"

    data = {
        "selectors": {
            "title": request.selectors.title,
            "description": request.selectors.description,
            "image": request.selectors.image,
            "author": request.selectors.author,
        },
        "fetch_content": request.fetch_content,
        "max_items": request.max_items,
    }

    with open(config_path, "w") as f:
        json.dump(data, f, indent=4)

    return SitemapConfigResponse(
        domain=domain,
        selectors=data["selectors"],
        fetch_content=data["fetch_content"],
        max_items=data["max_items"],
    )


@app.delete("/api/sitemap/configs/{domain}")
def delete_sitemap_config(domain: str):
    """Delete sitemap config for a domain."""
    from pathlib import Path

    config_path = Path("~/.omnifeed/sitemap_configs").expanduser() / f"{domain}.json"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="Config not found")

    config_path.unlink()
    return {"status": "deleted"}


# =============================================================================
# Routes: Extension API
# =============================================================================


class ExtensionAuthRequest(BaseModel):
    client_version: str
    platform: str | None = None


class ExtensionAuthResponse(BaseModel):
    authenticated: bool
    session_id: str


@app.post("/api/extension/auth", response_model=ExtensionAuthResponse)
def extension_auth(request: ExtensionAuthRequest):
    """Authenticate browser extension (currently always succeeds)."""
    # For now, just return a session ID - no real auth
    session_id = uuid.uuid4().hex
    logger.info(f"Extension auth: version={request.client_version}, platform={request.platform}")
    return ExtensionAuthResponse(
        authenticated=True,
        session_id=session_id,
    )


class ExtensionEventRequest(BaseModel):
    # Accept both 'type' and 'event_type' from extension
    type: str | None = None
    event_type: str | None = None
    timestamp: int
    url: str
    item_id: str | None = None
    payload: dict[str, Any] = {}

    @property
    def event_type_value(self) -> str:
        """Get the event type from either field."""
        return self.type or self.event_type or "unknown"


class ExtensionEventsRequest(BaseModel):
    events: list[ExtensionEventRequest]
    session_id: str | None = None  # Made optional for compatibility
    client_version: str | None = None  # Made optional for compatibility


class ExtensionEventsResponse(BaseModel):
    received: int
    processed: int


@app.post("/api/extension/events", response_model=ExtensionEventsResponse)
def submit_extension_events(request: ExtensionEventsRequest):
    """Receive batch of events from browser extension.

    Routes events to appropriate tables:
    - Ratings → explicit_feedback (+ auto-create item if needed)
    - Other events (page_view, page_leave) → feedback_events (implicit)
    """
    from omnifeed.models import FeedbackEvent, ExplicitFeedback, Item, ContentType, ConsumptionType

    processed = 0
    skipped = 0
    for event in request.events:
        try:
            timestamp = datetime.fromtimestamp(event.timestamp / 1000)
            raw_event_type = event.event_type_value

            # Check for duplicate (same second, url)
            ts_second = timestamp.isoformat()[:19]
            existing = state.store._conn.execute(
                """SELECT 1 FROM feedback_events
                   WHERE substr(timestamp, 1, 19) = ? AND json_extract(payload, '$.url') = ?
                   LIMIT 1""",
                (ts_second, event.url)
            ).fetchone()

            if existing:
                skipped += 1
                continue

            # RATING events → explicit_feedback table
            if raw_event_type == "rating":
                # Find or create item for this URL
                item = state.store.get_item_by_url(event.url)
                if not item:
                    # Auto-create item from extension
                    item = Item(
                        id=uuid.uuid4().hex[:12],
                        source_id="extension_capture",
                        external_id=event.url,
                        url=event.url,
                        title=event.payload.get("title", event.url.split("/")[-1]),
                        creator_id=None,
                        creator_name=event.payload.get("creator_name", "Unknown"),
                        published_at=timestamp,
                        ingested_at=datetime.utcnow(),
                        content_type=ContentType.VIDEO if "video" in event.url else ContentType.ARTICLE,
                        consumption_type=ConsumptionType.ONE_SHOT,
                        metadata={
                            "captured_by": "extension",
                            "platform": event.payload.get("platform", "web"),
                        },
                    )
                    state.store.upsert_item(item)
                    logger.info(f"Auto-created item from extension rating: {item.title}")

                # Check for duplicate explicit feedback (same item, same second)
                existing_fb = state.store._conn.execute(
                    """SELECT 1 FROM explicit_feedback
                       WHERE item_id = ? AND substr(timestamp, 1, 19) = ?
                       LIMIT 1""",
                    (item.id, ts_second)
                ).fetchone()

                if existing_fb:
                    skipped += 1
                    continue

                # Create explicit feedback
                explicit_fb = ExplicitFeedback(
                    id=uuid.uuid4().hex[:12],
                    item_id=item.id,
                    timestamp=timestamp,
                    reward_score=event.payload.get("rewardScore", 2.5),
                    selections=event.payload.get("selections", {}),
                    notes=event.payload.get("notes"),
                    completion_pct=event.payload.get("completionPct", 0),
                    is_checkpoint=False,
                )
                state.store.add_explicit_feedback(explicit_fb)
                processed += 1

            # OTHER events → feedback_events table (implicit feedback)
            else:
                feedback_event = FeedbackEvent(
                    id=uuid.uuid4().hex[:12],
                    item_id=event.item_id or "",
                    timestamp=timestamp,
                    event_type=f"extension_{raw_event_type}",
                    payload={
                        **event.payload,
                        "url": event.url,
                        "session_id": request.session_id or "",
                        "client_version": request.client_version or "",
                    },
                )
                state.store.add_feedback_event(feedback_event)
                processed += 1

        except Exception as e:
            logger.warning(f"Failed to process extension event: {e}")

    return ExtensionEventsResponse(
        received=len(request.events),
        processed=processed,
    )


class ExtensionItemRequest(BaseModel):
    url: str
    title: str
    creator_name: str | None = None
    content_type: str = "other"
    platform: str | None = None
    external_id: str | None = None
    thumbnail_url: str | None = None
    metadata: dict[str, Any] = {}


class ExtensionItemResponse(BaseModel):
    item_id: str
    created: bool
    matched_existing: bool


@app.post("/api/extension/items", response_model=ExtensionItemResponse)
def create_extension_item(request: ExtensionItemRequest):
    """Create or find item from extension capture."""
    from omnifeed.models import ContentType, ConsumptionType

    # Check if item exists by URL
    existing = state.store.get_item_by_url(request.url)
    if existing:
        return ExtensionItemResponse(
            item_id=existing.id,
            created=False,
            matched_existing=True,
        )

    # Map content type
    content_type_map = {
        "video": ContentType.VIDEO,
        "audio": ContentType.AUDIO,
        "article": ContentType.ARTICLE,
        "image": ContentType.IMAGE,
    }
    content_type = content_type_map.get(request.content_type, ContentType.ARTICLE)

    # Find or create creator
    creator = None
    if request.creator_name:
        creator = _find_or_create_creator(
            store=state.store,
            name=request.creator_name,
            source_type=request.platform or "extension",
            raw_metadata=request.metadata,
        )

    # Create extension source if needed
    extension_source = state.store.get_source_by_uri("extension://captured")
    if not extension_source:
        from omnifeed.models import Source, SourceInfo
        source_info = SourceInfo(
            source_type="extension",
            uri="extension://captured",
            display_name="Browser Extension",
            metadata={},
        )
        extension_source = state.store.add_source(source_info)

    # Create item
    item = Item(
        id=uuid.uuid4().hex[:12],
        source_id=extension_source.id,
        external_id=request.external_id or request.url,
        url=request.url,
        title=request.title,
        creator_id=creator.id if creator else None,
        creator_name=request.creator_name or "Unknown",
        published_at=datetime.utcnow(),
        ingested_at=datetime.utcnow(),
        content_type=content_type,
        consumption_type=ConsumptionType.ONE_SHOT,
        metadata={
            **request.metadata,
            "platform": request.platform,
            "thumbnail_url": request.thumbnail_url,
            "captured_by": "extension",
        },
    )
    state.store.upsert_item(item)

    return ExtensionItemResponse(
        item_id=item.id,
        created=True,
        matched_existing=False,
    )


class ExtensionRatingRequest(BaseModel):
    url: str
    item_id: str | None = None
    reward_score: float
    selections: dict[str, list[str]] = {}
    notes: str | None = None


class ExtensionRatingResponse(BaseModel):
    feedback_id: str
    item_id: str


@app.post("/api/extension/rating", response_model=ExtensionRatingResponse)
def submit_extension_rating(request: ExtensionRatingRequest):
    """Submit explicit rating from browser extension."""
    from omnifeed.models import ExplicitFeedback

    # Find item by URL or ID
    item = None
    if request.item_id:
        item = state.store.get_item(request.item_id)
    if not item:
        item = state.store.get_item_by_url(request.url)

    if not item:
        raise HTTPException(status_code=404, detail="Item not found. Create it first via /api/extension/items")

    # Validate reward score
    if not 0.0 <= request.reward_score <= 5.0:
        raise HTTPException(status_code=400, detail="Reward score must be between 0.0 and 5.0")

    feedback = ExplicitFeedback(
        id=uuid.uuid4().hex[:12],
        item_id=item.id,
        timestamp=datetime.utcnow(),
        reward_score=request.reward_score,
        selections=request.selections,
        notes=request.notes,
    )
    state.store.add_explicit_feedback(feedback)

    # Propagate rating up the retriever chain
    from omnifeed.retriever.scoring import record_content_feedback
    record_content_feedback(state.store, item.source_id, feedback.reward_score)

    return ExtensionRatingResponse(
        feedback_id=feedback.id,
        item_id=item.id,
    )


class MediaUploadRequest(BaseModel):
    media_type: str  # "audio" or "visual"
    data: str  # base64 encoded
    url: str
    timestamp: int


class MediaMatchResponse(BaseModel):
    matched: bool
    item_id: str | None = None
    confidence: float = 0.0


@app.post("/api/extension/media", response_model=MediaMatchResponse)
def upload_extension_media(request: MediaUploadRequest):
    """Upload audio/visual data for server-side matching.

    TODO: Implement actual fingerprint matching once we have a fingerprint database.
    For now, this just acknowledges receipt.
    """
    logger.info(f"Received {request.media_type} media from extension for {request.url}")

    # TODO: Decode base64 data, generate fingerprint, match against database
    # For now, return no match
    return MediaMatchResponse(
        matched=False,
        item_id=None,
        confidence=0.0,
    )


# =============================================================================
# Routes: Explore (Retriever-based source discovery)
# =============================================================================


class RetrieverResponse(BaseModel):
    id: str
    display_name: str
    kind: str
    handler_type: str
    uri: str
    score: float | None = None
    confidence: float | None = None
    is_enabled: bool = True


class ExploreResultResponse(BaseModel):
    retrievers: list[RetrieverResponse]
    items: list[ItemResponse]
    topic: str | None = None


def _select_strategies(
    all_strategies: list,
    store,
    max_strategies: int = 4,
    explore_ratio: float = 0.3,
) -> list:
    """Select strategies using explore/exploit balance.

    - Exploit: Prefer high-scoring strategies with good confidence
    - Explore: Include some low-confidence strategies to gather data
    - Skip: Avoid strategies with no retriever (never been run)
    """
    import random

    # Get retriever info for each strategy
    strategy_data = []
    for strategy in all_strategies:
        uri = f"strategy:{strategy.strategy_id}"
        retriever = store.get_retriever_by_uri(uri)

        if retriever and retriever.score:
            strategy_data.append({
                'strategy': strategy,
                'score': retriever.score.value,
                'confidence': retriever.score.confidence,
                'sample_size': retriever.score.sample_size,
            })
        else:
            # No data yet - candidate for exploration
            strategy_data.append({
                'strategy': strategy,
                'score': None,
                'confidence': 0.0,
                'sample_size': 0,
            })

    # Separate into exploit (high confidence) and explore (low confidence) pools
    exploit_pool = [s for s in strategy_data if s['confidence'] >= 0.3]
    explore_pool = [s for s in strategy_data if s['confidence'] < 0.3]

    # Sort exploit pool by score (descending)
    exploit_pool.sort(key=lambda x: x['score'] or 0, reverse=True)

    # Calculate how many from each pool
    n_exploit = int(max_strategies * (1 - explore_ratio))
    n_explore = max_strategies - n_exploit

    selected = []

    # Take top performers from exploit pool
    selected.extend([s['strategy'] for s in exploit_pool[:n_exploit]])

    # Randomly sample from explore pool
    if explore_pool and n_explore > 0:
        explore_sample = random.sample(explore_pool, min(n_explore, len(explore_pool)))
        selected.extend([s['strategy'] for s in explore_sample])

    # If we don't have enough, fill from whatever is available
    if len(selected) < max_strategies:
        remaining = [s['strategy'] for s in strategy_data if s['strategy'] not in selected]
        needed = max_strategies - len(selected)
        selected.extend(remaining[:needed])

    logger.info(f"[SELECT] Selected {len(selected)} strategies: {[s.strategy_id for s in selected]}")
    return selected


@app.post("/api/explore", response_model=ExploreResultResponse)
async def explore_sources(
    topic: str | None = Query(None, description="Topic to explore (random if not provided)"),
    limit: int = Query(9, ge=1, le=20, description="Max total items to return"),
    strategy_ids: str | None = Query(None, description="Comma-separated strategy IDs to use (uses all if not provided)"),
):
    """Discover new sources and content via exploration strategies.

    Uses registered exploration strategies to discover NEW sources.
    Each strategy represents a specific query/prompt construction method.
    Strategies are scored based on the quality of sources they discover.
    """
    from omnifeed.retriever import RetrieverOrchestrator, RetrievalContext, find_handler
    from omnifeed.retriever.handlers.strategy import get_all_strategies, get_strategy
    from omnifeed.retriever.scoring import RetrieverScorer

    logger.info(f"=== EXPLORE START === topic={topic}, limit={limit}, strategies={strategy_ids}")

    orchestrator = RetrieverOrchestrator(state.store)
    scorer = RetrieverScorer(state.store)

    # Determine which strategies to use
    if strategy_ids:
        selected_strategy_ids = [s.strip() for s in strategy_ids.split(",")]
        strategies = [get_strategy(sid) for sid in selected_strategy_ids if get_strategy(sid)]
    else:
        # Select strategies using explore/exploit balance
        all_strategies = get_all_strategies()
        strategies = _select_strategies(
            all_strategies,
            state.store,
            max_strategies=4,  # Only run 4 strategies max
            explore_ratio=0.3,  # 30% exploration
        )

    if not strategies:
        logger.error("No strategies available!")
        return ExploreResultResponse(retrievers=[], items=[], topic=topic)

    logger.info(f"[1] Using {len(strategies)} strategies: {[s.strategy_id for s in strategies]}")

    # Get or create retriever for each strategy
    handler = find_handler("strategy:")
    if not handler:
        logger.error("[1] No strategy handler found!")
        return ExploreResultResponse(retrievers=[], items=[], topic=topic)

    # Fetch context items for LLM strategies (once, outside loop)
    context_items = None
    try:
        feedbacks = state.store.get_explicit_feedback(limit=50)
        high_rated = [f for f in feedbacks if f.reward_score >= 4.0]
        if high_rated:
            item_ids = [f.item_id for f in high_rated[:10]]
            items_list = [state.store.get_item(iid) for iid in item_ids]
            context_items = [
                {"title": i.title, "creator_name": i.creator_name, "url": i.url}
                for i in items_list if i
            ]
            logger.info(f"[CTX] Built context with {len(context_items)} high-rated items")
    except Exception as e:
        logger.debug(f"Could not fetch context items: {e}")

    # Prepare strategy retrievers
    strategy_retrievers = []
    for strategy in strategies:
        strategy_uri = f"strategy:{strategy.strategy_id}"
        existing = state.store.get_retriever_by_uri(strategy_uri)
        if existing:
            strategy_retrievers.append((strategy, existing))
        else:
            new_retriever = handler.resolve(strategy_uri)
            new_retriever = state.store.add_retriever(new_retriever)
            strategy_retrievers.append((strategy, new_retriever))

    # Run all strategies IN PARALLEL
    async def invoke_strategy(strategy, retriever):
        context = RetrievalContext(
            max_depth=1,  # Recurse once to get content from discovered sources
            max_results=2,  # Limit sources per strategy
            explore_ratio=0.7,
            topic=topic,
            context_items=context_items,
        )
        try:
            result = await orchestrator.invoke(retriever, context)
            logger.info(f"[PARALLEL] {strategy.strategy_id}: {len(result.new_retrievers)} retrievers, {len(result.items)} items")
            return result
        except Exception as e:
            logger.error(f"[PARALLEL] {strategy.strategy_id} failed: {e}")
            return None

    logger.info(f"[2] Running {len(strategy_retrievers)} strategies in parallel...")
    results = await asyncio.gather(*[
        invoke_strategy(s, r) for s, r in strategy_retrievers
    ])

    # Aggregate results
    all_retrievers = []
    all_items = []
    for result in results:
        if result:
            all_retrievers.extend(result.new_retrievers)
            all_items.extend(result.items)

    # Dedupe retrievers by URI
    seen_uris = set()
    unique_retrievers = []
    for r in all_retrievers:
        if r.uri not in seen_uris:
            seen_uris.add(r.uri)
            unique_retrievers.append(r)

    logger.info(f"[5] Total: {len(unique_retrievers)} unique retrievers, {len(all_items)} items")
    result_retrievers = unique_retrievers[:limit]
    result_items = all_items[:limit]

    # Create a fake result object for compatibility with rest of function
    class AggregatedResult:
        def __init__(self, retrievers, items):
            self.new_retrievers = retrievers
            self.items = items
            self.errors = []

    result = AggregatedResult(result_retrievers, result_items)

    logger.info(f"[4] Orchestrator returned: {len(result.new_retrievers)} retrievers, {len(result.items)} items, {len(result.errors)} errors")
    for err_uri, err in result.errors:
        logger.error(f"[4] Error for {err_uri}: {err}")

    # Build retriever responses
    retriever_responses = []
    for r in result.new_retrievers[:limit]:
        retriever_responses.append(RetrieverResponse(
            id=r.id,
            display_name=r.display_name,
            kind=r.kind.value,
            handler_type=r.handler_type,
            uri=r.uri,
            score=r.score.value if r.score else None,
            confidence=r.score.confidence if r.score else None,
            is_enabled=r.is_enabled,
        ))

    # Ingest discovered items with unified pipeline (embeddings + persistence)
    if result.items:
        from omnifeed.ingestion import get_ingestion_pipeline
        pipeline = get_ingestion_pipeline(state.store)
        pipeline.ingest(result.items)
        logger.info(f"[5] Ingested {len(result.items)} discovered items")

    # Build item responses from discovered content
    item_responses = []
    sources_map = {s.id: s for s in state.store.list_sources()}

    for item in result.items[:limit]:
        source = sources_map.get(item.source_id)
        item_responses.append(ItemResponse(
            id=item.id,
            source_id=item.source_id,
            source_name=source.display_name if source else "Discovered",
            url=item.url,
            title=item.title,
            creator_id=item.creator_id,
            creator_name=item.creator_name,
            published_at=item.published_at,
            content_type=item.content_type.value,
            seen=item.seen,
            hidden=item.hidden,
            metadata=item.metadata,
            canonical_ids=item.canonical_ids,
            score=state.pipeline.score(item),
        ))

    return ExploreResultResponse(
        retrievers=retriever_responses,
        items=item_responses,
        topic=topic,
    )


async def _explore_discovery_only(topic: str | None, limit: int) -> ExploreResultResponse:
    """Fallback when no sources exist - just do discovery."""
    from omnifeed.retriever import RetrieverOrchestrator, RetrievalContext, get_handler

    orchestrator = RetrieverOrchestrator(state.store)
    context = RetrievalContext(max_depth=1, max_results=limit, explore_ratio=0.7)

    if topic:
        explore_uri = f"explore:topic:{topic}"
    else:
        explore_uri = "explore:random"

    handler = get_handler("exploratory")
    if not handler:
        return ExploreResultResponse(retrievers=[], items=[], topic=topic)

    explore_retriever = handler.resolve(explore_uri)
    existing = state.store.get_retriever_by_uri(explore_uri)
    if existing:
        explore_retriever = existing
    else:
        explore_retriever = state.store.add_retriever(explore_retriever)

    result = await orchestrator.invoke(explore_retriever, context)

    retriever_responses = []
    for r in result.new_retrievers[:limit]:
        retriever_responses.append(RetrieverResponse(
            id=r.id,
            display_name=r.display_name,
            kind=r.kind.value,
            handler_type=r.handler_type,
            uri=r.uri,
            score=r.score.value if r.score else None,
            confidence=r.score.confidence if r.score else None,
            is_enabled=r.is_enabled,
        ))

    return ExploreResultResponse(
        retrievers=retriever_responses,
        items=[],
        topic=topic,
    )


@app.get("/api/explore/stream")
async def explore_stream(
    topic: str | None = Query(None, description="Topic to explore"),
    limit: int = Query(9, ge=1, le=20),
    strategy_ids: str | None = Query(None),
):
    """Stream explore progress via Server-Sent Events.

    Events:
    - strategy_start: {strategy_id, display_name}
    - llm_prompt: {strategy_id, prompt}
    - llm_response: {strategy_id, queries}
    - search_start: {strategy_id, query, provider}
    - search_result: {strategy_id, count, provider}
    - strategy_complete: {strategy_id, retrievers, items}
    - complete: {total_retrievers, total_items}
    - error: {message}
    """
    from omnifeed.retriever import RetrieverOrchestrator, RetrievalContext, find_handler
    from omnifeed.retriever.handlers.strategy import get_all_strategies, get_strategy

    async def event_generator():
        try:
            # Determine strategies
            if strategy_ids:
                selected_ids = [s.strip() for s in strategy_ids.split(",")]
                strategies = [get_strategy(sid) for sid in selected_ids if get_strategy(sid)]
            else:
                # Use explore/exploit selection
                all_strategies = get_all_strategies()
                strategies = _select_strategies(
                    all_strategies,
                    state.store,
                    max_strategies=4,
                    explore_ratio=0.3,
                )

            if not strategies:
                yield f"data: {json.dumps({'event': 'error', 'message': 'No strategies available'})}\n\n"
                return

            yield f"data: {json.dumps({'event': 'start', 'strategies': [s.strategy_id for s in strategies], 'topic': topic})}\n\n"

            orchestrator = RetrieverOrchestrator(state.store)
            handler = find_handler("strategy:")
            if not handler:
                yield f"data: {json.dumps({'event': 'error', 'message': 'No strategy handler'})}\n\n"
                return

            all_retrievers = []
            all_items = []
            results_per_strategy = max(1, limit // len(strategies))

            # Fetch context for LLM strategies
            context_items = None
            try:
                feedbacks = state.store.get_explicit_feedback(limit=50)
                high_rated = [f for f in feedbacks if f.reward_score >= 4.0]
                if high_rated:
                    item_ids = [f.item_id for f in high_rated[:10]]
                    items = [state.store.get_item(iid) for iid in item_ids]
                    context_items = [
                        {"title": i.title, "creator_name": i.creator_name, "url": i.url}
                        for i in items if i
                    ]
            except Exception:
                pass

            # Prepare strategy retrievers
            strategy_retrievers = []
            for strategy in strategies:
                strategy_uri = f"strategy:{strategy.strategy_id}"
                existing = state.store.get_retriever_by_uri(strategy_uri)
                if existing:
                    strategy_retrievers.append((strategy, existing))
                else:
                    new_retriever = handler.resolve(strategy_uri)
                    new_retriever = state.store.add_retriever(new_retriever)
                    strategy_retrievers.append((strategy, new_retriever))

            yield f"data: {json.dumps({'event': 'running', 'message': f'Running {len(strategy_retrievers)} strategies in parallel...'})}\n\n"

            # Run all strategies IN PARALLEL
            async def invoke_one(strategy, retriever):
                context = RetrievalContext(
                    max_depth=1,  # Recurse once to get content
                    max_results=2,
                    explore_ratio=0.7,
                    topic=topic,
                    context_items=context_items,
                )
                try:
                    return strategy.strategy_id, await orchestrator.invoke(retriever, context)
                except Exception as e:
                    return strategy.strategy_id, None

            results = await asyncio.gather(*[
                invoke_one(s, r) for s, r in strategy_retrievers
            ])

            # Report results
            for strategy_id, result in results:
                if result:
                    yield f"data: {json.dumps({'event': 'strategy_complete', 'strategy_id': strategy_id, 'retrievers': len(result.new_retrievers), 'items': len(result.items)})}\n\n"
                    all_retrievers.extend(result.new_retrievers)
                    all_items.extend(result.items)
                else:
                    yield f"data: {json.dumps({'event': 'strategy_complete', 'strategy_id': strategy_id, 'retrievers': 0, 'items': 0, 'failed': True})}\n\n"

            # Dedupe
            seen_uris = set()
            unique_retrievers = []
            for r in all_retrievers:
                if r.uri not in seen_uris:
                    seen_uris.add(r.uri)
                    unique_retrievers.append(r)

            yield f"data: {json.dumps({'event': 'complete', 'total_retrievers': len(unique_retrievers), 'total_items': len(all_items)})}\n\n"

        except Exception as e:
            logger.exception("Explore stream error")
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/retrievers", response_model=list[RetrieverResponse])
def list_retrievers(
    kind: str | None = Query(None, description="Filter by kind (poll, explore, hybrid)"),
    enabled_only: bool = Query(True, description="Only enabled retrievers"),
    limit: int = Query(50, ge=1, le=200),
):
    """List all retrievers."""
    retrievers = state.store.list_retrievers(
        kind=kind,
        enabled_only=enabled_only,
        limit=limit,
    )

    return [
        RetrieverResponse(
            id=r.id,
            display_name=r.display_name,
            kind=r.kind.value,
            handler_type=r.handler_type,
            uri=r.uri,
            score=r.score.value if r.score else None,
            confidence=r.score.confidence if r.score else None,
            is_enabled=r.is_enabled,
        )
        for r in retrievers
    ]


@app.get("/api/retrievers/top", response_model=list[RetrieverResponse])
def get_top_retrievers(
    limit: int = Query(10, ge=1, le=50),
    min_confidence: float = Query(0.3, ge=0.0, le=1.0),
):
    """Get top-scoring retrievers."""
    from omnifeed.retriever import RetrieverScorer

    scorer = RetrieverScorer(state.store)
    top = scorer.get_top_retrievers(limit=limit, min_confidence=min_confidence)

    return [
        RetrieverResponse(
            id=r.id,
            display_name=r.display_name,
            kind=r.kind.value,
            handler_type=r.handler_type,
            uri=r.uri,
            score=r.score.value if r.score else None,
            confidence=r.score.confidence if r.score else None,
            is_enabled=r.is_enabled,
        )
        for r in top
    ]


class AddRetrieverRequest(BaseModel):
    uri: str
    display_name: str | None = None


@app.post("/api/retrievers", response_model=RetrieverResponse)
def add_retriever(request: AddRetrieverRequest):
    """Add a retriever from a URI."""
    from omnifeed.retriever import find_handler

    handler = find_handler(request.uri)
    if not handler:
        raise HTTPException(status_code=400, detail=f"No handler found for URI: {request.uri}")

    try:
        retriever = handler.resolve(request.uri, display_name=request.display_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Check if exists
    existing = state.store.get_retriever_by_uri(retriever.uri)
    if existing:
        raise HTTPException(status_code=409, detail="Retriever already exists")

    retriever = state.store.add_retriever(retriever)

    return RetrieverResponse(
        id=retriever.id,
        display_name=retriever.display_name,
        kind=retriever.kind.value,
        handler_type=retriever.handler_type,
        uri=retriever.uri,
        score=retriever.score.value if retriever.score else None,
        confidence=retriever.score.confidence if retriever.score else None,
        is_enabled=retriever.is_enabled,
    )


@app.delete("/api/retrievers/{retriever_id}")
def delete_retriever(retriever_id: str):
    """Delete a retriever."""
    retriever = state.store.get_retriever(retriever_id)
    if not retriever:
        raise HTTPException(status_code=404, detail="Retriever not found")

    count = state.store.delete_retriever(retriever_id)
    return {"status": "deleted", "count": count}


# =============================================================================
# Control Plane: Retriever Details & Hierarchy
# =============================================================================


class RetrieverDetailResponse(BaseModel):
    id: str
    display_name: str
    kind: str
    handler_type: str
    uri: str
    config: dict = {}
    parent_id: str | None = None
    depth: int = 0
    is_enabled: bool
    score: float | None = None
    confidence: float | None = None
    sample_size: int | None = None
    last_updated: datetime | None = None
    last_invoked_at: datetime | None = None
    created_at: datetime | None = None
    children_count: int = 0


class RetrieverHierarchyNode(BaseModel):
    id: str
    display_name: str
    kind: str
    handler_type: str
    score: float | None = None
    confidence: float | None = None
    sample_size: int | None = None
    is_enabled: bool
    children: list["RetrieverHierarchyNode"] = []


@app.get("/api/retrievers/hierarchy", response_model=list[RetrieverHierarchyNode])
def get_retriever_hierarchy():
    """Get full retriever hierarchy (tree view)."""
    all_retrievers = state.store.list_retrievers(enabled_only=False, limit=500)

    # Build lookup maps
    by_id = {r.id: r for r in all_retrievers}
    children_map: dict[str | None, list] = {None: []}
    for r in all_retrievers:
        if r.parent_id not in children_map:
            children_map[r.parent_id] = []
        children_map[r.parent_id].append(r)

    def build_node(r) -> RetrieverHierarchyNode:
        return RetrieverHierarchyNode(
            id=r.id,
            display_name=r.display_name,
            kind=r.kind.value,
            handler_type=r.handler_type,
            score=r.score.value if r.score else None,
            confidence=r.score.confidence if r.score else None,
            sample_size=r.score.sample_size if r.score else None,
            is_enabled=r.is_enabled,
            children=[build_node(c) for c in children_map.get(r.id, [])],
        )

    # Build tree from roots (parent_id is None)
    roots = children_map.get(None, [])
    return [build_node(r) for r in roots]


@app.get("/api/retrievers/{retriever_id}", response_model=RetrieverDetailResponse)
def get_retriever_detail(retriever_id: str):
    """Get detailed info for a single retriever."""
    retriever = state.store.get_retriever(retriever_id)
    if not retriever:
        raise HTTPException(status_code=404, detail="Retriever not found")

    children = state.store.get_children(retriever_id)

    return RetrieverDetailResponse(
        id=retriever.id,
        display_name=retriever.display_name,
        kind=retriever.kind.value,
        handler_type=retriever.handler_type,
        uri=retriever.uri,
        config=retriever.config,
        parent_id=retriever.parent_id,
        depth=retriever.depth,
        is_enabled=retriever.is_enabled,
        score=retriever.score.value if retriever.score else None,
        confidence=retriever.score.confidence if retriever.score else None,
        sample_size=retriever.score.sample_size if retriever.score else None,
        last_updated=retriever.score.last_updated if retriever.score else None,
        last_invoked_at=retriever.last_invoked_at,
        created_at=retriever.created_at,
        children_count=len(children),
    )


@app.get("/api/retrievers/{retriever_id}/children", response_model=list[RetrieverDetailResponse])
def get_retriever_children(retriever_id: str):
    """Get child retrievers (for hierarchy view)."""
    retriever = state.store.get_retriever(retriever_id)
    if not retriever:
        raise HTTPException(status_code=404, detail="Retriever not found")

    children = state.store.get_children(retriever_id)

    return [
        RetrieverDetailResponse(
            id=r.id,
            display_name=r.display_name,
            kind=r.kind.value,
            handler_type=r.handler_type,
            uri=r.uri,
            config=r.config,
            parent_id=r.parent_id,
            depth=r.depth,
            is_enabled=r.is_enabled,
            score=r.score.value if r.score else None,
            confidence=r.score.confidence if r.score else None,
            sample_size=r.score.sample_size if r.score else None,
            last_updated=r.score.last_updated if r.score else None,
            last_invoked_at=r.last_invoked_at,
            created_at=r.created_at,
            children_count=len(state.store.get_children(r.id)),
        )
        for r in children
    ]


class UpdateRetrieverRequest(BaseModel):
    is_enabled: bool | None = None
    display_name: str | None = None
    config: dict | None = None


@app.patch("/api/retrievers/{retriever_id}", response_model=RetrieverDetailResponse)
def update_retriever(retriever_id: str, request: UpdateRetrieverRequest):
    """Update retriever settings (enable/disable, config, name)."""
    retriever = state.store.get_retriever(retriever_id)
    if not retriever:
        raise HTTPException(status_code=404, detail="Retriever not found")

    if request.is_enabled is not None:
        state.store.enable_retriever(retriever_id, request.is_enabled)

    if request.display_name is not None:
        retriever.display_name = request.display_name

    if request.config is not None:
        retriever.config.update(request.config)

    if request.display_name is not None or request.config is not None:
        state.store.update_retriever(retriever)

    # Re-fetch updated retriever
    retriever = state.store.get_retriever(retriever_id)
    children = state.store.get_children(retriever_id)

    return RetrieverDetailResponse(
        id=retriever.id,
        display_name=retriever.display_name,
        kind=retriever.kind.value,
        handler_type=retriever.handler_type,
        uri=retriever.uri,
        config=retriever.config,
        parent_id=retriever.parent_id,
        depth=retriever.depth,
        is_enabled=retriever.is_enabled,
        score=retriever.score.value if retriever.score else None,
        confidence=retriever.score.confidence if retriever.score else None,
        sample_size=retriever.score.sample_size if retriever.score else None,
        last_updated=retriever.score.last_updated if retriever.score else None,
        last_invoked_at=retriever.last_invoked_at,
        created_at=retriever.created_at,
        children_count=len(children),
    )


# =============================================================================
# Strategies API
# =============================================================================


class StrategyResponse(BaseModel):
    strategy_id: str
    display_name: str
    description: str
    provider: str
    method: str
    retriever_id: str | None = None  # If instantiated as a retriever
    score: float | None = None
    confidence: float | None = None
    sample_size: int | None = None
    is_enabled: bool = True


@app.get("/api/strategies", response_model=list[StrategyResponse])
def list_strategies():
    """List all available exploration strategies with their scores."""
    from omnifeed.retriever.handlers.strategy import get_all_strategies

    strategies = get_all_strategies()
    responses = []

    for strategy in strategies:
        # Check if there's a retriever for this strategy
        strategy_uri = f"strategy:{strategy.strategy_id}"
        retriever = state.store.get_retriever_by_uri(strategy_uri)

        responses.append(StrategyResponse(
            strategy_id=strategy.strategy_id,
            display_name=strategy.display_name,
            description=strategy.description,
            provider=strategy.provider,
            method=strategy.method,
            retriever_id=retriever.id if retriever else None,
            score=retriever.score.value if retriever and retriever.score else None,
            confidence=retriever.score.confidence if retriever and retriever.score else None,
            sample_size=retriever.score.sample_size if retriever and retriever.score else None,
            is_enabled=retriever.is_enabled if retriever else True,
        ))

    return responses


@app.post("/api/strategies/{strategy_id}/enable")
def enable_strategy(strategy_id: str):
    """Enable a strategy (creates retriever if needed)."""
    from omnifeed.retriever.handlers.strategy import get_strategy
    from omnifeed.retriever import find_handler

    strategy = get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail=f"Strategy not found: {strategy_id}")

    strategy_uri = f"strategy:{strategy_id}"
    retriever = state.store.get_retriever_by_uri(strategy_uri)

    if retriever:
        state.store.enable_retriever(retriever.id, True)
    else:
        # Create the retriever
        handler = find_handler(strategy_uri)
        if handler:
            retriever = handler.resolve(strategy_uri)
            retriever = state.store.add_retriever(retriever)

    return {"status": "enabled", "retriever_id": retriever.id if retriever else None}


@app.post("/api/strategies/{strategy_id}/disable")
def disable_strategy(strategy_id: str):
    """Disable a strategy."""
    from omnifeed.retriever.handlers.strategy import get_strategy

    strategy = get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail=f"Strategy not found: {strategy_id}")

    strategy_uri = f"strategy:{strategy_id}"
    retriever = state.store.get_retriever_by_uri(strategy_uri)

    if retriever:
        state.store.enable_retriever(retriever.id, False)
        return {"status": "disabled", "retriever_id": retriever.id}

    return {"status": "not_instantiated"}


# =============================================================================
# Control Plane: Exploration Config
# =============================================================================


class ExplorationConfig(BaseModel):
    explore_ratio: float = 0.3
    min_exploit_confidence: float = 0.3
    max_depth: int = 1
    default_limit: int = 20


# In-memory exploration config (could be persisted to DB later)
_exploration_config = ExplorationConfig()


@app.get("/api/exploration/config", response_model=ExplorationConfig)
def get_exploration_config():
    """Get current exploration configuration."""
    return _exploration_config


@app.put("/api/exploration/config", response_model=ExplorationConfig)
def update_exploration_config(config: ExplorationConfig):
    """Update exploration configuration."""
    global _exploration_config

    # Validate
    if not 0.0 <= config.explore_ratio <= 1.0:
        raise HTTPException(status_code=400, detail="explore_ratio must be between 0 and 1")
    if not 0.0 <= config.min_exploit_confidence <= 1.0:
        raise HTTPException(status_code=400, detail="min_exploit_confidence must be between 0 and 1")

    _exploration_config = config
    return _exploration_config


class ExplorationStatsResponse(BaseModel):
    total_retrievers: int
    enabled_retrievers: int
    scored_retrievers: int
    unscored_retrievers: int
    avg_score: float | None
    avg_confidence: float | None
    by_kind: dict[str, int]
    by_handler: dict[str, int]
    top_performers: list[RetrieverResponse]
    needs_exploration: list[RetrieverResponse]


@app.get("/api/exploration/stats", response_model=ExplorationStatsResponse)
def get_exploration_stats():
    """Get exploration system statistics."""
    from omnifeed.retriever.scoring import RetrieverScorer

    all_retrievers = state.store.list_retrievers(enabled_only=False, limit=500)
    enabled = [r for r in all_retrievers if r.is_enabled]
    scored = [r for r in all_retrievers if r.score is not None]
    unscored = [r for r in all_retrievers if r.score is None]

    # Aggregate stats
    by_kind: dict[str, int] = {}
    by_handler: dict[str, int] = {}
    for r in all_retrievers:
        by_kind[r.kind.value] = by_kind.get(r.kind.value, 0) + 1
        by_handler[r.handler_type] = by_handler.get(r.handler_type, 0) + 1

    avg_score = sum(r.score.value for r in scored) / len(scored) if scored else None
    avg_confidence = sum(r.score.confidence for r in scored) / len(scored) if scored else None

    # Get top performers and exploration candidates
    scorer = RetrieverScorer(state.store)
    top = scorer.get_top_retrievers(limit=5, min_confidence=0.1)
    explore_candidates = scorer.get_exploration_candidates(limit=5, max_confidence=0.5)

    def to_response(r):
        return RetrieverResponse(
            id=r.id,
            display_name=r.display_name,
            kind=r.kind.value,
            handler_type=r.handler_type,
            uri=r.uri,
            score=r.score.value if r.score else None,
            confidence=r.score.confidence if r.score else None,
            is_enabled=r.is_enabled,
        )

    return ExplorationStatsResponse(
        total_retrievers=len(all_retrievers),
        enabled_retrievers=len(enabled),
        scored_retrievers=len(scored),
        unscored_retrievers=len(unscored),
        avg_score=avg_score,
        avg_confidence=avg_confidence,
        by_kind=by_kind,
        by_handler=by_handler,
        top_performers=[to_response(r) for r in top],
        needs_exploration=[to_response(r) for r in explore_candidates],
    )


# =============================================================================
# Health check
# =============================================================================


@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
