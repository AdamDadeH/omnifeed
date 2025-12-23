"""Adapters module - now redirects to omnifeed.sources.

This module is kept for backwards compatibility.
New code should import from omnifeed.sources instead.
"""

# Re-export from new locations for backwards compatibility
from omnifeed.sources.base import SourceAdapter, SourceInfo, RawItem

# Import adapters from new plugin locations
from omnifeed.sources.youtube.adapter import YouTubeAdapter
from omnifeed.sources.bandcamp.adapter import BandcampAdapter, BandcampFanAdapter
from omnifeed.sources.qobuz.adapter import QobuzAdapter, QobuzLabelAdapter
from omnifeed.sources.rss.adapter import RSSAdapter


def create_default_registry():
    """Create the default adapter registry.

    DEPRECATED: Use omnifeed.sources.get_registry() instead.
    This function is kept for backwards compatibility.
    """
    from omnifeed.sources import get_registry
    return get_registry()


# For backwards compatibility, also provide the old AdapterRegistry class
class AdapterRegistry:
    """DEPRECATED: Use omnifeed.sources.PluginRegistry instead."""

    def __init__(self):
        from omnifeed.sources import get_registry
        self._registry = get_registry()

    def register(self, adapter):
        from omnifeed.sources.base import SourcePlugin
        self._registry.register(SourcePlugin(adapter=adapter))

    def find_adapter(self, url: str):
        return self._registry.find_adapter(url)

    def get_adapter_by_type(self, source_type: str):
        return self._registry.get_adapter_by_type(source_type)


__all__ = [
    "SourceAdapter",
    "SourceInfo",
    "RawItem",
    "AdapterRegistry",
    "create_default_registry",
    "YouTubeAdapter",
    "BandcampAdapter",
    "BandcampFanAdapter",
    "QobuzAdapter",
    "QobuzLabelAdapter",
    "RSSAdapter",
]
