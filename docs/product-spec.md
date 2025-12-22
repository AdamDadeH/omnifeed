# OmniFeed Product Specification

## Vision

A unified content feed aggregating streams and discrete content from disparate sources, with personalized ranking optimized for discovery and consumption efficiency.

### Goals

1. **Centralized View** - Single interface replacing K separate apps/sites
2. **Optimized Read Order** - Personalized ranking surfaces most relevant content
3. **Discovery** - Expose nascent creators and content outside existing follow graph

---

## Core Entities

### Source

A content origin that produces items over time.

```
Source {
  id: UUID
  type: enum (youtube_channel, podcast, rss_blog, arxiv_author, arxiv_topic, substack, ...)
  uri: string                    # canonical identifier (channel URL, RSS feed URL, etc.)
  display_name: string
  avatar_url: string?
  metadata: JSON                 # source-type-specific fields
  created_at: timestamp
  last_polled_at: timestamp?
  poll_interval_seconds: int     # system-managed or user override
  status: enum (active, paused, error)
}
```

### Item

A single piece of content from a source.

```
Item {
  id: UUID
  source_id: FK → Source
  external_id: string            # platform-specific ID for deduplication
  content_type: enum (video, audio, article, paper, image, thread, ...)

  # Universal fields (all content types)
  title: string
  url: string                    # canonical link to content
  thumbnail_url: string?
  creator_name: string
  published_at: timestamp
  ingested_at: timestamp

  # Normalized metadata (see Unified Schema below)
  metadata: JSON

  # Consumption tracking
  consumption_type: enum (one_shot, replayable, serialized)
  series_id: string?             # for serialized content (episode grouping)
  series_position: int?

  # Computed/derived
  embedding: vector?             # for semantic similarity (future)
}
```

### UserItemState

Per-user state for each item.

```
UserItemState {
  user_id: FK → User
  item_id: FK → Item

  seen: boolean (default false)
  seen_at: timestamp?

  visibility: enum (visible, hidden_temp, hidden_permanent)
  hidden_until: timestamp?       # for hidden_temp (snooze)

  saved: boolean (default false)
  saved_at: timestamp?

  # Explicit feedback
  rating: enum (none, positive, negative)?
}
```

### FeedbackEvent

Implicit and explicit signals for training.

```
FeedbackEvent {
  id: UUID
  user_id: FK → User
  item_id: FK → Item
  timestamp: timestamp

  event_type: enum (
    # Implicit
    impression,          # item rendered in viewport
    hover,               # mouse entered item (desktop)
    click,               # opened content
    dwell,               # time on content before return
    scroll_past,         # scrolled past without interaction

    # Explicit
    hide_temp,
    hide_permanent,
    save,
    unsave,
    rate_positive,
    rate_negative
  )

  # Event-specific data
  payload: JSON {
    exposure_duration_ms: int?    # for impression
    hover_duration_ms: int?       # for hover
    dwell_duration_ms: int?       # for dwell
    scroll_velocity: float?       # for scroll_past
    viewport_position: int?       # where in feed (1st, 5th, 20th item)
  }
}
```

---

## Unified Metadata Schema

All items normalize to common fields plus type-specific extensions.

### Common Fields (all types)

| Field | Type | Description |
|-------|------|-------------|
| title | string | Content title |
| description | string? | Summary/excerpt |
| creator_name | string | Author/channel/artist name |
| creator_id | string? | Platform-specific creator ID |
| published_at | timestamp | Original publish time |
| duration_seconds | int? | For audio/video |
| word_count | int? | For articles |
| language | string? | ISO language code |
| tags | string[] | Content tags/categories |
| thumbnail_url | string? | Preview image |

### Type-Specific Extensions

**Video (YouTube, TikTok, etc.)**
```json
{
  "view_count": 150000,
  "like_count": 5000,
  "comment_count": 320,
  "channel_subscriber_count": 45000,
  "is_short": false,
  "is_live": false,
  "captions_available": true
}
```

**Article/Blog**
```json
{
  "word_count": 1200,
  "reading_time_minutes": 5,
  "publication_name": "Some Blog",
  "paywall": false
}
```

