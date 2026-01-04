"""Discogs search provider for discovering artists and labels."""

import httpx

from omnifeed.sources.base import SearchProvider, SourceSuggestion


DISCOGS_API_BASE = "https://api.discogs.com"


def get_discogs_token() -> str | None:
    """Get Discogs API token from config file."""
    try:
        from omnifeed.config import Config
        config = Config.load()
        return config.extra.get("discogs_token")
    except Exception:
        return None


class DiscogsSearchProvider(SearchProvider):
    """Search for artists and labels on Discogs."""

    def __init__(self):
        self._token = None

    @property
    def token(self) -> str | None:
        if self._token is None:
            self._token = get_discogs_token()
        return self._token

    @property
    def provider_id(self) -> str:
        return "discogs"

    @property
    def source_types(self) -> list[str]:
        return ["discogs_artist", "discogs_label"]

    def _headers(self) -> dict:
        headers = {
            "User-Agent": "OmniFeed/1.0 +https://github.com/omnifeed",
        }
        if self.token:
            headers["Authorization"] = f"Discogs token={self.token}"
        return headers

    async def search(self, query: str, limit: int = 10) -> list[SourceSuggestion]:
        """Search Discogs for artists and labels."""
        suggestions = []

        try:
            # Search for artists
            response = httpx.get(
                f"{DISCOGS_API_BASE}/database/search",
                params={
                    "q": query,
                    "type": "artist",
                    "per_page": min(limit, 10),
                },
                headers=self._headers(),
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            for result in data.get("results", []):
                artist_id = result.get("id")
                suggestions.append(SourceSuggestion(
                    url=f"https://www.discogs.com/artist/{artist_id}",
                    name=result.get("title", "Unknown Artist"),
                    source_type="discogs_artist",
                    description=f"Artist on Discogs",
                    thumbnail_url=result.get("thumb"),
                    provider="discogs",
                    metadata={"artist_id": artist_id},
                ))

            # Search for labels
            response = httpx.get(
                f"{DISCOGS_API_BASE}/database/search",
                params={
                    "q": query,
                    "type": "label",
                    "per_page": min(limit // 2, 5),
                },
                headers=self._headers(),
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            for result in data.get("results", []):
                label_id = result.get("id")
                suggestions.append(SourceSuggestion(
                    url=f"https://www.discogs.com/label/{label_id}",
                    name=result.get("title", "Unknown Label"),
                    source_type="discogs_label",
                    description="Label on Discogs",
                    thumbnail_url=result.get("thumb"),
                    provider="discogs",
                    metadata={"label_id": label_id},
                ))

        except httpx.HTTPError as e:
            # Return empty list on API error
            pass

        return suggestions[:limit]
