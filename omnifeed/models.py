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


class PlatformCapability(Enum):
    """Capabilities a platform can provide for content delivery."""
    STREAM = "stream"           # Can play in-app (YouTube, Spotify)
    DOWNLOAD = "download"       # Can download for offline
    PURCHASE = "purchase"       # Can buy permanently (Bandcamp, Qobuz)
    EMBED = "embed"            # Can embed in other pages (YouTube, Spotify)
    RENDER = "render"          # Can render content (articles, HTML)


class SignalType(Enum):
    """Type of discovery signal indicating why content is recommended."""
    CHART_POSITION = "chart_position"   # Ranked on a chart (RYM top albums)
    USER_RATING = "user_rating"         # User rating (4.5 stars on Letterboxd)
    RECOMMENDATION = "recommendation"   # Personal recommendation
    MENTION = "mention"                 # Mentioned in content (podcast discussed)
    AWARD = "award"                     # Won or nominated for award
    TRENDING = "trending"               # Viral or trending
    ALGORITHMIC = "algorithmic"         # Algorithm thinks you'll like it
    CURATED = "curated"                 # Expert/editorial curation


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
# Platform vs Discovery Source Architecture
#
# Platform: Delivers consumable media bytes or renderable content.
#   Examples: YouTube, Qobuz, Spotify, Netflix, Bandcamp
#
# DiscoverySource: Provides signals about what content exists and why you
#   should engage with it. Points TO content, doesn't host it.
#   Examples: RateYourMusic charts, Letterboxd lists, award lists, newsletters
# =============================================================================


@dataclass
class Platform:
    """A service that delivers consumable media (video, audio, articles).

    Platforms can stream, download, or render actual content. They may also
    have discovery features (recommendations, trending), but their primary
    function is content delivery.

    Examples: YouTube, Qobuz, Spotify, Bandcamp, Netflix
    """
    id: str
    name: str                                    # "Qobuz", "YouTube"
    platform_type: str                           # "music_streaming", "video_streaming"
    content_types: list[ContentType]             # [AUDIO], [VIDEO], etc.
    capabilities: list[PlatformCapability]       # [STREAM, DOWNLOAD, PURCHASE]

    # Configuration
    auth_required: bool = False
    api_available: bool = False
    base_url: str | None = None                  # "https://www.qobuz.com"

    # Matching configuration
    url_patterns: list[str] = field(default_factory=list)  # ["qobuz.com/album/"]

    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DiscoverySource:
    """A source that provides signals about content worth consuming.

    Discovery sources point TO content but don't host it. They provide context
    about why you should engage (rankings, ratings, recommendations, awards).

    Examples: RateYourMusic charts, Letterboxd lists, Hugo Awards, newsletters
    """
    id: str
    name: str                                    # "RateYourMusic Charts"
    source_type: str                             # "chart", "list", "awards", "newsletter"
    content_types: list[ContentType]             # [AUDIO] for RYM, [FILM] for Letterboxd

    # Which platforms typically have this content
    typical_platforms: list[str] = field(default_factory=list)  # ["qobuz", "spotify"]

    # Polling configuration for scraping
    poll_url: str | None = None
    poll_interval_seconds: int = 86400           # Daily by default

    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_polled_at: datetime | None = None


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
    """A signal from a discovery source about content worth consuming.

    Links discovery sources to content with context about why it's recommended.
    One piece of content can have multiple signals from different sources.
    """
    id: str
    source_id: str                               # FK to DiscoverySource
    item_id: str | None = None                   # FK to Item (resolved content)

    # Content identification (before resolution)
    content_info: ContentInfo | None = None

    # Signal metadata
    signal_type: SignalType = SignalType.CURATED
    rank: int | None = None                      # Position in list (1 = top)
    rating: float | None = None                  # Source rating (e.g., RYM 3.92)
    context: str | None = None                   # "#3 on RYM Top Albums 2025"
    recommender: str | None = None               # Who recommended (for social)
    url: str | None = None                       # Link to discovery page

    discovered_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlatformInstance:
    """Where a piece of content can be consumed on a platform.

    Links content (Item) to platforms where it's available. One piece of
    content may be available on multiple platforms with different quality
    tiers, prices, and availability.
    """
    id: str
    item_id: str                                 # FK to Item (content)
    platform_id: str                             # FK to Platform
    platform_item_id: str                        # ID within the platform
    url: str                                     # Direct URL to consume

    # Availability info
    availability: str = "available"              # "available", "region_locked", "unavailable"
    quality_tiers: list[str] = field(default_factory=list)  # ["FLAC", "Hi-Res 24-bit"]
    price: float | None = None                   # For purchase platforms
    currency: str | None = None

    # Region restrictions
    region_locks: list[str] = field(default_factory=list)  # ["US", "EU"]

    # Match confidence (0.0-1.0) when auto-matched
    match_confidence: float = 1.0

    discovered_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)
