"""RSS feed discovery via Feedly."""

import re

import httpx

from omnifeed.sources.base import SearchProvider, SourceSuggestion


FEEDLY_API_BASE = "https://cloud.feedly.com/v3"


class FeedlySearchProvider(SearchProvider):
    """Search for RSS feeds using Feedly's discovery API."""

    @property
    def provider_id(self) -> str:
        return "feedly"

    @property
    def source_types(self) -> list[str]:
        return ["rss"]

    async def search(self, query: str, limit: int = 10) -> list[SourceSuggestion]:
        url = f"{FEEDLY_API_BASE}/search/feeds"
        params = {"query": query, "count": limit}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=30.0, headers={"User-Agent": "OmniFeed/1.0"})

            if response.status_code != 200:
                return []

            data = response.json()
            suggestions = []

            for result in data.get("results", []):
                feed_id = result.get("feedId", "")
                feed_url = feed_id.replace("feed/", "", 1) if feed_id.startswith("feed/") else ""

                if not feed_url:
                    continue

                title = result.get("title", "")
                description = result.get("description", "")
                website = result.get("website", "")
                subscribers = result.get("subscribers", 0)
                thumbnail = result.get("iconUrl") or result.get("visualUrl")

                desc_parts = []
                if description:
                    desc_parts.append(description[:200])
                if subscribers:
                    desc_parts.append(f"{subscribers:,} subscribers")
                if website and website != feed_url:
                    desc_parts.append(website)

                suggestions.append(SourceSuggestion(
                    url=feed_url,
                    name=title or _extract_domain(feed_url),
                    source_type="rss",
                    description=" · ".join(desc_parts),
                    thumbnail_url=thumbnail,
                    subscriber_count=subscribers,
                    provider=self.provider_id,
                    metadata={
                        "website": website,
                        "feedly_id": feed_id,
                        "velocity": result.get("velocity"),
                    },
                ))

            suggestions.sort(key=lambda s: s.subscriber_count or 0, reverse=True)
            return suggestions[:limit]


def _extract_domain(url: str) -> str:
    match = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return match.group(1) if match else url
