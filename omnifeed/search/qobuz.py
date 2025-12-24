"""Qobuz artist/label search provider."""

from omnifeed.sources.qobuz.adapter import get_qobuz_credentials, QOBUZ_API_BASE
from omnifeed.search.base import SearchProvider, SourceSuggestion

import httpx


class QobuzSearchProvider(SearchProvider):
    """Search for Qobuz artists."""

    def __init__(self, app_id: str | None = None):
        self._app_id = app_id
        self._credentials = None

    @property
    def credentials(self) -> dict:
        if self._credentials is None:
            self._credentials = get_qobuz_credentials() or {}
            if self._app_id:
                self._credentials["app_id"] = self._app_id
        return self._credentials

    @property
    def provider_id(self) -> str:
        return "qobuz"

    @property
    def source_types(self) -> list[str]:
        return ["qobuz_artist"]

    async def search(self, query: str, limit: int = 10) -> list[SourceSuggestion]:
        if not self.credentials.get("app_id"):
            return []

        params = {
            "app_id": self.credentials["app_id"],
            "query": query,
            "limit": limit,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{QOBUZ_API_BASE}/artist/search",
                params=params,
                timeout=30.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                },
            )

            if response.status_code != 200:
                return []

            data = response.json()
            suggestions = []

            artists = data.get("artists", {}).get("items", [])

            for artist in artists:
                artist_id = artist.get("id")
                name = artist.get("name", "")

                # Get image
                image = artist.get("image", {})
                thumbnail = (
                    image.get("large")
                    or image.get("medium")
                    or image.get("small")
                )

                # Get album count for description
                albums_count = artist.get("albums_count", 0)
                description = f"{albums_count} albums" if albums_count else ""

                suggestions.append(SourceSuggestion(
                    url=f"https://www.qobuz.com/artist/{artist_id}",
                    name=name,
                    source_type="qobuz_artist",
                    description=description,
                    thumbnail_url=thumbnail,
                    provider=self.provider_id,
                    metadata={
                        "artist_id": str(artist_id),
                    },
                ))

            return suggestions