**Research Paper**
```json
{
  "authors": ["Alice Smith", "Bob Jones"],
  "abstract": "...",
  "arxiv_id": "2301.12345",
  "doi": "10.1234/...",
  "citation_count": 42,
  "venue": "NeurIPS 2024",
  "pdf_url": "https://..."
}
```

**Podcast Episode**
```json
{
  "show_name": "Some Podcast",
  "episode_number": 123,
  "season_number": 2,
  "explicit": false,
  "chapters": [...]
}
```

**Music Track** (future)
```json
{
  "artist": "...",
  "album": "...",
  "track_number": 5,
  "genre": ["electronic", "ambient"],
  "bpm": 120,
  "isrc": "..."
}
```

---

## User Flows

### 1. Feed Consumption (Primary Loop)

```
1. User opens OmniFeed
2. System fetches ranked feed for user
   - Applies filters (default: unseen + replayable)
   - Applies personalized ranking
3. User scrolls through items
   - Each scroll/pause generates impression events
4. User interacts with item:
   - Click → opens content, logs click event
   - Right-click → context menu (hide, not interested, save)
   - Keyboard: j/k navigate, o open, x hide, s save
5. On return from content:
   - Log dwell time
   - Mark item as seen
   - Update ranking model (future)
```

### 2. Add Source

```
1. User clicks "+ Add Source"
2. User pastes URL or searches by name
3. System detects source type:
   - YouTube URL → resolve channel metadata
   - RSS URL → fetch and parse feed
   - Search query → search across known platforms
4. System shows preview:
   - Source name, avatar
   - Recent N items
   - Detected content type
5. User configures (optional):
   - Custom display name
   - Tags/folders
   - Backfill depth (last N items or N days)
6. User confirms → source created
7. System backfills items into feed
8. Polling begins on system-managed schedule
```

### 3. Discovery Mode

```
1. User enters Discovery tab/mode
2. System surfaces content from:
   - Sources not currently followed
   - Weighted toward nascent creators (signals below)
   - Similar to followed sources (topic/embedding similarity)
3. User actions:
   - "Follow" → adds source permanently
   - "More like this" → positive signal for ranking, no follow
   - "Not interested" → negative signal
4. Discovery ranking signals:
   - Creator follower count (lower = more nascent)
   - Creator account age
   - Engagement rate (high engagement + low followers = promising)
   - Topic similarity to user interests
   - Not already hidden/rejected by user
```

### 4. Source Management

```
1. User opens Sources panel
2. Sees list of all sources:
   - Grouped by type or user-defined folders
   - Shows: name, last updated, item count, status
3. User can:
   - Pause/resume source
   - Edit source settings
   - Remove source (items remain in feed? or cascade delete?)
   - Force refresh
   - View source-specific feed
```

---

## Ranking System

### Input Signals

**Item-level signals:**
- Content type match to user preferences
- Topic/embedding similarity to past positive engagement
- Freshness (recency of publish_at)
- Source trust score (derived below)
- Metadata quality signals (has thumbnail, has description, etc.)

**Source-level signals (trust/quality):**
- User's historical engagement with this source
- Aggregate engagement from all users (future, multi-user)
- Source age and consistency
- Cross-reference: cited/shared by high-trust sources
- Creator metrics (followers, engagement rate)

**User-level signals:**
- Explicit feedback history (hides, saves, ratings)
- Implicit engagement patterns (dwell time, click-through rate)
- Time-of-day preferences
- Content type preferences

### Ranking Pipeline (Future)

```
1. Candidate generation
   - Fetch unseen + replayable items for user
   - Apply hard filters (not hidden_permanent)

2. Feature extraction
   - Item features (metadata, embeddings)
   - User features (preference vector)
   - Cross features (user-source affinity, etc.)

3. Scoring
   - Initial: heuristic scoring (weighted feature combination)
   - Later: trained model (learning-to-rank)

4. Re-ranking
   - Diversity injection (don't show 10 items from same source)
   - Freshness boost for breaking content
   - Discovery injection (N% slots for nascent creators)

5. Serve ranked list
```

