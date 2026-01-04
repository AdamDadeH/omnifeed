"""TMDB adapter for following actors, directors, and discovering movies/TV."""

import re
from datetime import datetime
from urllib.parse import urlparse

import httpx

from omnifeed.sources.base import SourceAdapter, SourceInfo, RawItem


TMDB_API_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"


def get_tmdb_api_key() -> str | None:
    """Get TMDB API key from config file.

    Set in ~/.omnifeed/config.json:
        {"extra": {"tmdb_api_key": "your_key"}}
    """
    try:
        from omnifeed.config import Config
        config = Config.load()
        return config.extra.get("tmdb_api_key")
    except Exception:
        return None


class TMDBPersonAdapter(SourceAdapter):
    """Adapter for TMDB person (actor/director) filmographies.

    Follows new movies/TV shows featuring a person.
    """

    def __init__(self):
        self._api_key = None

    @property
    def api_key(self) -> str | None:
        if self._api_key is None:
            self._api_key = get_tmdb_api_key()
        return self._api_key

    @property
    def source_type(self) -> str:
        return "tmdb_person"

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc in ("www.themoviedb.org", "themoviedb.org"):
            if "/person/" in parsed.path:
                return True
        return False

    def _extract_person_id(self, url: str) -> str:
        """Extract person ID from TMDB URL."""
        match = re.search(r"/person/(\d+)", url)
        if match:
            return match.group(1)
        raise ValueError(f"Could not extract person ID from URL: {url}")

    def _api_request(self, endpoint: str, params: dict | None = None) -> dict:
        """Make API request to TMDB."""
        if not self.api_key:
            raise ValueError("TMDB API key required. Set TMDB_API_KEY env var.")

        request_params = {"api_key": self.api_key, **(params or {})}
        response = httpx.get(
            f"{TMDB_API_BASE}{endpoint}",
            params=request_params,
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()

    def resolve(self, url: str) -> SourceInfo:
        person_id = self._extract_person_id(url)
        data = self._api_request(f"/person/{person_id}")

        name = data.get("name", f"Person {person_id}")
        profile_path = data.get("profile_path")
        avatar_url = f"{TMDB_IMAGE_BASE}/w185{profile_path}" if profile_path else None

        # Determine primary role
        known_for = data.get("known_for_department", "Acting")

        return SourceInfo(
            source_type=self.source_type,
            uri=f"tmdb:person:{person_id}",
            display_name=name,
            avatar_url=avatar_url,
            metadata={
                "person_id": person_id,
                "biography": data.get("biography", "")[:500],
                "birthday": data.get("birthday"),
                "known_for": known_for,
                "tmdb_url": f"https://www.themoviedb.org/person/{person_id}",
            },
        )

    def poll(self, source: SourceInfo, since: datetime | None = None) -> list[RawItem]:
        person_id = source.metadata.get("person_id")
        if not person_id:
            uri = source.uri
            if uri.startswith("tmdb:person:"):
                person_id = uri.replace("tmdb:person:", "")
            elif "themoviedb.org" in uri:
                person_id = self._extract_person_id(uri)
            else:
                person_id = uri

        # Get combined credits (movies + TV)
        data = self._api_request(f"/person/{person_id}/combined_credits")

        items = []
        seen_ids = set()

        # Process both cast and crew
        all_credits = data.get("cast", []) + data.get("crew", [])

        for credit in all_credits:
            media_type = credit.get("media_type", "movie")
            media_id = credit.get("id")

            # Deduplicate
            credit_key = f"{media_type}:{media_id}"
            if credit_key in seen_ids:
                continue
            seen_ids.add(credit_key)

            # Parse release date
            if media_type == "movie":
                date_str = credit.get("release_date", "")
                title = credit.get("title", "Untitled")
            else:
                date_str = credit.get("first_air_date", "")
                title = credit.get("name", "Untitled")

            if date_str:
                try:
                    published_at = datetime.fromisoformat(date_str)
                except ValueError:
                    published_at = datetime.now()
            else:
                published_at = datetime.now()

            if since and published_at <= since:
                continue

            poster_path = credit.get("poster_path")
            thumbnail = f"{TMDB_IMAGE_BASE}/w342{poster_path}" if poster_path else None

            # Role info
            character = credit.get("character", "")
            job = credit.get("job", "")
            role = character or job or "Unknown role"

            # Build content text
            overview = credit.get("overview", "")
            content_parts = [title]
            if role:
                content_parts.append(f"{source.display_name} as {role}" if character else f"{source.display_name} ({role})")
            if overview:
                content_parts.append(overview[:300])

            raw_item = RawItem(
                external_id=f"tmdb:{media_type}:{media_id}",
                url=f"https://www.themoviedb.org/{media_type}/{media_id}",
                title=title,
                published_at=published_at,
                raw_metadata={
                    "author": source.display_name,
                    "content_text": " | ".join(content_parts),
                    "description": overview[:500] if overview else "",
                    "thumbnail": thumbnail,
                    "media_type": media_type,
                    "media_id": media_id,
                    "role": role,
                    "vote_average": credit.get("vote_average"),
                    "genre_ids": credit.get("genre_ids", []),
                    "tmdb_url": f"https://www.themoviedb.org/{media_type}/{media_id}",
                },
            )
            items.append(raw_item)

        # Sort by date, newest first
        items.sort(key=lambda x: x.published_at, reverse=True)
        return items[:50]


class TMDBDiscoverAdapter(SourceAdapter):
    """Adapter for TMDB discover feeds by genre.

    Follows new releases in a genre.
    """

    def __init__(self):
        self._api_key = None

    @property
    def api_key(self) -> str | None:
        if self._api_key is None:
            self._api_key = get_tmdb_api_key()
        return self._api_key

    @property
    def source_type(self) -> str:
        return "tmdb_genre"

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc in ("www.themoviedb.org", "themoviedb.org"):
            if "/genre/" in parsed.path:
                return True
        return False

    def _extract_genre_info(self, url: str) -> tuple[str, str]:
        """Extract media type and genre ID from URL."""
        # Format: /genre/28-action/movie or /genre/28/movie
        match = re.search(r"/genre/(\d+)(?:-[^/]+)?/(movie|tv)", url)
        if match:
            return match.group(2), match.group(1)
        raise ValueError(f"Could not extract genre from URL: {url}")

    def _api_request(self, endpoint: str, params: dict | None = None) -> dict:
        if not self.api_key:
            raise ValueError("TMDB API key required. Set TMDB_API_KEY env var.")

        request_params = {"api_key": self.api_key, **(params or {})}
        response = httpx.get(
            f"{TMDB_API_BASE}{endpoint}",
            params=request_params,
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()

    def resolve(self, url: str) -> SourceInfo:
        media_type, genre_id = self._extract_genre_info(url)

        # Get genre name
        genres_data = self._api_request(f"/genre/{media_type}/list")
        genre_name = "Unknown"
        for g in genres_data.get("genres", []):
            if str(g.get("id")) == genre_id:
                genre_name = g.get("name", "Unknown")
                break

        type_label = "Movies" if media_type == "movie" else "TV Shows"

        return SourceInfo(
            source_type=self.source_type,
            uri=f"tmdb:genre:{media_type}:{genre_id}",
            display_name=f"{genre_name} {type_label}",
            avatar_url=None,
            metadata={
                "genre_id": genre_id,
                "genre_name": genre_name,
                "media_type": media_type,
                "tmdb_url": f"https://www.themoviedb.org/genre/{genre_id}/{media_type}",
            },
        )

    def poll(self, source: SourceInfo, since: datetime | None = None) -> list[RawItem]:
        genre_id = source.metadata.get("genre_id")
        media_type = source.metadata.get("media_type", "movie")

        if not genre_id:
            uri = source.uri
            if uri.startswith("tmdb:genre:"):
                parts = uri.split(":")
                if len(parts) >= 4:
                    media_type = parts[2]
                    genre_id = parts[3]

        # Discover new releases
        params = {
            "with_genres": genre_id,
            "sort_by": "primary_release_date.desc" if media_type == "movie" else "first_air_date.desc",
        }

        data = self._api_request(f"/discover/{media_type}", params)

        items = []
        for result in data.get("results", []):
            media_id = result.get("id")

            if media_type == "movie":
                date_str = result.get("release_date", "")
                title = result.get("title", "Untitled")
            else:
                date_str = result.get("first_air_date", "")
                title = result.get("name", "Untitled")

            if date_str:
                try:
                    published_at = datetime.fromisoformat(date_str)
                except ValueError:
                    published_at = datetime.now()
            else:
                published_at = datetime.now()

            if since and published_at <= since:
                continue

            poster_path = result.get("poster_path")
            thumbnail = f"{TMDB_IMAGE_BASE}/w342{poster_path}" if poster_path else None

            overview = result.get("overview", "")

            raw_item = RawItem(
                external_id=f"tmdb:{media_type}:{media_id}",
                url=f"https://www.themoviedb.org/{media_type}/{media_id}",
                title=title,
                published_at=published_at,
                raw_metadata={
                    "content_text": f"{title} | {overview[:300]}" if overview else title,
                    "description": overview[:500] if overview else "",
                    "thumbnail": thumbnail,
                    "media_type": media_type,
                    "media_id": media_id,
                    "vote_average": result.get("vote_average"),
                    "genre_ids": result.get("genre_ids", []),
                },
            )
            items.append(raw_item)

        return items
