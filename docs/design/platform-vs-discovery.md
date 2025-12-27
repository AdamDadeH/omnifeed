# Platform vs Discovery Source Architecture

## Core Distinction

### Platform
**Delivers consumable media bytes or renderable content.**

Examples:
- YouTube → video streams
- Qobuz → audio streams
- Bandcamp → audio streams + purchases
- Spotify → audio streams
- Netflix → video streams
- Websites → HTML/articles
- Podcasts → audio files

Characteristics:
- Has playback/rendering capability
- Provides the actual content
- May have its own discovery (recommendations, trending)
- Requires authentication/subscription for access

### Discovery Source
**Provides signals about what content exists and why you should engage with it.**

Examples:
- RateYourMusic charts → "top albums 2025" with rankings
- Letterboxd lists → "best horror films" with ratings
- Goodreads → book recommendations
- Newsletter recommendations → curated picks with context
- Podcast mentions → "we loved this album"
- Friend recommendations → social signals
- Critics/reviewers → professional opinions
- Award lists → Grammy nominees, Oscar winners

Characteristics:
- Points TO content, doesn't host it
- Provides context/reason (rank, rating, review, who recommended)
- May reference content across multiple platforms
- Often human-curated or algorithm-generated

## Data Model

```
┌─────────────────────────────────────────────────────────────────┐
│                         CONTENT                                  │
│  (The abstract "thing" - an album, film, article, etc.)         │
├─────────────────────────────────────────────────────────────────┤
│  id: string                                                      │
│  content_type: album | film | book | article | video | podcast  │
│  title: string                                                   │
│  creators: Creator[]                                             │
│  canonical_ids: { musicbrainz?, imdb?, isbn?, doi?, ... }       │
│  metadata: { year, genre, duration, ... }                        │
└─────────────────────────────────────────────────────────────────┘
           │                                    │
           │ 1:N                                │ 1:N
           ▼                                    ▼
┌─────────────────────────┐        ┌─────────────────────────────┐
│   PLATFORM_INSTANCE     │        │    DISCOVERY_SIGNAL         │
│  (Where to consume it)  │        │  (Why to consume it)        │
├─────────────────────────┤        ├─────────────────────────────┤
│  content_id: FK         │        │  content_id: FK             │
│  platform: Platform     │        │  source: DiscoverySource    │
│  platform_id: string    │        │  signal_type: enum          │
│  url: string            │        │  rank: int?                 │
│  availability: enum     │        │  rating: float?             │
│  quality_tiers: []      │        │  context: string?           │
│  price: Money?          │        │  recommender: string?       │
│  region_locks: []       │        │  discovered_at: datetime    │
└─────────────────────────┘        └─────────────────────────────┘

Signal Types:
- chart_position (rank 1-100 on RYM top albums)
- user_rating (4.5 stars on Letterboxd)
- recommendation (friend said "you'd love this")
- mention (podcast discussed this)
- award (Grammy winner 2025)
- trending (viral this week)
- algorithmic (Spotify thinks you'll like this)
```

## Platform Registry

```python
@dataclass
class Platform:
    id: str                          # "qobuz", "youtube", "spotify"
    name: str                        # "Qobuz"
    content_types: list[ContentType] # [AUDIO]
    capabilities: list[Capability]   # [STREAM, DOWNLOAD, PURCHASE]
    auth_required: bool
    api_available: bool

    # Methods
    def search(query: str) -> list[PlatformMatch]
    def get_content(platform_id: str) -> ContentMetadata
    def get_stream_url(platform_id: str) -> StreamInfo
    def match_content(content: Content) -> PlatformMatch | None

class Capability(Enum):
    STREAM = "stream"           # Can play in-app
    DOWNLOAD = "download"       # Can download for offline
    PURCHASE = "purchase"       # Can buy permanently
    EMBED = "embed"            # Can embed (YouTube, Spotify)
    RENDER = "render"          # Can render (articles, HTML)
```

## Discovery Source Registry

