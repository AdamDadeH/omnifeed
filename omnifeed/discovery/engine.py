"""Discovery engine for finding new sources."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from omnifeed.discovery.interests import (
    InterestProfile,
    build_interest_profile,
    generate_queries_from_prompt,
)
from omnifeed.discovery.llm import get_llm_backend
from omnifeed.search.service import get_search_service
from omnifeed.sources.base import SourceSuggestion

if TYPE_CHECKING:
    from omnifeed.store import Store

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryResult:
    """A discovered source with explanation."""
    suggestion: SourceSuggestion
    relevance_score: float  # 0-1, how relevant to user's interests
    explanation: str  # Why this source is recommended
    matched_interests: list[str] = field(default_factory=list)
    from_query: str = ""  # Which query found this


@dataclass
class DiscoveryResponse:
    """Full discovery response."""
    results: list[DiscoveryResult]
    queries_used: list[str]
    interest_profile: InterestProfile | None = None
    mode: str = "prompt"  # "prompt" or "auto"


EXPLAIN_PROMPT = """Given the user's interests and a discovered content source, explain why they might enjoy it.

User interests: {interests}

Discovered source:
- Name: {name}
- Type: {source_type}
- Description: {description}

Write a brief (1-2 sentence) explanation of why this source matches their interests.
Be specific about the connection. If there's no clear connection, say so.

