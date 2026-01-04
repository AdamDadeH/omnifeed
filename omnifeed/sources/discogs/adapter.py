"""Discogs adapter for artist/label release feeds."""

import re
from datetime import datetime
from urllib.parse import urlparse

import httpx

from omnifeed.sources.base import SourceAdapter, SourceInfo, RawItem


DISCOGS_API_BASE = "https://api.discogs.com"


def get_discogs_token() -> str | None:
    """Get Discogs API token from config file.

    Set in ~/.omnifeed/config.json:
        {"extra": {"discogs_token": "your_token"}}
    """
    try:
        from omnifeed.config import Config
        config = Config.load()
        return config.extra.get("discogs_token")
    except Exception:
        return None


class DiscogsArtistAdapter(SourceAdapter):
    """Adapter for Discogs artist discographies."""

    def __init__(self):
        self._token = None

    @property
    def token(self) -> str | None:
        if self._token is None:
            self._token = get_discogs_token()
        return self._token

    @property
    def source_type(self) -> str:
        return "discogs_artist"

    def _headers(self) -> dict:
        headers = {
            "User-Agent": "OmniFeed/1.0 +https://github.com/omnifeed",
        }
        if self.token:
            headers["Authorization"] = f"Discogs token={self.token}"
        return headers

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc in ("www.discogs.com", "discogs.com"):
            if "/artist/" in parsed.path:
                return True
        return False

    def _extract_artist_id(self, url: str) -> str:
        """Extract artist ID from Discogs URL."""
        # Format: /artist/12345-Artist-Name
        match = re.search(r"/artist/(\d+)", url)
        if match:
            return match.group(1)
        raise ValueError(f"Could not extract artist ID from URL: {url}")

    def _api_request(self, endpoint: str, params: dict | None = None) -> dict:
        """Make authenticated API request."""
        response = httpx.get(
            f"{DISCOGS_API_BASE}/{endpoint}",
            params=params,
            headers=self._headers(),
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()

    def resolve(self, url: str) -> SourceInfo:
        artist_id = self._extract_artist_id(url)
        data = self._api_request(f"artists/{artist_id}")

        name = data.get("name", f"Artist {artist_id}")
        images = data.get("images", [])
        avatar_url = images[0]["uri"] if images else None

        return SourceInfo(
            source_type=self.source_type,
            uri=f"discogs:artist:{artist_id}",
            display_name=name,
            avatar_url=avatar_url,
            metadata={
                "artist_id": artist_id,
                "profile": data.get("profile", "")[:500],
                "discogs_url": data.get("uri"),
                "members": [m.get("name") for m in data.get("members", [])],
            },
        )

    def poll(self, source: SourceInfo, since: datetime | None = None) -> list[RawItem]:
        artist_id = source.metadata.get("artist_id")
        if not artist_id:
            uri = source.uri
            if uri.startswith("discogs:artist:"):
                artist_id = uri.replace("discogs:artist:", "")
            elif "discogs.com" in uri:
                artist_id = self._extract_artist_id(uri)
            else:
                artist_id = uri

        # Get artist releases
        data = self._api_request(f"artists/{artist_id}/releases", {
            "sort": "year",
            "sort_order": "desc",
            "per_page": 50,
        })

        items = []
        for release in data.get("releases", []):
            year = release.get("year")
            if year:
                # Approximate date from year
                try:
                    published_at = datetime(int(year), 1, 1)
                except (ValueError, TypeError):
                    published_at = datetime.now()
            else:
                published_at = datetime.now()

            if since and published_at <= since:
                continue

            release_id = release.get("id", "")
            release_type = release.get("type", "release")
            role = release.get("role", "Main")

            # Build content text
            content_parts = [
                release.get("title", "Untitled"),
                f"by {release.get('artist', source.display_name)}",
            ]
            if release.get("format"):
                content_parts.append(f"Format: {release['format']}")
            if release.get("label"):
                content_parts.append(f"Label: {release['label']}")

            raw_item = RawItem(
                external_id=f"discogs:{release_type}:{release_id}",
                url=f"https://www.discogs.com/release/{release_id}" if release_type == "release" else f"https://www.discogs.com/master/{release_id}",
                title=release.get("title", "Untitled"),
                published_at=published_at,
                raw_metadata={
                    "author": release.get("artist", source.display_name),
                    "content_text": " | ".join(content_parts),
                    "thumbnail": release.get("thumb"),
                    "release_id": release_id,
                    "release_type": release_type,
                    "format": release.get("format"),
                    "label": release.get("label"),
                    "role": role,
                    "year": year,
                    "discogs_url": f"https://www.discogs.com/release/{release_id}",
                },
            )
            items.append(raw_item)

        return items


class DiscogsLabelAdapter(SourceAdapter):
    """Adapter for Discogs label releases."""

    def __init__(self):
        self._token = None

    @property
    def token(self) -> str | None:
        if self._token is None:
            self._token = get_discogs_token()
        return self._token

    @property
    def source_type(self) -> str:
        return "discogs_label"

    def _headers(self) -> dict:
        headers = {
            "User-Agent": "OmniFeed/1.0 +https://github.com/omnifeed",
        }
        if self.token:
            headers["Authorization"] = f"Discogs token={self.token}"
        return headers

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc in ("www.discogs.com", "discogs.com"):
            if "/label/" in parsed.path:
                return True
        return False

    def _extract_label_id(self, url: str) -> str:
        match = re.search(r"/label/(\d+)", url)
        if match:
            return match.group(1)
        raise ValueError(f"Could not extract label ID from URL: {url}")

    def _api_request(self, endpoint: str, params: dict | None = None) -> dict:
        response = httpx.get(
            f"{DISCOGS_API_BASE}/{endpoint}",
            params=params,
            headers=self._headers(),
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()

    def resolve(self, url: str) -> SourceInfo:
        label_id = self._extract_label_id(url)
        data = self._api_request(f"labels/{label_id}")

        name = data.get("name", f"Label {label_id}")
        images = data.get("images", [])
        avatar_url = images[0]["uri"] if images else None

        return SourceInfo(
            source_type=self.source_type,
            uri=f"discogs:label:{label_id}",
            display_name=name,
            avatar_url=avatar_url,
            metadata={
                "label_id": label_id,
                "profile": data.get("profile", "")[:500],
                "discogs_url": data.get("uri"),
            },
        )

    def poll(self, source: SourceInfo, since: datetime | None = None) -> list[RawItem]:
        label_id = source.metadata.get("label_id")
        if not label_id:
            uri = source.uri
            if uri.startswith("discogs:label:"):
                label_id = uri.replace("discogs:label:", "")
            elif "discogs.com" in uri:
                label_id = self._extract_label_id(uri)
            else:
                label_id = uri

        data = self._api_request(f"labels/{label_id}/releases", {
            "sort": "year",
            "sort_order": "desc",
            "per_page": 50,
        })

        items = []
        for release in data.get("releases", []):
            year = release.get("year")
            if year:
                try:
                    published_at = datetime(int(year), 1, 1)
                except (ValueError, TypeError):
                    published_at = datetime.now()
            else:
                published_at = datetime.now()

            if since and published_at <= since:
                continue

            release_id = release.get("id", "")

            raw_item = RawItem(
                external_id=f"discogs:release:{release_id}",
                url=f"https://www.discogs.com/release/{release_id}",
                title=release.get("title", "Untitled"),
                published_at=published_at,
                raw_metadata={
                    "author": release.get("artist", "Various"),
                    "thumbnail": release.get("thumb"),
                    "release_id": release_id,
                    "format": release.get("format"),
                    "catno": release.get("catno"),
                    "year": year,
                },
            )
            items.append(raw_item)

        return items
