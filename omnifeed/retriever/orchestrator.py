"""Orchestrator for recursive retriever invocation.

The orchestrator manages the invocation of retrievers, handling:
- Recursive invocation up to max_depth
- Deduplication of discovered retrievers
- Collection of content results
- Updating invocation timestamps
"""

from __future__ import annotations

import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from omnifeed.models import Item
from omnifeed.retriever.types import (
    Retriever,
    RetrievalContext,
    RetrievalResult,
    ResultType,
)
from omnifeed.retriever.registry import get_handler

if TYPE_CHECKING:
    from omnifeed.store.base import Store

logger = logging.getLogger(__name__)


@dataclass
class InvocationResult:
    """Result of orchestrator invocation.

    Collects all content and newly discovered retrievers.
    """
    items: list[Item] = field(default_factory=list)
    new_retrievers: list[Retriever] = field(default_factory=list)
    errors: list[tuple[str, Exception]] = field(default_factory=list)

    @property
    def content_count(self) -> int:
        return len(self.items)


class RetrieverOrchestrator:
    """Orchestrates recursive retriever invocation.

    Usage:
        orchestrator = RetrieverOrchestrator(store)

        # Invoke a single retriever
        result = await orchestrator.invoke(retriever, context)

        # Invoke for home feed (explores from root)
        result = await orchestrator.invoke_for_feed(context)
    """

    def __init__(self, store: Store):
        self.store = store
        self._seen_uris: set[str] = set()

    async def invoke(
        self,
        retriever: Retriever,
        context: RetrievalContext,
        current_depth: int = 0,
    ) -> InvocationResult:
        """Invoke a retriever and optionally recurse into sub-retrievers.

        Args:
            retriever: The retriever to invoke.
            context: Invocation context with limits and filters.
            current_depth: Current recursion depth (internal use).

        Returns:
            InvocationResult with collected content and new retrievers.
        """
        indent = "  " * current_depth
        logger.info(f"{indent}[ORCH] invoke() depth={current_depth} uri={retriever.uri} handler={retriever.handler_type}")

        result = InvocationResult()

        # Check if we've already seen this retriever
        if retriever.uri in self._seen_uris:
            logger.info(f"{indent}[ORCH] Already seen, skipping")
            return result
        self._seen_uris.add(retriever.uri)

        # Get the handler for this retriever
        handler = get_handler(retriever.handler_type)
        if not handler:
            logger.warning(f"{indent}[ORCH] No handler found for type: {retriever.handler_type}")
            result.errors.append((retriever.uri, ValueError(f"No handler: {retriever.handler_type}")))
            return result

        # Invoke the handler
        logger.info(f"{indent}[ORCH] Calling handler.invoke()...")
        try:
            raw_results = await handler.invoke(retriever, context)
            logger.info(f"{indent}[ORCH] Handler returned {len(raw_results)} results")
        except Exception as e:
            logger.error(f"{indent}[ORCH] Error invoking {retriever.uri}: {e}")
            result.errors.append((retriever.uri, e))
            return result

        # Update invocation timestamp
        now = datetime.utcnow()
        if retriever.id:
            self.store.update_retriever_invoked(retriever.id, now)

        # Process results
        content_count = 0
        retriever_count = 0
        for raw in raw_results:
            if raw.result_type == ResultType.CONTENT:
                # Content result
                content_count += 1
                if raw.item:
                    result.items.append(raw.item)
                    logger.info(f"{indent}[ORCH] Got CONTENT item: {raw.item.title[:50] if raw.item.title else 'no title'}...")

            elif raw.result_type == ResultType.RETRIEVER and raw.retriever:
                # Sub-retriever discovered
                retriever_count += 1
                sub_retriever = raw.retriever

                # Skip if already seen
                if sub_retriever.uri in self._seen_uris:
                    logger.info(f"{indent}[ORCH] Sub-retriever already seen: {sub_retriever.uri}")
                    continue

                logger.info(f"{indent}[ORCH] Got RETRIEVER: {sub_retriever.display_name} ({sub_retriever.uri})")

                # Set parent relationship
                sub_retriever.parent_id = retriever.id
                sub_retriever.depth = current_depth + 1

                # Check if this retriever already exists
                existing = self.store.get_retriever_by_uri(sub_retriever.uri)
                if existing:
                    sub_retriever = existing
                    logger.info(f"{indent}[ORCH] Retriever already exists in DB: {existing.id}")
                else:
                    # Store new retriever
                    sub_retriever = self.store.add_retriever(sub_retriever)
                    result.new_retrievers.append(sub_retriever)
                    logger.info(f"{indent}[ORCH] Created new retriever: {sub_retriever.id}")

                # Recurse if within depth limit
                if current_depth < context.max_depth:
                    logger.info(f"{indent}[ORCH] Recursing into sub-retriever (depth {current_depth} < max {context.max_depth})")
                    sub_result = await self.invoke(
                        sub_retriever, context, current_depth + 1
                    )
                    logger.info(f"{indent}[ORCH] Sub-invoke returned: {len(sub_result.items)} items, {len(sub_result.new_retrievers)} retrievers, {len(sub_result.errors)} errors")
                    # Merge results
                    result.items.extend(sub_result.items)
                    result.new_retrievers.extend(sub_result.new_retrievers)
                    result.errors.extend(sub_result.errors)
                else:
                    logger.info(f"{indent}[ORCH] NOT recursing (depth {current_depth} >= max {context.max_depth})")

        logger.info(f"{indent}[ORCH] Processed {content_count} CONTENT + {retriever_count} RETRIEVER results")
        logger.info(f"{indent}[ORCH] Final: {len(result.items)} items, {len(result.new_retrievers)} new_retrievers, {len(result.errors)} errors")
        return result

    async def invoke_for_feed(
        self,
        context: RetrievalContext | None = None,
        use_scores: bool = True,
    ) -> InvocationResult:
        """Invoke retrievers for the home feed with explore/exploit balance.

        This is the main entry point for building the feed. It:
        1. Selects retrievers using explore/exploit balance (if use_scores=True)
        2. Invokes each one to fetch new content
        3. Collects all results

        CRITICAL: Always reserves explore_ratio for exploration to prevent
        the system from only exploiting known-good sources.

        For explore mode, use invoke() with an EXPLORE retriever.

        Args:
            context: Optional context, uses defaults if not provided.
            use_scores: Whether to use score-based selection (default True).

        Returns:
            InvocationResult with all collected content.
        """
        if context is None:
            context = RetrievalContext()

        result = InvocationResult()
        self._seen_uris.clear()

        if use_scores:
            # Score-aware selection with guaranteed exploration
            from omnifeed.retriever.scoring import RetrieverScorer
            scorer = RetrieverScorer(self.store)

            exploit_retrievers, explore_retrievers = scorer.select_retrievers(
                limit=20,
                explore_ratio=context.explore_ratio,
            )

            retrievers = exploit_retrievers + explore_retrievers
            logger.info(
                f"Selected {len(exploit_retrievers)} exploit + "
                f"{len(explore_retrievers)} explore retrievers"
            )
        else:
            # Fallback: just get retrievers due for polling
            retrievers = self.store.get_retrievers_needing_poll(limit=20)

        for retriever in retrievers:
            if not context.include_disabled and not retriever.is_enabled:
                continue

            sub_result = await self.invoke(retriever, context)
            result.items.extend(sub_result.items)
            result.new_retrievers.extend(sub_result.new_retrievers)
            result.errors.extend(sub_result.errors)

        return result
