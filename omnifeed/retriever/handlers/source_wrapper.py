"""Handler that wraps existing Source + SourceAdapter patterns.

This provides backward compatibility by making existing sources work
as Retrievers without modification. Existing sources become leaf
Retrievers that poll for content.
"""

import uuid
from datetime import datetime, timezone

from omnifeed.models import Item, ContentType, ConsumptionType, Content, Encoding, Embedding
from omnifeed.sources.base import SourceInfo, RawItem, SourceAdapter
from omnifeed.sources.registry import get_registry
from omnifeed.retriever.types import (
    Retriever,
    RetrieverKind,
    RetrievalContext,
    RetrievalResult,
)
from omnifeed.retriever.handlers.base import RetrieverHandler


def _raw_item_to_item(raw: RawItem, source_id: str) -> Item:
    """Convert a RawItem from an adapter to an Item model."""
    # Extract common metadata
    metadata = dict(raw.raw_metadata)
    creator_name = metadata.pop("author", "")

    # Infer content type from metadata
    content_type = ContentType.ARTICLE  # default
    if "duration_seconds" in metadata:
        # Video or audio content
        if metadata.get("media_type") == "audio":
            content_type = ContentType.AUDIO
        else:
            content_type = ContentType.VIDEO
    elif metadata.get("content_type"):
        try:
            content_type = ContentType(metadata.pop("content_type"))
        except ValueError:
            pass

    return Item(
        id=uuid.uuid4().hex[:12],
        source_id=source_id,
        external_id=raw.external_id,
        url=raw.url,
        title=raw.title,
        creator_name=creator_name,
        published_at=raw.published_at,
        ingested_at=datetime.now(timezone.utc),
        content_type=content_type,
        consumption_type=ConsumptionType.ONE_SHOT,
        metadata=metadata,
    )


def _raw_item_to_content_and_encoding(
    raw: RawItem, source_type: str
) -> tuple[Content, Encoding]:
    """Convert a RawItem directly to Content + Encoding.

    This is the future path - skip Item entirely and create Content+Encoding.
    For now, used alongside _raw_item_to_item for dual-write.
    """
    from omnifeed.ingestion import CONTENT_METADATA_KEYS, ENCODING_METADATA_KEYS

    # Extract common metadata
    metadata = dict(raw.raw_metadata)
    creator_name = metadata.pop("author", "")

    # Infer content type
    content_type = ContentType.ARTICLE
    if "duration_seconds" in metadata:
        if metadata.get("media_type") == "audio":
            content_type = ContentType.AUDIO
        else:
            content_type = ContentType.VIDEO
    elif metadata.get("content_type"):
        try:
            content_type = ContentType(metadata.pop("content_type"))
        except ValueError:
            pass

    # Split metadata
    content_meta = {}
    encoding_meta = {}
    for key, value in metadata.items():
        if key in CONTENT_METADATA_KEYS:
            content_meta[key] = value
        elif key in ENCODING_METADATA_KEYS:
            encoding_meta[key] = value
        else:
            content_meta[key] = value

    content_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc)

    content = Content(
        id=content_id,
        title=raw.title,
        content_type=content_type,
        published_at=raw.published_at,
        ingested_at=now,
        creator_ids=[],  # TODO: lookup/create creator from creator_name
        consumption_type=ConsumptionType.ONE_SHOT,
        metadata=content_meta,
    )

    encoding = Encoding(
        id=uuid.uuid4().hex[:12],
        content_id=content_id,
        source_type=source_type,
        external_id=raw.external_id,
        uri=raw.url,
        media_type=encoding_meta.get("media_type"),
        metadata=encoding_meta,
        discovered_at=now,
        is_primary=True,
    )

    return content, encoding


class SourceRetrieverHandler(RetrieverHandler):
    """Wraps existing SourceAdapters as RetrieverHandlers.

    URI format: source:{source_type}:{original_uri}
    Example: source:youtube_channel:youtube:channel:UC...

    This handler creates POLL-type retrievers that periodically
    fetch content from existing source adapters.
    """

    @property
    def handler_type(self) -> str:
        return "source"

    def can_handle(self, uri: str) -> bool:
        """Check if this is a source:* URI or a URL we have an adapter for."""
        if uri.startswith("source:"):
            return True

        # Also check if any adapter can handle this URL
        registry = get_registry()
        return registry.find_adapter(uri) is not None

    def resolve(self, uri: str, display_name: str | None = None) -> Retriever:
        """Resolve a URI to a Retriever.

        Accepts either:
        - source:{type}:{uri} format
        - Raw URL that an adapter can handle
        """
        registry = get_registry()

        if uri.startswith("source:"):
            # Parse source:type:uri format
            parts = uri.split(":", 2)
            if len(parts) < 3:
                raise ValueError(f"Invalid source URI format: {uri}")
            _, source_type, source_uri = parts

            adapter = registry.get_adapter_by_type(source_type)
            if not adapter:
                raise ValueError(f"No adapter found for source type: {source_type}")

            # Get source info from adapter
            source_info = adapter.resolve(source_uri)

        else:
            # Raw URL - find adapter and resolve
            adapter = registry.find_adapter(uri)
            if not adapter:
                raise ValueError(f"No adapter found for URL: {uri}")

            source_info = adapter.resolve(uri)
            # Normalize to source: URI format
            uri = f"source:{source_info.source_type}:{source_info.uri}"

        return Retriever(
            id="",  # Will be assigned by store
            display_name=display_name or source_info.display_name,
            kind=RetrieverKind.POLL,
            handler_type=self.handler_type,
            uri=uri,
            config={
                "source_type": source_info.source_type,
                "source_uri": source_info.uri,
                "avatar_url": source_info.avatar_url,
                "source_metadata": source_info.metadata,
            },
        )

    async def invoke(
        self,
        retriever: Retriever,
        context: RetrievalContext,
    ) -> list[RetrievalResult]:
        """Poll the underlying source adapter for new content."""
        registry = get_registry()

        # Extract source info from config
        source_type = retriever.config.get("source_type")
        source_uri = retriever.config.get("source_uri")

        if not source_type or not source_uri:
            # Fall back to parsing URI
            parts = retriever.uri.split(":", 2)
            if len(parts) >= 3:
                source_type = parts[1]
                source_uri = parts[2]
            else:
                raise ValueError(f"Cannot parse source from URI: {retriever.uri}")

        adapter = registry.get_adapter_by_type(source_type)
        if not adapter:
            raise ValueError(f"No adapter found for source type: {source_type}")

        # Rebuild SourceInfo for the adapter
        source_info = SourceInfo(
            source_type=source_type,
            uri=source_uri,
            display_name=retriever.display_name,
            avatar_url=retriever.config.get("avatar_url"),
            metadata=retriever.config.get("source_metadata", {}),
        )

        # Determine since timestamp
        since = retriever.last_invoked_at

        # Poll for new items
        raw_items = adapter.poll(source_info, since)

        # Convert to RetrievalResults
        results: list[RetrievalResult] = []
        for i, raw in enumerate(raw_items[:context.max_results]):
            item = _raw_item_to_item(raw, retriever.id)
            result = RetrievalResult.from_item(
                item,
                rank=i + 1,
                context=f"From {retriever.display_name}",
            )
            results.append(result)

        return results


def source_to_retriever(source_type: str, source_uri: str, display_name: str) -> Retriever:
    """Create a Retriever from source information.

    Helper function for migrating existing Source records to Retrievers.
    """
    handler = SourceRetrieverHandler()
    uri = f"source:{source_type}:{source_uri}"
    return handler.resolve(uri, display_name=display_name)
