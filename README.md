# OmniFeed

A unified content feed aggregator with personalized ML-powered ranking. Aggregate content from YouTube, RSS, Bandcamp, Qobuz, TikTok, and more into a single feed ranked by your preferences.

## Features

- **Multi-source aggregation**: YouTube channels/playlists, RSS/Atom feeds, Bandcamp artists/labels/fans, Qobuz artists/labels, TikTok (via RSSHub), sitemaps
- **ML-powered ranking**: Learn from your engagement to surface content you'll enjoy
- **Multi-objective ranking**: Filter feed by goal (entertainment, curiosity, learning, expertise)
- **Smart discovery**: LLM-powered source recommendations based on your interests
- **Inline rendering**: Watch YouTube, view articles, and browse content without leaving the app
- **Explicit feedback**: Rate content on multiple dimensions (entertainment, curiosity, foundational knowledge, etc.)
- **Engagement tracking**: Automatic scroll/watch progress tracking for implicit signals

## Quick Start

```bash
# Clone and setup
git clone <repo-url>
cd omni-feed

# One command to start everything
./dev.sh
```

Then open http://localhost:5173

## Installation

### Prerequisites

- Python 3.11+
- Node.js 18+
- (Optional) Ollama for LLM-powered discovery

### Backend Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install with all extras
pip install -e ".[dev,ml]"
```

### Frontend Setup

```bash
cd web
npm install
```

### Running

**Development (recommended):**
```bash
./dev.sh
# Opens API on :8000 and frontend on :5173
```

**Manual startup:**
```bash
# Terminal 1: API server
source .venv/bin/activate
uvicorn api.main:app --reload --port 8000

# Terminal 2: Frontend
cd web && npm run dev
```

## Usage Guide

### Adding Sources

1. Click **"+ Add"** in the sidebar
2. Choose a method:
   - **Search**: Search YouTube, Bandcamp, Qobuz by name
   - **Discover**: Get AI-powered recommendations based on your interests
   - **Add by URL**: Paste any supported URL directly

### Supported URL Formats

| Source | Example URLs |
|--------|-------------|
| YouTube | `https://youtube.com/@ChannelName`, `https://youtube.com/playlist?list=...` |
| RSS/Atom | `https://example.com/feed.xml`, `https://example.com/rss` |
| Bandcamp | `https://artist.bandcamp.com`, `https://bandcamp.com/username` (fan) |
| Qobuz | `https://www.qobuz.com/artist/...`, `https://www.qobuz.com/label/...` |
| TikTok | `https://tiktok.com/@username/video/123`, `tiktok:@username` |
| Sitemap | `sitemap:https://example.com/sitemap.xml?pattern=/articles/` |

### Browsing Content

- **All Items**: Shows ranked feed from all sources
- **Source filter**: Click a source in sidebar to view only its content
- **Objective filter**: Select an objective (entertainment, curiosity, etc.) to re-rank the feed
- **Show read**: Toggle to include already-seen items
- **Sources**: Manage sources (poll, delete, view status)
- **Stats**: View engagement statistics and train models
- **Refresh**: Polls the current source (or all sources) for new content

### Reading & Rating

1. Click any item to open it in the reader pane
2. Content renders inline (YouTube embeds, HTML articles, etc.)
3. When done, click **"Rate & Close"** or **"Mark Complete"**
4. Rate from 0-5 stars and optionally tag the content type:
   - Entertainment
   - Curiosity
   - Foundational Knowledge
   - Targeted Expertise

### Training Models

After providing feedback on 10+ items:
1. Go to **Stats** (top right)
2. View all models and their training status
3. Click **"Train"** on individual models or **"Train All"**

Two models are available:
- **Default**: General ranking based on click and reward prediction
- **Multi-Objective**: Separate reward heads for each objective type (requires selecting reward types during feedback)

## Discovery (LLM-Powered)

OmniFeed can suggest new sources based on your interests using a local or cloud LLM.

### Setup Options

**Option 1: Ollama (Local, Free)**
```bash
# Install Ollama: https://ollama.ai
ollama pull llama3.2  # or any model

# OmniFeed auto-detects running Ollama
```

**Option 2: OpenAI API**
```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4o-mini"  # optional, defaults to gpt-4o-mini
```

