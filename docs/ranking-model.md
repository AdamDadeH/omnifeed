# Ranking Model

OmniFeed uses a multi-head ML model to rank content based on predicted engagement and reward.

## Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Content Embeddings                        │
│         (sentence-transformers: all-MiniLM-L6-v2)           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Feature Vector                            │
│  [embedding] + [source_stats] + [metadata_features]         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                       StandardScaler
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
     LogisticRegression                    Ridge
      P(click) → [0,1]              E[reward] → [0,5]
              │                               │
              └───────────────┬───────────────┘
                              ▼
                    Final Score = P(click) × E[reward]
```

## Installation

Install ML dependencies:

```bash
pip install -e ".[ml]"
```

This installs:
- `sentence-transformers` - Text embeddings
- `torch` - Neural network backend
- `scikit-learn` - Classification/regression models

## Embeddings

### Generation

Embeddings are generated automatically on ingest during polling:

```python
# In poll_source():
from omnifeed.ranking.embeddings import get_embedding_service

embedding_service = get_embedding_service()
embeddings = embedding_service.embed_items(new_items)
for item, embedding in zip(new_items, embeddings):
    item.embedding = embedding
```

### Text Extraction

The embedding is computed from:
1. Item title
2. Creator name
3. Content text (first 1000 chars) or description (first 500 chars)

```python
def get_item_text(self, item: Item) -> str:
    parts = [item.title]
    if item.creator_name:
        parts.append(f"by {item.creator_name}")
    if content_text := item.metadata.get("content_text"):
        parts.append(content_text[:1000])
    return " ".join(parts)
```

### Model

Default: `all-MiniLM-L6-v2` (384 dimensions, fast, good quality)

To use a different model:

```python
from omnifeed.ranking.embeddings import EmbeddingService, SentenceTransformerEmbedder

embedder = SentenceTransformerEmbedder("all-mpnet-base-v2")  # 768 dim, higher quality
service = EmbeddingService(model=embedder)
```

### Refreshing Embeddings

For existing items without embeddings, or to regenerate all embeddings:

```bash
# Generate embeddings for items missing them
curl -X POST "http://localhost:8000/api/model/refresh-embeddings"

# Force regenerate all embeddings
curl -X POST "http://localhost:8000/api/model/refresh-embeddings?force=true"

# Only refresh a specific source
curl -X POST "http://localhost:8000/api/model/refresh-embeddings?source_id=abc123"
```

Response:
```json
{
  "updated_count": 45,
  "skipped_count": 10,
  "failed_count": 0
}
```

## Feature Vector

The model uses these features:

| Feature | Dimensions | Source |
|---------|------------|--------|
| Content embedding | 384 | sentence-transformers |
| Source avg_reward | 1 | Aggregate from explicit feedback |
| Source click_rate | 1 | clicks / item_count |
| Source engagement_count | 1 | Normalized engagement volume |
| Has thumbnail | 1 | Boolean |
| Title length | 1 | Normalized |
| Content type one-hot | 7 | article, video, audio, etc. |

**Total: ~396 features**

## Training

### Training Data

The model trains only on items with engagement:
- Clicked items (from `click` events)
- Rated items (from explicit feedback)

```python
from omnifeed.ranking.model import collect_training_data

examples = collect_training_data(store)
# Returns list of TrainingExample with:
#   - embedding
#   - clicked (bool)
#   - reward_score (float or None)
#   - metadata features
```

### Training Process

```python
from omnifeed.ranking.model import get_ranking_model, DEFAULT_MODEL_PATH

model = get_ranking_model()
result = model.train(store)

if result["status"] == "success":
    model.save(DEFAULT_MODEL_PATH)
    print(f"Trained on {result['example_count']} examples")
```

### API Trigger

```bash
# Train the model
curl -X POST http://localhost:8000/api/model/train

# Check status
curl http://localhost:8000/api/model/status
```

### Minimum Data

- Requires at least 5 training examples
- Reward model requires at least 3 items with explicit feedback
- Falls back to source averages when insufficient data

## Scoring

### Individual Item

```python
model = get_ranking_model()
click_prob, expected_reward = model.predict(item)
score = model.score(item)  # = click_prob * expected_reward
```

### Ranking Pipeline

The `RankingPipeline` automatically uses the ML model when available:

```python
from omnifeed.ranking.pipeline import RankingPipeline

pipeline = RankingPipeline(use_ml_model=True)
ranked_items = pipeline.rank(items)
```

### Fallback Behavior

When ML model isn't available or item has no embedding:

```python
# Recency-based fallback (newer = higher score)
age_seconds = (now - item.published_at).total_seconds()
recency_score = max(0, 5 - (age_seconds / 86400))  # 1 day old ≈ 4.0
```

## Diversity Injection

To prevent feed domination by a single source:

```python
ranked = pipeline.rank_with_diversity(items, max_per_source=3)
```

This limits consecutive items from the same source, deferring extras to the end.

## Cold Start

New items without engagement data:

1. **With embedding**: Uses source average reward and default click probability (0.5)
2. **Without embedding**: Falls back to recency scoring

```python
if not model.is_trained or item.embedding is None:
    source = source_stats.get(item.source_id)
    default_reward = source.avg_reward if source else 2.5
    return 0.5, default_reward
```

## Model Persistence

Models are saved to `~/.omnifeed/ranking_model.pkl`:

```python
from omnifeed.ranking.model import DEFAULT_MODEL_PATH

model.save(DEFAULT_MODEL_PATH)  # Save
model.load(DEFAULT_MODEL_PATH)  # Load on startup
```

The model file contains:
- Trained sklearn models (LogisticRegression, Ridge)
- StandardScaler for feature normalization
- Source statistics snapshot
- Training state flag

## Future Improvements

Planned enhancements:

1. **Incremental updates** - Update model with new feedback without full retrain
2. **Learned source embeddings** - Replace aggregate stats with learned representations
3. **Time-aware features** - Model engagement patterns by time of day/week
4. **Exploration bonus** - Boost new/unknown content for discovery
5. **Multi-task learning** - Jointly predict completion rate, time spent
