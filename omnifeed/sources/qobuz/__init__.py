"""Qobuz artist/label source plugin.

Supports:
- Artist pages: https://www.qobuz.com/us-en/interpreter/artist-name/123456
- Label pages: https://www.qobuz.com/label/label-name/123456

Uses Qobuz public API. Default app_id may work, or set QOBUZ_APP_ID.
"""

from omnifeed.sources.qobuz.adapter import QobuzAdapter, QobuzLabelAdapter
from omnifeed.sources.qobuz.search import QobuzSearchProvider
from omnifeed.sources.base import SourcePlugin

# Plugin instances for auto-discovery
plugin = SourcePlugin(
    adapter=QobuzAdapter(),
    search=QobuzSearchProvider(),
)

# Label adapter is a separate plugin
label_plugin = SourcePlugin(
    adapter=QobuzLabelAdapter(),
    search=None,  # Could add label search if needed
)

__all__ = ["QobuzAdapter", "QobuzLabelAdapter", "QobuzSearchProvider", "plugin", "label_plugin"]
