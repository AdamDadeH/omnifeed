# Feedback System

OmniFeed captures two types of feedback to learn user preferences:

1. **Implicit feedback** - Automatic signals from user behavior
2. **Explicit feedback** - User-provided ratings and categorizations

## Implicit Feedback (FeedbackEvent)

Captured automatically during content consumption:

| Event Type | Payload | When Captured |
|------------|---------|---------------|
| `click` | `{}` | User opens an item |
| `reading_complete` | `time_spent_ms`, `max_scroll_pct`, `completed`, `scroll_events` | User closes ReaderPane |
| `watching_complete` | `time_spent_ms`, `progress_pct`, `completed` | User finishes video |
| `listening_complete` | `time_spent_ms`, `progress_pct`, `completed` | User finishes audio |

### API

```
POST /api/feedback
{
  "item_id": "abc123",
  "event_type": "reading_complete",
  "payload": {
    "time_spent_ms": 45000,
    "max_scroll_pct": 87.5,
    "completed": false,
    "scroll_events": 12
  }
}
```

## Explicit Feedback

User-provided ratings captured when closing the reader. Consists of:

### Reward Score (0.0 - 5.0)

A continuous score representing **reward per unit time**:
- 0.0 = Complete waste of time
- 2.5 = Neutral / met expectations
- 5.0 = Exceptionally valuable

### Feedback Dimensions

Configurable categorization dimensions stored in the database. Each dimension has multiple options that can be selected.

**Default dimensions seeded on startup:**

#### reward_type (multi-select)
What type of value did this content provide?

| Option | Description |
|--------|-------------|
| Entertainment | Pure enjoyment or fun |
| Curiosity | Satisfied intellectual curiosity |
| Foundational Knowledge | Core knowledge or skills |
| Targeted Expertise | Specific expertise I need |

#### replayability (single-select)
How likely are you to revisit this content?

| Option | Description |
|--------|-------------|
| One and Done | Liked it but won't revisit |
| Might Revisit | Could see myself coming back |
| Will Definitely Revisit | So good I'll re-consume |
| Reference Material | Will come back to look things up |

### Notes

Free-form text field for capturing unstructured thoughts. Useful for:
- Training future models on nuanced preferences
- Personal annotations
- Capturing context-specific reactions

### API

**Get available dimensions:**
```
GET /api/feedback/dimensions

Response:
[
  {
    "id": "reward_type",
    "name": "reward_type",
    "description": "What type of value did this content provide?",
    "allow_multiple": true,
    "options": [
      {"id": "reward_type_entertainment", "label": "Entertainment", ...},
      ...
    ]
  },
  ...
]
```

**Submit explicit feedback:**
```
POST /api/feedback/explicit
{
  "item_id": "abc123",
  "reward_score": 4.2,
  "selections": {
    "reward_type": ["reward_type_curiosity", "reward_type_foundational"],
    "replayability": ["replayability_might_revisit"]
  },
  "notes": "Great introduction to the topic, bookmarking for later",
  "completion_pct": 95.0,
  "is_checkpoint": false
}
```

**Get feedback for an item:**
```
GET /api/feedback/explicit/{item_id}
```

## Data Model

### FeedbackDimension

```python
@dataclass
class FeedbackDimension:
    id: str                       # "reward_type"
    name: str                     # Display name
    description: str | None       # Shown to user
    allow_multiple: bool          # Multi-select vs single
    active: bool                  # Soft delete
    created_at: datetime
```

### FeedbackOption

```python
@dataclass
class FeedbackOption:
    id: str                       # "reward_type_entertainment"
    dimension_id: str             # FK to dimension
    label: str                    # "Entertainment"
    description: str | None       # Tooltip text
    sort_order: int               # Display order
    active: bool                  # Soft delete
    created_at: datetime
```

### ExplicitFeedback

```python
@dataclass
class ExplicitFeedback:
    id: str
    item_id: str
    timestamp: datetime
    reward_score: float           # 0.0 - 5.0
    selections: dict[str, list[str]]  # dimension_id -> option_ids
    notes: str | None
    completion_pct: float | None  # Where user was when rating
    is_checkpoint: bool           # Periodic check-in vs final
```

## Extending Dimensions

Dimensions are stored in the database and can be extended without code changes:

```python
from omnifeed.models import FeedbackDimension, FeedbackOption

# Add a new dimension
store.add_dimension(FeedbackDimension(
    id="difficulty",
    name="difficulty",
    description="How challenging was this content?",
    allow_multiple=False,
))

# Add options
store.add_option(FeedbackOption(
    id="difficulty_easy",
    dimension_id="difficulty",
    label="Easy",
    description="Comfortable, no struggle",
    sort_order=0,
))
```

Old feedback retains original values even if dimensions/options change.

## Checkpoint Feedback

For long-form content, periodic check-ins can be recorded:

```python
ExplicitFeedback(
    item_id="abc123",
    reward_score=3.5,
    completion_pct=50.0,
    is_checkpoint=True,  # Not final rating
    ...
)
```

This allows tracking how engagement evolves during consumption.