---

## Technical Architecture (High-Level)

```
┌─────────────────────────────────────────────────────────────┐
│                        Desktop Client                        │
│  (Electron / Web App)                                        │
│  - Feed UI                                                   │
│  - Source management                                         │
│  - Event capture (clicks, hovers, scrolls)                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                         API Server                           │
│  - Feed endpoint (ranked items)                              │
│  - Source CRUD                                               │
│  - Feedback ingestion                                        │
│  - User state management                                     │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│    Database     │ │  Ingestion      │ │  Ranking        │
│  (PostgreSQL)   │ │  Workers        │ │  Service        │
│                 │ │                 │ │                 │
│  - Sources      │ │  - Poll sources │ │  - Score items  │
│  - Items        │ │  - Parse feeds  │ │  - Train model  │
│  - UserState    │ │  - Normalize    │ │  (future)       │
│  - Events       │ │    metadata     │ │                 │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

---

## Design Decisions

| Decision | Choice | Notes |
|----------|--------|-------|
| User model | Single-user initially | Future: multi-user with separate queues, shared ranking data |
| Backfill on source add | Configurable | User chooses depth (last N items or N days) |
| Source removal | Soft delete / disable | Items remain orphaned; prefer disabling over deletion |
| Offline support | Not required | Always-connected assumption |
| Deduplication | Yes, configurable | See Deduplication section below |

---

## Deduplication

Two layers of deduplication are needed:

### 1. Content Deduplication

Detect when the same content appears across multiple sources.

**Examples:**
- Same video uploaded to YouTube and TikTok
- Same article syndicated across multiple blogs
- Same paper on arXiv and conference proceedings

**Approach:**
```
ContentCluster {
  id: UUID
  canonical_item_id: FK → Item    # primary/first instance
  items: FK[] → Item              # all instances of this content
  confidence: float               # dedup confidence score
  method: enum (exact_url, fingerprint, embedding_similarity, manual)
}
```

**Matching signals:**
- Exact URL match (rare cross-platform)
- Title + creator fuzzy match
- Content fingerprint (perceptual hash for video/images, text similarity for articles)
- Embedding cosine similarity above threshold
- Duration match (for audio/video)

**Feed behavior (configurable):**
- Show only canonical item (hide duplicates)
- Show canonical with "also on: [platforms]" indicator
- Show all separately (no dedup in display)

### 2. Entity Deduplication (NER)

Recognize that different mentions refer to the same entity.

**Entity types:**
- Person (creator, author, subject)
- Organization (company, institution, publication)
- Topic/concept
- Creative work (a specific album, paper, project)

```
Entity {
  id: UUID
  type: enum (person, org, topic, work)
  canonical_name: string
  aliases: string[]               # all known names/handles
  external_ids: JSON {            # platform-specific IDs
    twitter: "@handle",
    youtube: "channel_id",
    orcid: "0000-0001-...",
    ...
  }
  metadata: JSON                  # type-specific fields
}

