"""Ranking pipeline for scoring and ordering items."""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from omnifeed.models import Item
from omnifeed.ranking.embeddings import get_embedding_by_type
from omnifeed.ranking.registry import FeatureRegistry
from omnifeed.ranking.model_registry import get_model_registry

if TYPE_CHECKING:
    from omnifeed.store import Store

logger = logging.getLogger(__name__)


# =============================================================================
# Retriever interface
# =============================================================================


@dataclass
class RetrievalStats:
    """Stats from retrieval step."""
    candidates: int
    retrieval_time_ms: float


class Retriever(ABC):
    """Base class for candidate retrieval."""

    @abstractmethod
    def retrieve(
        self,
        store: "Store",
        seen: bool | None = None,
        hidden: bool = False,
        source_id: str | None = None,
        limit: int | None = None,
    ) -> tuple[list[Item], RetrievalStats]:
        """Retrieve candidate items for ranking.

        Args:
            store: Data store
            seen: Filter by seen status (None = all)
            hidden: Filter by hidden status
            source_id: Filter by source
            limit: Max candidates to retrieve (None = all)

        Returns:
            (items, stats)
        """
        pass


class AllRetriever(Retriever):
    """Retrieves ALL matching items. Simple but doesn't scale."""

    def retrieve(
        self,
        store: "Store",
        seen: bool | None = None,
        hidden: bool = False,
        source_id: str | None = None,
        limit: int | None = None,
    ) -> tuple[list[Item], RetrievalStats]:
        t0 = time.perf_counter()

        # Fetch all matching items
        items = store.get_items(
            seen=seen,
            hidden=hidden,
            source_id=source_id,
            limit=limit or 100000,  # Effectively unlimited
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000

        return items, RetrievalStats(
            candidates=len(items),
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
        retriever: Retriever | None = None,
        use_ml_model: bool = True,
    ):
        self.feature_registry = feature_registry or FeatureRegistry()
        self.retriever = retriever or AllRetriever()
        self.use_ml_model = use_ml_model

    def score(self, item: Item, objective: str | None = None) -> float:
        """Score a single item.

        Args:
            item: The item to score
            objective: Optional objective to optimize for (entertainment, curiosity, etc.)
                      Registry maps objectives to appropriate models.

        Uses ML model if trained, otherwise falls back to recency.
        """
        if not self.use_ml_model:
            return self._recency_score(item)

        # Get model from registry (handles objective -> model mapping)
        registry = get_model_registry()
        model, model_name = registry.get_model_for_objective(objective)

        if model and model.is_trained and get_embedding_by_type(item.embeddings, "text"):
            try:
                return model.score(item, objective=objective)
            except Exception as e:
                logger.warning(f"ML scoring failed ({model_name}): {e}")

        # Fallback: recency-based scoring
        return self._recency_score(item)

    def _recency_score(self, item: Item) -> float:
        """Compute recency-based score."""
        age_seconds = (datetime.utcnow() - item.published_at).total_seconds()
        # Normalize to roughly 0-5 range (1 day old = ~2.5)
        return max(0, 5 - (age_seconds / 86400))

    def rank(self, items: list[Item]) -> list[Item]:
        """Return items sorted by score descending."""
        return sorted(items, key=lambda i: self.score(i), reverse=True)

    def retrieve_and_rank(
        self,
        store: "Store",
        seen: bool | None = None,
        hidden: bool = False,
        source_id: str | None = None,
        limit: int = 50,
        objective: str | None = None,
    ) -> tuple[list[Item], RankingStats]:
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
        items, retrieval_stats = self.retriever.retrieve(
            store=store,
            seen=seen,
            hidden=hidden,
            source_id=source_id,
        )

        # Step 2: Score all candidates
        t1 = time.perf_counter()
        scored = [(item, self.score(item, objective=objective)) for item in items]
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

        # Return top items with scores attached
        top_items = [item for item, _ in scored[:limit]]
        return top_items, stats

    def rank_with_diversity(
        self,
        items: list[Item],
        max_per_source: int = 3,
    ) -> list[Item]:
        """Rank items with diversity injection.

        Limits consecutive items from same source.
        """
        scored = [(item, self.score(item)) for item in items]
        scored.sort(key=lambda x: x[1], reverse=True)

        result = []
        source_counts: dict[str, int] = {}
        deferred: list[tuple[Item, float]] = []

        for item, score in scored:
            count = source_counts.get(item.source_id, 0)
            if count < max_per_source:
                result.append(item)
                source_counts[item.source_id] = count + 1
            else:
                deferred.append((item, score))

        # Add deferred items at the end
        for item, _ in deferred:
            result.append(item)

        return result


def create_default_pipeline() -> RankingPipeline:
    """Create a ranking pipeline with default extractors."""
    from omnifeed.ranking.extractors import FreshnessExtractor, ContentTypeExtractor

    registry = FeatureRegistry()
    registry.register(FreshnessExtractor())
    registry.register(ContentTypeExtractor())

    return RankingPipeline(registry, retriever=AllRetriever())
