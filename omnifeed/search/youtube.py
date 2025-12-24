"""YouTube channel search provider."""

import httpx

from omnifeed.sources.youtube.adapter import get_api_key, YOUTUBE_API_BASE
from omnifeed.search.base import SearchProvider, SourceSuggestion


class YouTubeSearchProvider(SearchProvider):
    """Search for YouTube channels."""

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key

    @property
    def api_key(self) -> str | None:
        if self._api_key is None:
            self._api_key = get_api_key()
        return self._api_key

    @property
    def provider_id(self) -> str:
        return "youtube"

    @property
    def source_types(self) -> list[str]:
        return ["youtube_channel"]

    async def search(self, query: str, limit: int = 10) -> list[SourceSuggestion]:
        if not self.api_key:
            return []

        params = {
            "key": self.api_key,
            "part": "snippet",
            "q": query,
            "type": "channel",
            "maxResults": min(limit, 50),
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{YOUTUBE_API_BASE}/search",
                params=params,
                timeout=30.0,
            )

            if response.status_code != 200:
                return []

            data = response.json()
            suggestions = []

            # Get channel IDs for subscriber count lookup
            channel_ids = [
                item["snippet"]["channelId"]
                for item in data.get("items", [])
            ]

            # Fetch subscriber counts
            subscriber_counts = await self._get_subscriber_counts(client, channel_ids)

            for item in data.get("items", []):
                snippet = item["snippet"]
                channel_id = snippet["channelId"]

                thumbnails = snippet.get("thumbnails", {})
                thumbnail = (
                    thumbnails.get("high", {}).get("url")
                    or thumbnails.get("medium", {}).get("url")
                    or thumbnails.get("default", {}).get("url")
                )

                suggestions.append(SourceSuggestion(
                    url=f"https://www.youtube.com/channel/{channel_id}",
                    name=snippet.get("title", ""),
                    source_type="youtube_channel",
                    description=snippet.get("description", ""),
                    thumbnail_url=thumbnail,
                    subscriber_count=subscriber_counts.get(channel_id),
                    provider=self.provider_id,
                    metadata={
                        "channel_id": channel_id,
                    },
                ))

            return suggestions

    async def _get_subscriber_counts(
        self,
        client: httpx.AsyncClient,
        channel_ids: list[str],
    ) -> dict[str, int]:
        """Fetch subscriber counts for channels."""
        if not channel_ids:
            return {}

        params = {
            "key": self.api_key,
            "part": "statistics",
            "id": ",".join(channel_ids),
        }

        response = await client.get(
            f"{YOUTUBE_API_BASE}/channels",
            params=params,
            timeout=30.0,
        )

        if response.status_code != 200:
            return {}

        data = response.json()
        counts = {}

        for item in data.get("items", []):
            channel_id = item["id"]
            stats = item.get("statistics", {})
            if stats.get("hiddenSubscriberCount"):
                counts[channel_id] = None
            else:
                counts[channel_id] = int(stats.get("subscriberCount", 0))

        return counts
