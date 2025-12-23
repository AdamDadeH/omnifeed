"""Source plugins for OmniFeed.

Each source type (YouTube, Bandcamp, RSS, etc.) is a plugin in its own directory.

Quick start for adding a new source:
1. Copy omnifeed/sources/_template/ to omnifeed/sources/yourname/
2. Implement the adapter in adapter.py
3. Optionally implement search in search.py
4. Update __init__.py to export your plugin

See omnifeed/sources/base.py for the SourceAdapter and SearchProvider protocols.
"""

# Base protocols
from omnifeed.sources.base import (
    SourceAdapter,
    SearchProvider,
    SourcePlugin,
    SourceInfo,
    RawItem,
    SourceSuggestion,
)

# Registry
from omnifeed.sources.registry import (
    PluginRegistry,
    get_registry,
    create_registry,
    discover_plugins,
)

__all__ = [
    # Protocols
    "SourceAdapter",
    "SearchProvider",
    "SourcePlugin",
    # Data models
    "SourceInfo",
    "RawItem",
    "SourceSuggestion",
    # Registry
    "PluginRegistry",
    "get_registry",
    "create_registry",
    "discover_plugins",
]
