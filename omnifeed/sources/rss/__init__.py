"""RSS/Atom feed source plugin.

Supports:
- RSS 2.0 feeds
- Atom feeds
- Any URL with an RSS/Atom content type

Search powered by Feedly's discovery API.
"""

from omnifeed.sources.rss.adapter import RSSAdapter
from omnifeed.sources.rss.discovery import FeedlySearchProvider
from omnifeed.sources.base import SourcePlugin

# Plugin instance for auto-discovery
plugin = SourcePlugin(
    adapter=RSSAdapter(),
    search=FeedlySearchProvider(),
)

__all__ = ["RSSAdapter", "FeedlySearchProvider", "plugin"]
