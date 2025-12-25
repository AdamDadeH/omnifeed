"""Sitemap adapter for harvesting links from website sitemaps.

Supports config-driven content extraction from pages using selectors.
"""

import gzip
import html
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urljoin

import httpx

from omnifeed.sources.base import SourceAdapter, SourceInfo, RawItem

logger = logging.getLogger(__name__)

# Sitemap XML namespaces
SITEMAP_NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
}

# Default selectors for common patterns
DEFAULT_SELECTORS = {
    "title": "og:title",
    "description": "og:description",
    "image": "og:image",
    "author": None,  # Site-specific
}


class SitemapAdapter(SourceAdapter):
    """Adapter for website sitemaps.

    Harvests URLs from sitemap.xml files and creates items for each matching URL.
    Supports config-driven content extraction using selectors.

    URL format for adding:
        sitemap:<sitemap_url>?pattern=<url_pattern>

    Examples:
        sitemap:https://example.com/sitemap.xml?pattern=/articles/
        sitemap:https://example.com/sitemap.xml?pattern=/blog/\\d{4}/

    With config file at ~/.omnifeed/sitemap_configs/<domain>.json:
    {
        "selectors": {
            "title": "og:title",
            "description": "og:description",
            "image": "og:image",
            "author": "div.byline"
        },
        "fetch_content": true,
        "max_items": 1000
    }
    """

    def __init__(self, request_delay: float = 0.5, config_dir: Path | None = None):
        """Initialize adapter.

        Args:
            request_delay: Seconds to wait between requests (rate limiting)
            config_dir: Directory for site-specific configs
        """
        self.request_delay = request_delay
        self._last_request_time = 0.0
        self.config_dir = config_dir or Path("~/.omnifeed/sitemap_configs").expanduser()
        self._config_cache: dict[str, dict] = {}

    @property
    def source_type(self) -> str:
        return "sitemap"

    def can_handle(self, url: str) -> bool:
        # Handle sitemap: protocol
        if url.startswith("sitemap:"):
            return True
        # Handle direct sitemap.xml URLs
        parsed = urlparse(url)
        if parsed.path.endswith("sitemap.xml") or "sitemap" in parsed.path:
            return True
        return False

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self._last_request_time = time.time()

    def _fetch(self, url: str) -> httpx.Response:
        """Fetch URL with rate limiting."""
        self._rate_limit()
        response = httpx.get(
            url,
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": "OmniFeed/1.0 (sitemap crawler)"},
        )
        response.raise_for_status()
        return response

    def _fetch_sitemap_content(self, url: str) -> bytes:
        """Fetch sitemap content, handling gzip if needed."""
        response = self._fetch(url)
        content = response.content

        # Handle gzipped sitemaps
        if url.endswith(".gz") or response.headers.get("content-encoding") == "gzip":
            try:
                content = gzip.decompress(content)
            except gzip.BadGzipFile:
                pass  # Not actually gzipped

        return content

    def _parse_sitemap_url(self, url: str) -> tuple[str, str | None]:
        """Parse sitemap URL and extract pattern filter.

        Returns:
            (sitemap_url, url_pattern)
        """
        if url.startswith("sitemap:"):
            url = url[8:]  # Remove "sitemap:" prefix

        # Check for pattern parameter
        if "?pattern=" in url:
            sitemap_url, pattern = url.split("?pattern=", 1)
            return sitemap_url, pattern

        return url, None

    def _parse_sitemap(self, content: bytes) -> tuple[list[str], list[dict]]:
        """Parse sitemap XML content.

        Returns:
            (child_sitemaps, url_entries)
            - child_sitemaps: URLs of nested sitemaps (for sitemap index files)
            - url_entries: List of {loc, lastmod} dicts
        """
        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            logger.error(f"Failed to parse sitemap XML: {e}")
            return [], []

        child_sitemaps = []
        url_entries = []

        # Handle sitemap index files
        for sitemap in root.findall(".//sm:sitemap", SITEMAP_NS):
            loc = sitemap.find("sm:loc", SITEMAP_NS)
            if loc is not None and loc.text:
                child_sitemaps.append(loc.text.strip())

        # Handle regular sitemap entries
        for url_elem in root.findall(".//sm:url", SITEMAP_NS):
            loc = url_elem.find("sm:loc", SITEMAP_NS)
            if loc is None or not loc.text:
                continue

            entry = {"loc": loc.text.strip()}

            lastmod = url_elem.find("sm:lastmod", SITEMAP_NS)
            if lastmod is not None and lastmod.text:
                entry["lastmod"] = lastmod.text.strip()

            url_entries.append(entry)

        return child_sitemaps, url_entries

    def _get_site_config(self, domain: str) -> dict[str, Any]:
        """Load site-specific config if it exists."""
        if domain in self._config_cache:
            return self._config_cache[domain]

        config = {"selectors": DEFAULT_SELECTORS.copy(), "fetch_content": True}

        config_path = self.config_dir / f"{domain}.json"
        if config_path.exists():
            try:
                with open(config_path) as f:
                    site_config = json.load(f)
                    config.update(site_config)
                    if "selectors" in site_config:
                        config["selectors"] = {**DEFAULT_SELECTORS, **site_config["selectors"]}
                logger.info(f"Loaded config for {domain}: {config_path}")
            except Exception as e:
                logger.warning(f"Failed to load config for {domain}: {e}")

        self._config_cache[domain] = config
        return config

    def _extract_meta(self, html_content: str, property_name: str) -> str | None:
        """Extract content from meta tag by property or name."""
        # Try property="X"
        match = re.search(
            rf'<meta\s+[^>]*property=["\'](?:og:)?{re.escape(property_name)}["\'][^>]*content=["\']([^"\']+)["\']',
            html_content,
            re.IGNORECASE,
        )
        if match:
            return html.unescape(match.group(1).strip())

        # Try content before property
        match = re.search(
            rf'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*property=["\'](?:og:)?{re.escape(property_name)}["\']',
            html_content,
            re.IGNORECASE,
        )
        if match:
            return html.unescape(match.group(1).strip())

        # Try name="X"
        match = re.search(
            rf'<meta\s+[^>]*name=["\'](?:og:)?{re.escape(property_name)}["\'][^>]*content=["\']([^"\']+)["\']',
            html_content,
            re.IGNORECASE,
        )
        if match:
            return html.unescape(match.group(1).strip())

        return None

    def _extract_by_selector(self, html_content: str, selector: str) -> str | None:
        """Extract text content using a simple selector.

        Supported selector formats:
        - "og:title" or "title" -> meta property
        - "div.classname" -> first div with that class
        - ".classname" -> first element with that class
        """
        if not selector:
            return None

        # Meta tag selector (og:X or just X for common meta)
        if ":" in selector or selector in ("title", "description", "author"):
            return self._extract_meta(html_content, selector.replace("og:", ""))

        # CSS class selector: div.classname or .classname
        if "." in selector:
            parts = selector.split(".", 1)
            tag = parts[0] if parts[0] else r"\w+"
            classname = re.escape(parts[1])

            # Match element with class
            pattern = rf'<{tag}[^>]*class=["\'][^"\']*\b{classname}\b[^"\']*["\'][^>]*>(.*?)</{tag}>'
            match = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL)
            if match:
                # Strip HTML tags from content
                content = re.sub(r"<[^>]+>", " ", match.group(1))
                content = html.unescape(content)
                content = re.sub(r"\s+", " ", content).strip()
                return content if content else None

        return None

    def _extract_page_content(
        self, url: str, html_content: str, selectors: dict[str, str | None]
    ) -> dict[str, str | None]:
        """Extract content from page using configured selectors."""
        result = {}
        for field, selector in selectors.items():
            if selector:
                result[field] = self._extract_by_selector(html_content, selector)
            else:
                result[field] = None
        return result

    def _collect_urls(
        self, sitemap_url: str, pattern: str | None, max_sitemaps: int = 50
    ) -> list[dict]:
        """Recursively collect URLs from sitemap(s).

        Args:
            sitemap_url: Root sitemap URL
            pattern: Regex pattern to filter URLs (optional)
            max_sitemaps: Maximum number of child sitemaps to process

        Returns:
            List of {loc, lastmod} dicts for matching URLs
        """
        all_entries = []
        sitemaps_to_process = [sitemap_url]
        processed_sitemaps = set()

        pattern_re = re.compile(pattern) if pattern else None

        while sitemaps_to_process and len(processed_sitemaps) < max_sitemaps:
            current_url = sitemaps_to_process.pop(0)
            if current_url in processed_sitemaps:
                continue

            logger.info(f"Fetching sitemap: {current_url}")
            try:
                content = self._fetch_sitemap_content(current_url)
                child_sitemaps, url_entries = self._parse_sitemap(content)

                # Add child sitemaps to queue
                for child in child_sitemaps:
                    if child not in processed_sitemaps:
                        sitemaps_to_process.append(child)

                # Filter and collect URLs
                for entry in url_entries:
                    if pattern_re is None or pattern_re.search(entry["loc"]):
                        all_entries.append(entry)

                processed_sitemaps.add(current_url)
                logger.info(
                    f"Found {len(url_entries)} URLs, {len(child_sitemaps)} child sitemaps"
                )

            except httpx.HTTPError as e:
                logger.warning(f"Failed to fetch sitemap {current_url}: {e}")
                processed_sitemaps.add(current_url)

        return all_entries

    def resolve(self, url: str) -> SourceInfo:
        sitemap_url, pattern = self._parse_sitemap_url(url)

        # Fetch sitemap to validate and get info
        try:
            response = self._fetch(sitemap_url)
        except httpx.HTTPError as e:
            raise ValueError(f"Failed to fetch sitemap: {e}")

        child_sitemaps, url_entries = self._parse_sitemap(response.content)

        # Get domain for display name
        parsed = urlparse(sitemap_url)
        domain = parsed.netloc.replace("www.", "")

        # Count matching URLs (sample)
        if pattern:
            pattern_re = re.compile(pattern)
            matching = sum(1 for e in url_entries if pattern_re.search(e["loc"]))
        else:
            matching = len(url_entries)

        description = f"{matching} URLs"
        if child_sitemaps:
            description += f" + {len(child_sitemaps)} sub-sitemaps"
        if pattern:
            description += f" (pattern: {pattern})"

        return SourceInfo(
            source_type=self.source_type,
            uri=f"sitemap:{sitemap_url}" + (f"?pattern={pattern}" if pattern else ""),
            display_name=f"{domain} (sitemap)",
            avatar_url=f"https://www.google.com/s2/favicons?domain={parsed.netloc}&sz=128",
            metadata={
                "sitemap_url": sitemap_url,
                "pattern": pattern,
                "domain": parsed.netloc,
                "child_sitemap_count": len(child_sitemaps),
                "sample_url_count": len(url_entries),
            },
        )

    def poll(self, source: SourceInfo, since: datetime | None = None) -> list[RawItem]:
        sitemap_url = source.metadata.get("sitemap_url")
        pattern = source.metadata.get("pattern")

        if not sitemap_url:
            # Parse from URI
            sitemap_url, pattern = self._parse_sitemap_url(source.uri)

        # Get domain and config
        parsed_sitemap = urlparse(sitemap_url)
        domain = parsed_sitemap.netloc.replace("www.", "")
        config = self._get_site_config(domain)
        selectors = config.get("selectors", DEFAULT_SELECTORS)
        fetch_content = config.get("fetch_content", True)
        max_items = config.get("max_items", 5000)

        # Collect all matching URLs
        entries = self._collect_urls(sitemap_url, pattern)
        logger.info(f"Collected {len(entries)} URLs from sitemap")

        # Sort by lastmod (newest first) and limit
        entries.sort(key=lambda e: e.get("lastmod", ""), reverse=True)
        entries = entries[:max_items]

        items = []
        for i, entry in enumerate(entries):
            url = entry["loc"]

            # Parse lastmod date
            published_at = datetime.utcnow()
            if entry.get("lastmod"):
                try:
                    lastmod = entry["lastmod"]
                    if "T" in lastmod:
                        published_at = datetime.fromisoformat(
                            lastmod.replace("Z", "+00:00")
                        )
                        published_at = published_at.replace(tzinfo=None)
                    else:
                        published_at = datetime.strptime(lastmod, "%Y-%m-%d")
                except ValueError:
                    pass

            # Skip if older than since
            if since and published_at <= since:
                continue

            # Default: generate title from URL path
            parsed_url = urlparse(url)
            path_parts = [p for p in parsed_url.path.split("/") if p]
            title = path_parts[-1] if path_parts else parsed_url.netloc
            title = title.replace("-", " ").replace("_", " ")
            title = re.sub(r"\.(html?|php|aspx?)$", "", title, flags=re.IGNORECASE)
            title = title.title()

            description = None
            image = None
            author = domain

            # Fetch page content if configured
            if fetch_content:
                try:
                    response = self._fetch(url)
                    html_content = response.text

                    extracted = self._extract_page_content(url, html_content, selectors)

                    if extracted.get("title"):
                        title = extracted["title"]
                    if extracted.get("description"):
                        description = extracted["description"]
                    if extracted.get("image"):
                        image = extracted["image"]
                    if extracted.get("author"):
                        author = extracted["author"]

                    if (i + 1) % 50 == 0:
                        logger.info(f"Fetched {i + 1}/{len(entries)} pages")

                except Exception as e:
                    logger.warning(f"Failed to fetch {url}: {e}")

            raw_item = RawItem(
                external_id=url,
                url=url,
                title=title,
                published_at=published_at,
                raw_metadata={
                    "author": author,
                    "content_text": description,
                    "thumbnail": image,
                    "lastmod": entry.get("lastmod"),
                    "needs_content_fetch": True,  # Tells UI to use iframe renderer
                },
            )
            items.append(raw_item)

        logger.info(f"Created {len(items)} items from sitemap")
        return items