Response (just the explanation, no prefix):"""


class DiscoveryEngine:
    """Engine for discovering new sources based on user interests."""

    def __init__(self, store: "Store"):
        self.store = store
        self._search_service = get_search_service()
        self._llm = None  # Lazy load

    async def discover_from_prompt(
        self,
        prompt: str,
        limit: int = 10,
        platforms: list[str] | None = None,
    ) -> DiscoveryResponse:
        """Discover sources based on user's explicit request.

        Args:
            prompt: What the user is looking for (e.g., "jazz piano tutorials")
            limit: Max results to return
            platforms: Optional filter by platform (youtube, bandcamp, etc.)

        Returns:
            DiscoveryResponse with ranked suggestions
        """
        # Generate search queries from prompt
        query_result = generate_queries_from_prompt(prompt)

        if not query_result:
            # Fall back to using prompt directly
            queries = [prompt]
            platforms = platforms or []
        else:
            queries = query_result.get("queries", [prompt])
            if not platforms:
                platforms = query_result.get("platforms", [])

        # Search across all queries
        all_suggestions: list[tuple[SourceSuggestion, str]] = []
        for query in queries[:5]:  # Limit queries to avoid too many API calls
            suggestions = await self._search_service.search(
                query=query,
                limit=limit,
                provider_ids=platforms if platforms else None,
            )
            for s in suggestions:
                all_suggestions.append((s, query))

        # Dedupe by URL
        seen_urls = set()
        unique: list[tuple[SourceSuggestion, str]] = []
        for s, q in all_suggestions:
            if s.url not in seen_urls:
                seen_urls.add(s.url)
                unique.append((s, q))

        # Filter out sources user already has
        existing_uris = {src.uri for src in self.store.list_sources()}
        # We don't have the URI yet, but we can check by URL pattern
        # This is imperfect but catches obvious dupes
        filtered: list[tuple[SourceSuggestion, str]] = []
        for s, q in unique:
            # Check if any existing source has a similar URL
            is_dupe = any(
                s.url in uri or uri in s.url
                for uri in existing_uris
            )
            if not is_dupe:
                filtered.append((s, q))

        # Score and rank
        results = []
        for suggestion, query in filtered[:limit]:
            # Simple relevance based on query match in name/description
            relevance = self._compute_relevance(suggestion, prompt, queries)

            result = DiscoveryResult(
                suggestion=suggestion,
                relevance_score=relevance,
                explanation=f"Found via search: '{query}'",
                matched_interests=[prompt],
                from_query=query,
            )
            results.append(result)

        # Sort by relevance
        results.sort(key=lambda r: r.relevance_score, reverse=True)

        return DiscoveryResponse(
            results=results[:limit],
            queries_used=queries,
            interest_profile=None,
            mode="prompt",
        )

    async def discover_from_interests(
        self,
        limit: int = 10,
        min_feedback_score: float = 3.0,
    ) -> DiscoveryResponse:
        """Discover sources based on user's engagement history.

        Args:
            limit: Max results to return
            min_feedback_score: Minimum score to consider content as "liked"

        Returns:
            DiscoveryResponse with ranked suggestions
        """
        # Build interest profile from store data
        profile = build_interest_profile(self.store, min_score=min_feedback_score)

        if not profile or not profile.generated_queries:
            return DiscoveryResponse(
                results=[],
                queries_used=[],
                interest_profile=profile,
                mode="auto",
            )

        # Search using generated queries
        all_suggestions: list[tuple[SourceSuggestion, str]] = []
        for query in profile.generated_queries[:5]:
            suggestions = await self._search_service.search(
                query=query,
                limit=limit,
            )
            for s in suggestions:
                all_suggestions.append((s, query))

        # Dedupe
        seen_urls = set()
        unique: list[tuple[SourceSuggestion, str]] = []
        for s, q in all_suggestions:
            if s.url not in seen_urls:
                seen_urls.add(s.url)
                unique.append((s, q))

        # Filter existing sources
        existing_uris = {src.uri for src in self.store.list_sources()}
        filtered: list[tuple[SourceSuggestion, str]] = []
        for s, q in unique:
            is_dupe = any(s.url in uri or uri in s.url for uri in existing_uris)
            if not is_dupe:
                filtered.append((s, q))

        # Build interest string for explanations
        interest_str = ", ".join([i.topic for i in profile.interests[:5]])

        # Score and explain each result
        results = []
        for suggestion, query in filtered[:limit]:
            # Compute relevance to interests
            relevance = self._compute_relevance(
                suggestion,
                interest_str,
                profile.generated_queries,
            )

            # Find which interests match
            matched = []
            for interest in profile.interests:
                if interest.topic.lower() in suggestion.name.lower() or \
                   interest.topic.lower() in suggestion.description.lower():
                    matched.append(interest.topic)

            # Generate explanation using Ollama
            explanation = self._generate_explanation(
                interests=interest_str,
                suggestion=suggestion,
            )

            result = DiscoveryResult(
                suggestion=suggestion,
                relevance_score=relevance,
                explanation=explanation,
                matched_interests=matched,
                from_query=query,
            )
            results.append(result)

        # Sort by relevance
        results.sort(key=lambda r: r.relevance_score, reverse=True)

        return DiscoveryResponse(
            results=results[:limit],
            queries_used=profile.generated_queries,
            interest_profile=profile,
            mode="auto",
        )

    def _compute_relevance(
        self,
        suggestion: SourceSuggestion,
        primary_interest: str,
        queries: list[str],
    ) -> float:
        """Compute relevance score for a suggestion."""
        score = 0.5  # Base score

        name_lower = suggestion.name.lower()
        desc_lower = suggestion.description.lower()

        # Primary interest match
        if primary_interest.lower() in name_lower:
            score += 0.3
        if primary_interest.lower() in desc_lower:
            score += 0.1

        # Query matches
        for query in queries:
            query_words = query.lower().split()
            for word in query_words:
                if len(word) > 3 and word in name_lower:
                    score += 0.05
                if len(word) > 3 and word in desc_lower:
                    score += 0.02

        # Subscriber count as quality signal
        if suggestion.subscriber_count:
            if suggestion.subscriber_count > 1_000_000:
                score += 0.1
            elif suggestion.subscriber_count > 100_000:
                score += 0.05

        return min(1.0, score)

    def _get_llm(self):
        """Lazy load LLM backend."""
        if self._llm is None:
            try:
                self._llm = get_llm_backend()
            except RuntimeError:
                self._llm = False  # No LLM available
        return self._llm if self._llm else None

    def _generate_explanation(
        self,
        interests: str,
        suggestion: SourceSuggestion,
    ) -> str:
        """Generate explanation for why a source is recommended."""
        llm = self._get_llm()
        if not llm:
            return f"Matches your interest in {interests.split(',')[0] if interests else 'this topic'}"

        try:
            prompt = EXPLAIN_PROMPT.format(
                interests=interests,
                name=suggestion.name,
                source_type=suggestion.source_type,
                description=suggestion.description or "No description available",
            )

            explanation = llm.generate(
                prompt=prompt,
                temperature=0.7,
                max_tokens=100,
            )

            return explanation.strip() or f"Related to: {interests}"
        except Exception as e:
            logger.warning(f"Failed to generate explanation: {e}")
            return f"Related to: {interests}"


# Convenience function for sync contexts
def discover_sources(
    store: "Store",
    prompt: str | None = None,
    limit: int = 10,
) -> DiscoveryResponse:
    """Discover sources (sync wrapper).

    Args:
        store: Data store
        prompt: Optional discovery prompt. If None, uses interest profile.
        limit: Max results

    Returns:
        DiscoveryResponse
    """
    engine = DiscoveryEngine(store)

    if prompt:
        return asyncio.run(engine.discover_from_prompt(prompt, limit))
    else:
        return asyncio.run(engine.discover_from_interests(limit))
