"""Ranking pipeline for scoring and ordering content."""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from omnifeed.models import Content
from omnifeed.featurization import get_embedding_by_type
from omnifeed.ranking.registry import FeatureRegistry
from omnifeed.ranking.model_registry import get_model_registry

if TYPE_CHECKING:
    from omnifeed.store import Store

logger = logging.getLogger(__name__)


def _get_embeddings(content: Content) -> list[dict]:
    """Get embeddings from Content as dicts.

    Handles both Embedding objects and legacy dict format.
    """
    result = []
    for e in content.embeddings:
        if isinstance(e, dict):
            result.append(e)
        else:
            result.append({"name": e.name, "type": e.type, "vector": e.vector, "model": e.model})
    return result


def _get_source_key(content: Content, store: "Store" = None) -> str:
    """Get a source identifier for diversity calculation."""
    if store:
        encoding = store.get_primary_encoding(content.id)
        if encoding:
            return encoding.source_type
    return content.id


# =============================================================================
# Retriever interface
# =============================================================================


@dataclass
class RetrievalStats:
    """Stats from retrieval step."""
    candidates: int
    retrieval_time_ms: float


class ContentRetriever:
    """Retrieves Content from the store."""

    def retrieve(
        self,
        store: "Store",
        seen: bool | None = None,
        hidden: bool = False,
        source_type: str | None = None,
        limit: int | None = None,
    ) -> tuple[list[Content], RetrievalStats]:
        t0 = time.perf_counter()

        contents = store.get_contents(
            seen=seen,
            hidden=hidden,
            source_type=source_type,
            limit=limit or 100000,
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000

        return contents, RetrievalStats(
            candidates=len(contents),
            retrieval_time_ms=round(elapsed_ms, 2),
        )


# =============================================================================
# Ranking pipeline
# =============================================================================


@dataclass
class RankingStats:
    """Stats from the full ranking pipeline."""
    retrieval: RetrievalStats
    score_time_ms: float
    sort_time_ms: float
    total_time_ms: float
    scored_count: int


class RankingPipeline:
    """Scores and ranks items for the feed.

    Architecture:
    1. Retriever fetches candidates
    2. Ranker scores each candidate
    3. Sort by score

    Uses trained ML model when available, falls back to chronological.
    """

    def __init__(
        self,
        feature_registry: FeatureRegistry | None = None,
        retriever: ContentRetriever | None = None,
        use_ml_model: bool = True,
    ):
        self.feature_registry = feature_registry or FeatureRegistry()
        self.retriever = retriever or ContentRetriever()
        self.use_ml_model = use_ml_model

    def score(self, content: Content, objective: str | None = None) -> float:
        """Score content.

        Args:
            content: The content to score
            objective: Optional objective to optimize for (entertainment, curiosity, etc.)
        """
        if not self.use_ml_model:
            return self._recency_score(content)

        registry = get_model_registry()
        model, model_name = registry.get_model_for_objective(objective)

        embeddings = _get_embeddings(content)

        if model and model.is_trained and get_embedding_by_type(embeddings, "text"):
            try:
                return model.score(content, objective=objective)
            except Exception as e:
                logger.warning(f"ML scoring failed ({model_name}): {e}")

        return self._recency_score(content)

    def _recency_score(self, content: Content) -> float:
        """Compute recency-based score."""
        age_seconds = (datetime.utcnow() - content.published_at).total_seconds()
        return max(0, 5 - (age_seconds / 86400))

    def rank(self, contents: list[Content]) -> list[Content]:
        """Return contents sorted by score descending."""
        return sorted(contents, key=lambda c: self.score(c), reverse=True)

    def retrieve_and_rank(
        self,
        store: "Store",
        seen: bool | None = None,
        hidden: bool = False,
        source_id: str | None = None,
        limit: int = 50,
        objective: str | None = None,
    ) -> tuple[list[Content], RankingStats]:
        """Full pipeline: retrieve candidates, score, rank, return top.

        Args:
            store: Data store
            seen: Filter by seen status
            hidden: Filter by hidden status
            source_id: Filter by source
            limit: Number of items to return
            objective: Ranking objective (e.g., entertainment, curiosity)

        Returns:
            (ranked_items, stats)
        """
        # Step 1: Retrieve candidates
        contents, retrieval_stats = self.retriever.retrieve(
            store=store,
            seen=seen,
            hidden=hidden,
            source_id=source_id,
        )

        # Step 2: Score all candidates
        t1 = time.perf_counter()
        scored = [(content, self.score(content, objective=objective)) for content in contents]
        score_time_ms = (time.perf_counter() - t1) * 1000

        # Step 3: Sort by score
        t2 = time.perf_counter()
        scored.sort(key=lambda x: x[1], reverse=True)
        sort_time_ms = (time.perf_counter() - t2) * 1000

        total_time_ms = retrieval_stats.retrieval_time_ms + score_time_ms + sort_time_ms

        stats = RankingStats(
            retrieval=retrieval_stats,
            score_time_ms=round(score_time_ms, 2),
            sort_time_ms=round(sort_time_ms, 2),
            total_time_ms=round(total_time_ms, 2),
            scored_count=len(scored),
        )

        # Log performance
        logger.info(
            f"Ranking: {stats.scored_count} items in {stats.total_time_ms:.0f}ms "
            f"(retrieve={stats.retrieval.retrieval_time_ms:.0f}ms, "
            f"score={stats.score_time_ms:.0f}ms, sort={stats.sort_time_ms:.0f}ms)"
        )

        # Return top contents with scores attached
        top_contents = [content for content, _ in scored[:limit]]
        return top_contents, stats

    def rank_with_diversity(
        self,
        contents: list[Content],
        max_per_source: int = 3,
        store: "Store" = None,
    ) -> list[Content]:
        """Rank contents with diversity injection.

        Limits consecutive items from same source.
        """
        scored = [(c, self.score(c)) for c in contents]
        scored.sort(key=lambda x: x[1], reverse=True)

        result = []
        source_counts: dict[str, int] = {}
        deferred: list[tuple[Content, float]] = []

        for content, score in scored:
            source_key = _get_source_key(content, store)
            count = source_counts.get(source_key, 0)
            if count < max_per_source:
                result.append(content)
                source_counts[source_key] = count + 1
            else:
                deferred.append((content, score))

        for content, _ in deferred:
            result.append(content)

        return result


def create_default_pipeline() -> RankingPipeline:
    """Create a ranking pipeline with default extractors."""
    from omnifeed.ranking.extractors import FreshnessExtractor, ContentTypeExtractor

    registry = FeatureRegistry()
    registry.register(FreshnessExtractor())
    registry.register(ContentTypeExtractor())

    return RankingPipeline(registry, retriever=ContentRetriever())
