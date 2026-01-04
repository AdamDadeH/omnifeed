"""TMDB search provider for discovering people, movies, and TV shows."""

import httpx

from omnifeed.sources.base import SearchProvider, SourceSuggestion


TMDB_API_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"


def get_tmdb_api_key() -> str | None:
    """Get TMDB API key from config file."""
    try:
        from omnifeed.config import Config
        config = Config.load()
        return config.extra.get("tmdb_api_key")
    except Exception:
        return None


class TMDBSearchProvider(SearchProvider):
    """Search for people and content on TMDB."""

    def __init__(self):
        self._api_key = None

    @property
    def api_key(self) -> str | None:
        if self._api_key is None:
            self._api_key = get_tmdb_api_key()
        return self._api_key

    @property
    def provider_id(self) -> str:
        return "tmdb"

    @property
    def source_types(self) -> list[str]:
        return ["tmdb_person", "tmdb_genre"]

    async def search(self, query: str, limit: int = 10) -> list[SourceSuggestion]:
        """Search TMDB for people."""
        if not self.api_key:
            return []

        suggestions = []

        try:
            # Search for people (actors, directors)
            response = httpx.get(
                f"{TMDB_API_BASE}/search/person",
                params={
                    "api_key": self.api_key,
                    "query": query,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            for result in data.get("results", [])[:limit]:
                person_id = result.get("id")
                name = result.get("name", "Unknown")
                known_for = result.get("known_for_department", "Acting")

                profile_path = result.get("profile_path")
                thumbnail = f"{TMDB_IMAGE_BASE}/w185{profile_path}" if profile_path else None

                # Build description from known_for works
                known_for_titles = []
                for work in result.get("known_for", [])[:3]:
                    title = work.get("title") or work.get("name")
                    if title:
                        known_for_titles.append(title)

                description = known_for
                if known_for_titles:
                    description += f" • {', '.join(known_for_titles)}"

                suggestions.append(SourceSuggestion(
                    url=f"https://www.themoviedb.org/person/{person_id}",
                    name=name,
                    source_type="tmdb_person",
                    description=description,
                    thumbnail_url=thumbnail,
                    provider="tmdb",
                    metadata={"person_id": person_id, "known_for": known_for},
                ))

        except httpx.HTTPError:
            pass

        return suggestions[:limit]
