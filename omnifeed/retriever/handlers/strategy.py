"""Exploration Strategy handler.

Strategies are the scorable, swappable methods for discovering new sources.
Each strategy represents a specific QUERY/PROMPT CONSTRUCTION METHOD, not
just a provider. This means we can have multiple YouTube strategies (each
with different query building logic) and multiple LLM strategies (each with
different prompt construction methods).

URI format:
- strategy:{provider}:{method}

Examples:
- strategy:youtube:trending_topic    - YouTube search using trending modifiers
- strategy:youtube:deep_cuts         - YouTube search for obscure/niche content
- strategy:youtube:similar_to_liked  - YouTube search based on liked channels
- strategy:llm:interest_expansion    - LLM expands on your interests
- strategy:llm:similar_creators      - LLM finds similar creators
- strategy:llm:contrast_exploration  - LLM suggests contrasting content
- strategy:rss:topic_feeds           - RSS aggregator topic search

Each strategy is ONE retriever that gets scored based on the quality
of sources it discovers over time. The key insight is that different
query/prompt construction methods will have different effectiveness,
so they need to be scored independently.
"""

import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from omnifeed.retriever.types import (
    Retriever,
    RetrieverKind,
    RetrievalContext,
    RetrievalResult,
)
from omnifeed.retriever.handlers.base import RetrieverHandler
from omnifeed.sources.registry import get_registry
from omnifeed.sources.base import SourceSuggestion

logger = logging.getLogger(__name__)


@dataclass
class StrategyInvocation:
    """Parameters for a strategy invocation."""
    topic: str | None = None
    context_items: list[dict] | None = None  # High-rated content for LLM context
    max_results: int = 10


@dataclass
class StrategyResult:
    """Result from a strategy invocation."""
    suggestions: list[SourceSuggestion]
    strategy_id: str
    query_used: str | None = None
    metadata: dict | None = None


class ExplorationStrategy(ABC):
    """Base class for exploration strategies.

    Each strategy represents a specific query/prompt construction method.
    The strategy itself gets scored based on the quality of sources it discovers.

    Strategy IDs follow the format: {provider}:{method}
    """

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Unique identifier: {provider}:{method} (e.g., 'youtube:trending_topic')."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name (e.g., 'YouTube Trending Topics')."""
        pass

    @property
    def description(self) -> str:
        """Description of how this strategy works."""
        return ""

    @property
    def provider(self) -> str:
        """Provider component of strategy ID (e.g., 'youtube', 'llm', 'rss')."""
        return self.strategy_id.split(":")[0]

    @property
    def method(self) -> str:
        """Method component of strategy ID (e.g., 'trending_topic', 'interest_expansion')."""
        parts = self.strategy_id.split(":", 1)
        return parts[1] if len(parts) > 1 else "default"

    @abstractmethod
    async def discover(self, invocation: StrategyInvocation) -> StrategyResult:
        """Execute the strategy and return discovered sources."""
        pass


# =============================================================================
# YouTube Strategies - Different query construction methods
# =============================================================================


class BaseYouTubeStrategy(ExplorationStrategy):
    """Base class for YouTube strategies with shared helpers."""

    # Default sample topics - subclasses can override
    SAMPLE_TOPICS = ["jazz", "programming", "physics", "philosophy", "design", "cooking"]

    def _get_youtube_provider(self, registry):
        """Find the YouTube search provider."""
        for provider in registry.search_providers:
            if "youtube" in provider.provider_id.lower():
                return provider
        return None

    def _sample_topics(self) -> list[str]:
        """Get sample topics for random exploration."""
        return self.SAMPLE_TOPICS