EntityMention {
  id: UUID
  entity_id: FK → Entity
  item_id: FK → Item
  mention_type: enum (creator, subject, reference, tag)
  surface_form: string            # as it appeared in content
  confidence: float
}
```

**Use cases:**
- "Show me all content by [Entity]" across platforms
- "Show me all content mentioning [Entity]" as subject
- Entity-level affinity in ranking (user likes content from/about this entity)
- Discovery: "Creators similar to [Entity]"

**Resolution pipeline:**
1. Extract mentions from item metadata (creator name, tags, description NER)
2. Normalize surface forms (lowercase, strip handles, etc.)
3. Match against known entities (fuzzy match + external ID lookup)
4. Cluster unmatched mentions → propose new entities
5. Manual merge/split for corrections

---

## Read Position Tracking

Track user's consumption progress for long-form content.

```
ReadProgress {
  user_id: FK → User
  item_id: FK → Item

  # Position tracking
  progress_pct: float             # 0.0 to 1.0
  progress_raw: JSON {            # content-type specific
    scroll_position: int,         # for articles (pixels or paragraph index)
    timestamp_seconds: int,       # for audio/video
    page_number: int,             # for PDFs
  }

  # Timing
  started_at: timestamp
  last_updated_at: timestamp
  completed_at: timestamp?        # null until 100% (or threshold like 90%)
  total_time_spent_ms: int        # cumulative across sessions
  session_count: int              # how many times they returned
}
```

**UX Features:**
- "Continue reading" / "Continue watching" indicator in feed
- Progress bar on item cards
- Filter: "In Progress" to see partially consumed content

**Engagement signals derived:**
- Completion rate (did they finish?)
- Drop-off point (where did they stop? → content quality signal)
- Time-to-complete vs expected (based on duration/word count)
- Return rate (came back to finish vs abandoned)

---

## Entity Management View

Separate admin/cleanup mode for entity resolution.

**Entity List View:**
```
- Search/filter entities by name, type, source count
- Sort by: mention count, unresolved aliases, recently added
- Bulk actions: merge selected, set canonical, delete
```

**Entity Detail View:**
```
- Canonical name (editable)
- Aliases (add/remove)
- External IDs (link to platforms)
- Linked items preview (by this entity, about this entity)
- Suggested merges (other entities that might be the same)
- Split action (if incorrectly merged)
```

**Resolution Queue:**
```
- Low-confidence matches needing review
- Unresolved mentions (no entity linked)
- Proposed new entities from clustering
- Quick actions: confirm, reject, merge with existing
```

---

## Deduplication Thresholds

Configurable thresholds for content deduplication behavior.

```
DedupConfig {
  auto_merge_threshold: float     # default 0.95 - auto-cluster, no review
  suggest_threshold: float        # default 0.70 - show in review queue
  ignore_threshold: float         # default 0.50 - below this, treat as distinct

  # Per content-type overrides (video more reliable than text)
  type_overrides: {
    video: { auto: 0.90, suggest: 0.65 },
    article: { auto: 0.98, suggest: 0.80 },
    ...
  }
}
```

**Dedup Review Queue:**
- Suggested matches (between thresholds) for user review
- Actions: confirm merge, reject (mark as distinct), adjust canonical

---

## Design Decisions (Updated)

| Decision | Choice | Notes |
|----------|--------|-------|
| User model | Single-user initially | Future: multi-user with separate queues, shared ranking data |
| Backfill on source add | Configurable | User chooses depth (last N items or N days) |
| Source removal | Soft delete / disable | Items remain orphaned; prefer disabling over deletion |
| Offline support | Not required | Always-connected assumption |
| Deduplication | Yes, configurable | Thresholds for auto/suggest/ignore |
| Read position tracking | Yes | Enables continue-reading + granular engagement signals |
| Entity management | Separate admin view | Cleanup mode with resolution queue |
| MVP language | Python | Fast iteration; designed for future rewrite |
| Data portability | Required | SQLite + JSON; no language-specific serialization |

---

## Language Portability

MVP is Python for speed of iteration. Design supports future rewrite in Go/Rust/etc.

**Portable by design:**
- **Storage**: SQLite (universal bindings) + JSON files (trivial to parse)
- **Interfaces**: Map directly to language constructs:
  | Python | Go | Rust |
  |--------|-----|------|
  | `ABC` | `interface` | `trait` |
  | `@dataclass` | `struct` | `struct` |
  | `dict[str, Any]` | `map[string]interface{}` | `HashMap<String, Value>` |
- **No pickle/cloudpickle**: All persistence is JSON or SQLite
- **No Python-specific ORMs**: Raw SQL or simple query builders

**Schema is the contract:**
```sql
-- SQLite schema is the language-agnostic source of truth
CREATE TABLE sources (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    uri TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    avatar_url TEXT,
    metadata JSON,
    created_at TEXT NOT NULL,
    last_polled_at TEXT,
    poll_interval_seconds INTEGER DEFAULT 3600,
    status TEXT DEFAULT 'active'
);

