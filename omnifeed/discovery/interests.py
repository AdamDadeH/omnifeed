"""Interest extraction from engaged content."""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from omnifeed.discovery.llm import get_llm_backend

if TYPE_CHECKING:
    from omnifeed.models import Item, ExplicitFeedback
    from omnifeed.store import Store

logger = logging.getLogger(__name__)


@dataclass
class Interest:
    """A detected user interest/topic."""
    topic: str
    confidence: float  # 0-1
    source_types: list[str] = field(default_factory=list)  # e.g., ["youtube", "rss"]
    example_items: list[str] = field(default_factory=list)  # Item titles as examples
    search_queries: list[str] = field(default_factory=list)  # Suggested search queries


@dataclass
class InterestProfile:
    """User's interest profile derived from engagement."""
    interests: list[Interest]
    top_creators: list[str]  # Creators user engages with most
    content_types: list[str]  # Preferred content types
    generated_queries: list[str]  # Ready-to-use search queries


INTEREST_EXTRACTION_PROMPT = """Analyze these content items that a user has engaged with and enjoyed.
Extract their interests, themes, and topics.

Content items (title and source):
{items_text}

Based on this content, identify:
1. Main topics/interests (be specific, not generic)
2. Themes or patterns you notice
3. 3-5 search queries to find similar content/creators

Respond in JSON format:
{{
  "interests": [
    {{"topic": "specific topic", "confidence": 0.9, "examples": ["item title 1"]}},
    ...
  ],
  "themes": ["theme1", "theme2"],
  "search_queries": ["query 1", "query 2", ...]
}}
"""


def extract_interests_from_items(
    items: list["Item"],
    feedbacks: list["ExplicitFeedback"] | None = None,
) -> InterestProfile | None:
    """Extract interests from a list of engaged items.

    Args:
        items: Items the user has engaged with
        feedbacks: Optional explicit feedback for weighting

    Returns:
        InterestProfile or None if extraction fails
    """
    if not items:
        return None

    llm = get_llm_backend()

    # Build item text for the prompt
    # Weight by feedback score if available
    feedback_map = {}
    if feedbacks:
        feedback_map = {fb.item_id: fb.reward_score for fb in feedbacks}

    # Sort by feedback score (higher first) then recency
    def score_item(item):
        fb_score = feedback_map.get(item.id, 2.5)  # Default to middle score
        return fb_score

    sorted_items = sorted(items, key=score_item, reverse=True)

    # Take top 30 items for analysis (balance context vs prompt length)
    sample = sorted_items[:30]

    items_text = "\n".join([
        f"- {item.title} (from: {item.creator_name})"
        for item in sample
    ])

    prompt = INTEREST_EXTRACTION_PROMPT.format(items_text=items_text)

    result = llm.extract_json(
        prompt=prompt,
        system="You are an expert at understanding user preferences from their content consumption. Be specific and insightful.",
        temperature=0.4,
    )

    if not result:
        logger.warning("Failed to extract interests from items")
        return None

    # Build Interest objects
    interests = []
    for item_data in result.get("interests", []):
        interests.append(Interest(
            topic=item_data.get("topic", ""),
            confidence=item_data.get("confidence", 0.5),
            example_items=item_data.get("examples", []),
            search_queries=[],
        ))

    # Extract top creators from the items
    creator_counts: dict[str, int] = {}
    for item in items:
        creator_counts[item.creator_name] = creator_counts.get(item.creator_name, 0) + 1

    top_creators = sorted(creator_counts.keys(), key=lambda c: creator_counts[c], reverse=True)[:10]

    # Content types
    content_types = list(set(item.content_type.value for item in items))

    return InterestProfile(
        interests=interests,
        top_creators=top_creators,
        content_types=content_types,
        generated_queries=result.get("search_queries", []),
    )


QUERY_GENERATION_PROMPT = """Based on this user request, generate search queries to find relevant content sources.

User request: {user_prompt}

The user is looking for content sources (YouTube channels, podcasts, blogs, etc.) to follow.

Generate 3-5 specific search queries that would help find:
1. Creators/channels in this space
2. Related topics they might enjoy
3. Different platforms/formats for this content

Respond in JSON format:
{{
  "queries": ["query 1", "query 2", ...],
  "platforms": ["youtube", "podcast", ...],
  "related_topics": ["topic 1", "topic 2"]
}}
"""


def generate_queries_from_prompt(user_prompt: str) -> dict | None:
    """Generate search queries from a user's discovery prompt.

    Args:
        user_prompt: What the user is looking for (e.g., "jazz piano tutorials")

    Returns:
        Dict with queries, platforms, and related_topics
    """
    llm = get_llm_backend()

    prompt = QUERY_GENERATION_PROMPT.format(user_prompt=user_prompt)

    result = llm.extract_json(
        prompt=prompt,
        system="You are a content discovery assistant. Generate specific, searchable queries.",
        temperature=0.5,
    )

    return result


def build_interest_profile(store: "Store", min_score: float = 3.0) -> InterestProfile | None:
    """Build interest profile from store data.

    Args:
        store: Data store
        min_score: Minimum feedback score to consider as "liked"

    Returns:
        InterestProfile or None
    """
    # Get explicitly rated items with good scores
    feedbacks = store.get_explicit_feedback(limit=200)
    high_rated = [fb for fb in feedbacks if fb.reward_score >= min_score]

    if not high_rated:
        # Fall back to engaged items (seen items)
        items = store.get_items(seen=True, limit=50)
        if not items:
            return None
        return extract_interests_from_items(items)

    # Get the items for high-rated feedback
    item_ids = [fb.item_id for fb in high_rated]
    items = [store.get_item(item_id) for item_id in item_ids]
    items = [i for i in items if i is not None]

    if not items:
        return None

    return extract_interests_from_items(items, high_rated)