class YouTubeTrendingTopicStrategy(BaseYouTubeStrategy):
    """YouTube search using trending/popular modifiers."""

    @property
    def strategy_id(self) -> str:
        return "youtube:trending_topic"

    @property
    def display_name(self) -> str:
        return "YouTube Trending Topics"

    @property
    def description(self) -> str:
        return "Searches YouTube with trending/popular modifiers for mainstream content"

    async def discover(self, invocation: StrategyInvocation) -> StrategyResult:
        registry = get_registry()
        youtube_provider = self._get_youtube_provider(registry)

        if not youtube_provider:
            return StrategyResult(suggestions=[], strategy_id=self.strategy_id)

        topic = invocation.topic or random.choice(self._sample_topics())
        # Add trending modifiers
        query = f"{topic} popular best 2024"

        try:
            suggestions = await youtube_provider.search(query=query, limit=invocation.max_results)
            return StrategyResult(
                suggestions=suggestions,
                strategy_id=self.strategy_id,
                query_used=query,
            )
        except Exception as e:
            logger.error(f"YouTube trending search failed: {e}")
            return StrategyResult(suggestions=[], strategy_id=self.strategy_id, query_used=query)


class YouTubeDeepCutsStrategy(BaseYouTubeStrategy):
    """YouTube search for obscure/niche content."""

    SAMPLE_TOPICS = ["ambient music", "mathematics", "film theory", "vintage computing"]

    @property
    def strategy_id(self) -> str:
        return "youtube:deep_cuts"

    @property
    def display_name(self) -> str:
        return "YouTube Deep Cuts"

    @property
    def description(self) -> str:
        return "Searches YouTube for obscure, niche, or underrated content"

    async def discover(self, invocation: StrategyInvocation) -> StrategyResult:
        registry = get_registry()
        youtube_provider = self._get_youtube_provider(registry)

        if not youtube_provider:
            return StrategyResult(suggestions=[], strategy_id=self.strategy_id)

        topic = invocation.topic or random.choice(self._sample_topics())
        # Add obscure/niche modifiers
        modifiers = ["underrated", "hidden gem", "unknown", "obscure", "deep dive"]
        modifier = random.choice(modifiers)
        query = f"{topic} {modifier}"

        try:
            suggestions = await youtube_provider.search(query=query, limit=invocation.max_results)
            return StrategyResult(
                suggestions=suggestions,
                strategy_id=self.strategy_id,
                query_used=query,
            )
        except Exception as e:
            logger.error(f"YouTube deep cuts search failed: {e}")
            return StrategyResult(suggestions=[], strategy_id=self.strategy_id, query_used=query)


# =============================================================================
# RSS Strategies
# =============================================================================


class RSSTopicFeedsStrategy(ExplorationStrategy):
    """RSS aggregator topic-based search."""

    @property
    def strategy_id(self) -> str:
        return "rss:topic_feeds"

    @property
    def display_name(self) -> str:
        return "RSS Topic Feeds"

    @property
    def description(self) -> str:
        return "Searches RSS aggregators and directories for topic-relevant feeds"

    async def discover(self, invocation: StrategyInvocation) -> StrategyResult:
        registry = get_registry()
        rss_providers = [
            p for p in registry.search_providers
            if "rss" in p.provider_id.lower() or "feed" in p.provider_id.lower()
        ]

        if not rss_providers:
            return StrategyResult(suggestions=[], strategy_id=self.strategy_id)

        topic = invocation.topic or "technology"
        all_suggestions = []

        for provider in rss_providers:
            try:
                suggestions = await provider.search(
                    query=topic,
                    limit=invocation.max_results // len(rss_providers) + 1,
                )
                all_suggestions.extend(suggestions)
            except Exception as e:
                logger.error(f"RSS search failed for {provider.provider_id}: {e}")

        return StrategyResult(
            suggestions=all_suggestions[:invocation.max_results],
            strategy_id=self.strategy_id,
            query_used=topic,
        )


# =============================================================================
# Bandcamp Strategies
# =============================================================================


