"""OpenLibrary source plugin for authors and subjects."""

from omnifeed.sources.openlibrary.adapter import (
    OpenLibraryAuthorAdapter,
    OpenLibrarySubjectAdapter,
)
from omnifeed.sources.openlibrary.search import OpenLibrarySearchProvider
from omnifeed.sources.base import SourcePlugin

# Create plugin instances
plugin = SourcePlugin(
    adapter=OpenLibraryAuthorAdapter(),
    search=OpenLibrarySearchProvider(),
)

openlibrary_subject_plugin = SourcePlugin(
    adapter=OpenLibrarySubjectAdapter(),
    search=None,
)

__all__ = [
    "OpenLibraryAuthorAdapter",
    "OpenLibrarySubjectAdapter",
    "OpenLibrarySearchProvider",
    "plugin",
    "openlibrary_subject_plugin",
]
