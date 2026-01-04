"""Core types for the Retriever abstraction.

A Retriever is anything that, when invoked, returns either:
- More Retrievers (drill deeper into a hierarchy)
- Content (leaf nodes - Items)

This enables recursive content discovery where sources can return sub-sources,
and quality scores propagate upward from user feedback.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from omnifeed.models import Item


class RetrieverKind(Enum):
    """How a retriever behaves when invoked."""
    POLL = "poll"       # Periodically fetch content (RSS, YouTube channel)
    EXPLORE = "explore" # One-time expansion into sub-retrievers
    HYBRID = "hybrid"   # Can return both content and sub-retrievers


class ResultType(Enum):
    """Type of result returned from a retriever invocation."""
    CONTENT = "content"     # Item
    RETRIEVER = "retriever" # Another Retriever to explore


@dataclass
class RetrieverScore:
    """Quality score for a retriever, derived from feedback on its content.

    For leaf retrievers: EMA of content ratings from that source.
    For parent retrievers: Weighted average of children's scores.
    """
    value: float           # 0.0 - 5.0 scale
    confidence: float      # 0.0 - 1.0 (increases with sample size)
    sample_size: int       # Number of feedback events contributing
    last_updated: datetime


@dataclass
class Retriever:
    """A source of content or sub-sources in the discovery hierarchy.

    Examples:
        - "RateYourMusic" → returns [RYM Charts 2025, RYM Lists, ...]
        - "RYM Charts 2025" → returns [Album1, Album2, ...] (content)
        - "RSS: blog.com/feed" → returns [Post1, Post2, ...] (leaf)
        - "explore:random" → returns [discovered sources...]
    """
    id: str
    display_name: str
    kind: RetrieverKind
    handler_type: str            # Maps to RetrieverHandler implementation
    uri: str                     # Primary identifier / configuration

    # Handler-specific configuration
    config: dict[str, Any] = field(default_factory=dict)

    # Scheduling (for POLL kind)
    poll_interval_seconds: int = 3600
    last_invoked_at: datetime | None = None

    # DAG structure (tree for MVP, DAG later)
    parent_id: str | None = None
    depth: int = 0
    is_enabled: bool = True

    # Quality score (derived from children's feedback)
    score: RetrieverScore | None = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RetrievalContext:
    """Context passed to retriever handlers during invocation."""
    max_depth: int = 1           # How deep to recurse
    max_results: int = 50        # Max results per invocation
    include_disabled: bool = False

    # For explore/exploit balancing
    explore_ratio: float = 0.3   # Fraction of results from exploration

    # Filtering
    content_types: list[str] | None = None  # Filter by content type

    # For strategy invocations
    topic: str | None = None                 # Topic to explore
    context_items: list[dict] | None = None  # High-rated content for LLM context


@dataclass
class RetrievalResult:
    """A single result from invoking a retriever.

    Can be either content (Item) or another Retriever.
    """
    result_type: ResultType

    # Content result (when result_type == CONTENT)
    item: Item | None = None

    # Retriever result (when result_type == RETRIEVER)
    retriever: Retriever | None = None

    # Metadata about this result
    rank: int | None = None           # Position in source list
    source_score: float | None = None # Score from the source (e.g., RYM rating)
    context: str | None = None        # "Winner - Best Novel 2024"

    @classmethod
    def from_item(
        cls,
        item: Item,
        rank: int | None = None,
        context: str | None = None,
    ) -> "RetrievalResult":
        """Create a content result from an Item."""
        return cls(
            result_type=ResultType.CONTENT,
            item=item,
            rank=rank,
            context=context,
        )

    @classmethod
    def from_retriever(
        cls,
        retriever: Retriever,
        context: str | None = None,
    ) -> "RetrievalResult":
        """Create a retriever result for further exploration."""
        return cls(
            result_type=ResultType.RETRIEVER,
            retriever=retriever,
            source_score=retriever.score.value if retriever.score else None,
            context=context,
        )