```python
@dataclass
class DiscoverySource:
    id: str                          # "rym_charts", "letterboxd_lists"
    name: str                        # "RateYourMusic Charts"
    source_type: str                 # "chart", "list", "feed", "social"
    content_types: list[ContentType] # [AUDIO] for RYM

    # What platforms might have this content
    typical_platforms: list[str]     # ["qobuz", "spotify", "bandcamp"]

    # Scraping/polling config
    poll_config: PollConfig

    # Methods
    def fetch_signals() -> list[DiscoverySignal]
    def extract_content_info(signal) -> ContentInfo  # title, artist, year

@dataclass
class DiscoverySignal:
    source_id: str
    content_info: ContentInfo        # What we know about the content
    signal_type: SignalType
    rank: int | None
    rating: float | None
    context: str | None              # "Best album of 2025"
    url: str                         # Link to the discovery page
    discovered_at: datetime
```

## Content Resolution Flow

```
Discovery Signal                    Content                     Platform Instance
      │                                │                               │
      │  1. Extract content info       │                               │
      │  ─────────────────────────────>│                               │
      │     (title, artist, year)      │                               │
      │                                │                               │
      │                                │  2. Find/create Content       │
      │                                │  ─────────────────────────────│
      │                                │     Look up by canonical ID   │
      │                                │     or fuzzy match            │
      │                                │                               │
      │                                │  3. Match to platforms        │
      │                                │  ─────────────────────────────>
      │                                │     Search Qobuz, Spotify,    │
      │                                │     Bandcamp for this album   │
      │                                │                               │
      │                                │  4. Store platform instances  │
      │                                │  <─────────────────────────────
      │                                │     qobuz_id, spotify_id, etc │
      │                                │                               │
      │  5. Link signal to content     │                               │
      │  <─────────────────────────────│                               │
      │     "RYM #3 2025" → album_xyz  │                               │
```

## Example: RateYourMusic Charts

```python
class RYMChartSource(DiscoverySource):
    """Scrapes RateYourMusic chart pages for album rankings."""

    def fetch_signals(self, chart_url: str) -> list[DiscoverySignal]:
        # Scrape https://rateyourmusic.com/charts/top/album/2025/
        # Extract: rank, album title, artist, year, RYM rating

        signals = []
        for row in scrape_chart(chart_url):
            signals.append(DiscoverySignal(
                source_id=self.id,
                content_info=ContentInfo(
                    content_type=ContentType.ALBUM,
                    title=row.album_title,
                    creators=[row.artist_name],
                    year=row.year,
                    external_ids={"rym": row.rym_album_id},
                ),
                signal_type=SignalType.CHART_POSITION,
                rank=row.position,
                rating=row.rym_rating,
                context=f"#{row.position} on RYM Top Albums 2025",
                url=row.rym_url,
            ))
        return signals

class QobuzPlatform(Platform):
    """Qobuz music streaming platform."""

    def match_content(self, content: Content) -> PlatformMatch | None:
        # Search Qobuz API for album by title + artist
        results = self.api.search_albums(
            query=f"{content.title} {content.creators[0].name}"
        )

        # Fuzzy match and verify
        for result in results:
            if self._is_match(content, result):
                return PlatformMatch(
                    platform_id=result.qobuz_id,
                    url=result.url,
                    availability=Availability.STREAM,
                    quality_tiers=result.formats,  # FLAC, Hi-Res, etc
                    confidence=0.95,
                )
        return None
```

## UI Implications

### Feed View
Items show both discovery context AND available platforms:

```
┌────────────────────────────────────────────────────────────┐
│  Waxahatchee - Tigers Blood                                │
│  ────────────────────────────────────────────────────────  │
│  🏆 #3 on RYM Top Albums 2025  ·  ⭐ 3.92                   │
│  ────────────────────────────────────────────────────────  │
│  Available on:  [Qobuz Hi-Res]  [Spotify]  [Bandcamp]      │
└────────────────────────────────────────────────────────────┘
```

### Platform Preference
User can set preferred platforms for each content type:
- Audio: Qobuz > Bandcamp > Spotify
- Video: YouTube > Netflix
- Articles: Direct > Archive

When opening content, use highest-preference available platform.

## Migration Path

1. **Current Item model** → becomes Content + PlatformInstance
2. **Current Source** → splits into Platform and DiscoverySource
3. **Current creator extraction** → feeds into Content.creators
4. **Current canonical_ids** → used for cross-platform matching

## Next Steps

1. Define Content entity (abstract representation)
2. Define PlatformInstance (where to consume)
3. Define DiscoverySignal (why to consume)
4. Build content resolution/matching pipeline
5. Add RYM chart scraper as first DiscoverySource
6. Add Qobuz search as first Platform matcher
