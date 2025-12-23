"""YouTube adapter using the Data API.

Supports:
- Channels: youtube.com/@handle, youtube.com/channel/UC...
- Playlists: youtube.com/playlist?list=PL...
"""

import logging
import os
import re
from datetime import datetime
from urllib.parse import urlparse, parse_qs

import httpx

from omnifeed.sources.base import SourceAdapter, SourceInfo, RawItem

logger = logging.getLogger(__name__)

# Default max videos to fetch on initial sync (when since is None)
# This prevents stalling on large channels
DEFAULT_INITIAL_SYNC_MAX = 500


# YouTube Data API v3 endpoints
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# Regex patterns for YouTube URLs
CHANNEL_ID_PATTERN = re.compile(r"^UC[\w-]{22}$")
PLAYLIST_ID_PATTERN = re.compile(r"^PL[\w-]+$")
CHANNEL_URL_PATTERNS = [
    re.compile(r"youtube\.com/channel/(UC[\w-]{22})"),
    re.compile(r"youtube\.com/@([\w.-]+)"),
    re.compile(r"youtube\.com/c/([\w.-]+)"),
    re.compile(r"youtube\.com/user/([\w.-]+)"),
]


def get_api_key() -> str | None:
    """Get YouTube API key from environment or config."""
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if api_key:
        return api_key

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

    def __init__(self, api_key: str | None = None, max_results: int | None = None):
        self._api_key = api_key
        self.max_results = max_results

    @property
    def api_key(self) -> str | None:
        if self._api_key is None:
            self._api_key = get_api_key()
        return self._api_key

    @property
    def source_type(self) -> str:
        return "youtube_channel"

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc not in ("youtube.com", "www.youtube.com", "m.youtube.com"):
            return False
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

        for pattern in CHANNEL_URL_PATTERNS:
            match = pattern.search(url)
            if match:
                identifier = match.group(1)
                if CHANNEL_ID_PATTERN.match(identifier):
                    return identifier
                return self._lookup_channel_id(identifier)

        raise ValueError(f"Could not parse YouTube channel URL: {url}")

    def _lookup_channel_id(self, identifier: str) -> str:
        """Look up channel ID from handle or username."""
        # Try as handle first
        params = {
            "key": self.api_key,
            "part": "id",
            "forHandle": identifier if identifier.startswith("@") else f"@{identifier}",
        }

        response = httpx.get(f"{YOUTUBE_API_BASE}/channels", params=params, timeout=30.0)
        if response.status_code == 200:
            data = response.json()
            if data.get("items"):
                return data["items"][0]["id"]

        # Try as username
        params = {"key": self.api_key, "part": "id", "forUsername": identifier}
        response = httpx.get(f"{YOUTUBE_API_BASE}/channels", params=params, timeout=30.0)
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
        response = httpx.get(f"{YOUTUBE_API_BASE}/search", params=params, timeout=30.0)
        if response.status_code == 200:
            data = response.json()
            if data.get("items"):
                return data["items"][0]["snippet"]["channelId"]

        raise ValueError(f"Could not find YouTube channel: {identifier}")

    def _get_channel_info(self, channel_id: str) -> dict:
        """Get channel metadata."""
        params = {"key": self.api_key, "part": "snippet,contentDetails", "id": channel_id}
        response = httpx.get(f"{YOUTUBE_API_BASE}/channels", params=params, timeout=30.0)
        response.raise_for_status()

        data = response.json()
        if not data.get("items"):
            raise ValueError(f"Channel not found: {channel_id}")
        return data["items"][0]

    def resolve(self, url: str) -> SourceInfo:
        channel_id = self._resolve_channel_id(url)
        channel_info = self._get_channel_info(channel_id)

        snippet = channel_info["snippet"]
        thumbnails = snippet.get("thumbnails", {})
        avatar_url = (
            thumbnails.get("high", {}).get("url")
            or thumbnails.get("medium", {}).get("url")
            or thumbnails.get("default", {}).get("url")
        )

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

    def _get_playlist_items(self, playlist_id: str, max_results: int = 50, page_token: str | None = None) -> dict:
        params = {
            "key": self.api_key,
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": min(max_results, 50),
        }
        if page_token:
            params["pageToken"] = page_token

        response = httpx.get(f"{YOUTUBE_API_BASE}/playlistItems", params=params, timeout=30.0)
        response.raise_for_status()
        return response.json()

    def _get_video_details(self, video_ids: list[str]) -> dict[str, dict]:
        if not video_ids:
            return {}

        params = {
            "key": self.api_key,
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(video_ids),
        }
        response = httpx.get(f"{YOUTUBE_API_BASE}/videos", params=params, timeout=30.0)
        response.raise_for_status()

        data = response.json()
        return {item["id"]: item for item in data.get("items", [])}

    def _parse_duration(self, duration: str) -> int:
        """Parse ISO 8601 duration to seconds."""
        match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
        if not match:
            return 0
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds

    def poll(self, source: SourceInfo, since: datetime | None = None) -> list[RawItem]:
        if not self.api_key:
            raise ValueError("YouTube API key required")

        playlist_id = source.metadata.get("uploads_playlist_id")
        if not playlist_id:
            raise ValueError("Missing uploads_playlist_id in source metadata")

        # Determine effective max_results
        # If no since date (initial sync), cap at DEFAULT_INITIAL_SYNC_MAX to prevent stalls
        effective_max = self.max_results
        if effective_max is None and since is None:
            effective_max = DEFAULT_INITIAL_SYNC_MAX
            logger.info(f"Initial sync: limiting to {effective_max} videos")

        items = []
        page_token = None
        fetched = 0
        old_content_streak = 0  # Track consecutive old items to stop early

        while True:
            batch_size = 50
            if effective_max is not None:
                remaining = effective_max - fetched
                if remaining <= 0:
                    break
                batch_size = min(remaining, 50)

            logger.debug(f"Fetching page, fetched so far: {fetched}")
            data = self._get_playlist_items(playlist_id, max_results=batch_size, page_token=page_token)

            playlist_items = data.get("items", [])
            if not playlist_items:
                break

            fetched += len(playlist_items)
            video_ids = [item["contentDetails"]["videoId"] for item in playlist_items]
            video_details = self._get_video_details(video_ids)

            batch_old_count = 0
            for playlist_item in playlist_items:
                snippet = playlist_item["snippet"]
                video_id = playlist_item["contentDetails"]["videoId"]

                published_str = snippet.get("publishedAt", "")
                try:
                    published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                    published_at = published_at.replace(tzinfo=None)
                except ValueError:
                    published_at = datetime.utcnow()

                if since and published_at <= since:
                    batch_old_count += 1
                    continue

                details = video_details.get(video_id, {})
                content_details = details.get("contentDetails", {})
                statistics = details.get("statistics", {})

                thumbnails = snippet.get("thumbnails", {})
                thumbnail = (
                    thumbnails.get("maxres", {}).get("url")
                    or thumbnails.get("high", {}).get("url")
                    or thumbnails.get("medium", {}).get("url")
                    or thumbnails.get("default", {}).get("url")
                )

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
                        "enclosures": [{"url": f"https://www.youtube.com/watch?v={video_id}", "type": "video/youtube"}],
                        "tags": snippet.get("tags", []),
                    },
                )
                items.append(raw_item)

            # If entire batch was old content, stop pagination early
            # (videos are in reverse chronological order)
            if since and batch_old_count == len(playlist_items):
                old_content_streak += 1
                if old_content_streak >= 2:
                    logger.info(f"Stopping early: 2 consecutive pages of old content")
                    break
            else:
                old_content_streak = 0

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        logger.info(f"Fetched {len(items)} new items from {source.display_name}")
        return items


