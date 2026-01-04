"""Bandcamp adapter for artist/label feeds and fan collections."""

import logging
import re
from datetime import datetime
from urllib.parse import urlparse

import httpx

from omnifeed.sources.base import SourceAdapter, SourceInfo, RawItem

logger = logging.getLogger(__name__)


class BandcampAdapter(SourceAdapter):
    """Adapter for Bandcamp artist/label feeds.

    Supports:
    - Artist pages: https://artistname.bandcamp.com
    - Label pages: https://labelname.bandcamp.com
    """

    @property
    def source_type(self) -> str:
        return "bandcamp"

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc.endswith(".bandcamp.com"):
            subdomain = parsed.netloc.replace(".bandcamp.com", "")
            if subdomain and subdomain not in ("www", "daily", "bandcamp"):
                return True
        return False

    def _get_artist_slug(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.netloc.endswith(".bandcamp.com"):
            return parsed.netloc.replace(".bandcamp.com", "")
        raise ValueError(f"Could not extract artist from URL: {url}")

    def _fetch_page_metadata(self, base_url: str) -> dict:
        try:
            response = httpx.get(base_url, follow_redirects=True, timeout=30.0)
            response.raise_for_status()
            html = response.text
        except httpx.HTTPError as e:
            raise ValueError(f"Failed to fetch Bandcamp page: {e}")

        metadata = {}

        name_match = re.search(r'<meta property="og:site_name" content="([^"]+)"', html)
        if name_match:
            metadata["name"] = name_match.group(1)
        else:
            title_match = re.search(r"<title>([^<|]+)", html)
            if title_match:
                metadata["name"] = title_match.group(1).strip()

        img_match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
        if img_match:
            metadata["image"] = img_match.group(1)

        desc_match = re.search(r'<meta name="description" content="([^"]+)"', html)
        if desc_match:
            metadata["description"] = desc_match.group(1)

        if "label" in html.lower() and "artists" in html.lower():
            metadata["is_label"] = True

        return metadata

    def resolve(self, url: str) -> SourceInfo:
        slug = self._get_artist_slug(url)
        base_url = f"https://{slug}.bandcamp.com"
        metadata = self._fetch_page_metadata(base_url)

        return SourceInfo(
            source_type=self.source_type,
            uri=f"bandcamp:{slug}",
            display_name=metadata.get("name", slug),
            avatar_url=metadata.get("image"),
            metadata={
                "slug": slug,
                "base_url": base_url,
                "feed_url": f"{base_url}/feed",
                "description": metadata.get("description"),
                "is_label": metadata.get("is_label", False),
            },
        )

    def poll(self, source: SourceInfo, since: datetime | None = None) -> list[RawItem]:
        slug = source.metadata.get("slug")
        if not slug:
            # Handle both URI formats: "bandcamp:slug" or full URL
            uri = source.uri
            if uri.startswith("bandcamp:"):
                slug = uri.replace("bandcamp:", "")
            elif ".bandcamp.com" in uri:
                slug = self._get_artist_slug(uri)
            else:
                slug = uri
        base_url = f"https://{slug}.bandcamp.com"
        music_url = f"{base_url}/music"

        try:
            response = httpx.get(music_url, follow_redirects=True, timeout=30.0)
            if response.status_code == 404:
                response = httpx.get(base_url, follow_redirects=True, timeout=30.0)
            response.raise_for_status()
            html = response.text
        except httpx.HTTPError as e:
            raise ValueError(f"Failed to fetch Bandcamp page: {e}")

        items = []

        # Find all album/track URLs
        found_urls = set()
        simple_pattern = re.compile(r'href="(https?://[^"]+\.bandcamp\.com/(?:album|track)/[^"]+)"')
        for match in simple_pattern.finditer(html):
            found_urls.add(match.group(1))

        relative_pattern = re.compile(r'href="(/(?:album|track)/[^"]+)"')
        for match in relative_pattern.finditer(html):
            found_urls.add(f"{base_url}{match.group(1)}")

        for url in list(found_urls)[:50]:
            try:
                release = self._fetch_release_details(url, source.display_name)
                if release:
                    if since and release.published_at <= since:
                        continue
                    items.append(release)
            except Exception as e:
                logger.warning(f"Failed to fetch release {url}: {e}")
                continue

        return items

    def _fetch_release_details(self, url: str, artist_name: str) -> RawItem | None:
        try:
            response = httpx.get(url, follow_redirects=True, timeout=30.0)
            response.raise_for_status()
            html = response.text
        except httpx.HTTPError:
            return None

        # Extract title
        title_match = re.search(r'<h2 class="trackTitle">([^<]+)</h2>', html)
        if not title_match:
            title_match = re.search(r'"name"\s*:\s*"([^"]+)"', html)
        title = title_match.group(1).strip() if title_match else "Untitled"

        # Extract release date
        date_match = re.search(r'album_release_date:\s*"([^"]+)"', html)
        if not date_match:
            date_match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)

        published_at = datetime.utcnow()
        if date_match:
            try:
                date_str = date_match.group(1)
                for fmt in ["%d %b %Y %H:%M:%S GMT", "%Y-%m-%d", "%d %B %Y"]:
                    try:
                        published_at = datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue
            except Exception:
                pass

        # Extract thumbnail
        img_match = re.search(r'<a class="popupImage"[^>]+href="([^"]+)"', html)
        if not img_match:
            img_match = re.search(r'"image"\s*:\s*"([^"]+)"', html)
        thumbnail = img_match.group(1) if img_match else None

        item_type = "album" if "/album/" in url else "track"

        artist_match = re.search(r'<span[^>]*>by\s*<a[^>]*>([^<]+)</a>', html)
        artist = artist_match.group(1).strip() if artist_match else artist_name

        # Extract description
        description = ""
        desc_match = re.search(
            r'<div class="tralbumData tralbum-about"[^>]*>\s*(?:<div[^>]*>)?\s*(.*?)\s*(?:</div>)?\s*</div>',
            html, re.DOTALL
        )
        if desc_match:
            description = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()

        # Extract tags
        tags = []
        tag_matches = re.findall(r'<a class="tag"[^>]*>([^<]+)</a>', html)
        tags = [t.strip() for t in tag_matches]

        # Extract tracks
        tracks = []
        track_pattern = re.compile(r'<span class="track-title">([^<]+)</span>.*?(?:<span class="time[^"]*">([^<]+)</span>)?', re.DOTALL)
        for match in track_pattern.finditer(html):
            track_title = match.group(1).strip()
            duration = match.group(2).strip() if match.group(2) else None
            tracks.append({"title": track_title, "duration": duration})

        # Extract credits
        credits = ""
        credits_match = re.search(r'<div class="tralbumData tralbum-credits"[^>]*>(.*?)</div>', html, re.DOTALL)
        if credits_match:
            credits = re.sub(r'<[^>]+>', ' ', credits_match.group(1)).strip()
            credits = re.sub(r'\s+', ' ', credits)

        # Extract audio preview (handle both literal quotes and HTML entities)
        audio_url = None
        # Try literal quotes first
        audio_match = re.search(r'"mp3-128"\s*:\s*"([^"]+)"', html)
        if not audio_match:
            # Try HTML entity encoded quotes (&quot;)
            audio_match = re.search(r'&quot;mp3-128&quot;\s*:\s*&quot;([^&]+(?:&amp;[^&]+)*)', html)
        if audio_match:
            audio_url = audio_match.group(1)
            # Decode HTML entities in URL
            audio_url = audio_url.replace("&amp;", "&").replace("&quot;", "")

        # Build content text for embeddings
        content_parts = [title, f"by {artist}"]
        if description:
            content_parts.append(description)
        if tags:
            content_parts.append(f"Tags: {', '.join(tags)}")
        if tracks:
            content_parts.append(f"Tracks: {', '.join(t['title'] for t in tracks[:10])}")
        if credits:
            content_parts.append(credits[:500])
        content_text = " | ".join(content_parts)

        return RawItem(
            external_id=url,
            url=url,
            title=title,
            published_at=published_at,
            raw_metadata={
                "author": artist,
                "content_text": content_text,
                "description": description,
                "thumbnail": thumbnail,
                "item_type": item_type,
                "tags": tags,
                "tracks": tracks,
                "credits": credits,
                "audio_preview_url": audio_url,
                "bandcamp_url": url,
                "enclosures": [{"url": url, "type": "audio/bandcamp"}],
            },
        )


