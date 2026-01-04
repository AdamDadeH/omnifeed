"""Discogs source plugin for artist and label releases."""

from omnifeed.sources.discogs.adapter import DiscogsArtistAdapter, DiscogsLabelAdapter
from omnifeed.sources.discogs.search import DiscogsSearchProvider
from omnifeed.sources.base import SourcePlugin

# Create plugin instances - use unique names for auto-discovery
plugin = SourcePlugin(
    adapter=DiscogsArtistAdapter(),
    search=DiscogsSearchProvider(),
)

discogs_label_plugin = SourcePlugin(
    adapter=DiscogsLabelAdapter(),
    search=None,  # Shared search provider
)

__all__ = [
    "DiscogsArtistAdapter",
    "DiscogsLabelAdapter",
    "DiscogsSearchProvider",
    "plugin",
    "discogs_label_plugin",
]
