"""Podcast Index search provider for discovering podcasts."""

import httpx

from omnifeed.sources.base import SearchProvider, SourceSuggestion


PODCASTINDEX_API_BASE = "https://api.podcastindex.org/api/1.0"


def get_podcastindex_api_key() -> str | None:
    """Get Podcast Index API key from config file."""
    try:
        from omnifeed.config import Config
        config = Config.load()
        return config.extra.get("podcastindex_api_key")
    except Exception:
        return None


class PodcastIndexSearchProvider(SearchProvider):
    """Search for podcasts on Podcast Index."""

    def __init__(self):
        self._api_key = None

    @property
    def api_key(self) -> str | None:
        if self._api_key is None:
            self._api_key = get_podcastindex_api_key()
        return self._api_key

    @property
    def provider_id(self) -> str:
        return "podcastindex"

    @property
    def source_types(self) -> list[str]:
        return ["podcast"]

    def _auth_headers(self) -> dict:
        if not self.api_key:
            return {}

        return {
            "User-Agent": "OmniFeed/1.0",
            "X-Auth-Key": self.api_key,
        }

    async def search(self, query: str, limit: int = 10) -> list[SourceSuggestion]:
        """Search Podcast Index for podcasts."""
        if not self.api_key:
            return []

        suggestions = []

        try:
            response = httpx.get(
                f"{PODCASTINDEX_API_BASE}/search/byterm",
                params={
                    "q": query,
                    "max": min(limit, 20),
                },
                headers=self._auth_headers(),
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            for feed in data.get("feeds", []):
                podcast_id = feed.get("id")
                title = feed.get("title", "Unknown Podcast")
                author = feed.get("author", "")
                artwork = feed.get("artwork") or feed.get("image")

                description = author
                episode_count = feed.get("episodeCount")
                if episode_count:
                    description += f" • {episode_count} episodes"

                suggestions.append(SourceSuggestion(
                    url=f"https://podcastindex.org/podcast/{podcast_id}",
                    name=title,
                    source_type="podcast",
                    description=description,
                    thumbnail_url=artwork,
                    provider="podcastindex",
                    metadata={
                        "podcast_id": podcast_id,
                        "feed_url": feed.get("url"),
                        "author": author,
                    },
                ))

        except httpx.HTTPError:
            pass

        return suggestions[:limit]
