"""Core data models for OmniFeed."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from enum import Enum

# Import SourceInfo and RawItem from sources module (canonical definitions)
from omnifeed.sources.base import SourceInfo, RawItem


class SourceStatus(Enum):
    """Status of a content source."""
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"


class ContentType(Enum):
    """Type of content item."""
    VIDEO = "video"
    AUDIO = "audio"
    ARTICLE = "article"
    PAPER = "paper"
    IMAGE = "image"
    THREAD = "thread"
    # Long-form media (may not have direct URL)
    BOOK = "book"
    GAME = "game"
    SHOW = "show"      # TV series
    FILM = "film"
    PODCAST = "podcast"  # Series-level (vs individual audio episodes)
    OTHER = "other"


class ConsumptionType(Enum):
    """How content is typically consumed."""
    ONE_SHOT = "one_shot"      # Read once (news, article)
    REPLAYABLE = "replayable"  # May revisit (music, video essay)
    SERIALIZED = "serialized"  # Part of a series (episode, chapter)


class CreatorType(Enum):
    """Type of content creator."""
    INDIVIDUAL = "individual"  # Single person
    COMPANY = "company"        # Business or organization
    GROUP = "group"            # Band, collective, team
    AI_AGENT = "ai_agent"      # AI-generated content
    UNKNOWN = "unknown"        # Default when type is unclear


@dataclass
class Source:
    """A content source stored in the database."""
    id: str
    source_type: str
    uri: str
    display_name: str
    avatar_url: str | None
    metadata: dict[str, Any]
    created_at: datetime
    last_polled_at: datetime | None = None
    poll_interval_seconds: int = 3600
    status: SourceStatus = SourceStatus.ACTIVE

    @classmethod
    def from_info(cls, id: str, info: SourceInfo, created_at: datetime) -> "Source":
        """Create a Source from SourceInfo."""
        return cls(
            id=id,
            source_type=info.source_type,
            uri=info.uri,
            display_name=info.display_name,
            avatar_url=info.avatar_url,
            metadata=info.metadata,
            created_at=created_at,
        )

    def to_info(self) -> SourceInfo:
        """Convert back to SourceInfo."""
        return SourceInfo(
            source_type=self.source_type,
            uri=self.uri,
            display_name=self.display_name,
            avatar_url=self.avatar_url,
            metadata=self.metadata,
        )


@dataclass
class Creator:
    """An individual, company, or agent that creates content.

    Creators are deduplicated across sources using external_ids and name matching.
    """
    id: str
    name: str                      # Display name (canonical)
    creator_type: CreatorType = CreatorType.UNKNOWN

    # Alternative names, spellings, aliases for matching
    name_variants: list[str] = field(default_factory=list)

    # External identifiers for deduplication across platforms
    # Keys: "youtube", "twitter", "bandcamp", "spotify", "orcid", etc.
    external_ids: dict[str, str] = field(default_factory=dict)

    # Profile information
    avatar_url: str | None = None
    bio: str | None = None
    url: str | None = None         # Personal website or primary link

    # Extensible metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Item:
    """Normalized content item stored in database.

    Conceptually, Item represents "Content" - a piece of content that can be
    discovered from multiple sources and created by one or more creators.
    """
    id: str                       # Internal UUID
    source_id: str                # Primary source (first discovered from)
    external_id: str              # Platform-specific ID (from primary source)
    url: str                      # May be empty for books/games without direct URL
    title: str
    published_at: datetime
    ingested_at: datetime
    content_type: ContentType

    # Creator reference (normalized)
    creator_id: str | None = None  # FK to Creator entity
    creator_name: str = ""         # Denormalized for display; deprecated for new code

    consumption_type: ConsumptionType = ConsumptionType.ONE_SHOT

    # Extensible metadata - common fields extracted, rest preserved
    metadata: dict[str, Any] = field(default_factory=dict)

    # Canonical identifiers for deduplication across sources
    # Keys: "isbn", "isbn13", "imdb", "tmdb", "igdb", "steam", "openlibrary", etc.
    canonical_ids: dict[str, str] = field(default_factory=dict)

    # User state (MVP - simple flags, no separate UserItemState table yet)
    seen: bool = False
    hidden: bool = False

    # Optional series tracking
    series_id: str | None = None
    series_position: int | None = None

    # Content embeddings for ranking - list of typed embeddings
    # Each entry: {"type": "text"|"audio"|"image", "model": "...", "vector": [...]}
    embeddings: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ItemAttribution:
    """Tracks which sources an item (content) was discovered from.

    Enables provenance: "This book was recommended by Hugo Awards, NYT Books, and @friend"
    An item can have multiple attributions from different sources.

    Also known as "ContentSource" conceptually - links content to sources.
    """
    id: str
    item_id: str
    source_id: str
    discovered_at: datetime

    # Provenance tracking
    external_id: str = ""             # ID within this source (for dedup)
    is_primary: bool = False          # Was this the first source we discovered from?

    # Optional context about the recommendation
    rank: int | None = None           # Position in list (1 = top)
    context: str | None = None        # "Winner - Best Novel 2024", "Staff Pick"

    # Metadata from the source about this recommendation
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FeedbackEvent:
    """Implicit or explicit user feedback for training."""
    id: str
    item_id: str
    timestamp: datetime
    event_type: str  # "click", "impression", "hide_temp", "hide_permanent", "save", etc.
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class FeedbackOption:
    """An option within a feedback dimension."""
    id: str
    dimension_id: str
    label: str
    description: str | None = None
    sort_order: int = 0
    active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class FeedbackDimension:
    """A configurable dimension for explicit feedback (e.g., reward_type, replayability)."""
    id: str
    name: str                     # "reward_type", "replayability"
    description: str | None = None
    allow_multiple: bool = False  # multi-select vs single
    active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ExplicitFeedback:
    """User's explicit rating and categorization of content."""
    id: str
    item_id: str
    timestamp: datetime

    # Core rating: reward per unit time (0.0 - 5.0)
    reward_score: float

    # Dimension selections: dimension_id -> list of option_ids
    # e.g., {"reward_type": ["entertainment", "curiosity"], "replayability": ["will_revisit"]}
    selections: dict[str, list[str]] = field(default_factory=dict)

    # Optional context
    notes: str | None = None
    completion_pct: float | None = None  # where they were when rating
    is_checkpoint: bool = False          # periodic check-in vs final rating


