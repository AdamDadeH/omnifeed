"""Unified item ingestion pipeline.

Ensures consistent feature extraction (embeddings, metadata) regardless of
how items enter the system: polling, explore, extension, manual import.

The pipeline is source-agnostic: it embeds whatever content_text is available
in item metadata. Source adapters are responsible for providing content_text
(transcripts, article bodies, etc.) during polling or via enrichment functions.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from omnifeed.models import Item, Content, Encoding, Embedding

if TYPE_CHECKING:
    from omnifeed.store.base import Store

logger = logging.getLogger(__name__)


# Metadata keys that belong to Content (about the content itself)
CONTENT_METADATA_KEYS = {
    "content_text",
    "content_html",
    "description",
    "thumbnail",
    "tags",
    "author",  # Will be used for creator lookup
}

# Metadata keys that belong to Encoding (about this specific access method)
ENCODING_METADATA_KEYS = {
    "view_count",
    "like_count",
    "duration_seconds",
    "bitrate",
    "resolution",
    "file_size",
    "video_id",
    "channel_id",
}


def _split_metadata(metadata: dict) -> tuple[dict, dict]:
    """Split metadata into content-level and encoding-level portions.

    Returns:
        (content_metadata, encoding_metadata)
    """
    content_meta = {}
    encoding_meta = {}

    for key, value in metadata.items():
        if key in CONTENT_METADATA_KEYS:
            content_meta[key] = value
        elif key in ENCODING_METADATA_KEYS:
            encoding_meta[key] = value
        else:
            # Default: put in content metadata (it's about the content)
            content_meta[key] = value

    return content_meta, encoding_meta


def item_to_content_and_encoding(item: Item) -> tuple[Content, Encoding]:
    """Convert an Item to Content + Encoding pair.

    Used for dual-write during migration. The Content keeps the same ID
    as the Item for backwards compatibility.
    """
    # Split metadata
    content_meta, encoding_meta = _split_metadata(item.metadata)

    # Convert old embeddings format (list of dicts) to Embedding objects
    embeddings = []
    for emb in item.embeddings:
        embeddings.append(Embedding(
            name=emb.get("name", "default"),
            type=emb.get("type", "text"),
            vector=emb.get("vector", []),
            model=emb.get("model", ""),
        ))

    # Build creator_ids list from single creator_id
    creator_ids = []
    if item.creator_id:
        creator_ids.append(item.creator_id)

    content = Content(
        id=item.id,  # Keep same ID for backwards compat
        title=item.title,
        content_type=item.content_type,
        published_at=item.published_at,
        ingested_at=item.ingested_at,
        creator_ids=creator_ids,
        consumption_type=item.consumption_type,
        canonical_ids=item.canonical_ids,
        seen=item.seen,
        hidden=item.hidden,
        series_id=item.series_id,
        series_position=item.series_position,
        metadata=content_meta,
        embeddings=embeddings,
    )

    encoding = Encoding(
        id=uuid.uuid4().hex[:12],
        content_id=item.id,
        source_type=item.source_id,  # source_id becomes source_type
        external_id=item.external_id,
        uri=item.url,
        media_type=encoding_meta.get("media_type"),
        metadata=encoding_meta,
        discovered_at=item.ingested_at,
        is_primary=True,
    )

    return content, encoding


class ItemIngestionPipeline:
    """Unified pipeline for ingesting items with feature extraction.

    Usage:
        pipeline = ItemIngestionPipeline(store)
        items = pipeline.ingest(items, source_type="rss")

    The pipeline embeds content_text from item metadata. Source adapters
    should populate content_text with whatever text best represents the item
    (transcript, article body, description, etc.).
    """

    def __init__(self, store: Store):
        self.store = store
        self._embedding_service = None

    @property
    def embedding_service(self):
        """Lazy-load embedding service."""
        if self._embedding_service is None:
            from omnifeed.featurization import get_embedding_service
            self._embedding_service = get_embedding_service()
        return self._embedding_service

    @property
    def audio_embedding_service(self):
        """Lazy-load audio embedding service."""
        if not hasattr(self, "_audio_embedding_service"):
            self._audio_embedding_service = None
        if self._audio_embedding_service is None:
            try:
                from omnifeed.featurization.audio import get_audio_embedding_service
                self._audio_embedding_service = get_audio_embedding_service()
            except Exception as e:
                logger.debug(f"Audio embedding service not available: {e}")
                self._audio_embedding_service = False  # Mark as unavailable
        return self._audio_embedding_service if self._audio_embedding_service else None

    def ingest(
        self,
        items: list[Item],
        source_type: str | None = None,
        generate_embeddings: bool = True,
        enrich_content: bool = True,
        persist: bool = True,
    ) -> list[Item]:
        """Ingest items with unified feature extraction.

        Args:
            items: Items to ingest
            source_type: Type of source (for source-specific enrichment)
            generate_embeddings: Whether to generate embeddings
            enrich_content: Whether to run source-specific content enrichment
            persist: Whether to save to store

        Returns:
            Processed items (same list, mutated in place)
        """
        if not items:
            return items

        logger.info(f"Ingesting {len(items)} items (source_type={source_type})")

        # 1. Source-specific content enrichment (e.g., fetch transcripts)
        if enrich_content and source_type:
            self._enrich_content(items, source_type)

        # 2. Text embeddings (uses content_text from metadata)
        if generate_embeddings:
            self._add_text_embeddings(items)

        # 3. Audio embeddings (for items with audio_preview_url)
        if generate_embeddings:
            self._add_audio_embeddings(items)

        # 4. Persist items (dual-write: Item + Content/Encoding)
        if persist:
            for item in items:
                # Write legacy Item
                self.store.upsert_item(item)

                # Dual-write: also create Content + Encoding
                try:
                    content, encoding = item_to_content_and_encoding(item)
                    self.store.upsert_content(content)

                    # Check if encoding already exists (dedup by source_type + external_id)
                    existing = self.store.get_encoding_by_external_id(
                        encoding.source_type, encoding.external_id
                    )
                    if not existing:
                        self.store.add_encoding(encoding)
                except Exception as e:
                    # Log but don't fail - dual-write is for migration
                    logger.debug(f"Dual-write failed for {item.id}: {e}")

            logger.info(f"Persisted {len(items)} items (with dual-write)")

        return items

    def _enrich_content(self, items: list[Item], source_type: str) -> None:
        """Run source-specific content enrichment.

        Each source type can register an enrichment function that enhances
        content_text with additional content (transcripts, full article text, etc.).
        """
        enrichment_functions = {
            "youtube_channel": self._enrich_youtube,
            "youtube_playlist": self._enrich_youtube,
        }

        enrich_fn = enrichment_functions.get(source_type)
        if enrich_fn:
            try:
                enrich_fn(items)
            except Exception as e:
                logger.warning(f"Content enrichment failed for {source_type}: {e}")

    def _enrich_youtube(self, items: list[Item]) -> None:
        """Enrich YouTube items with transcripts in content_text."""
        try:
            from omnifeed.sources.youtube.adapter import enrich_with_transcript
            enriched = enrich_with_transcript(items)
            if enriched:
                logger.info(f"Enriched {enriched} items with transcripts")
        except ImportError:
            logger.debug("YouTube transcript enrichment not available")

    def _add_text_embeddings(self, items: list[Item]) -> None:
        """Generate text embeddings for items that don't have them.

        Uses content_text from metadata if available, which may include
        transcripts, article bodies, or other enriched content.
        """
        # Filter to items without text embeddings
        needs_embedding = [
            item for item in items
            if not any(e.get("type") == "text" for e in item.embeddings)
        ]

        if not needs_embedding:
            return

        try:
            embeddings = self.embedding_service.embed_items(needs_embedding)
            for item, emb in zip(needs_embedding, embeddings):
                item.embeddings.append(emb)
            logger.info(f"Generated text embeddings for {len(needs_embedding)} items")
        except Exception as e:
            logger.warning(f"Failed to generate text embeddings: {e}")

    def _add_audio_embeddings(self, items: list[Item]) -> None:
        """Generate audio embeddings for items with audio_preview_url.

        Uses CLAP to embed audio previews (e.g., Bandcamp MP3 previews).
        This enables audio-based similarity and cross-modal search.
        """
        audio_service = self.audio_embedding_service
        if not audio_service:
            return

        # Filter to items with audio preview URLs and no audio embeddings
        needs_embedding = [
            item for item in items
            if item.metadata.get("audio_preview_url")
            and not any(e.get("type") == "audio" for e in item.embeddings)
        ]

        if not needs_embedding:
            return

        logger.info(f"Generating audio embeddings for {len(needs_embedding)} items...")

        embedded_count = 0
        for item in needs_embedding:
            audio_url = item.metadata.get("audio_preview_url")
            try:
                emb = audio_service.embed_from_url(audio_url)
                if emb:
                    item.embeddings.append(emb)
                    embedded_count += 1
            except Exception as e:
                logger.debug(f"Failed to embed audio for {item.title}: {e}")

        if embedded_count > 0:
            logger.info(f"Generated audio embeddings for {embedded_count} items")

    def refresh_embeddings(
        self,
        items: list[Item] | None = None,
        source_id: str | None = None,
        embedding_type: str = "text",
        force: bool = False,
    ) -> dict[str, int]:
        """Refresh embeddings for existing items.

        Args:
            items: Specific items to refresh (if None, queries from store)
            source_id: Filter by source
            embedding_type: Type of embedding to refresh
            force: Regenerate even if embedding exists

        Returns:
            Stats dict with updated_count, skipped_count, failed_count
        """
        if items is None:
            items = self.store.get_items(source_id=source_id, limit=10000)

        # Filter to items needing embeddings
        if force:
            to_embed = items
        else:
            to_embed = [
                item for item in items
                if not any(e.get("type") == embedding_type for e in item.embeddings)
            ]

        if not to_embed:
            return {"updated_count": 0, "skipped_count": len(items), "failed_count": 0}

        updated = 0
        failed = 0

        try:
            embeddings = self.embedding_service.embed_items(to_embed)
            for item, emb in zip(to_embed, embeddings):
                try:
                    # Remove old embedding of same type
                    item.embeddings = [e for e in item.embeddings if e.get("type") != embedding_type]
                    item.embeddings.append(emb)
                    self.store.upsert_item(item)

                    # Dual-write: update Content embeddings too
                    try:
                        content, encoding = item_to_content_and_encoding(item)
                        self.store.upsert_content(content)
                    except Exception:
                        pass  # Silently skip if dual-write fails

                    updated += 1
                except Exception as e:
                    logger.warning(f"Failed to save embedding for {item.id}: {e}")
                    failed += 1
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            failed = len(to_embed)

        return {
            "updated_count": updated,
            "skipped_count": len(items) - len(to_embed),
            "failed_count": failed,
        }


# Singleton for reuse
_pipeline: ItemIngestionPipeline | None = None


def get_ingestion_pipeline(store: Store) -> ItemIngestionPipeline:
    """Get or create the ingestion pipeline singleton."""
    global _pipeline
    if _pipeline is None or _pipeline.store is not store:
        _pipeline = ItemIngestionPipeline(store)
    return _pipeline
