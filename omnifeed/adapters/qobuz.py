"""Qobuz adapter for artist catalogs and new releases."""

import hashlib
import os
import re
from datetime import datetime
from urllib.parse import urlparse, parse_qs

import httpx

from omnifeed.adapters.base import SourceAdapter
from omnifeed.models import SourceInfo, RawItem


# Qobuz API configuration
QOBUZ_API_BASE = "https://www.qobuz.com/api.json/0.2"

# Known app IDs (from web player) - these may need updating
QOBUZ_APP_ID = "950096963"


def get_qobuz_credentials() -> dict | None:
    """Get Qobuz credentials from environment or config."""
    app_id = os.environ.get("QOBUZ_APP_ID", QOBUZ_APP_ID)

    # Check for user token (for user-specific features)
    user_token = os.environ.get("QOBUZ_USER_TOKEN")

    if not user_token:
        try:
            from omnifeed.config import Config
            config = Config.load()
            user_token = config.extra.get("qobuz_user_token")
            app_id = config.extra.get("qobuz_app_id", app_id)
        except Exception:
            pass

    return {
        "app_id": app_id,
        "user_token": user_token,
    }


class QobuzAdapter(SourceAdapter):
    """Adapter for Qobuz artist catalogs.

    Tracks releases from specific artists on Qobuz.
    Uses the Qobuz API to fetch artist discography.

    Supports URLs like:
    - https://www.qobuz.com/us-en/interpreter/artist-name/123456
    - https://open.qobuz.com/artist/123456
    """

    def __init__(self, app_id: str | None = None):
        self._app_id = app_id
        self._credentials = None

    @property
    def credentials(self) -> dict:
        """Get API credentials (lazy load)."""
        if self._credentials is None:
            self._credentials = get_qobuz_credentials() or {}
            if self._app_id:
                self._credentials["app_id"] = self._app_id
        return self._credentials

    @property
    def source_type(self) -> str:
        return "qobuz_artist"

    def can_handle(self, url: str) -> bool:
        """Check if URL is a Qobuz artist page."""
        parsed = urlparse(url)

        if parsed.netloc in ("www.qobuz.com", "qobuz.com", "open.qobuz.com"):
            # Check for artist patterns
            if "/interpreter/" in parsed.path or "/artist/" in parsed.path:
                return True

        return False

    def _extract_artist_id(self, url: str) -> str:
        """Extract artist ID from Qobuz URL."""
        parsed = urlparse(url)
        path = parsed.path

        # Pattern: /interpreter/artist-name/123456
        match = re.search(r"/interpreter/[^/]+/(\d+)", path)
        if match:
            return match.group(1)

        # Pattern: /artist/123456
        match = re.search(r"/artist/(\d+)", path)
        if match:
            return match.group(1)

        # Try query parameter
        params = parse_qs(parsed.query)
        if "id" in params:
            return params["id"][0]

        raise ValueError(f"Could not extract artist ID from URL: {url}")

    def _api_request(self, endpoint: str, params: dict | None = None) -> dict:
        """Make a request to the Qobuz API."""
        if not self.credentials.get("app_id"):
            raise ValueError(
                "Qobuz app_id required. The default may work, or set QOBUZ_APP_ID."
            )

        request_params = {
            "app_id": self.credentials["app_id"],
            **(params or {}),
        }

        # Add user token if available (for user-specific endpoints)
        if self.credentials.get("user_token"):
            request_params["user_auth_token"] = self.credentials["user_token"]

        try:
            response = httpx.get(
                f"{QOBUZ_API_BASE}/{endpoint}",
                params=request_params,
                timeout=30.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                },
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise ValueError("Qobuz API authentication failed. Check app_id.")
            raise ValueError(f"Qobuz API error: {e}")
        except httpx.HTTPError as e:
            raise ValueError(f"Failed to connect to Qobuz: {e}")

    def _get_artist_info(self, artist_id: str) -> dict:
        """Fetch artist information."""
        data = self._api_request("artist/get", {
            "artist_id": artist_id,
            "extra": "albums",
            "limit": 100,
        })
        return data

    def resolve(self, url: str) -> SourceInfo:
        """Resolve Qobuz artist URL to source info."""
        artist_id = self._extract_artist_id(url)
        artist_data = self._get_artist_info(artist_id)

        name = artist_data.get("name", f"Artist {artist_id}")

        # Get artist image
        image = artist_data.get("image", {})
        avatar_url = (
            image.get("extralarge")
            or image.get("large")
            or image.get("medium")
            or image.get("small")
        )

        # Get album count
        albums_data = artist_data.get("albums", {})
        album_count = albums_data.get("total", 0)

        return SourceInfo(
            source_type=self.source_type,
            uri=f"qobuz:artist:{artist_id}",
            display_name=name,
            avatar_url=avatar_url,
            metadata={
                "artist_id": artist_id,
                "biography": artist_data.get("biography", {}).get("content"),
                "album_count": album_count,
                "qobuz_url": f"https://www.qobuz.com/artist/{artist_id}",
            },
        )

    def poll(self, source: SourceInfo, since: datetime | None = None) -> list[RawItem]:
        """Fetch releases from the artist."""
        artist_id = source.metadata.get("artist_id")
        if not artist_id:
            artist_id = source.uri.replace("qobuz:artist:", "")

        # Fetch artist albums
        data = self._api_request("artist/get", {
            "artist_id": artist_id,
            "extra": "albums",
            "limit": 100,
            "offset": 0,
        })

        albums_data = data.get("albums", {})
        albums = albums_data.get("items", [])

        items = []
        for album in albums:
            # Parse release date
            release_date_str = album.get("released_at") or album.get("release_date_original")
            if release_date_str:
                try:
                    # Try epoch timestamp first
                    if isinstance(release_date_str, (int, float)):
                        published_at = datetime.utcfromtimestamp(release_date_str)
                    else:
                        # Try ISO format
                        published_at = datetime.fromisoformat(release_date_str.replace("Z", "+00:00"))
                        published_at = published_at.replace(tzinfo=None)
                except (ValueError, TypeError):
                    published_at = datetime.utcnow()
            else:
                published_at = datetime.utcnow()

            # Skip items older than since
            if since and published_at <= since:
                continue

            # Get album image
            image = album.get("image", {})
            thumbnail = (
                image.get("large")
                or image.get("medium")
                or image.get("small")
                or image.get("thumbnail")
            )

            # Get artist name (might be various artists)
            artist_name = album.get("artist", {}).get("name", source.display_name)

            # Determine album type
            album_type = "album"
            if album.get("release_type"):
                album_type = album["release_type"].lower()

            # Get track count and duration
            tracks_count = album.get("tracks_count", 0)
            duration = album.get("duration", 0)

            # Build Qobuz URL
            album_id = album.get("id", "")
            album_url = f"https://open.qobuz.com/album/{album_id}"

            raw_item = RawItem(
                external_id=f"qobuz:album:{album_id}",
                url=album_url,
                title=album.get("title", "Untitled"),
                published_at=published_at,
                raw_metadata={
                    "author": artist_name,
                    "content_text": album.get("description"),
                    "thumbnail": thumbnail,
                    "album_id": album_id,
                    "album_type": album_type,
                    "tracks_count": tracks_count,
                    "duration_seconds": duration,
                    "genre": album.get("genre", {}).get("name"),
                    "label": album.get("label", {}).get("name"),
                    "hires_available": album.get("hires", False),
                    "qobuz_url": album_url,
                    "enclosures": [{
                        "url": album_url,
                        "type": "audio/qobuz",
                    }],
                },
            )
            items.append(raw_item)

        return items