class BandcampGenreStrategy(ExplorationStrategy):
    """Bandcamp genre-based discovery."""

    @property
    def strategy_id(self) -> str:
        return "bandcamp:genre_explore"

    @property
    def display_name(self) -> str:
        return "Bandcamp Genre Explorer"

    @property
    def description(self) -> str:
        return "Discovers new artists and labels on Bandcamp by genre"

    async def discover(self, invocation: StrategyInvocation) -> StrategyResult:
        registry = get_registry()
        bandcamp_provider = None
        for p in registry.search_providers:
            if "bandcamp" in p.provider_id.lower():
                bandcamp_provider = p
                break

        if not bandcamp_provider:
            return StrategyResult(suggestions=[], strategy_id=self.strategy_id)

        genres = ["electronic", "ambient", "jazz", "experimental", "classical", "post-rock"]
        topic = invocation.topic or random.choice(genres)

        try:
            suggestions = await bandcamp_provider.search(query=topic, limit=invocation.max_results)
            return StrategyResult(
                suggestions=suggestions,
                strategy_id=self.strategy_id,
                query_used=topic,
            )
        except Exception as e:
            logger.error(f"Bandcamp genre search failed: {e}")
            return StrategyResult(suggestions=[], strategy_id=self.strategy_id, query_used=topic)


# =============================================================================
# Qobuz Strategies (High-Quality Audio)
# =============================================================================


class QobuzDiscoveryStrategy(ExplorationStrategy):
    """Qobuz high-quality audio discovery."""

    @property
    def strategy_id(self) -> str:
        return "qobuz:discovery"

    @property
    def display_name(self) -> str:
        return "Qobuz Hi-Res Discovery"

    @property
    def description(self) -> str:
        return "Discovers high-quality audio releases on Qobuz"

    async def discover(self, invocation: StrategyInvocation) -> StrategyResult:
        registry = get_registry()
        qobuz_provider = None
        for p in registry.search_providers:
            if "qobuz" in p.provider_id.lower():
                qobuz_provider = p
                break

        if not qobuz_provider:
            return StrategyResult(suggestions=[], strategy_id=self.strategy_id)

        # Music-focused search terms
        topics = ["piano", "orchestra", "quartet", "acoustic", "vinyl"]
        topic = invocation.topic or random.choice(topics)

        try:
            suggestions = await qobuz_provider.search(query=topic, limit=invocation.max_results)
            return StrategyResult(
                suggestions=suggestions,
                strategy_id=self.strategy_id,
                query_used=topic,
            )
        except Exception as e:
            logger.error(f"Qobuz search failed: {e}")
            return StrategyResult(suggestions=[], strategy_id=self.strategy_id, query_used=topic)


# =============================================================================
# RSS/Blog Strategies
# =============================================================================


class RSSBlogDiscoveryStrategy(ExplorationStrategy):
    """RSS blog and news feed discovery."""

    @property
    def strategy_id(self) -> str:
        return "rss:blog_discovery"

    @property
    def display_name(self) -> str:
        return "RSS Blog Discovery"

    @property
    def description(self) -> str:
        return "Discovers interesting blogs and news feeds via RSS"

    async def discover(self, invocation: StrategyInvocation) -> StrategyResult:
        registry = get_registry()
        rss_providers = [
            p for p in registry.search_providers
            if "rss" in p.provider_id.lower() or "feed" in p.provider_id.lower()
        ]

        if not rss_providers:
            return StrategyResult(suggestions=[], strategy_id=self.strategy_id)

        topics = ["programming", "design", "science", "philosophy", "economics"]
        topic = invocation.topic or random.choice(topics)
        all_suggestions = []

        for provider in rss_providers:
            try:
                suggestions = await provider.search(query=topic, limit=invocation.max_results)
                all_suggestions.extend(suggestions)
            except Exception as e:
                logger.error(f"RSS blog search failed: {e}")

        return StrategyResult(
            suggestions=all_suggestions[:invocation.max_results],
            strategy_id=self.strategy_id,
            query_used=topic,
        )


# =============================================================================
# LLM Strategies - Different prompt construction methods
# =============================================================================


