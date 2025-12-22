"""Registry for source adapters."""

from omnifeed.adapters.base import SourceAdapter


class AdapterRegistry:
    """Registry of source adapters."""

    def __init__(self) -> None:
        self._adapters: list[SourceAdapter] = []

    def register(self, adapter: SourceAdapter) -> None:
        """Register an adapter."""
        self._adapters.append(adapter)

    def find_adapter(self, url: str) -> SourceAdapter | None:
        """Find first adapter that can handle this URL."""
        for adapter in self._adapters:
            if adapter.can_handle(url):
                return adapter
        return None

    def get_adapter_by_type(self, source_type: str) -> SourceAdapter | None:
        """Get an adapter by its source type."""
        for adapter in self._adapters:
            if adapter.source_type == source_type:
                return adapter
        return None

    def list_adapters(self) -> list[SourceAdapter]:
        """List all registered adapters."""
        return list(self._adapters)


def create_default_registry() -> AdapterRegistry:
    """Create a registry with all default adapters."""
    from omnifeed.adapters.rss import RSSAdapter

    registry = AdapterRegistry()
    registry.register(RSSAdapter())
    return registry