class QobuzLabelAdapter(SourceAdapter):
    """Adapter for Qobuz label catalogs.

    Tracks releases from a specific record label.
    """

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
    def source_type(self) -> str:
        return "qobuz_label"

    def can_handle(self, url: str) -> bool:
        """Check if URL is a Qobuz label page."""
        parsed = urlparse(url)

        if parsed.netloc in ("www.qobuz.com", "qobuz.com", "open.qobuz.com"):
            if "/label/" in parsed.path:
                return True

        return False

    def _extract_label_id(self, url: str) -> str:
        """Extract label ID from Qobuz URL."""
        match = re.search(r"/label/[^/]+/(\d+)", url)
        if match:
            return match.group(1)

        match = re.search(r"/label/(\d+)", url)
        if match:
            return match.group(1)

        raise ValueError(f"Could not extract label ID from URL: {url}")

    def _api_request(self, endpoint: str, params: dict | None = None) -> dict:
        """Make a request to the Qobuz API."""
        if not self.credentials.get("app_id"):
            raise ValueError("Qobuz app_id required.")

        request_params = {
            "app_id": self.credentials["app_id"],
            **(params or {}),
        }

        response = httpx.get(
            f"{QOBUZ_API_BASE}/{endpoint}",
            params=request_params,
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            },
        )
        response.raise_for_status()
        return response.json()

    def resolve(self, url: str) -> SourceInfo:
        """Resolve Qobuz label URL to source info."""
        label_id = self._extract_label_id(url)

        # Fetch label info
        data = self._api_request("label/get", {
            "label_id": label_id,
            "extra": "albums",
            "limit": 1,
        })

        name = data.get("name", f"Label {label_id}")
        image = data.get("image", {})
        avatar_url = image.get("large") or image.get("medium")

        return SourceInfo(
            source_type=self.source_type,
            uri=f"qobuz:label:{label_id}",
            display_name=name,
            avatar_url=avatar_url,
            metadata={
                "label_id": label_id,
                "description": data.get("description"),
                "albums_count": data.get("albums_count", 0),
            },
        )

    def poll(self, source: SourceInfo, since: datetime | None = None) -> list[RawItem]:
        """Fetch releases from the label."""
        label_id = source.metadata.get("label_id")
        if not label_id:
            label_id = source.uri.replace("qobuz:label:", "")

        data = self._api_request("label/get", {
            "label_id": label_id,
            "extra": "albums",
            "limit": 100,
        })

        albums = data.get("albums", {}).get("items", [])

        items = []
        for album in albums:
            release_date_str = album.get("released_at") or album.get("release_date_original")
            if release_date_str:
                try:
                    if isinstance(release_date_str, (int, float)):
                        published_at = datetime.utcfromtimestamp(release_date_str)
                    else:
                        published_at = datetime.fromisoformat(release_date_str.replace("Z", "+00:00"))
                        published_at = published_at.replace(tzinfo=None)
                except (ValueError, TypeError):
                    published_at = datetime.utcnow()
            else:
                published_at = datetime.utcnow()

            if since and published_at <= since:
                continue

            image = album.get("image", {})
            thumbnail = image.get("large") or image.get("medium")

            artist_name = album.get("artist", {}).get("name", "Various Artists")
            album_id = album.get("id", "")
            album_url = f"https://open.qobuz.com/album/{album_id}"

            raw_item = RawItem(
                external_id=f"qobuz:album:{album_id}",
                url=album_url,
                title=album.get("title", "Untitled"),
                published_at=published_at,
                raw_metadata={
                    "author": artist_name,
                    "thumbnail": thumbnail,
                    "album_id": album_id,
                    "label": source.display_name,
                    "enclosures": [{
                        "url": album_url,
                        "type": "audio/qobuz",
                    }],
                },
            )
            items.append(raw_item)

        return items