class BandcampFanAdapter(SourceAdapter):
    """Adapter for Bandcamp fan collection/wishlist."""

    @property
    def source_type(self) -> str:
        return "bandcamp_fan"

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc in ("bandcamp.com", "www.bandcamp.com"):
            path = parsed.path.strip("/")
            if path and "/" not in path and path not in ("discover", "feed", "daily"):
                return True
        return False

    def _get_username(self, url: str) -> str:
        parsed = urlparse(url)
        return parsed.path.strip("/")

    def _fetch_fan_data(self, username: str) -> dict:
        url = f"https://bandcamp.com/{username}"

        try:
            response = httpx.get(url, follow_redirects=True, timeout=30.0)
            response.raise_for_status()
            html = response.text
        except httpx.HTTPError as e:
            raise ValueError(f"Failed to fetch fan page: {e}")

        data = {"username": username, "collection_count": 0, "wishlist_count": 0}

        name_match = re.search(r'<span class="name">([^<]+)</span>', html)
        if name_match:
            data["name"] = name_match.group(1).strip()

        avatar_match = re.search(r'<img class="fan-photo"[^>]+src="([^"]+)"', html)
        if avatar_match:
            data["avatar"] = avatar_match.group(1)

        coll_match = re.search(r'collection-count">(\d+)</span>', html)
        if coll_match:
            data["collection_count"] = int(coll_match.group(1))

        wish_match = re.search(r'wishlist-count">(\d+)</span>', html)
        if wish_match:
            data["wishlist_count"] = int(wish_match.group(1))

        return data

    def resolve(self, url: str) -> SourceInfo:
        username = self._get_username(url)
        fan_data = self._fetch_fan_data(username)

        return SourceInfo(
            source_type=self.source_type,
            uri=f"bandcamp:fan:{username}",
            display_name=f"{fan_data.get('name', username)}'s Collection",
            avatar_url=fan_data.get("avatar"),
            metadata={
                "username": username,
                "collection_count": fan_data.get("collection_count", 0),
                "wishlist_count": fan_data.get("wishlist_count", 0),
            },
        )

    def poll(self, source: SourceInfo, since: datetime | None = None) -> list[RawItem]:
        # Fan page scraping requires JavaScript - return empty for now
        return []
