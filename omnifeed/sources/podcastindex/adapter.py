"""Podcast Index adapter for podcast feeds."""

import re
from datetime import datetime
from urllib.parse import urlparse

import httpx

from omnifeed.sources.base import SourceAdapter, SourceInfo, RawItem


PODCASTINDEX_API_BASE = "https://api.podcastindex.org/api/1.0"


def get_podcastindex_api_key() -> str | None:
    """Get Podcast Index API key from config file.

    Set in ~/.omnifeed/config.json:
        {"extra": {"podcastindex_api_key": "your_key"}}
    """
    try:
        from omnifeed.config import Config
        config = Config.load()
        return config.extra.get("podcastindex_api_key")
    except Exception:
        return None


class PodcastIndexAdapter(SourceAdapter):
    """Adapter for Podcast Index podcast feeds.

    Follows new episodes from a podcast.
    """

    def __init__(self):
        self._api_key = None

    @property
    def api_key(self) -> str | None:
        if self._api_key is None:
            self._api_key = get_podcastindex_api_key()
        return self._api_key

    @property
    def source_type(self) -> str:
        return "podcast"

    def _auth_headers(self) -> dict:
        """Generate authentication headers for Podcast Index API."""
        if not self.api_key:
            raise ValueError(
                "Podcast Index API key required. "
                "Set podcastindex_api_key in ~/.omnifeed/config.json"
            )

        return {
            "User-Agent": "OmniFeed/1.0",
            "X-Auth-Key": self.api_key,
        }

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        # Handle podcastindex.org URLs
        if parsed.netloc in ("podcastindex.org", "www.podcastindex.org"):
            if "/podcast/" in parsed.path:
                return True
        # Also handle direct feed URLs (RSS)
        if url.endswith(".xml") or url.endswith("/feed") or "/rss" in url.lower():
            return True
        return False

    def _extract_podcast_id(self, url: str) -> str | None:
        """Extract podcast ID from Podcast Index URL."""
        match = re.search(r"/podcast/(\d+)", url)
        if match:
            return match.group(1)
        return None

    def _api_request(self, endpoint: str, params: dict | None = None) -> dict:
        """Make authenticated API request."""
        response = httpx.get(
            f"{PODCASTINDEX_API_BASE}/{endpoint}",
            params=params,
            headers=self._auth_headers(),
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()

    def resolve(self, url: str) -> SourceInfo:
        # Try to extract podcast ID from URL
        podcast_id = self._extract_podcast_id(url)

        if podcast_id:
            # Lookup by ID
            data = self._api_request("podcasts/byfeedid", {"id": podcast_id})
        else:
            # Lookup by feed URL
            data = self._api_request("podcasts/byfeedurl", {"url": url})

        feed = data.get("feed", {})
        if not feed:
            raise ValueError(f"Podcast not found: {url}")

        podcast_id = feed.get("id")
        title = feed.get("title", f"Podcast {podcast_id}")
        artwork = feed.get("artwork") or feed.get("image")

        return SourceInfo(
            source_type=self.source_type,
            uri=f"podcast:{podcast_id}",
            display_name=title,
            avatar_url=artwork,
            metadata={
                "podcast_id": podcast_id,
                "feed_url": feed.get("url"),
                "description": feed.get("description", "")[:500],
                "author": feed.get("author"),
                "language": feed.get("language"),
                "categories": feed.get("categories", {}),
                "episode_count": feed.get("episodeCount"),
                "podcastindex_url": f"https://podcastindex.org/podcast/{podcast_id}",
            },
        )

    def poll(self, source: SourceInfo, since: datetime | None = None) -> list[RawItem]:
        podcast_id = source.metadata.get("podcast_id")
        if not podcast_id:
            uri = source.uri
            if uri.startswith("podcast:"):
                podcast_id = uri.replace("podcast:", "")
            elif "podcastindex.org" in uri:
                podcast_id = self._extract_podcast_id(uri)

        if not podcast_id:
            return []

        # Get recent episodes
        params = {"id": podcast_id, "max": 50}
        if since:
            params["since"] = int(since.timestamp())

        data = self._api_request("episodes/byfeedid", params)

        items = []
        for episode in data.get("items", []):
            # Parse date
            date_published = episode.get("datePublished")
            if date_published:
                try:
                    published_at = datetime.fromtimestamp(date_published)
                except (ValueError, TypeError, OSError):
                    published_at = datetime.now()
            else:
                published_at = datetime.now()

            if since and published_at <= since:
                continue

            episode_id = episode.get("id")
            title = episode.get("title", "Untitled Episode")
            description = episode.get("description", "")

            # Clean HTML from description
            clean_description = re.sub(r'<[^>]+>', '', description)

            # Get enclosure (audio file)
            enclosure_url = episode.get("enclosureUrl")
            enclosure_type = episode.get("enclosureType", "audio/mpeg")
            duration = episode.get("duration", 0)

            # Build content text
            content_parts = [title]
            if clean_description:
                content_parts.append(clean_description[:500])

            raw_item = RawItem(
                external_id=f"podcast:episode:{episode_id}",
                url=episode.get("link") or f"https://podcastindex.org/podcast/{podcast_id}",
                title=title,
                published_at=published_at,
                raw_metadata={
                    "author": source.display_name,
                    "content_text": " | ".join(content_parts),
                    "description": clean_description[:500],
                    "thumbnail": episode.get("image") or episode.get("feedImage"),
                    "episode_id": episode_id,
                    "duration_seconds": duration,
                    "enclosures": [{"url": enclosure_url, "type": enclosure_type}] if enclosure_url else [],
                    "audio_url": enclosure_url,
                    "episode_number": episode.get("episode"),
                    "season": episode.get("season"),
                    "explicit": episode.get("explicit", 0),
                },
            )
            items.append(raw_item)

        return items


class PodcastIndexTrendingAdapter(SourceAdapter):
    """Adapter for Podcast Index trending podcasts.

    Follows trending/new podcasts in a category.
    """

    def __init__(self):
        self._api_key = None

    @property
    def api_key(self) -> str | None:
        if self._api_key is None:
            self._api_key = get_podcastindex_api_key()
        return self._api_key

    @property
    def source_type(self) -> str:
        return "podcast_trending"

    def _auth_headers(self) -> dict:
        if not self.api_key:
            raise ValueError("Podcast Index API key required.")

        return {
            "User-Agent": "OmniFeed/1.0",
            "X-Auth-Key": self.api_key,
        }

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc in ("podcastindex.org", "www.podcastindex.org"):
            if "/trending" in parsed.path or "/category/" in parsed.path:
                return True
        return False

    def _api_request(self, endpoint: str, params: dict | None = None) -> dict:
        response = httpx.get(
            f"{PODCASTINDEX_API_BASE}/{endpoint}",
            params=params,
            headers=self._auth_headers(),
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()

    def resolve(self, url: str) -> SourceInfo:
        # For now, just return a general trending feed
        return SourceInfo(
            source_type=self.source_type,
            uri="podcast:trending",
            display_name="Trending Podcasts",
            avatar_url=None,
            metadata={
                "podcastindex_url": "https://podcastindex.org/trending",
            },
        )

    def poll(self, source: SourceInfo, since: datetime | None = None) -> list[RawItem]:
        # Get trending podcasts
        data = self._api_request("podcasts/trending", {"max": 50})

        items = []
        for podcast in data.get("feeds", []):
            podcast_id = podcast.get("id")
            title = podcast.get("title", "Untitled")

            # Use newestItemPublishTime as the date
            newest_time = podcast.get("newestItemPublishTime")
            if newest_time:
                try:
                    published_at = datetime.fromtimestamp(newest_time)
                except (ValueError, TypeError, OSError):
                    published_at = datetime.now()
            else:
                published_at = datetime.now()

            if since and published_at <= since:
                continue

            description = podcast.get("description", "")
            clean_description = re.sub(r'<[^>]+>', '', description)

            raw_item = RawItem(
                external_id=f"podcast:{podcast_id}",
                url=f"https://podcastindex.org/podcast/{podcast_id}",
                title=title,
                published_at=published_at,
                raw_metadata={
                    "author": podcast.get("author", ""),
                    "content_text": f"{title} | {clean_description[:300]}" if clean_description else title,
                    "description": clean_description[:500],
                    "thumbnail": podcast.get("artwork") or podcast.get("image"),
                    "podcast_id": podcast_id,
                    "trend_score": podcast.get("trendScore"),
                    "categories": podcast.get("categories", {}),
                },
            )
            items.append(raw_item)

        return items
