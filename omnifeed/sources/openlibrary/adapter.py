"""OpenLibrary adapter for author works and book editions."""

import re
from datetime import datetime
from urllib.parse import urlparse

import httpx

from omnifeed.sources.base import SourceAdapter, SourceInfo, RawItem


OPENLIBRARY_API_BASE = "https://openlibrary.org"


class OpenLibraryAuthorAdapter(SourceAdapter):
    """Adapter for OpenLibrary author works.

    Follows new works by an author.
    """

    @property
    def source_type(self) -> str:
        return "openlibrary_author"

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc in ("openlibrary.org", "www.openlibrary.org"):
            if "/authors/" in parsed.path:
                return True
        return False

    def _extract_author_id(self, url: str) -> str:
        """Extract author ID from OpenLibrary URL.

        Format: /authors/OL123A or /authors/OL123A/Author-Name
        """
        match = re.search(r"/authors/(OL\d+A)", url)
        if match:
            return match.group(1)
        raise ValueError(f"Could not extract author ID from URL: {url}")

    def _api_request(self, endpoint: str) -> dict:
        """Make API request to OpenLibrary."""
        response = httpx.get(
            f"{OPENLIBRARY_API_BASE}{endpoint}",
            headers={"User-Agent": "OmniFeed/1.0"},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()

    def resolve(self, url: str) -> SourceInfo:
        author_id = self._extract_author_id(url)
        data = self._api_request(f"/authors/{author_id}.json")

        name = data.get("name", f"Author {author_id}")

        # Get author photo
        photos = data.get("photos", [])
        avatar_url = None
        if photos:
            photo_id = photos[0] if isinstance(photos[0], int) else photos[0].get("id")
            if photo_id and photo_id > 0:
                avatar_url = f"https://covers.openlibrary.org/a/id/{photo_id}-M.jpg"

        # Get bio
        bio = data.get("bio")
        if isinstance(bio, dict):
            bio = bio.get("value", "")
        elif not isinstance(bio, str):
            bio = ""

        return SourceInfo(
            source_type=self.source_type,
            uri=f"openlibrary:author:{author_id}",
            display_name=name,
            avatar_url=avatar_url,
            metadata={
                "author_id": author_id,
                "bio": bio[:500] if bio else "",
                "birth_date": data.get("birth_date"),
                "death_date": data.get("death_date"),
                "openlibrary_url": f"https://openlibrary.org/authors/{author_id}",
            },
        )

    def poll(self, source: SourceInfo, since: datetime | None = None) -> list[RawItem]:
        author_id = source.metadata.get("author_id")
        if not author_id:
            uri = source.uri
            if uri.startswith("openlibrary:author:"):
                author_id = uri.replace("openlibrary:author:", "")
            elif "openlibrary.org" in uri:
                author_id = self._extract_author_id(uri)
            else:
                author_id = uri

        # Get author's works
        data = self._api_request(f"/authors/{author_id}/works.json?limit=50")

        items = []
        for work in data.get("entries", []):
            work_id = work.get("key", "").replace("/works/", "")

            # Parse created date
            created = work.get("created", {})
            if isinstance(created, dict):
                date_str = created.get("value", "")
            else:
                date_str = str(created) if created else ""

            try:
                published_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                published_at = published_at.replace(tzinfo=None)
            except (ValueError, TypeError):
                published_at = datetime.now()

            if since and published_at <= since:
                continue

            title = work.get("title", "Untitled")

            # Get cover
            covers = work.get("covers", [])
            thumbnail = None
            if covers:
                cover_id = covers[0]
                if cover_id and cover_id > 0:
                    thumbnail = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"

            # Get description
            description = work.get("description")
            if isinstance(description, dict):
                description = description.get("value", "")
            elif not isinstance(description, str):
                description = ""

            # Get subjects
            subjects = work.get("subjects", [])
            if subjects:
                subjects = subjects[:10]  # Limit

            # Build content text
            content_parts = [title, f"by {source.display_name}"]
            if description:
                content_parts.append(description[:500])
            if subjects:
                content_parts.append(f"Subjects: {', '.join(subjects)}")

            raw_item = RawItem(
                external_id=f"openlibrary:work:{work_id}",
                url=f"https://openlibrary.org/works/{work_id}",
                title=title,
                published_at=published_at,
                raw_metadata={
                    "author": source.display_name,
                    "content_text": " | ".join(content_parts),
                    "description": description[:500] if description else "",
                    "thumbnail": thumbnail,
                    "work_id": work_id,
                    "subjects": subjects,
                    "first_publish_year": work.get("first_publish_date"),
                    "openlibrary_url": f"https://openlibrary.org/works/{work_id}",
                },
            )
            items.append(raw_item)

        return items


class OpenLibrarySubjectAdapter(SourceAdapter):
    """Adapter for OpenLibrary subject feeds.

    Follows new works in a subject/genre.
    """

    @property
    def source_type(self) -> str:
        return "openlibrary_subject"

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc in ("openlibrary.org", "www.openlibrary.org"):
            if "/subjects/" in parsed.path:
                return True
        return False

    def _extract_subject(self, url: str) -> str:
        match = re.search(r"/subjects/([^/?]+)", url)
        if match:
            return match.group(1)
        raise ValueError(f"Could not extract subject from URL: {url}")

    def _api_request(self, endpoint: str) -> dict:
        response = httpx.get(
            f"{OPENLIBRARY_API_BASE}{endpoint}",
            headers={"User-Agent": "OmniFeed/1.0"},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()

    def resolve(self, url: str) -> SourceInfo:
        subject = self._extract_subject(url)
        data = self._api_request(f"/subjects/{subject}.json?limit=1")

        name = data.get("name", subject.replace("_", " ").title())
        work_count = data.get("work_count", 0)

        return SourceInfo(
            source_type=self.source_type,
            uri=f"openlibrary:subject:{subject}",
            display_name=f"Books: {name}",
            avatar_url=None,
            metadata={
                "subject": subject,
                "work_count": work_count,
                "openlibrary_url": f"https://openlibrary.org/subjects/{subject}",
            },
        )

    def poll(self, source: SourceInfo, since: datetime | None = None) -> list[RawItem]:
        subject = source.metadata.get("subject")
        if not subject:
            uri = source.uri
            if uri.startswith("openlibrary:subject:"):
                subject = uri.replace("openlibrary:subject:", "")
            elif "openlibrary.org" in uri:
                subject = self._extract_subject(uri)
            else:
                subject = uri

        data = self._api_request(f"/subjects/{subject}.json?limit=50")

        items = []
        for work in data.get("works", []):
            work_key = work.get("key", "")
            work_id = work_key.replace("/works/", "")

            # Use first_publish_year as approximate date
            year = work.get("first_publish_year")
            if year:
                try:
                    published_at = datetime(int(year), 1, 1)
                except (ValueError, TypeError):
                    published_at = datetime.now()
            else:
                published_at = datetime.now()

            if since and published_at <= since:
                continue

            title = work.get("title", "Untitled")
            authors = work.get("authors", [])
            author_names = [a.get("name", "") for a in authors if a.get("name")]
            author = ", ".join(author_names) if author_names else "Unknown"

            # Get cover
            cover_id = work.get("cover_id")
            thumbnail = None
            if cover_id and cover_id > 0:
                thumbnail = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"

            raw_item = RawItem(
                external_id=f"openlibrary:work:{work_id}",
                url=f"https://openlibrary.org/works/{work_id}",
                title=title,
                published_at=published_at,
                raw_metadata={
                    "author": author,
                    "content_text": f"{title} by {author}",
                    "thumbnail": thumbnail,
                    "work_id": work_id,
                    "first_publish_year": year,
                    "subject": source.metadata.get("subject"),
                },
            )
            items.append(raw_item)

        return items
