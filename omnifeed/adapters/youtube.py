"""YouTube channel adapter using the Data API."""

import os
import re
from datetime import datetime
from urllib.parse import urlparse, parse_qs

import httpx

from omnifeed.adapters.base import SourceAdapter
from omnifeed.models import SourceInfo, RawItem


# YouTube Data API v3 endpoints
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# Regex patterns for YouTube URLs
CHANNEL_ID_PATTERN = re.compile(r"^UC[\w-]{22}$")
CHANNEL_URL_PATTERNS = [
    re.compile(r"youtube\.com/channel/(UC[\w-]{22})"),
    re.compile(r"youtube\.com/@([\w.-]+)"),
    re.compile(r"youtube\.com/c/([\w.-]+)"),
    re.compile(r"youtube\.com/user/([\w.-]+)"),
]


def get_api_key() -> str | None:
    """Get YouTube API key from environment or config."""
    # Check environment variable first
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if api_key:
        return api_key

    # Try loading from config
    try:
        from omnifeed.config import Config
        config = Config.load()
        return config.extra.get("youtube_api_key")
    except Exception:
        return None


class YouTubeAdapter(SourceAdapter):
    """Adapter for YouTube channels using the Data API.

    Requires a YouTube Data API key. Set via:
    - Environment variable: YOUTUBE_API_KEY
    - Config file: ~/.omnifeed/config.json with {"extra": {"youtube_api_key": "..."}}
    """

    def __init__(self, api_key: str | None = None, max_results: int = 50):
        self._api_key = api_key
        self.max_results = max_results  # Max videos per poll (API limit is 50)

    @property
    def api_key(self) -> str | None:
        """Get API key (lazy load)."""
        if self._api_key is None:
            self._api_key = get_api_key()
        return self._api_key

    @property
    def source_type(self) -> str:
        return "youtube_channel"

    def can_handle(self, url: str) -> bool:
        """Check if URL is a YouTube channel."""
        parsed = urlparse(url)

        if parsed.netloc not in ("youtube.com", "www.youtube.com", "m.youtube.com"):
            return False

        # Check for channel patterns
        for pattern in CHANNEL_URL_PATTERNS:
            if pattern.search(url):
                return True

        return False

    def _resolve_channel_id(self, url: str) -> str:
        """Resolve a YouTube URL to a channel ID."""
        if not self.api_key:
            raise ValueError(
                "YouTube API key required. Set YOUTUBE_API_KEY environment variable "
                "or add youtube_api_key to config.json extra field."
            )

        # Try to extract channel ID directly
        for pattern in CHANNEL_URL_PATTERNS:
            match = pattern.search(url)
            if match:
                identifier = match.group(1)

                # If it's already a channel ID, return it
                if CHANNEL_ID_PATTERN.match(identifier):
                    return identifier

                # Otherwise, resolve handle/username to channel ID
                return self._lookup_channel_id(identifier)

        raise ValueError(f"Could not parse YouTube channel URL: {url}")

    def _lookup_channel_id(self, identifier: str) -> str:
        """Look up channel ID from handle or username."""
        # Try as handle first (@ prefix)
        params = {
            "key": self.api_key,
            "part": "id",
            "forHandle": identifier if identifier.startswith("@") else f"@{identifier}",
        }

        response = httpx.get(
            f"{YOUTUBE_API_BASE}/channels",
            params=params,
            timeout=30.0,
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("items"):
                return data["items"][0]["id"]

        # Try as username
        params = {
            "key": self.api_key,
            "part": "id",
            "forUsername": identifier,
        }

        response = httpx.get(
            f"{YOUTUBE_API_BASE}/channels",
            params=params,
            timeout=30.0,
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("items"):
                return data["items"][0]["id"]

        # Try search as last resort
        params = {
            "key": self.api_key,
            "part": "snippet",
            "q": identifier,
            "type": "channel",
            "maxResults": 1,
        }

        response = httpx.get(
            f"{YOUTUBE_API_BASE}/search",
            params=params,
            timeout=30.0,
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("items"):
                return data["items"][0]["snippet"]["channelId"]

        raise ValueError(f"Could not find YouTube channel: {identifier}")

    def _get_channel_info(self, channel_id: str) -> dict:
        """Get channel metadata."""
        params = {
            "key": self.api_key,
            "part": "snippet,contentDetails",
            "id": channel_id,
        }

        response = httpx.get(
            f"{YOUTUBE_API_BASE}/channels",
            params=params,
            timeout=30.0,
        )
        response.raise_for_status()

        data = response.json()
        if not data.get("items"):
            raise ValueError(f"Channel not found: {channel_id}")

        return data["items"][0]

    def resolve(self, url: str) -> SourceInfo:
        """Fetch channel metadata."""
        channel_id = self._resolve_channel_id(url)
        channel_info = self._get_channel_info(channel_id)

        snippet = channel_info["snippet"]

        # Get best available thumbnail
        thumbnails = snippet.get("thumbnails", {})
        avatar_url = (
            thumbnails.get("high", {}).get("url")
            or thumbnails.get("medium", {}).get("url")
            or thumbnails.get("default", {}).get("url")
        )

        # Get uploads playlist ID
        uploads_playlist_id = channel_info["contentDetails"]["relatedPlaylists"]["uploads"]

        return SourceInfo(
            source_type=self.source_type,
            uri=f"youtube:channel:{channel_id}",
            display_name=snippet["title"],
            avatar_url=avatar_url,
            metadata={
                "channel_id": channel_id,
                "uploads_playlist_id": uploads_playlist_id,
                "description": snippet.get("description"),
                "custom_url": snippet.get("customUrl"),
                "country": snippet.get("country"),
            },
        )

    def _get_playlist_items(
        self,
        playlist_id: str,
        max_results: int = 50,
        page_token: str | None = None,
    ) -> dict:
        """Get items from a playlist."""
        params = {
            "key": self.api_key,
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": min(max_results, 50),  # API max is 50
        }
        if page_token:
            params["pageToken"] = page_token

        response = httpx.get(
            f"{YOUTUBE_API_BASE}/playlistItems",
            params=params,
            timeout=30.0,
        )
        response.raise_for_status()

        return response.json()

    def _get_video_details(self, video_ids: list[str]) -> dict[str, dict]:
        """Get detailed info for multiple videos."""
        if not video_ids:
            return {}

        params = {
            "key": self.api_key,
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(video_ids),
        }

        response = httpx.get(
            f"{YOUTUBE_API_BASE}/videos",
            params=params,
            timeout=30.0,
        )
        response.raise_for_status()

        data = response.json()
        return {item["id"]: item for item in data.get("items", [])}

    def _parse_duration(self, duration: str) -> int:
        """Parse ISO 8601 duration to seconds."""
        # Format: PT#H#M#S or PT#M#S or PT#S
        match = re.match(
            r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?",
            duration,
        )
        if not match:
            return 0

        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)

        return hours * 3600 + minutes * 60 + seconds

    def poll(self, source: SourceInfo, since: datetime | None = None) -> list[RawItem]:
        """Fetch videos from the channel."""
        if not self.api_key:
            raise ValueError("YouTube API key required")

        playlist_id = source.metadata.get("uploads_playlist_id")
        if not playlist_id:
            raise ValueError("Missing uploads_playlist_id in source metadata")

        items = []
        page_token = None
        remaining = self.max_results

        while remaining > 0:
            # Fetch playlist items
            data = self._get_playlist_items(
                playlist_id,
                max_results=min(remaining, 50),
                page_token=page_token,
            )

            playlist_items = data.get("items", [])
            if not playlist_items:
                break

            # Extract video IDs for batch details request
            video_ids = [
                item["contentDetails"]["videoId"]
                for item in playlist_items
            ]

            # Get detailed video info
            video_details = self._get_video_details(video_ids)

            for playlist_item in playlist_items:
                snippet = playlist_item["snippet"]
                video_id = playlist_item["contentDetails"]["videoId"]

                # Parse publish date
                published_str = snippet.get("publishedAt", "")
                try:
                    published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                    published_at = published_at.replace(tzinfo=None)  # Store as naive UTC
                except ValueError:
                    published_at = datetime.utcnow()

                # Skip items older than since
                if since and published_at <= since:
                    continue

                # Get video details
                details = video_details.get(video_id, {})
                content_details = details.get("contentDetails", {})
                statistics = details.get("statistics", {})

                # Get best thumbnail
                thumbnails = snippet.get("thumbnails", {})
                thumbnail = (
                    thumbnails.get("maxres", {}).get("url")
                    or thumbnails.get("high", {}).get("url")
                    or thumbnails.get("medium", {}).get("url")
                    or thumbnails.get("default", {}).get("url")
                )

                # Parse duration
                duration_str = content_details.get("duration", "PT0S")
                duration_seconds = self._parse_duration(duration_str)

                raw_item = RawItem(
                    external_id=video_id,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    title=snippet.get("title", "Untitled"),
                    published_at=published_at,
                    raw_metadata={
                        "author": snippet.get("channelTitle", source.display_name),
                        "content_text": snippet.get("description", ""),
                        "thumbnail": thumbnail,
                        "video_id": video_id,
                        "channel_id": snippet.get("channelId"),
                        "duration_seconds": duration_seconds,
                        "view_count": int(statistics.get("viewCount", 0)),
                        "like_count": int(statistics.get("likeCount", 0)),
                        "comment_count": int(statistics.get("commentCount", 0)),
                        "enclosures": [{
                            "url": f"https://www.youtube.com/watch?v={video_id}",
                            "type": "video/youtube",
                        }],
                        "tags": snippet.get("tags", []),
                    },
                )
                items.append(raw_item)

            remaining -= len(playlist_items)

            # Check for more pages
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return items
