"""Plugin registry with auto-discovery.

The registry finds all plugins in omnifeed/sources/ subdirectories
and provides unified access to adapters and search providers.
"""

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Iterator

from omnifeed.sources.base import SourceAdapter, SearchProvider, SourcePlugin, SourceInfo

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Registry for source plugins with adapters and search providers."""

    def __init__(self):
        self._plugins: list[SourcePlugin] = []
        self._adapters_by_type: dict[str, SourceAdapter] = {}

    def register(self, plugin: SourcePlugin) -> None:
        """Register a source plugin."""
        self._plugins.append(plugin)
        self._adapters_by_type[plugin.source_type] = plugin.adapter
        logger.info(f"Registered plugin: {plugin.source_type}")

    @property
    def plugins(self) -> list[SourcePlugin]:
        """All registered plugins."""
        return list(self._plugins)

    @property
    def adapters(self) -> list[SourceAdapter]:
        """All registered adapters."""
        return [p.adapter for p in self._plugins]

    @property
    def search_providers(self) -> list[SearchProvider]:
        """All registered search providers (excluding None)."""
        return [p.search for p in self._plugins if p.search is not None]

    def find_adapter(self, url: str) -> SourceAdapter | None:
        """Find an adapter that can handle the given URL.

        Tries adapters in registration order. More specific adapters
        (YouTube, Bandcamp) should be registered before generic ones (RSS).
        """
        for adapter in self.adapters:
            if adapter.can_handle(url):
                return adapter
        return None

    def get_adapter_by_type(self, source_type: str) -> SourceAdapter | None:
        """Get an adapter by its source type."""
        return self._adapters_by_type.get(source_type)


def discover_plugins() -> Iterator[SourcePlugin]:
    """Discover all plugins in omnifeed/sources/ subdirectories.

    Each subdirectory (except _template) should have:
    - __init__.py with a `plugin` variable (SourcePlugin instance)
    - Optionally additional `*_plugin` variables for variants
    """
    sources_dir = Path(__file__).parent

    for item in sources_dir.iterdir():
        # Skip non-directories and special names
        if not item.is_dir():
            continue
        if item.name.startswith("_") or item.name.startswith("."):
            continue
        if item.name == "__pycache__":
            continue

        # Try to import the module
        module_name = f"omnifeed.sources.{item.name}"
        try:
            module = importlib.import_module(module_name)
        except ImportError as e:
            logger.warning(f"Failed to import plugin {module_name}: {e}")
            continue

        # Look for plugin instances
        for attr_name in dir(module):
            if attr_name == "plugin" or attr_name.endswith("_plugin"):
                attr = getattr(module, attr_name)
                if isinstance(attr, SourcePlugin):
                    yield attr


def create_registry() -> PluginRegistry:
    """Create a registry with all discovered plugins.

    Plugin order matters - more specific adapters should come first
    so they get priority in URL matching.
    """
    registry = PluginRegistry()

    # Discover and register plugins in a sensible order
    # (YouTube before RSS, etc.)
    priority_order = ["youtube", "bandcamp", "qobuz", "rss"]

    plugins_by_type: dict[str, list[SourcePlugin]] = {}
    for plugin in discover_plugins():
        source_type = plugin.source_type
        # Group by base type (e.g., "bandcamp" and "bandcamp_fan")
        base_type = source_type.split("_")[0]
        if base_type not in plugins_by_type:
            plugins_by_type[base_type] = []
        plugins_by_type[base_type].append(plugin)

    # Register in priority order
    for base_type in priority_order:
        for plugin in plugins_by_type.pop(base_type, []):
            registry.register(plugin)

    # Register any remaining plugins
    for plugins in plugins_by_type.values():
        for plugin in plugins:
            registry.register(plugin)

    return registry


# Singleton registry
_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    """Get or create the default plugin registry."""
    global _registry
    if _registry is None:
        _registry = create_registry()
    return _registry
