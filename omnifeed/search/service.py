"""Search service that aggregates multiple search providers."""

import asyncio
import logging

from omnifeed.sources.base import SearchProvider, SourceSuggestion

logger = logging.getLogger(__name__)


class SearchService:
    """Aggregates search results from multiple providers."""

    def __init__(self):
        self._providers: list[SearchProvider] = []

    def register(self, provider: SearchProvider) -> None:
        """Register a search provider."""
        self._providers.append(provider)
        logger.info(f"Registered search provider: {provider.provider_id}")

    def register_all(self, providers: list[SearchProvider]) -> None:
        """Register multiple providers."""
        for provider in providers:
            self.register(provider)

    @property
    def providers(self) -> list[SearchProvider]:
        """Get all registered providers."""
        return list(self._providers)

    @property
    def provider_ids(self) -> list[str]:
        """Get IDs of all registered providers."""
        return [p.provider_id for p in self._providers]

    async def search(
        self,
        query: str,
        limit: int = 20,
        provider_ids: list[str] | None = None,
    ) -> list[SourceSuggestion]:
        """Search across all (or specified) providers."""
        providers = self._providers
        if provider_ids:
            providers = [p for p in providers if p.provider_id in provider_ids]

        if not providers:
            return []

        tasks = [self._search_provider(provider, query, limit) for provider in providers]
        results = await asyncio.gather(*tasks)

        all_suggestions = []
        for suggestions in results:
            all_suggestions.extend(suggestions)

        return all_suggestions

    async def _search_provider(
        self,
        provider: SearchProvider,
        query: str,
        limit: int,
    ) -> list[SourceSuggestion]:
        """Search a single provider with error handling."""
        try:
            return await provider.search(query, limit)
        except Exception as e:
            logger.warning(f"Search failed for {provider.provider_id}: {e}")
            return []


# Default service singleton
_search_service: SearchService | None = None


def get_search_service() -> SearchService:
    """Get or create the default search service.

    Uses the plugin registry to auto-discover search providers.
    """
    global _search_service

    if _search_service is None:
        _search_service = SearchService()

        # Use the new plugin registry to get search providers
        try:
            from omnifeed.sources import get_registry
            registry = get_registry()
            for provider in registry.search_providers:
                _search_service.register(provider)
        except Exception as e:
            logger.warning(f"Failed to load search providers from registry: {e}")

    return _search_service