class BaseLLMStrategy(ExplorationStrategy):
    """Base class for LLM-powered discovery strategies."""

    def _get_llm(self):
        """Get the LLM backend, handling import to avoid circular deps."""
        from omnifeed.discovery.llm import get_llm_backend
        try:
            return get_llm_backend()
        except RuntimeError:
            logger.warning("No LLM backend available")
            return None

    def _build_context_summary(self, context_items: list[dict] | None) -> str:
        """Build a summary of user's content preferences from context items."""
        if not context_items:
            return "No viewing history available."

        titles = [item.get("title", "") for item in context_items[:10] if item.get("title")]
        creators = list(set(item.get("creator_name", "") for item in context_items if item.get("creator_name")))[:5]

        summary = "Recent content I've enjoyed:\n"
        if titles:
            summary += f"- Titles: {', '.join(titles[:5])}\n"
        if creators:
            summary += f"- Creators: {', '.join(creators)}\n"

        return summary

    def _parse_suggestions(self, llm_response: dict | list | None) -> list[dict]:
        """Parse LLM response into search queries."""
        if not llm_response:
            return []

        if isinstance(llm_response, dict):
            queries = llm_response.get("queries", [])
            if not queries:
                queries = llm_response.get("suggestions", [])
        elif isinstance(llm_response, list):
            queries = llm_response
        else:
            return []

        results = []
        for item in queries:
            if isinstance(item, str):
                results.append({"query": item, "platform": "youtube"})
            elif isinstance(item, dict):
                results.append({
                    "query": item.get("query") or item.get("name", ""),
                    "platform": item.get("platform", "youtube"),
                    "reason": item.get("reason", ""),
                })
        return results

    async def _search_for_suggestions(
        self,
        queries: list[dict],
        max_results: int,
    ) -> list[SourceSuggestion]:
        """Execute searches based on LLM-generated queries across ALL providers."""
        registry = get_registry()
        all_suggestions: list[SourceSuggestion] = []
        seen_urls: set[str] = set()

        # Get all available search providers
        providers = registry.search_providers
        if not providers:
            logger.warning("No search providers available")
            return []

        for query_info in queries[:5]:  # Limit to 5 queries
            query = query_info.get("query", "")
            platform = query_info.get("platform", "")

            if not query:
                continue

            # If specific platform requested, use that provider
            if platform:
                providers_to_use = [
                    p for p in providers
                    if platform.lower() in p.provider_id.lower()
                ]
                if not providers_to_use:
                    providers_to_use = providers  # Fallback to all
            else:
                # Search ALL providers for maximum diversity
                providers_to_use = providers

            for provider in providers_to_use:
                try:
                    results = await provider.search(query=query, limit=2)
                    for suggestion in results:
                        if suggestion.url not in seen_urls:
                            seen_urls.add(suggestion.url)
                            all_suggestions.append(suggestion)
                except Exception as e:
                    logger.debug(f"Search failed for '{query}' on {provider.provider_id}: {e}")

            if len(all_suggestions) >= max_results:
                break

        return all_suggestions[:max_results]


class LLMInterestExpansionStrategy(BaseLLMStrategy):
    """LLM strategy that expands on user's interests to find new content."""

    @property
    def strategy_id(self) -> str:
        return "llm:interest_expansion"

    @property
    def display_name(self) -> str:
        return "LLM Interest Expansion"

    @property
    def description(self) -> str:
        return "Uses AI to expand on your interests and suggest related content areas"

    async def discover(self, invocation: StrategyInvocation) -> StrategyResult:
        logger.info(f"LLM Interest Expansion: {len(invocation.context_items or [])} context items")

        llm = self._get_llm()
        if not llm:
            return StrategyResult(suggestions=[], strategy_id=self.strategy_id)

        context_summary = self._build_context_summary(invocation.context_items)

        system_prompt = """You suggest YouTube search queries to find new creators.
Output JSON: {"queries": [{"query": "search text", "reason": "why"}]}
Keep queries specific and searchable. Focus on discovering channels, not videos."""

        user_prompt = f"""{context_summary}

Based on this viewing history, suggest 5 search queries to find NEW YouTube channels
in RELATED but UNEXPLORED areas. Think adjacent topics, deeper niches, or
cross-disciplinary connections. The goal is expansion beyond the obvious."""

        try:
            result = llm.extract_json(user_prompt, system=system_prompt, temperature=0.8)
            queries = self._parse_suggestions(result)
            logger.info(f"LLM Interest Expansion generated {len(queries)} queries")

            suggestions = await self._search_for_suggestions(queries, invocation.max_results)

            return StrategyResult(
                suggestions=suggestions,
                strategy_id=self.strategy_id,
                query_used="; ".join(q["query"] for q in queries[:3]),
                metadata={"prompt_method": "interest_expansion", "queries": queries},
            )
        except Exception as e:
            logger.error(f"LLM Interest Expansion failed: {e}")
            return StrategyResult(suggestions=[], strategy_id=self.strategy_id)


