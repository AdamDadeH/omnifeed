"""Adapters module - source-specific content fetchers."""

from omnifeed.adapters.base import SourceAdapter
from omnifeed.adapters.registry import AdapterRegistry, create_default_registry
from omnifeed.adapters.rss import RSSAdapter

__all__ = ["SourceAdapter", "AdapterRegistry", "RSSAdapter", "create_default_registry"]
