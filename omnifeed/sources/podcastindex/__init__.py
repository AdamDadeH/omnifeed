"""Podcast Index source plugin for podcasts."""

from omnifeed.sources.podcastindex.adapter import (
    PodcastIndexAdapter,
    PodcastIndexTrendingAdapter,
)
from omnifeed.sources.podcastindex.search import PodcastIndexSearchProvider
from omnifeed.sources.base import SourcePlugin

# Create plugin instances
plugin = SourcePlugin(
    adapter=PodcastIndexAdapter(),
    search=PodcastIndexSearchProvider(),
)

podcast_trending_plugin = SourcePlugin(
    adapter=PodcastIndexTrendingAdapter(),
    search=None,
)

__all__ = [
    "PodcastIndexAdapter",
    "PodcastIndexTrendingAdapter",
    "PodcastIndexSearchProvider",
    "plugin",
    "podcast_trending_plugin",
]