class LLMSimilarCreatorsStrategy(BaseLLMStrategy):
    """LLM strategy that finds creators similar to ones user likes."""

    @property
    def strategy_id(self) -> str:
        return "llm:similar_creators"

    @property
    def display_name(self) -> str:
        return "LLM Similar Creators"

    @property
    def description(self) -> str:
        return "Uses AI to find creators similar to ones you've rated highly"

    async def discover(self, invocation: StrategyInvocation) -> StrategyResult:
        logger.info(f"LLM Similar Creators: {len(invocation.context_items or [])} context items")

        llm = self._get_llm()
        if not llm:
            return StrategyResult(suggestions=[], strategy_id=self.strategy_id)

        # Extract creator names from context
        creators = []
        if invocation.context_items:
            creators = list(set(
                item.get("creator_name", "")
                for item in invocation.context_items
                if item.get("creator_name")
            ))[:5]

        if not creators:
            return StrategyResult(suggestions=[], strategy_id=self.strategy_id)

        system_prompt = """You suggest YouTube search queries to find creators similar to given ones.
Output JSON: {"queries": [{"query": "search text", "reason": "why similar"}]}
Focus on finding channels with similar style, topics, or production quality."""

        user_prompt = f"""Creators I enjoy:
{chr(10).join(f'- {c}' for c in creators)}

Suggest 5 YouTube search queries to find similar creators. Think about:
- Channels in the same niche
- Creators with similar presentation style
- Related topics with comparable depth/quality
- Collaborators or frequently mentioned peers"""

        try:
            result = llm.extract_json(user_prompt, system=system_prompt, temperature=0.7)
            queries = self._parse_suggestions(result)
            logger.info(f"LLM Similar Creators generated {len(queries)} queries")

            suggestions = await self._search_for_suggestions(queries, invocation.max_results)

            return StrategyResult(
                suggestions=suggestions,
                strategy_id=self.strategy_id,
                query_used="; ".join(q["query"] for q in queries[:3]),
                metadata={"prompt_method": "similar_creators", "source_creators": creators},
            )
        except Exception as e:
            logger.error(f"LLM Similar Creators failed: {e}")
            return StrategyResult(suggestions=[], strategy_id=self.strategy_id)