CREATE TABLE items (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id),
    external_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    creator_name TEXT NOT NULL,
    published_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    content_type TEXT NOT NULL,
    metadata JSON,
    seen INTEGER DEFAULT 0,
    hidden INTEGER DEFAULT 0,
    UNIQUE(source_id, external_id)
);

CREATE INDEX idx_items_published ON items(published_at DESC);
CREATE INDEX idx_items_source ON items(source_id);
CREATE INDEX idx_items_seen ON items(seen);
```

**Rewrite path:**
1. Keep same SQLite schema
2. Reimplement interfaces in target language
3. FileStore JSON format is documented, parse directly
4. CLI args/behavior stay consistent (same UX)

---

## MVP: Minimum Viable Implementation

The smallest thing that pulls data, stores it, and displays it with ranking extensibility baked in.

### MVP Scope

```
┌─────────────────────────────────────────────────────────────┐
│                          CLI                                 │
│  feed, sources add <url>, sources list, mark-seen <id>      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       Core Library                           │
│  - SourceAdapter interface                                   │
│  - ItemStore (SQLite)                                        │
│  - RankingPipeline (no-op: chronological)                   │
│  - FeatureExtractor interface                                │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│   RSSAdapter            │     │   YouTubeAdapter        │
│   (first implementation)│     │   (second)              │
└─────────────────────────┘     └─────────────────────────┘
```

---

### 1. Source Adapter Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

@dataclass
class SourceInfo:
    """Metadata about a source, resolved from a URL or identifier."""
    source_type: str              # "rss", "youtube_channel", etc.
    uri: str                      # canonical identifier
    display_name: str
    avatar_url: str | None
    metadata: dict[str, Any]      # source-type specific

@dataclass
class RawItem:
    """Item as pulled from source, before normalization."""
    external_id: str              # platform-specific ID
    url: str
    title: str
    published_at: datetime
    raw_metadata: dict[str, Any]  # everything from the source

class SourceAdapter(ABC):
    """Interface for pulling content from a source type."""

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Return True if this adapter can handle the given URL."""
        pass

    @abstractmethod
    def resolve(self, url: str) -> SourceInfo:
        """Resolve a URL to source metadata. Called when adding a source."""
        pass

    @abstractmethod
    def poll(self, source: SourceInfo, since: datetime | None = None) -> list[RawItem]:
        """Fetch new items from the source since the given timestamp."""
        pass
```

**Adapter Registry:**
```python
class AdapterRegistry:
    adapters: list[SourceAdapter]

    def register(self, adapter: SourceAdapter) -> None: ...

    def find_adapter(self, url: str) -> SourceAdapter | None:
        """Find first adapter that can handle this URL."""
        for adapter in self.adapters:
            if adapter.can_handle(url):
                return adapter
        return None
```

---

### 2. Normalized Item & Feature Interface

```python
@dataclass
class Item:
    """Normalized item stored in database."""
    id: str                       # internal UUID
    source_id: str
    external_id: str
    url: str
    title: str
    creator_name: str
    published_at: datetime
    ingested_at: datetime
    content_type: str             # "video", "article", "audio", etc.

    # Extensible metadata - common fields extracted, rest preserved
    metadata: dict[str, Any]

    # Seen state (MVP - no full UserItemState table yet)
    seen: bool = False
    hidden: bool = False


class FeatureExtractor(ABC):
    """Interface for extracting ranking features from an item."""

    @abstractmethod
    def name(self) -> str:
        """Unique name for this feature extractor."""
        pass

    @abstractmethod
    def extract(self, item: Item) -> dict[str, float]:
        """Extract feature(s) from item. Returns feature_name -> value."""
        pass


# Example extractors (implement later):
# - FreshnessExtractor: days_since_published
# - SourceAffinityExtractor: user's historical engagement with source
# - ContentTypeExtractor: one-hot encoding of content type
# - DurationExtractor: normalized duration for video/audio
```

