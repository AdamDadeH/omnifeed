"""Template search provider - implement this to enable source discovery.

A search provider is OPTIONAL. If your source has a search API,
implement this to let users discover sources to add.

If your source doesn't support search, you can skip this file
and set search=None in your plugin definition.
"""

import httpx

from omnifeed.sources.base import SearchProvider, SourceSuggestion


class MySearchProvider(SearchProvider):
    """Search provider for [Your Source Name].

    Describe what this searches:
    - What entities it finds (creators, channels, feeds, etc.)
    - Any API keys needed
    - Rate limits
    """

    @property
    def provider_id(self) -> str:
        """Unique identifier for this search provider.

        Usually matches the source_type, but can be different.
        For example, "feedly" provides search for "rss" sources.
        """
        return "my_source"

    @property
    def source_types(self) -> list[str]:
        """Source types this provider can discover.

        Must match source_type values from adapters.
        Usually just one, but could be multiple.
        """
        return ["my_source"]

    async def search(self, query: str, limit: int = 10) -> list[SourceSuggestion]:
        """Search for sources matching the query.

        Args:
            query: Search terms (creator name, topic, etc.)
            limit: Maximum results to return.

        Returns:
            List of SourceSuggestion objects, each representing
            a source the user could add.

        Note: This is async! Use httpx.AsyncClient for HTTP requests.
        """
        # TODO: Implement search
        # Example:
        # async with httpx.AsyncClient() as client:
        #     response = await client.get(
        #         "https://api.example.com/search",
        #         params={"q": query, "limit": limit},
        #         timeout=30.0,
        #     )
        #     if response.status_code != 200:
        #         return []
        #
        #     data = response.json()
        #     suggestions = []
        #
        #     for result in data.get("results", []):
        #         suggestions.append(SourceSuggestion(
        #             url=result["url"],  # URL that can_handle() will accept
        #             name=result["name"],
        #             source_type="my_source",  # Must match adapter.source_type
        #             description=result.get("description", ""),
        #             thumbnail_url=result.get("avatar_url"),
        #             subscriber_count=result.get("followers"),  # Optional
        #             provider=self.provider_id,
        #             metadata={
        #                 # Any extra info useful for display
        #                 "creator_id": result["id"],
        #             },
        #         ))
        #
        #     return suggestions

        return []  # Remove this and implement above
