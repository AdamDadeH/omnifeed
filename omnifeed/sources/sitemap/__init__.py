"""Sitemap source adapter for harvesting links from website sitemaps."""

from omnifeed.sources.base import SourcePlugin
from omnifeed.sources.sitemap.adapter import SitemapAdapter

plugin = SourcePlugin(
    adapter=SitemapAdapter(),
    search=None,  # No search provider for sitemaps
)

__all__ = ["SitemapAdapter", "plugin"]