@dataclass
class CreatorStats:
    """Aggregated statistics for a creator, derived from content feedback."""
    creator_id: str
    total_items: int = 0
    total_feedback_events: int = 0
    avg_reward_score: float | None = None
    total_time_spent_ms: float = 0.0

    # Breakdown by content type
    content_types: dict[str, int] = field(default_factory=dict)


@dataclass
class SourceStats:
    """Aggregated statistics for a source, derived from content feedback."""
    source_id: str
    total_items: int = 0
    total_feedback_events: int = 0
    avg_reward_score: float | None = None
    total_time_spent_ms: float = 0.0

    # Unique creators whose content appears in this source
    unique_creators: int = 0


# =============================================================================
# Discovery Signals
#
# Some sources (e.g., RYM charts, Letterboxd lists) provide signals about
# content worth consuming rather than the content itself. These signals
# point TO content and explain why you should engage with it.
# =============================================================================


@dataclass
class ContentInfo:
    """Extracted information about content from a discovery signal.

    This is the "pointer" data extracted from a discovery source - just enough
    to identify and match the content across platforms.
    """
    content_type: ContentType
    title: str
    creators: list[str]                          # ["Artist Name"]
    year: int | None = None

    # Known external IDs (may be partial)
    external_ids: dict[str, str] = field(default_factory=dict)  # {"rym": "album/123"}


@dataclass
class DiscoverySignal:
    """A signal from a source about content worth consuming.

    Links sources to content with context about why it's recommended.
    One piece of content can have multiple signals from different sources.
    """
    id: str
    source_id: str                               # FK to Source
    item_id: str | None = None                   # FK to Item (resolved content)

    # Content identification (before resolution)
    content_info: ContentInfo | None = None

    # Signal metadata
    rank: int | None = None                      # Position in list (1 = top)
    rating: float | None = None                  # Source rating (e.g., RYM 3.92)
    context: str | None = None                   # "#3 on RYM Top Albums 2025"
    url: str | None = None                       # Link to discovery page

    discovered_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Content + Encoding Model
#
# Content represents WHAT something is (a song, video, article).
# Encoding represents WHERE/HOW to access it (YouTube URL, Qobuz deep link).
# One Content can have multiple Encodings (same song on Spotify and Bandcamp).
# =============================================================================


@dataclass
class Embedding:
    """A featurized representation of content."""
    name: str          # "transcript", "description", "audio_sample"
    type: str          # "text", "audio", "image"
    vector: list[float]
    model: str = ""    # "all-MiniLM-L6-v2", "laion/clap"


@dataclass
class Content:
    """Abstract content - what it IS, not where it lives.

    Content represents a piece of content independent of how it's accessed.
    The same song can have multiple Encodings (Qobuz, Bandcamp, YouTube).
    Content can exist without any Encodings (references to books we know about).
    """
    id: str
    title: str
    content_type: ContentType
    published_at: datetime
    ingested_at: datetime  # First time we learned about it

    # Creators (usually multiple - songs have artists, papers have authors)
    creator_ids: list[str] = field(default_factory=list)

    consumption_type: ConsumptionType = ConsumptionType.ONE_SHOT

    # Cross-platform identity (ISBN, IMDB, etc.)
    canonical_ids: dict[str, str] = field(default_factory=dict)

    # User state
    seen: bool = False
    hidden: bool = False

    # Series tracking
    series_id: str | None = None
    series_position: int | None = None

    # Content-level metadata (content_text, description)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Featurized representations
    embeddings: list[Embedding] = field(default_factory=list)


@dataclass
class Encoding:
    """A specific way to access content on a platform.

    Encodings link Content to platform-specific access methods.
    Examples:
    - YouTube video URL
    - Qobuz deep link (qobuz://track/12345)
    - Bandcamp album page
    - Local file path
    """
    id: str
    content_id: str              # FK to Content

    source_type: str             # "youtube", "qobuz", "bandcamp", "web"
    external_id: str             # Platform-specific ID
    uri: str                     # URL or deep link

    media_type: str | None = None    # "video/youtube", "audio/flac"

    # Encoding-specific metadata (view_count, duration, bitrate)
    metadata: dict[str, Any] = field(default_factory=dict)

    discovered_at: datetime = field(default_factory=datetime.utcnow)
    is_primary: bool = False     # First encoding we found


@dataclass
class ContentWithEncoding:
    """Convenience wrapper for the common 1:1 case.

    Most content is discovered from a single source, so this wrapper
    simplifies handling when you have exactly one encoding.
    """
    content: Content
    encoding: Encoding

    @property
    def id(self) -> str:
        """Content ID for backwards compatibility."""
        return self.content.id

    @property
    def url(self) -> str:
        """Primary URL for backwards compatibility."""
        return self.encoding.uri

    @property
    def title(self) -> str:
        return self.content.title

    @property
    def content_type(self) -> ContentType:
        return self.content.content_type
