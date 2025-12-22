"""RSS/Atom feed adapter."""

import hashlib
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import feedparser
import httpx

from omnifeed.adapters.base import SourceAdapter
from omnifeed.models import SourceInfo, RawItem


def _parse_date(entry: dict[str, Any]) -> datetime:
    """Parse a date from a feed entry."""
    # Try various date fields
    for field in ["published_parsed", "updated_parsed", "created_parsed"]:
        if field in entry and entry[field]:
            try:
                return datetime(*entry[field][:6])
            except (TypeError, ValueError):
                pass

    # Try string fields
    for field in ["published", "updated", "created"]:
        if field in entry and entry[field]:
            try:
                return parsedate_to_datetime(entry[field])
            except (TypeError, ValueError):
                pass

    # Fallback to now
    return datetime.utcnow()


def _extract_text(html: str) -> str:
    """Extract plain text from HTML content."""
    # Simple HTML tag removal
    text = re.sub(r"<[^>]+>", "", html)
    # Decode common entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _generate_entry_id(entry: dict[str, Any], feed_url: str) -> str:
    """Generate a stable ID for a feed entry."""
    # Prefer entry's own ID
    if entry.get("id"):
        return entry["id"]

    # Fall back to link
    if entry.get("link"):
        return entry["link"]

    # Last resort: hash of title + feed URL
    title = entry.get("title", "")
    content = f"{feed_url}:{title}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


class RSSAdapter(SourceAdapter):
    """Adapter for RSS and Atom feeds."""

    @property
    def source_type(self) -> str:
        return "rss"

    def can_handle(self, url: str) -> bool:
        """Check if URL looks like an RSS feed."""
        parsed = urlparse(url)

        # Must be http(s)
        if parsed.scheme not in ("http", "https"):
            return False

        # Check for common feed indicators in path
        path = parsed.path.lower()
        if any(
            indicator in path
            for indicator in ["/feed", "/rss", "/atom", ".xml", ".rss", ".atom"]
        ):
            return True

        # Check for common feed query parameters
        if "feed" in parsed.query.lower() or "rss" in parsed.query.lower():
            return True

        # Try to fetch and detect content type
        # For now, be permissive - will validate on resolve
        return True

    def resolve(self, url: str) -> SourceInfo:
        """Fetch and parse the feed to extract metadata."""
        # Fetch the feed
        try:
            response = httpx.get(url, follow_redirects=True, timeout=30.0)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise ValueError(f"Failed to fetch feed: {e}")

        # Parse with feedparser
        feed = feedparser.parse(response.content)

        if feed.bozo and not feed.entries:
            raise ValueError(f"Invalid feed: {feed.bozo_exception}")

        # Extract feed metadata
        feed_info = feed.feed
        title = feed_info.get("title", urlparse(url).netloc)
        description = feed_info.get("description", feed_info.get("subtitle", ""))

        # Try to find an image/icon
        avatar_url = None
        if feed_info.get("image"):
            avatar_url = feed_info.image.get("href") or feed_info.image.get("url")
        elif feed_info.get("icon"):
            avatar_url = feed_info.icon

        # Store the final URL (after redirects)
        final_url = str(response.url)

        return SourceInfo(
            source_type=self.source_type,
            uri=final_url,
            display_name=_extract_text(title),
            avatar_url=avatar_url,
            metadata={
                "description": _extract_text(description) if description else None,
                "link": feed_info.get("link"),
                "language": feed_info.get("language"),
                "generator": feed_info.get("generator"),
            },
        )

    def poll(self, source: SourceInfo, since: datetime | None = None) -> list[RawItem]:
        """Fetch entries from the feed."""
        # Fetch the feed
        try:
            response = httpx.get(source.uri, follow_redirects=True, timeout=30.0)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise ValueError(f"Failed to fetch feed: {e}")

        # Parse with feedparser
        feed = feedparser.parse(response.content)

        items = []
        for entry in feed.entries:
            published_at = _parse_date(entry)

            # Skip items older than since
            if since and published_at <= since:
                continue

            # Extract content
            content = ""
            if entry.get("content"):
                content = entry.content[0].get("value", "")
            elif entry.get("summary"):
                content = entry.summary
            elif entry.get("description"):
                content = entry.description

            # Extract author
            author = entry.get("author", "")
            if not author and entry.get("authors"):
                author = entry.authors[0].get("name", "")
            if not author:
                author = feed.feed.get("author", source.display_name)

            # Extract media (images, enclosures)
            thumbnail = None
            enclosures = []

            if entry.get("media_thumbnail"):
                thumbnail = entry.media_thumbnail[0].get("url")

            if entry.get("enclosures"):
                for enc in entry.enclosures:
                    enclosures.append({
                        "url": enc.get("href") or enc.get("url"),
                        "type": enc.get("type"),
                        "length": enc.get("length"),
                    })

            # Look for image in content
            if not thumbnail and content:
                img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content)
                if img_match:
                    thumbnail = img_match.group(1)

            raw_item = RawItem(
                external_id=_generate_entry_id(entry, source.uri),
                url=entry.get("link", ""),
                title=_extract_text(entry.get("title", "Untitled")),
                published_at=published_at,
                raw_metadata={
                    "author": author,
                    "content_html": content,
                    "content_text": _extract_text(content) if content else None,
                    "thumbnail": thumbnail,
                    "enclosures": enclosures,
                    "tags": [tag.get("term") for tag in entry.get("tags", []) if tag.get("term")],
                    "comments_url": entry.get("comments"),
                },
            )
            items.append(raw_item)

        return items