class YouTubePlaylistAdapter(SourceAdapter):
    """Adapter for YouTube playlists using the Data API.

    Handles playlist URLs like:
    - youtube.com/playlist?list=PLxxxxx
    - RSS feed URLs with playlist_id parameter
    """

    def __init__(self, api_key: str | None = None, max_results: int | None = None):
        self._api_key = api_key
        self.max_results = max_results

    @property
    def api_key(self) -> str | None:
        if self._api_key is None:
            self._api_key = get_api_key()
        return self._api_key

    @property
    def source_type(self) -> str:
        return "youtube_playlist"

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc not in ("youtube.com", "www.youtube.com", "m.youtube.com"):
            return False

        # Check for playlist URL
        if "/playlist" in parsed.path:
            query = parse_qs(parsed.query)
            if "list" in query:
                return True

        # Check for RSS feed with playlist_id
        if "feeds/videos.xml" in parsed.path:
            query = parse_qs(parsed.query)
            if "playlist_id" in query:
                return True

        return False

    def _extract_playlist_id(self, url: str) -> str:
        """Extract playlist ID from URL."""
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        if "list" in query:
            return query["list"][0]
        if "playlist_id" in query:
            return query["playlist_id"][0]

        raise ValueError(f"Could not extract playlist ID from URL: {url}")

    def _get_playlist_info(self, playlist_id: str) -> dict:
        """Get playlist metadata."""
        params = {
            "key": self.api_key,
            "part": "snippet,contentDetails",
            "id": playlist_id,
        }
        response = httpx.get(f"{YOUTUBE_API_BASE}/playlists", params=params, timeout=30.0)
        response.raise_for_status()

        data = response.json()
        if not data.get("items"):
            raise ValueError(f"Playlist not found: {playlist_id}")
        return data["items"][0]

    def resolve(self, url: str) -> SourceInfo:
        if not self.api_key:
            raise ValueError("YouTube API key required.")

        playlist_id = self._extract_playlist_id(url)
        playlist_info = self._get_playlist_info(playlist_id)

        snippet = playlist_info["snippet"]
        thumbnails = snippet.get("thumbnails", {})
        thumbnail = (
            thumbnails.get("high", {}).get("url")
            or thumbnails.get("medium", {}).get("url")
            or thumbnails.get("default", {}).get("url")
        )

        item_count = playlist_info.get("contentDetails", {}).get("itemCount", 0)

        return SourceInfo(
            source_type=self.source_type,
            uri=f"youtube:playlist:{playlist_id}",
            display_name=snippet["title"],
            avatar_url=thumbnail,
            metadata={
                "playlist_id": playlist_id,
                "channel_id": snippet.get("channelId"),
                "channel_title": snippet.get("channelTitle"),
                "description": snippet.get("description"),
                "item_count": item_count,
            },
        )

    def _get_playlist_items(self, playlist_id: str, max_results: int = 50, page_token: str | None = None) -> dict:
        params = {
            "key": self.api_key,
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": min(max_results, 50),
        }
        if page_token:
            params["pageToken"] = page_token

        response = httpx.get(f"{YOUTUBE_API_BASE}/playlistItems", params=params, timeout=30.0)
        response.raise_for_status()
        return response.json()

    def _get_video_details(self, video_ids: list[str]) -> dict[str, dict]:
        if not video_ids:
            return {}

        params = {
            "key": self.api_key,
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(video_ids),
        }
        response = httpx.get(f"{YOUTUBE_API_BASE}/videos", params=params, timeout=30.0)
        response.raise_for_status()

        data = response.json()
        return {item["id"]: item for item in data.get("items", [])}

    def _parse_duration(self, duration: str) -> int:
        match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
        if not match:
            return 0
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds

    def poll(self, source: SourceInfo, since: datetime | None = None) -> list[RawItem]:
        if not self.api_key:
            raise ValueError("YouTube API key required")

        playlist_id = source.metadata.get("playlist_id")
        if not playlist_id:
            raise ValueError("Missing playlist_id in source metadata")

        # Determine effective max_results
        # If no since date (initial sync), cap at DEFAULT_INITIAL_SYNC_MAX to prevent stalls
        effective_max = self.max_results
        if effective_max is None and since is None:
            effective_max = DEFAULT_INITIAL_SYNC_MAX
            logger.info(f"Initial sync: limiting to {effective_max} videos")

        items = []
        page_token = None
        fetched = 0
        old_content_streak = 0

        while True:
            batch_size = 50
            if effective_max is not None:
                remaining = effective_max - fetched
                if remaining <= 0:
                    break
                batch_size = min(remaining, 50)

            logger.debug(f"Fetching page, fetched so far: {fetched}")
            data = self._get_playlist_items(playlist_id, max_results=batch_size, page_token=page_token)

            playlist_items = data.get("items", [])
            if not playlist_items:
                break

            fetched += len(playlist_items)
            video_ids = [item["contentDetails"]["videoId"] for item in playlist_items]
            video_details = self._get_video_details(video_ids)

            batch_old_count = 0
            for playlist_item in playlist_items:
                snippet = playlist_item["snippet"]
                video_id = playlist_item["contentDetails"]["videoId"]

                published_str = snippet.get("publishedAt", "")
                try:
                    published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                    published_at = published_at.replace(tzinfo=None)
                except ValueError:
                    published_at = datetime.utcnow()

                if since and published_at <= since:
                    batch_old_count += 1
                    continue

                details = video_details.get(video_id, {})
                content_details = details.get("contentDetails", {})
                statistics = details.get("statistics", {})

                thumbnails = snippet.get("thumbnails", {})
                thumbnail = (
                    thumbnails.get("maxres", {}).get("url")
                    or thumbnails.get("high", {}).get("url")
                    or thumbnails.get("medium", {}).get("url")
                    or thumbnails.get("default", {}).get("url")
                )

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
                        "enclosures": [{"url": f"https://www.youtube.com/watch?v={video_id}", "type": "video/youtube"}],
                        "tags": details.get("snippet", {}).get("tags", []),
                    },
                )
                items.append(raw_item)

            # If entire batch was old content, stop pagination early
            if since and batch_old_count == len(playlist_items):
                old_content_streak += 1
                if old_content_streak >= 2:
                    logger.info(f"Stopping early: 2 consecutive pages of old content")
                    break
            else:
                old_content_streak = 0

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        logger.info(f"Fetched {len(items)} new items from {source.display_name}")
        return items
