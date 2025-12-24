# Multi-Objective Ranking

## Problem

A single linear ranker presumes a known, static objective. In reality, user goals shift over time—flipping between different objectives to optimize:

- Happiness / entertainment
- Financial success
- Intellectual growth
- Social connection
- Career advancement
- Creative inspiration
- etc.

## Proposed Evolution

### Phase 1: Explicit Objective Declaration
User declares the type of engagement after consuming content. We train separate rankers (or a multi-head model) that estimate value per objective. Ranking uses the estimated value for the user's currently-selected objective.

### Phase 2: Manual Objective Switching
Allow users to toggle through objectives in the UI. "Show me content for intellectual growth" vs "Show me content for relaxation." Each mode uses its corresponding ranker/head.

### Phase 3: Dynamic Mixing
Instead of discrete switching, maintain a mixture of objectives. Shift balance toward objectives the user engages with more. If user keeps clicking "intellectual growth" content even when in "relaxation" mode, the system learns their actual current intent.

### Phase 4: Emergent Clusters
Remove manual reward-type tagging entirely. Identify natural clusters of engagement patterns from behavioral signals alone. The system discovers objective-types rather than having them predefined.

## Current State (Bootstrap for Phase 1)

We already have manually annotated data via `ExplicitFeedback`:
```
reward_score: float          # 0.0 - 5.0
selections: {"reward_type": ["entertainment", "curiosity"], ...}
```

Training signal per objective:
- **Selected types** → use `reward_score` as target
- **Unselected types** → use `0.0` as target

This gives us per-objective reward labels from existing data without schema changes.

## Implications

- Model architecture: multi-head or mixture-of-experts rather than single output
- UI: objective selector, possibly auto-suggested based on time/context
- Feedback: engagement patterns become signal for objective inference
- Cold start: may still need some explicit tagging initially to bootstrap clusters