**Option 3: Anthropic API**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export ANTHROPIC_MODEL="claude-3-haiku-20240307"  # optional
```

### Using Discovery

1. Click **"+ Add"** → **"Discover"** tab
2. Choose mode:
   - **From My Interests**: Analyzes your liked content to suggest sources
   - **Custom Search**: Enter what you're looking for (e.g., "jazz piano tutorials")
3. Click **"Discover"** to get AI-powered recommendations

## Configuration

Config file: `~/.omnifeed/config.json`

```json
{
  "store_type": "sqlite",
  "store_path": "~/.omnifeed/data.db",
  "extra": {
    "youtube_api_key": "AIza...",
    "qobuz_app_id": "...",
    "qobuz_app_secret": "...",
    "rsshub_url": "http://localhost:1200",
    "proxitok_url": "http://localhost:8080"
  }
}
```

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `YOUTUBE_API_KEY` | YouTube Data API (optional, enables search) |
| `QOBUZ_APP_ID` | Qobuz API access |
| `QOBUZ_APP_SECRET` | Qobuz API access |
| `OLLAMA_URL` | Custom Ollama endpoint (default: http://localhost:11434) |
| `OLLAMA_MODEL` | Ollama model to use (default: auto-detected) |
| `OPENAI_API_KEY` | OpenAI API for discovery |
| `ANTHROPIC_API_KEY` | Anthropic API for discovery |
| `RSSHUB_URL` | Self-hosted RSSHub for TikTok feeds |
| `PROXITOK_URL` | Self-hosted ProxiTok for TikTok feeds |

## CLI Usage

```bash
# Add a source
omni-feed sources add https://youtube.com/@ChannelName

# List sources
omni-feed sources list

# Poll for new content
omni-feed sources poll

# View feed
omni-feed feed

# Open item by number
omni-feed open 1
```

## Architecture

```
omnifeed/                 # Core Python library
  ├── models.py           # Data models (Item, Source, Feedback)
  ├── config.py           # Configuration management
  ├── store/              # SQLite storage backend
  ├── sources/            # Source adapters
  │   ├── youtube/        # YouTube channels & playlists
  │   ├── rss/            # RSS/Atom feeds
  │   ├── bandcamp/       # Bandcamp artists, labels, fans
  │   ├── qobuz/          # Qobuz music catalog
  │   ├── tiktok/         # TikTok via RSSHub/ProxiTok
  │   └── sitemap/        # Website sitemaps
  ├── ranking/            # ML ranking pipeline
  │   ├── pipeline.py     # Retrieval + scoring
  │   ├── model.py        # Click & reward prediction
  │   └── embeddings.py   # Text embeddings
  ├── discovery/          # LLM-powered discovery
  │   ├── llm.py          # Multi-backend LLM abstraction
  │   ├── interests.py    # Interest extraction
  │   └── engine.py       # Discovery engine
  └── search/             # Source search providers

api/                      # FastAPI REST API
  └── main.py

web/                      # React + TypeScript frontend
  └── src/
      ├── api/            # API client
      ├── components/     # React components
      │   └── renderers/  # Content-type specific renderers
      └── App.tsx
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sources` | GET | List all sources |
| `/api/sources` | POST | Add a new source |
| `/api/sources/{id}/poll` | POST | Poll source for new items |
| `/api/feed` | GET | Get ranked feed |
| `/api/items/{id}` | GET | Get single item |
| `/api/items/{id}/seen` | POST | Mark item as seen |
| `/api/feedback` | POST | Record engagement event |
| `/api/feedback/explicit` | POST | Submit rating |
| `/api/discover` | GET | Get source recommendations |
| `/api/discover/interests` | GET | Get extracted interest profile |
| `/api/model/train` | POST | Train ranking model |
| `/api/search` | GET | Search for sources |

## Development

```bash
# Run tests
pytest

# Type checking
mypy omnifeed

# Linting
ruff check .

# Format
ruff format .
```

## Troubleshooting

**YouTube polling is slow**: Large channels fetch many videos on first sync. Subsequent polls are incremental.

**TikTok feeds not working**: Public RSSHub/ProxiTok instances are often blocked. Self-host for reliability.

**Model training fails**: Need at least 10 items with explicit feedback. Check Stats → Model Status for diagnostics.

**Discovery returns no results**: Ensure Ollama is running or API keys are set. Check `/api/discover/llm-status`.

## License

MIT
