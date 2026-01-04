"""Bandcamp artist/label search provider."""

import re

import httpx

from omnifeed.sources.base import SearchProvider, SourceSuggestion


class BandcampSearchProvider(SearchProvider):
    """Search for Bandcamp artists and labels."""

    @property
    def provider_id(self) -> str:
        return "bandcamp"

    @property
    def source_types(self) -> list[str]:
        return ["bandcamp"]

    async def search(self, query: str, limit: int = 10) -> list[SourceSuggestion]:
        url = "https://bandcamp.com/search"
        params = {"q": query, "item_type": "b"}  # b = bands

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=30.0, follow_redirects=True)
            if response.status_code != 200:
                return []

            html = response.text
            suggestions = []

            # Updated pattern for current Bandcamp HTML structure
            # Matches: <li class="searchresult data-search" ...>...</li>
            result_pattern = re.compile(
                r'<li class="searchresult[^"]*"[^>]*>.*?'
                r'<img[^>]+src="([^"]*)".*?'
                r'<div class="heading">\s*<a href="([^"]+)"[^>]*>\s*([^<]+?)\s*</a>.*?'
                r'(?:<div class="subhead">\s*([^<]*?)\s*</div>)?.*?'
                r'(?:<div class="genre">\s*([^<]*?)\s*</div>)?.*?'
                r'</li>',
                re.DOTALL
            )

            for match in result_pattern.finditer(html):
                if len(suggestions) >= limit:
                    break

                thumbnail = match.group(1)
                artist_url = match.group(2)
                name = match.group(3).strip()
                subhead = match.group(4).strip() if match.group(4) else ""
                genre = match.group(5).strip() if match.group(5) else ""

                # Clean URL by removing tracking params
                clean_url = artist_url.split("?")[0]

                desc_parts = []
                if genre:
                    desc_parts.append(genre)
                if subhead:
                    desc_parts.append(subhead)
                description = " · ".join(desc_parts)

                slug_match = re.match(r"https?://([^.]+)\.bandcamp\.com", clean_url)
                slug = slug_match.group(1) if slug_match else None

                suggestions.append(SourceSuggestion(
                    url=clean_url,
                    name=name,
                    source_type="bandcamp",
                    description=description,
                    thumbnail_url=thumbnail if thumbnail else None,
                    provider=self.provider_id,
                    metadata={"slug": slug, "genre": genre, "location": subhead},
                ))

            return suggestions
