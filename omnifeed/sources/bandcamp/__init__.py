"""Bandcamp artist/label source plugin.

Supports:
- Artist pages: https://artistname.bandcamp.com
- Label pages: https://labelname.bandcamp.com
- Fan collections: https://bandcamp.com/username

No API key required - uses web scraping.
"""

from omnifeed.sources.bandcamp.adapter import BandcampAdapter, BandcampFanAdapter
from omnifeed.sources.bandcamp.search import BandcampSearchProvider
from omnifeed.sources.base import SourcePlugin

# Plugin instances for auto-discovery
plugin = SourcePlugin(
    adapter=BandcampAdapter(),
    search=BandcampSearchProvider(),
)

# Fan adapter is a separate plugin (different source_type)
fan_plugin = SourcePlugin(
    adapter=BandcampFanAdapter(),
    search=None,  # No search for fan collections
)

__all__ = ["BandcampAdapter", "BandcampFanAdapter", "BandcampSearchProvider", "plugin", "fan_plugin"]
