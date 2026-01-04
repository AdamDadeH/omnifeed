"""TMDB source plugin for movies and TV shows."""

from omnifeed.sources.tmdb.adapter import TMDBPersonAdapter, TMDBDiscoverAdapter
from omnifeed.sources.tmdb.search import TMDBSearchProvider
from omnifeed.sources.base import SourcePlugin

# Create plugin instances
plugin = SourcePlugin(
    adapter=TMDBPersonAdapter(),
    search=TMDBSearchProvider(),
)

tmdb_genre_plugin = SourcePlugin(
    adapter=TMDBDiscoverAdapter(),
    search=None,
)

__all__ = [
    "TMDBPersonAdapter",
    "TMDBDiscoverAdapter",
    "TMDBSearchProvider",
    "plugin",
    "tmdb_genre_plugin",
]
