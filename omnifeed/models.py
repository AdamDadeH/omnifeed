"""Core data models for OmniFeed."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from enum import Enum


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
    OTHER = "other"


class ConsumptionType(Enum):
    """How content is typically consumed."""
    ONE_SHOT = "one_shot"      # Read once (news, article)
    REPLAYABLE = "replayable"  # May revisit (music, video essay)
    SERIALIZED = "serialized"  # Part of a series (episode, chapter)


@dataclass
class SourceInfo:
    """Metadata about a content source, resolved from a URL or identifier."""
    source_type: str              # "rss", "youtube_channel", etc.
    uri: str                      # Canonical identifier (feed URL, channel URL)
    display_name: str
    avatar_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


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
class RawItem:
    """Item as pulled from source, before normalization."""
    external_id: str              # Platform-specific ID for deduplication
    url: str
    title: str
    published_at: datetime
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Item:
    """Normalized content item stored in database."""
    id: str                       # Internal UUID
    source_id: str
    external_id: str              # Platform-specific ID
    url: str
    title: str
    creator_name: str
    published_at: datetime
    ingested_at: datetime
    content_type: ContentType
    consumption_type: ConsumptionType = ConsumptionType.ONE_SHOT

    # Extensible metadata - common fields extracted, rest preserved
    metadata: dict[str, Any] = field(default_factory=dict)

    # User state (MVP - simple flags, no separate UserItemState table yet)
    seen: bool = False
    hidden: bool = False

    # Optional series tracking
    series_id: str | None = None
    series_position: int | None = None


@dataclass
class FeedbackEvent:
    """Implicit or explicit user feedback for training."""
    id: str
    item_id: str
    timestamp: datetime
    event_type: str  # "click", "impression", "hide_temp", "hide_permanent", "save", etc.
    payload: dict[str, Any] = field(default_factory=dict)
