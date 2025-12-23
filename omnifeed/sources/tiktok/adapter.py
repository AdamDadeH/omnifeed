"""TikTok adapter - supports direct video URLs and optional feed backends.

TikTok aggressively blocks scraping, so automatic feed discovery is unreliable.
Primary use: Add individual TikTok video URLs for viewing/tracking.

Optional backends (require self-hosting for reliability):
- RSSHub: https://docs.rsshub.app/
- Proxitok: https://github.com/pablouser1/ProxiTok
"""

import logging
import os
import re
from datetime import datetime
from urllib.parse import urlparse

import feedparser
import httpx

from omnifeed.sources.base import SourceAdapter, SourceInfo, RawItem

logger = logging.getLogger(__name__)

# Feed backend instances - public instances are unreliable
# Self-host for production use
DEFAULT_RSSHUB_URL = None  # No default - requires config
DEFAULT_PROXITOK_URL = None  # No default - requires config


def get_feed_backend() -> tuple[str | None, str]:
    """Get feed backend URL and type from config.

    Returns:
        (url, backend_type) - backend_type is 'rsshub' or 'proxitok'
    """
    try:
        from omnifeed.config import Config
        config = Config.load()

        rsshub = config.extra.get("rsshub_url") or os.environ.get("RSSHUB_URL")
        if rsshub:
            return rsshub.rstrip("/"), "rsshub"

        proxitok = config.extra.get("proxitok_url") or os.environ.get("PROXITOK_URL")
        if proxitok:
            return proxitok.rstrip("/"), "proxitok"
    except Exception:
        pass

    return None, "none"


