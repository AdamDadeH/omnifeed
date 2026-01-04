"""Exploratory handler for discovering new sources.

This handler provides random/topic-based source discovery, enabling
the "explore" functionality where users can discover new content sources.

URI formats:
- explore:all - Explore across all source types
- explore:random - Random source discovery
- explore:topic:{topic} - Topic-based discovery (e.g., explore:topic:jazz)
"""

import random
import logging
from datetime import datetime

from omnifeed.retriever.types import (
    Retriever,
    RetrieverKind,
    RetrievalContext,
    RetrievalResult,
)
from omnifeed.retriever.handlers.base import RetrieverHandler
from omnifeed.sources.registry import get_registry
from omnifeed.sources.base import SourceSuggestion

logger = logging.getLogger(__name__)


class ExploratoryHandler(RetrieverHandler):
    """Handler for discovering new sources through exploration.

    This handler returns sub-retrievers (not content directly) that
    represent newly discovered sources to explore.

    It uses the search providers from existing source adapters to
    find new sources based on topics or random exploration.
    """

    # Sample topics for random exploration
    SAMPLE_TOPICS = [
        # Music genres
        "jazz", "classical", "electronic", "ambient", "indie rock",
        "hip hop", "folk", "metal", "punk", "soul", "r&b",
        # Tech topics
        "programming", "machine learning", "web development", "devops",
        "security", "open source", "rust programming", "python",
        # Science
        "physics", "biology", "astronomy", "climate", "mathematics",
        # Other interests
        "philosophy", "history", "economics", "design", "art",
        "photography", "film", "cooking", "travel", "books",
    ]

    @property
    def handler_type(self) -> str:
        return "exploratory"

    def can_handle(self, uri: str) -> bool:
        return uri.startswith("explore:")

    def resolve(self, uri: str, display_name: str | None = None) -> Retriever:
        """Create an exploratory retriever."""
        parts = uri.split(":", 2)

        if len(parts) == 2 and parts[1] in ("all", "random"):
            name = display_name or "Explore All"
            config = {"mode": parts[1]}
        elif len(parts) == 3 and parts[1] == "topic":
            topic = parts[2]
            name = display_name or f"Explore: {topic}"
            config = {"mode": "topic", "topic": topic}
        else:
            name = display_name or "Explore"
            config = {"mode": "all"}

        return Retriever(
            id="",
            display_name=name,
            kind=RetrieverKind.EXPLORE,
            handler_type=self.handler_type,
            uri=uri,
            config=config,
        )

    async def invoke(
        self,
        retriever: Retriever,
        context: RetrievalContext,
    ) -> list[RetrievalResult]:
        """Discover new sources and return them as sub-retrievers."""
        mode = retriever.config.get("mode", "all")
        topic = retriever.config.get("topic")

        if mode == "random" or (mode == "all" and not topic):
            # Pick a random topic
            topic = random.choice(self.SAMPLE_TOPICS)
            logger.info(f"Exploring random topic: {topic}")

        # Get search providers
        registry = get_registry()
        search_providers = registry.search_providers

        if not search_providers:
            logger.warning("No search providers available for exploration")
            return []

        results: list[RetrievalResult] = []
        seen_urls: set[str] = set()

        # Search across all providers
        for provider in search_providers:
            try:
                suggestions = await provider.search(
                    query=topic or "popular",
                    limit=context.max_results // len(search_providers) + 1,
                )

                for suggestion in suggestions:
                    # Skip duplicates
                    if suggestion.url in seen_urls:
                        continue
                    seen_urls.add(suggestion.url)

                    # Convert suggestion to a retriever
                    sub_retriever = self._suggestion_to_retriever(suggestion)
                    result = RetrievalResult.from_retriever(
                        sub_retriever,
                        context=f"Discovered via {provider.provider_id}: {topic}",
                    )
                    results.append(result)

                    if len(results) >= context.max_results:
                        break

            except Exception as e:
                logger.error(f"Error searching {provider.provider_id}: {e}")
                continue

            if len(results) >= context.max_results:
                break

        # Shuffle results for variety
        random.shuffle(results)

        return results[:context.max_results]

    def _suggestion_to_retriever(self, suggestion: SourceSuggestion) -> Retriever:
        """Convert a source suggestion to a retriever."""
        # Build the source URI
        uri = f"source:{suggestion.source_type}:{suggestion.url}"

        return Retriever(
            id="",
            display_name=suggestion.name,
            kind=RetrieverKind.POLL,
            handler_type="source",  # Will be handled by SourceRetrieverHandler
            uri=uri,
            config={
                "source_type": suggestion.source_type,
                "source_uri": suggestion.url,
                "description": suggestion.description,
                "thumbnail_url": suggestion.thumbnail_url,
                "subscriber_count": suggestion.subscriber_count,
                "discovery_metadata": suggestion.metadata,
            },
        )
