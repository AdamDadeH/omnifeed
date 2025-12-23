"""Template source plugin - copy this directory to create a new source.

To create a new source plugin:
1. Copy this entire _template/ directory to a new name, e.g., sources/spotify/
2. Rename MySourceAdapter and MySearchProvider in adapter.py and search.py
3. Implement the required methods
4. Update this __init__.py to export your plugin

The plugin will be automatically discovered and registered.
"""

# Uncomment and modify after copying:
#
# from omnifeed.sources.myname.adapter import MySourceAdapter
# from omnifeed.sources.myname.search import MySearchProvider
# from omnifeed.sources.base import SourcePlugin
#
# plugin = SourcePlugin(
#     adapter=MySourceAdapter(),
#     search=MySearchProvider(),  # Optional - set to None if no search
# )
#
# __all__ = ["MySourceAdapter", "MySearchProvider", "plugin"]
