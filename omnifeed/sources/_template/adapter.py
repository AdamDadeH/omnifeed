"""Template adapter - implement this for your source.

An adapter is responsible for:
1. Detecting if it can handle a URL (can_handle)
2. Resolving a URL to source metadata (resolve)
3. Fetching new items from the source (poll)
"""

from datetime import datetime
from urllib.parse import urlparse

import httpx

from omnifeed.sources.base import SourceAdapter, SourceInfo, RawItem


class MySourceAdapter(SourceAdapter):
    """Adapter for [Your Source Name].

    Describe what this adapter supports:
    - What URLs it handles
    - Any API keys or credentials needed
    - Rate limits or other considerations
    """

    @property
    def source_type(self) -> str:
        """Unique identifier for this source type.

        This is used in the database and UI to identify the source type.
        Use lowercase with underscores, e.g., "my_source", "spotify_artist".
        """
        return "my_source"

    def can_handle(self, url: str) -> bool:
        """Return True if this adapter can handle the given URL.

        This is called when a user tries to add a new source.
        Be specific to avoid matching URLs meant for other adapters.

        Example:
            parsed = urlparse(url)
            return parsed.netloc == "example.com" and "/creator/" in parsed.path
        """
        parsed = urlparse(url)
        # TODO: Implement URL detection
        return False

    def resolve(self, url: str) -> SourceInfo:
        """Resolve a URL to source metadata.

        Fetch information about the source (name, avatar, etc.)
        to show the user before they confirm adding it.

        Args:
            url: The URL provided by the user.

        Returns:
            SourceInfo with:
            - source_type: must match self.source_type
            - uri: unique identifier for this source (used to detect duplicates)
            - display_name: human-readable name
            - avatar_url: optional image URL
            - metadata: dict with any additional info needed for polling

        Raises:
            ValueError: If the URL cannot be resolved (invalid, not found, etc.)
        """
        # TODO: Fetch source metadata
        # Example:
        # response = httpx.get(url, timeout=30.0)
        # response.raise_for_status()
        # data = response.json()

        raise NotImplementedError("Implement resolve()")

        # return SourceInfo(
        #     source_type=self.source_type,
        #     uri=f"my_source:{unique_id}",
        #     display_name="Source Name",
        #     avatar_url="https://example.com/avatar.jpg",
        #     metadata={
        #         "creator_id": "...",
        #         "description": "...",
        #         # Store anything needed for polling
        #     },
        # )

    def poll(self, source: SourceInfo, since: datetime | None = None) -> list[RawItem]:
        """Fetch new items from the source.

        This is called periodically to check for new content.

        Args:
            source: The source to poll (from resolve()).
                   Access source.metadata for stored info like IDs.
            since: If provided, only return items published after this time.
                   Can be ignored if the source doesn't support date filtering.

        Returns:
            List of RawItem objects. Each item should have:
            - external_id: unique ID within this source (for deduplication)
            - url: link to the content
            - title: content title
            - published_at: publication date
            - raw_metadata: dict with:
                - author: creator name
                - content_text: text for embeddings
                - content_html: HTML for display (optional)
                - thumbnail: image URL (optional)
                - enclosures: list of media attachments (optional)
        """
        # TODO: Fetch items
        # Example:
        # creator_id = source.metadata.get("creator_id")
        # response = httpx.get(f"https://api.example.com/creators/{creator_id}/items")
        # items_data = response.json()

        raise NotImplementedError("Implement poll()")

        # items = []
        # for item_data in items_data:
        #     published_at = datetime.fromisoformat(item_data["created_at"])
        #
        #     # Skip old items if since is provided
        #     if since and published_at <= since:
        #         continue
        #
        #     items.append(RawItem(
        #         external_id=item_data["id"],
        #         url=item_data["url"],
        #         title=item_data["title"],
        #         published_at=published_at,
        #         raw_metadata={
        #             "author": item_data.get("creator_name", source.display_name),
        #             "content_text": item_data.get("description", ""),
        #             "thumbnail": item_data.get("thumbnail_url"),
        #             "enclosures": [],  # For audio/video attachments
        #         },
        #     ))
        #
        # return items