class LLMContrastExplorationStrategy(BaseLLMStrategy):
    """LLM strategy that suggests contrasting/opposing viewpoints."""

    @property
    def strategy_id(self) -> str:
        return "llm:contrast_exploration"

    @property
    def display_name(self) -> str:
        return "LLM Contrast Exploration"

    @property
    def description(self) -> str:
        return "Uses AI to suggest content with different perspectives from your usual"

    async def discover(self, invocation: StrategyInvocation) -> StrategyResult:
        logger.info(f"LLM Contrast Exploration: {len(invocation.context_items or [])} context items")

        llm = self._get_llm()
        if not llm:
            return StrategyResult(suggestions=[], strategy_id=self.strategy_id)

        context_summary = self._build_context_summary(invocation.context_items)

        system_prompt = """You suggest YouTube search queries to find contrasting content.
Output JSON: {"queries": [{"query": "search text", "reason": "how it contrasts"}]}
The goal is intellectual diversity - find valuable content outside the user's bubble."""

        user_prompt = f"""{context_summary}

Suggest 5 YouTube search queries to find quality content that CONTRASTS with my usual viewing:
- Different perspectives on similar topics
- Completely different genres/fields that might appeal
- Alternative schools of thought
- Content from different cultures or backgrounds
- Creators with opposing but well-reasoned viewpoints

Focus on high-quality educational content, not controversy for its own sake."""

        try:
            result = llm.extract_json(user_prompt, system=system_prompt, temperature=0.9)
            queries = self._parse_suggestions(result)
            logger.info(f"LLM Contrast Exploration generated {len(queries)} queries")

            suggestions = await self._search_for_suggestions(queries, invocation.max_results)

            return StrategyResult(
                suggestions=suggestions,
                strategy_id=self.strategy_id,
                query_used="; ".join(q["query"] for q in queries[:3]),
                metadata={"prompt_method": "contrast_exploration", "queries": queries},
            )
        except Exception as e:
            logger.error(f"LLM Contrast Exploration failed: {e}")
            return StrategyResult(suggestions=[], strategy_id=self.strategy_id)


# =============================================================================
# Strategy Registry
# =============================================================================


STRATEGIES: dict[str, ExplorationStrategy] = {}


def register_strategy(strategy: ExplorationStrategy):
    """Register an exploration strategy."""
    STRATEGIES[strategy.strategy_id] = strategy
    logger.debug(f"Registered strategy: {strategy.strategy_id}")


def get_strategy(strategy_id: str) -> ExplorationStrategy | None:
    """Get a strategy by ID."""
    return STRATEGIES.get(strategy_id)


def get_all_strategies() -> list[ExplorationStrategy]:
    """Get all registered strategies."""
    return list(STRATEGIES.values())


def get_strategies_by_provider(provider: str) -> list[ExplorationStrategy]:
    """Get all strategies for a provider (youtube, llm, rss, etc.)."""
    return [s for s in STRATEGIES.values() if s.provider == provider]


# =============================================================================
# Auto-Generated Provider Strategy - one instance per registered provider
# =============================================================================


class ProviderStrategy(ExplorationStrategy):
    """Generic strategy that wraps a single SearchProvider.

    Instances are auto-generated for each registered provider,
    so new sources are automatically included without manual code.
    """

    SAMPLE_TOPICS = [
        "jazz", "classical", "electronic", "ambient", "indie",
        "programming", "machine learning", "physics", "philosophy",
        "film", "horror", "science fiction", "documentary",
        "history", "economics", "design", "cooking",
    ]

    def __init__(self, provider_id: str):
        self._provider_id = provider_id

    @property
    def strategy_id(self) -> str:
        return f"provider:{self._provider_id}"

    @property
    def display_name(self) -> str:
        return f"{self._provider_id.title()} Discovery"

    @property
    def description(self) -> str:
        return f"Searches {self._provider_id} for new sources"

    def _get_provider(self):
        registry = get_registry()
        for p in registry.search_providers:
            if p.provider_id == self._provider_id:
                return p
        return None

    async def discover(self, invocation: StrategyInvocation) -> StrategyResult:
        provider = self._get_provider()
        if not provider:
            return StrategyResult(suggestions=[], strategy_id=self.strategy_id)

        topic = invocation.topic or random.choice(self.SAMPLE_TOPICS)

        try:
            suggestions = await provider.search(query=topic, limit=invocation.max_results)
            return StrategyResult(
                suggestions=suggestions,
                strategy_id=self.strategy_id,
                query_used=topic,
            )
        except Exception as e:
            logger.debug(f"Provider {self._provider_id} search failed: {e}")
            return StrategyResult(suggestions=[], strategy_id=self.strategy_id)


# Register built-in strategies
# YouTube (2 strategies - reduced from 3)
register_strategy(YouTubeTrendingTopicStrategy())
register_strategy(YouTubeDeepCutsStrategy())

# Bandcamp (1 strategy)
register_strategy(BandcampGenreStrategy())

