# OmniFeed

Unified content feed aggregator with personalized ranking.

## Installation

```bash
# Python backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Web frontend
cd web && npm install
```

## Running

### Web UI (recommended)

```bash
./dev.sh
```

Opens API on :8000 and frontend on :5173. Visit http://localhost:5173

### CLI

```bash
# Add a source
omni-feed sources add https://example.com/feed.xml

# Poll for new items
omni-feed sources poll

# View feed
omni-feed feed

# Open an item (by # from feed)
omni-feed open 1
```

## Architecture

```
omnifeed/           # Core Python library
  ├── models.py     # Data models
  ├── store/        # SQLite + JSON backends
  ├── adapters/     # Source adapters (RSS, etc.)
  └── ranking/      # Ranking pipeline

api/                # FastAPI server
  └── main.py       # REST API

web/                # React frontend
  └── src/
      ├── api/      # API client
      └── components/
```
