"""YouTube source plugins.

Supports:
- YouTube channel URLs (youtube.com/channel/..., youtube.com/@..., etc.)
- YouTube playlist URLs (youtube.com/playlist?list=...)
- Fetches videos via YouTube Data API v3
- Searches for channels

Requires:
- YOUTUBE_API_KEY environment variable (or in config)
"""

from omnifeed.sources.youtube.adapter import YouTubeAdapter, YouTubePlaylistAdapter
from omnifeed.sources.youtube.search import YouTubeSearchProvider
from omnifeed.sources.base import SourcePlugin

# Plugin instances for auto-discovery
# Channel plugin (handles @handles, /channel/ URLs)
plugin = SourcePlugin(
    adapter=YouTubeAdapter(),
    search=YouTubeSearchProvider(),
)

# Playlist plugin (handles /playlist?list= URLs)
playlist_plugin = SourcePlugin(
    adapter=YouTubePlaylistAdapter(),
    search=None,  # Could add playlist search later
)

__all__ = ["YouTubeAdapter", "YouTubePlaylistAdapter", "YouTubeSearchProvider", "plugin", "playlist_plugin"]
