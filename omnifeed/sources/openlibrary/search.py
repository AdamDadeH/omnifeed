"""OpenLibrary search provider for discovering authors and books."""

import httpx

from omnifeed.sources.base import SearchProvider, SourceSuggestion


OPENLIBRARY_API_BASE = "https://openlibrary.org"


class OpenLibrarySearchProvider(SearchProvider):
    """Search for authors on OpenLibrary."""

    @property
    def provider_id(self) -> str:
        return "openlibrary"

    @property
    def source_types(self) -> list[str]:
        return ["openlibrary_author", "openlibrary_subject"]

    async def search(self, query: str, limit: int = 10) -> list[SourceSuggestion]:
        """Search OpenLibrary for authors."""
        suggestions = []

        try:
            # Search for authors
            response = httpx.get(
                f"{OPENLIBRARY_API_BASE}/search/authors.json",
                params={
                    "q": query,
                    "limit": min(limit, 10),
                },
                headers={"User-Agent": "OmniFeed/1.0"},
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            for doc in data.get("docs", []):
                author_key = doc.get("key", "")
                author_id = author_key.replace("/authors/", "")
                name = doc.get("name", "Unknown")
                work_count = doc.get("work_count", 0)

                # Get top work for description
                top_work = doc.get("top_work", "")
                description = f"{work_count} works"
                if top_work:
                    description += f" • {top_work}"

                suggestions.append(SourceSuggestion(
                    url=f"https://openlibrary.org/authors/{author_id}",
                    name=name,
                    source_type="openlibrary_author",
                    description=description,
                    thumbnail_url=None,
                    provider="openlibrary",
                    metadata={"author_id": author_id, "work_count": work_count},
                ))

            # Also search for subjects if query looks like a genre
            if len(query.split()) <= 2:
                response = httpx.get(
                    f"{OPENLIBRARY_API_BASE}/search/subjects.json",
                    params={
                        "q": query,
                        "limit": 5,
                    },
                    headers={"User-Agent": "OmniFeed/1.0"},
                    timeout=30.0,
                )
                if response.status_code == 200:
                    data = response.json()
                    for doc in data.get("docs", []):
                        subject = doc.get("key", "").replace("/subjects/", "")
                        name = doc.get("name", subject)
                        work_count = doc.get("work_count", 0)

                        suggestions.append(SourceSuggestion(
                            url=f"https://openlibrary.org/subjects/{subject}",
                            name=f"Subject: {name}",
                            source_type="openlibrary_subject",
                            description=f"{work_count} works",
                            provider="openlibrary",
                            metadata={"subject": subject},
                        ))

        except httpx.HTTPError:
            pass

        return suggestions[:limit]