**Feature Registry:**
```python
class FeatureRegistry:
    extractors: list[FeatureExtractor]

    def register(self, extractor: FeatureExtractor) -> None: ...

    def extract_all(self, item: Item) -> dict[str, float]:
        """Run all extractors, return combined feature dict."""
        features = {}
        for ext in self.extractors:
            features.update(ext.extract(item))
        return features
```

---

### 3. Ranking Pipeline (No-op MVP)

```python
class RankingPipeline:
    """Scores and ranks items for the feed."""

    def __init__(self, feature_registry: FeatureRegistry):
        self.feature_registry = feature_registry

    def score(self, item: Item) -> float:
        """Score a single item. MVP: just use recency."""
        # Extract features (for logging/future use)
        features = self.feature_registry.extract_all(item)

        # MVP scoring: newer = higher score
        age_seconds = (datetime.utcnow() - item.published_at).total_seconds()
        return -age_seconds  # negative so newer = higher

    def rank(self, items: list[Item]) -> list[Item]:
        """Return items sorted by score descending."""
        return sorted(items, key=lambda i: self.score(i), reverse=True)
```

---

### 4. Store Interface + Implementations

Abstract interface with swappable backends.

```python
from abc import ABC, abstractmethod

class Store(ABC):
    """Abstract persistence layer for sources and items."""

    # Sources
    @abstractmethod
    def add_source(self, info: SourceInfo) -> str: ...

    @abstractmethod
    def list_sources(self) -> list[SourceInfo]: ...

    @abstractmethod
    def get_source(self, source_id: str) -> SourceInfo | None: ...

    @abstractmethod
    def update_source_poll_time(self, source_id: str, polled_at: datetime) -> None: ...

    @abstractmethod
    def disable_source(self, source_id: str) -> None: ...

    # Items
    @abstractmethod
    def upsert_item(self, item: Item) -> None: ...

    @abstractmethod
    def get_items(
        self,
        seen: bool | None = None,
        hidden: bool = False,
        limit: int = 50,
    ) -> list[Item]: ...

    @abstractmethod
    def get_item(self, item_id: str) -> Item | None: ...

    @abstractmethod
    def mark_seen(self, item_id: str) -> None: ...

    @abstractmethod
    def mark_hidden(self, item_id: str) -> None: ...

    # Lifecycle
    @abstractmethod
    def close(self) -> None: ...
```

**SQLite Implementation:**
```python
class SQLiteStore(Store):
    """SQLite-backed store. Good for production single-user."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        """Create tables if not exist."""
        ...

    # ... implement all abstract methods ...
```

**File-based Implementation (JSON):**
```python
class FileStore(Store):
    """JSON file-backed store. Simple, inspectable, good for testing."""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.sources_file = self.data_dir / "sources.json"
        self.items_file = self.data_dir / "items.json"
        self._load()

    def _load(self) -> None:
        """Load data from JSON files."""
        self._sources: dict[str, SourceInfo] = {}
        self._items: dict[str, Item] = {}
        if self.sources_file.exists():
            self._sources = self._parse_sources(json.loads(self.sources_file.read_text()))
        if self.items_file.exists():
            self._items = self._parse_items(json.loads(self.items_file.read_text()))

    def _save(self) -> None:
        """Persist to JSON files."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sources_file.write_text(json.dumps(self._serialize_sources(), indent=2))
        self.items_file.write_text(json.dumps(self._serialize_items(), indent=2))

    # ... implement all abstract methods, call _save() after mutations ...
```

**Store Factory:**
```python
from enum import Enum

class StoreType(Enum):
    SQLITE = "sqlite"
    FILE = "file"

def create_store(store_type: StoreType, path: str) -> Store:
    """Factory to create store by type."""
    match store_type:
        case StoreType.SQLITE:
            return SQLiteStore(path)
        case StoreType.FILE:
            return FileStore(path)
        case _:
            raise ValueError(f"Unknown store type: {store_type}")
```

**Config:**
```python
@dataclass
class Config:
    store_type: StoreType = StoreType.SQLITE
    store_path: str = "~/.omnifeed/data"

    @classmethod
    def load(cls, path: str = "~/.omnifeed/config.json") -> "Config": ...

    def create_store(self) -> Store:
        return create_store(self.store_type, self.store_path)
```

