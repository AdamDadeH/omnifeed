# OmniFeed Architecture

## High-Level Overview

```mermaid
flowchart TB
    subgraph Clients
        WEB[Web UI<br/>React + TypeScript]
        CLI[CLI<br/>Click]
    end

    subgraph API["API Layer (FastAPI)"]
        ROUTES[Routes]
    end

    subgraph Core["Core Services"]
        STORE[Store]
        RANKING[Ranking Pipeline]
        DISCOVERY[Discovery Engine]
        SEARCH[Search Service]
    end

    subgraph Sources["Source Adapters"]
        REGISTRY[Plugin Registry]
        ADAPTERS[Adapters]
    end

    WEB --> ROUTES
    CLI --> ROUTES
    CLI --> STORE

    ROUTES --> STORE
    ROUTES --> RANKING
    ROUTES --> DISCOVERY
    ROUTES --> SEARCH
    ROUTES --> REGISTRY

    RANKING --> STORE
    DISCOVERY --> STORE
    DISCOVERY --> SEARCH
    SEARCH --> REGISTRY
    REGISTRY --> ADAPTERS
```

## Data Layer

```mermaid
flowchart TB
    subgraph Models["Models (omnifeed/models.py)"]
        SOURCE[Source]
        ITEM[Item]
        ATTRIBUTION[ItemAttribution]
        FEEDBACK[FeedbackEvent]
        EXPLICIT[ExplicitFeedback]
        DIMENSION[FeedbackDimension]
    end

    subgraph Store["Store (omnifeed/store/)"]
        BASE_STORE[Store ABC]
        SQLITE[SQLiteStore]
        FILE[FileStore]
    end

    BASE_STORE --> SQLITE
    BASE_STORE --> FILE

    SQLITE --> SOURCE
    SQLITE --> ITEM
    SQLITE --> ATTRIBUTION
    SQLITE --> FEEDBACK
    SQLITE --> EXPLICIT

    ITEM --> SOURCE
    ATTRIBUTION --> ITEM
    ATTRIBUTION --> SOURCE
    FEEDBACK --> ITEM
    EXPLICIT --> ITEM
```

## Source Adapter System

```mermaid
flowchart TB
    subgraph Registry["Registry (omnifeed/sources/registry.py)"]
        PLUGIN_REG[PluginRegistry]
        DISCOVER[discover_plugins]
    end

    subgraph Base["Base (omnifeed/sources/base.py)"]
        ADAPTER_ABC[SourceAdapter ABC]
        SEARCH_ABC[SearchProvider ABC]
        PLUGIN[SourcePlugin]
        RAW_ITEM[RawItem]
        SOURCE_INFO[SourceInfo]
    end

    subgraph Adapters["Adapter Plugins"]
        YT[YouTube]
        BC[Bandcamp]
        QZ[Qobuz]
        RSS[RSS]
        SM[Sitemap]
        TT[TikTok]
    end

    DISCOVER --> PLUGIN_REG
    PLUGIN --> ADAPTER_ABC
    PLUGIN --> SEARCH_ABC

    YT --> ADAPTER_ABC
    BC --> ADAPTER_ABC
    QZ --> ADAPTER_ABC
    RSS --> ADAPTER_ABC
    SM --> ADAPTER_ABC
    TT --> ADAPTER_ABC

    ADAPTER_ABC --> SOURCE_INFO
    ADAPTER_ABC --> RAW_ITEM
```

## Ranking System

```mermaid
flowchart TB
    subgraph Pipeline["Pipeline (omnifeed/ranking/pipeline.py)"]
        RANK_PIPE[RankingPipeline]
        RETRIEVER[Retriever ABC]
        ALL_RET[AllRetriever]
        SOURCE_RET[SourceRetriever]
    end

    subgraph Model["Model (omnifeed/ranking/model.py)"]
        RANK_MODEL[RankingModel]
        FEATURES[Feature Extraction]
        TRAIN[Training]
    end

    subgraph Embeddings["Embeddings"]
        EMB_SVC[EmbeddingService]
        TRANSCRIPT[TranscriptEmbeddings]
    end

    RANK_PIPE --> RETRIEVER
    RETRIEVER --> ALL_RET
    RETRIEVER --> SOURCE_RET

    RANK_PIPE --> RANK_MODEL
    RANK_MODEL --> FEATURES
    RANK_MODEL --> TRAIN

    RANK_PIPE --> EMB_SVC
    EMB_SVC --> TRANSCRIPT
```

## Discovery System

```mermaid
flowchart TB
    subgraph LLM["LLM (omnifeed/discovery/llm.py)"]
        LLM_ABC[LLMBackend ABC]
        OLLAMA[OllamaBackend]
        OPENAI[OpenAIBackend]
        ANTHROPIC[AnthropicBackend]
    end

    subgraph Interests["Interests (omnifeed/discovery/interests.py)"]
        EXTRACT[extract_interests_from_items]
        PROFILE[InterestProfile]
    end

    subgraph Engine["Engine (omnifeed/discovery/engine.py)"]
        DISC_ENG[DiscoveryEngine]
        FROM_PROMPT[discover_from_prompt]
        FROM_INT[discover_from_interests]
    end

    GET_LLM[get_llm_backend] --> ANTHROPIC
    GET_LLM --> OPENAI
    GET_LLM --> OLLAMA

    DISC_ENG --> GET_LLM
    DISC_ENG --> EXTRACT
    EXTRACT --> PROFILE

    DISC_ENG --> FROM_PROMPT
    DISC_ENG --> FROM_INT
```

## API Routes

```mermaid
flowchart LR
    subgraph Sources
        GET_SRC[GET /sources]
        POST_SRC[POST /sources]
        POLL[POST /sources/id/poll]
    end

    subgraph Feed
        GET_FEED[GET /feed]
        GET_ITEM[GET /items/id]
        MARK_SEEN[POST /items/id/seen]
        GET_ATTR[GET /items/id/attributions]
    end

    subgraph Feedback
        POST_FB[POST /feedback]
        POST_EXPLICIT[POST /feedback/explicit]
    end

    subgraph Discovery
        GET_DISC[GET /discover]
        GET_INT[GET /discover/interests]
    end

    subgraph Search
        SEARCH[GET /search]
    end

    subgraph Model
        TRAIN[POST /model/train]
        STATUS[GET /model/status]
    end
```

## Directory Structure

```
omnifeed/
├── models.py           # Core data models
├── config.py           # Configuration
├── cli.py              # CLI commands
├── store/
│   ├── base.py         # Store ABC
│   ├── sqlite.py       # SQLite implementation
│   └── file.py         # JSON file implementation
├── sources/
│   ├── base.py         # Adapter/SearchProvider ABCs
│   ├── registry.py     # Plugin discovery
│   ├── youtube/        # YouTube adapter + search
│   ├── bandcamp/       # Bandcamp adapter + search
│   ├── qobuz/          # Qobuz adapter + search
│   ├── rss/            # RSS adapter + Feedly search
│   ├── sitemap/        # Sitemap adapter
│   └── tiktok/         # TikTok adapter
├── adapters/
│   └── __init__.py     # Compatibility shim → sources/
├── ranking/
│   ├── pipeline.py     # Retrieval + scoring
│   ├── model.py        # ML model
│   └── embeddings.py   # Text embeddings
├── discovery/
│   ├── llm.py          # Multi-backend LLM
│   ├── interests.py    # Interest extraction
│   └── engine.py       # Discovery engine
└── search/
    ├── service.py      # Unified search service
    └── *.py            # Provider implementations

api/
└── main.py             # FastAPI routes

web/
└── src/                # React frontend
```