# Qobuz (1 strategy)
register_strategy(QobuzDiscoveryStrategy())

# RSS (2 strategies)
register_strategy(RSSTopicFeedsStrategy())
register_strategy(RSSBlogDiscoveryStrategy())

# LLM - cross-platform discovery (3 strategies)
register_strategy(LLMInterestExpansionStrategy())
register_strategy(LLMSimilarCreatorsStrategy())
register_strategy(LLMContrastExplorationStrategy())

# Auto-register a strategy for EACH search provider in the registry
def _auto_register_provider_strategies():
    """Auto-generate strategies for all registered search providers."""
    registry = get_registry()
    for provider in registry.search_providers:
        strategy_id = f"provider:{provider.provider_id}"
        if strategy_id not in STRATEGIES:
            register_strategy(ProviderStrategy(provider.provider_id))

_auto_register_provider_strategies()

logger.info(f"Registered {len(STRATEGIES)} exploration strategies")


class StrategyHandler(RetrieverHandler):
    """Handler for exploration strategies.

    Unlike the old ExploratoryHandler which created retrievers per topic,
    this creates ONE retriever per strategy. The strategy gets scored,
    not individual queries.
    """

    @property
    def handler_type(self) -> str:
        return "strategy"

    def can_handle(self, uri: str) -> bool:
        return uri.startswith("strategy:")

    def resolve(self, uri: str, display_name: str | None = None) -> Retriever:
        """Create a retriever for a strategy."""
        parts = uri.split(":", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid strategy URI: {uri}")

        strategy_id = parts[1]
        strategy = get_strategy(strategy_id)

        if not strategy:
            raise ValueError(f"Unknown strategy: {strategy_id}")

        return Retriever(
            id="",
            display_name=display_name or strategy.display_name,
            kind=RetrieverKind.EXPLORE,
            handler_type=self.handler_type,
            uri=uri,
            config={
                "strategy_id": strategy_id,
                "description": strategy.description,
            },
        )

    async def invoke(
        self,
        retriever: Retriever,
        context: RetrievalContext,
    ) -> list[RetrievalResult]:
        """Invoke a strategy and return discovered sources as sub-retrievers."""
        strategy_id = retriever.config.get("strategy_id")
        strategy = get_strategy(strategy_id)

        if not strategy:
            logger.error(f"Strategy not found: {strategy_id}")
            return []

        # Build invocation from context
        invocation = StrategyInvocation(
            topic=context.topic if hasattr(context, 'topic') else None,
            context_items=context.context_items if hasattr(context, 'context_items') else None,
            max_results=context.max_results,
        )

        # Execute strategy
        result = await strategy.discover(invocation)

        # Convert suggestions to sub-retrievers
        results: list[RetrievalResult] = []
        seen_urls: set[str] = set()

        for suggestion in result.suggestions:
            if suggestion.url in seen_urls:
                continue
            seen_urls.add(suggestion.url)

            sub_retriever = self._suggestion_to_retriever(suggestion, retriever.id)
            results.append(RetrievalResult.from_retriever(
                sub_retriever,
                context=f"Discovered via {strategy.display_name}: {result.query_used or 'auto'}",
            ))

        return results

    def _suggestion_to_retriever(
        self,
        suggestion: SourceSuggestion,
        parent_id: str,
    ) -> Retriever:
        """Convert a source suggestion to a retriever."""
        uri = f"source:{suggestion.source_type}:{suggestion.url}"

        return Retriever(
            id="",
            display_name=suggestion.name,
            kind=RetrieverKind.POLL,
            handler_type="source",
            uri=uri,
            parent_id=parent_id,  # Link to the strategy that discovered it
            config={
                "source_type": suggestion.source_type,
                "source_uri": suggestion.url,
                "description": suggestion.description,
                "thumbnail_url": suggestion.thumbnail_url,
                "subscriber_count": suggestion.subscriber_count,
                "discovery_metadata": suggestion.metadata,
            },
        )