**Migration between stores:**
```python
def migrate_store(source: Store, target: Store) -> None:
    """Copy all data from source store to target store."""
    # Migrate sources
    for src in source.list_sources():
        target.add_source(src)

    # Migrate items
    for item in source.get_items(seen=None, hidden=None, limit=None):
        target.upsert_item(item)

# Usage:
# old_store = FileStore("~/.omnifeed/data")
# new_store = SQLiteStore("~/.omnifeed/data.db")
# migrate_store(old_store, new_store)
```

---

### 5. CLI Interface (MVP Frontend)

```
omni-feed sources add <url>       # resolve and add source
omni-feed sources list            # show all sources
omni-feed sources poll [source]   # poll one or all sources

omni-feed feed                    # show ranked feed (unseen)
omni-feed feed --all              # include seen
omni-feed feed --limit 20         # control count

omni-feed open <item_id>          # open URL in browser, mark seen
omni-feed seen <item_id>          # mark seen without opening
omni-feed hide <item_id>          # hide permanently
```

**Example output:**
```
$ omni-feed feed

  #   Age     Source              Title
  1   2h      @simonwillison      SQLite 3.45 Released
  2   4h      ArXiv               Attention Is All You Need (v2)
  3   5h      Hacker News         Show HN: I built a thing
  4   1d      @karpathy           Let's build GPT from scratch

> open 1
Opening https://... (marked as seen)
```

---

### MVP File Structure

```
omni-feed/
├── omnifeed/
│   ├── __init__.py
│   ├── models.py              # Item, SourceInfo, RawItem dataclasses
│   ├── config.py              # Config loading, store factory
│   ├── store/
│   │   ├── __init__.py        # Store ABC, create_store factory
│   │   ├── base.py            # Store abstract base class
│   │   ├── sqlite.py          # SQLiteStore implementation
│   │   ├── file.py            # FileStore (JSON) implementation
│   │   └── migrate.py         # migrate_store utility
│   ├── adapters/
│   │   ├── __init__.py        # AdapterRegistry
│   │   ├── base.py            # SourceAdapter ABC
│   │   ├── rss.py             # RSSAdapter
│   │   └── youtube.py         # YouTubeAdapter
│   ├── ranking/
│   │   ├── __init__.py        # FeatureRegistry, RankingPipeline
│   │   ├── base.py            # FeatureExtractor ABC
│   │   └── extractors.py      # FreshnessExtractor, etc.
│   └── cli.py                 # CLI entry point
├── tests/
│   ├── test_store.py          # Test both store implementations
│   ├── test_adapters.py
│   └── test_ranking.py
├── pyproject.toml
└── README.md
```

---

### MVP Milestones (ordered)

1. **Data model + store** - models.py, store.py with SQLite
2. **Adapter interface + RSS** - base.py, rss.py (simplest source)
3. **CLI: add source + poll** - can add RSS feed and pull items
4. **CLI: feed display** - chronological list of items
5. **CLI: seen/hide** - basic state management
6. **Ranking scaffold** - FeatureExtractor interface, no-op pipeline
7. **YouTube adapter** - second source type to validate abstraction

---

## Future Milestones (Post-MVP)

### M2: Feedback Loop
- [ ] FeedbackEvent model and storage
- [ ] Event capture in CLI (implicit: opened, explicit: hide)
- [ ] Filter presets (unseen, in-progress, saved)

### M3: Basic Ranking
- [ ] Implement feature extractors (freshness, source affinity)
- [ ] Weighted scoring formula
- [ ] Diversity injection (don't stack same source)

### M4: Web UI
- [ ] Replace CLI with desktop web app
- [ ] Rich item cards with thumbnails
- [ ] Keyboard navigation

### M5: Discovery & Entities
- [ ] Discovery mode
- [ ] Entity extraction and linking
- [ ] Entity management view

### M6: Trained Ranking
- [ ] Feature extraction pipeline
- [ ] Model training on feedback data
- [ ] A/B testing infrastructure