class TikTokAdapter(SourceAdapter):
    """Adapter for TikTok content.

    Supports:
    1. Individual video URLs (always works)
    2. User feeds via RSSHub or Proxitok (requires self-hosting)

    URL formats:
        - https://www.tiktok.com/@username/video/123456  (single video)
        - https://www.tiktok.com/@username  (user feed - needs backend)
        - tiktok:@username  (user feed - needs backend)

    Configure backend in ~/.omnifeed/config.json:
        {"extra": {"rsshub_url": "http://localhost:1200"}}
        or
        {"extra": {"proxitok_url": "http://localhost:8080"}}
    """

    def __init__(self):
        self._backend_url, self._backend_type = get_feed_backend()

    @property
    def source_type(self) -> str:
        return "tiktok"

    def can_handle(self, url: str) -> bool:
        if url.startswith("tiktok:"):
            return True
        if "tiktok.com" in url or "vm.tiktok.com" in url:
            return True
        return False

    def _is_single_video(self, url: str) -> bool:
        """Check if URL is a single video vs user profile."""
        return "/video/" in url or "vm.tiktok.com" in url

    def _extract_video_info(self, url: str) -> dict:
        """Extract video ID and username from video URL."""
        video_id = None
        username = None

        # Extract video ID
        match = re.search(r"/video/(\d+)", url)
        if match:
            video_id = match.group(1)

        # Extract username
        match = re.search(r"tiktok\.com/@([^/?]+)", url)
        if match:
            username = match.group(1)

        return {"video_id": video_id, "username": username}

    def _extract_username(self, url: str) -> str:
        """Extract TikTok username from URL."""
        if url.startswith("tiktok:"):
            return url[7:].lstrip("@")

        match = re.search(r"tiktok\.com/@([^/?]+)", url)
        if match:
            return match.group(1)

        raise ValueError(f"Could not extract TikTok username from: {url}")

    def _get_feed_url(self, username: str) -> str | None:
        """Get feed URL for a TikTok user based on configured backend."""
        if not self._backend_url:
            return None

        if self._backend_type == "rsshub":
            return f"{self._backend_url}/tiktok/user/@{username}"
        elif self._backend_type == "proxitok":
            return f"{self._backend_url}/@{username}/rss"

        return None

    def resolve(self, url: str) -> SourceInfo:
        # Single video - create a source for just this video
        if self._is_single_video(url):
            info = self._extract_video_info(url)
            video_id = info["video_id"] or "unknown"
            username = info["username"] or "unknown"

            return SourceInfo(
                source_type=self.source_type,
                uri=f"tiktok:video:{video_id}",
                display_name=f"TikTok by @{username}",
                avatar_url=None,
                metadata={
                    "video_id": video_id,
                    "username": username,
                    "video_url": url,
                    "is_single_video": True,
                },
            )

        # User profile - check if we have a backend
        username = self._extract_username(url)
        feed_url = self._get_feed_url(username)

        if not feed_url:
            # No backend configured - still allow adding, but warn
            logger.warning(
                f"No TikTok feed backend configured. "
                f"Add rsshub_url or proxitok_url to config for @{username} feed updates."
            )
            return SourceInfo(
                source_type=self.source_type,
                uri=f"tiktok:@{username}",
                display_name=f"@{username} (TikTok)",
                avatar_url=None,
                metadata={
                    "username": username,
                    "tiktok_url": f"https://www.tiktok.com/@{username}",
                    "backend_configured": False,
                },
            )

        # Try to fetch user info from backend
        try:
            response = httpx.get(
                feed_url,
                follow_redirects=True,
                timeout=30.0,
                headers={"User-Agent": "OmniFeed/1.0"},
            )
            response.raise_for_status()
            feed = feedparser.parse(response.content)

            return SourceInfo(
                source_type=self.source_type,
                uri=f"tiktok:@{username}",
                display_name=feed.feed.get("title", f"@{username}"),
                avatar_url=feed.feed.get("image", {}).get("href"),
                metadata={
                    "username": username,
                    "tiktok_url": f"https://www.tiktok.com/@{username}",
                    "feed_url": feed_url,
                    "backend_configured": True,
                    "backend_type": self._backend_type,
                },
            )
        except httpx.HTTPError as e:
            raise ValueError(
                f"Failed to fetch TikTok feed for @{username}. "
                f"Backend ({self._backend_type}) may be down or blocking requests: {e}"
            )

    def poll(self, source: SourceInfo, since: datetime | None = None) -> list[RawItem]:
        # Single video sources don't need polling - they're static
        if source.metadata.get("is_single_video"):
            video_url = source.metadata.get("video_url")
            video_id = source.metadata.get("video_id")
            username = source.metadata.get("username", "unknown")

            return [
                RawItem(
                    external_id=video_id,
                    url=video_url,
                    title=f"TikTok by @{username}",
                    published_at=datetime.utcnow(),
                    raw_metadata={
                        "author": username,
                        "video_id": video_id,
                        "enclosures": [{"url": video_url, "type": "video/tiktok"}],
                    },
                )
            ]

        # User feed - need backend
        if not source.metadata.get("backend_configured"):
            logger.warning(
                f"Cannot poll TikTok user without backend configured. "
                f"Skipping {source.display_name}"
            )
            return []

        username = source.metadata.get("username")
        feed_url = source.metadata.get("feed_url") or self._get_feed_url(username)

        if not feed_url:
            return []

        try:
            response = httpx.get(
                feed_url,
                follow_redirects=True,
                timeout=30.0,
                headers={"User-Agent": "OmniFeed/1.0"},
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch TikTok feed: {e}")
            return []

        feed = feedparser.parse(response.content)

        items = []
        for entry in feed.entries:
            published_at = datetime.utcnow()
            for field in ["published_parsed", "updated_parsed"]:
                if hasattr(entry, field) and getattr(entry, field):
                    try:
                        published_at = datetime(*getattr(entry, field)[:6])
                        break
                    except (TypeError, ValueError):
                        pass

            if since and published_at <= since:
                continue

            video_url = entry.get("link", "")
            video_id = None
            match = re.search(r"/video/(\d+)", video_url)
            if match:
                video_id = match.group(1)

            content = entry.get("summary", "") or entry.get("description", "")
            thumbnail = None
            img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content)
            if img_match:
                thumbnail = img_match.group(1)

            description = re.sub(r"<[^>]+>", "", content).strip()

            raw_item = RawItem(
                external_id=video_id or entry.get("id", video_url),
                url=video_url,
                title=entry.get("title", "TikTok video"),
                published_at=published_at,
                raw_metadata={
                    "author": username,
                    "video_id": video_id,
                    "thumbnail": thumbnail,
                    "content_text": description,
                    "enclosures": [{"url": video_url, "type": "video/tiktok"}],
                },
            )
            items.append(raw_item)

        return items
