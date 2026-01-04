"""Multi-objective ranking model with per-objective reward heads.

This model trains separate reward predictors for each objective type
(entertainment, curiosity, foundational, targeted). Users can then
rank content by their current objective.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from omnifeed.models import Content, ExplicitFeedback
from omnifeed.store.base import Store
from omnifeed.ranking.model import (
    TrainingExample,
    EmbeddingFusionLayer,
    SourceStats,
    TrainingDataStats,
    compute_source_stats,
)

logger = logging.getLogger(__name__)

# Objective types - must match FeedbackOption ids in reward_type dimension
OBJECTIVE_TYPES = ["entertainment", "curiosity", "foundational", "targeted"]

OBJECTIVE_LABELS = {
    "entertainment": "Entertainment",
    "curiosity": "Curiosity",
    "foundational": "Foundational Knowledge",
    "targeted": "Targeted Expertise",
}


@dataclass
class MultiObjectiveExample:
    """Training example with per-objective reward labels."""
    item_id: str
    embeddings_by_type: dict[str, list[float]]
    source_id: str
    clicked: bool

    # Per-objective rewards: objective -> score (0.0 if not selected)
    objective_rewards: dict[str, float] = field(default_factory=dict)

    # Metadata
    content_type: str = ""
    has_thumbnail: bool = False
    title_length: int = 0


def collect_multi_objective_data(store: Store) -> tuple[list[MultiObjectiveExample], TrainingDataStats]:
    """Collect training examples with per-objective labels.

    For each explicit feedback:
    - Selected objectives get the reward_score
    - Unselected objectives get 0.0
    """
    examples = []

    # Get all items with embeddings
    items = store.get_items(limit=10000)
    items_with_embeddings = {
        item.id: item for item in items
        if item.embeddings
    }

    # Get engagement events
    all_events = store.get_feedback_events(limit=10000)
    engagement_types = {"click", "reading_complete", "watching_complete", "listening_complete"}
    clicked_items = {e.item_id for e in all_events if e.event_type in engagement_types}

    # Get explicit feedback with reward_type selections
    explicit_fb = store.get_explicit_feedback(limit=10000)
    fb_by_item: dict[str, ExplicitFeedback] = {}
    for fb in explicit_fb:
        if fb.item_id not in fb_by_item:
            fb_by_item[fb.item_id] = fb

    # Build examples from items with explicit feedback (need reward_type selections)
    missing_embeddings = 0

    for item_id, fb in fb_by_item.items():
        item = items_with_embeddings.get(item_id)
        if not item:
            missing_embeddings += 1
            continue

        # Build per-objective rewards
        # Selection IDs are prefixed like "reward_type_entertainment", strip prefix
        raw_selections = fb.selections.get("reward_type", [])
        selected_types = set()
        for sel in raw_selections:
            # Handle both "entertainment" and "reward_type_entertainment" formats
            if sel.startswith("reward_type_"):
                selected_types.add(sel[len("reward_type_"):])
            else:
                selected_types.add(sel)

        objective_rewards = {}
        for obj_type in OBJECTIVE_TYPES:
            if obj_type in selected_types:
                objective_rewards[obj_type] = fb.reward_score
            else:
                objective_rewards[obj_type] = 0.0

        # Collect embeddings
        embeddings_by_type = {}
        for emb_entry in item.embeddings:
            emb_type = emb_entry.get("type")
            emb_vector = emb_entry.get("vector")
            if emb_type and emb_vector:
                embeddings_by_type[emb_type] = emb_vector

        example = MultiObjectiveExample(
            item_id=item_id,
            embeddings_by_type=embeddings_by_type,
            source_id=item.source_id,
            clicked=item_id in clicked_items,
            objective_rewards=objective_rewards,
            content_type=item.content_type.value,
            has_thumbnail=bool(item.metadata.get("thumbnail")),
            title_length=len(item.title),
        )
        examples.append(example)

    stats = TrainingDataStats(
        total_items=len(items),
        items_with_embeddings=len(items_with_embeddings),
        click_events=len([e for e in all_events if e.event_type in engagement_types]),
        explicit_feedbacks=len(explicit_fb),
        engaged_items=len(fb_by_item),
        examples_built=len(examples),
        missing_embeddings=missing_embeddings,
    )

    return examples, stats


class MultiObjectiveModel:
    """Ranking model with separate reward heads per objective.

    Allows ranking content by different objectives:
    - entertainment: pure enjoyment
    - curiosity: intellectual satisfaction
    - foundational: core knowledge/skills
    - targeted: specific expertise
    """

    def __init__(self, fusion_dim: int = 128):
        self.fusion_layer = EmbeddingFusionLayer(output_dim=fusion_dim)
        self.click_model = None
        self.reward_models: dict[str, Any] = {}  # objective -> Ridge model
        self.source_stats: dict[str, SourceStats] = {}
        self.scaler = None
        self.is_trained = False
        self.training_counts: dict[str, int] = {}  # objective -> example count

    def train(self, store: Store) -> dict[str, Any]:
        """Train click model and per-objective reward models."""
        try:
            from sklearn.linear_model import LogisticRegression, Ridge
            from sklearn.preprocessing import StandardScaler
            import numpy as np
        except ImportError:
            raise RuntimeError("scikit-learn required: pip install scikit-learn")

        examples, data_stats = collect_multi_objective_data(store)
        self.source_stats = compute_source_stats(store)

        if len(examples) == 0:
            logger.warning("No training examples with objective labels")
            return {"status": "no_data", "example_count": 0}

        logger.info(f"Training multi-objective model on {len(examples)} examples")

        # Train fusion layer
        # Convert to base TrainingExample format for fusion layer
        base_examples = [
            TrainingExample(
                item_id=ex.item_id,
                embeddings_by_type=ex.embeddings_by_type,
                source_id=ex.source_id,
                clicked=ex.clicked,
                reward_score=max(ex.objective_rewards.values()) if ex.objective_rewards else None,
                content_type=ex.content_type,
                has_thumbnail=ex.has_thumbnail,
                title_length=ex.title_length,
            )
            for ex in examples
        ]
        self.fusion_layer.fit(base_examples)

        # Build feature matrix
        X = []
        y_click = []
        y_objectives: dict[str, list[float]] = {obj: [] for obj in OBJECTIVE_TYPES}

        for ex in examples:
            features = self._build_features(ex)
            X.append(features)
            y_click.append(1 if ex.clicked else 0)

            for obj_type in OBJECTIVE_TYPES:
                y_objectives[obj_type].append(ex.objective_rewards.get(obj_type, 0.0))

        X = np.array(X)
        y_click = np.array(y_click)

        # Standardize
        self.scaler = StandardScaler()
        self.scaler.fit(X)
        self.scaler.scale_ = np.maximum(self.scaler.scale_, 0.01)
        X_scaled = self.scaler.transform(X)

        # Train click model
        if len(set(y_click)) > 1:
            self.click_model = LogisticRegression(max_iter=1000)
            self.click_model.fit(X_scaled, y_click)

        # Train per-objective reward models
        self.reward_models = {}
        self.training_counts = {}

        for obj_type in OBJECTIVE_TYPES:
            y = np.array(y_objectives[obj_type])

            # Count non-zero examples for this objective
            nonzero_count = int((y > 0).sum())
            self.training_counts[obj_type] = nonzero_count

            if nonzero_count >= 1:
                model = Ridge(alpha=1.0)
                model.fit(X_scaled, y)
                self.reward_models[obj_type] = model
                logger.info(f"  {obj_type}: {nonzero_count} examples")

        self.is_trained = True

        return {
            "status": "success",
            "example_count": len(examples),
            "click_examples": int(y_click.sum()),
            "objective_counts": self.training_counts,
            "embedding_types": list(self.fusion_layer.seen_types),
        }

    def _build_features(self, ex: MultiObjectiveExample) -> list[float]:
        """Build feature vector."""
        fused = self.fusion_layer.transform(ex.embeddings_by_type)
        features = list(fused)

        # Source stats
        source = self.source_stats.get(ex.source_id)
        if source:
            features.extend([source.avg_reward, source.click_rate, min(source.engagement_count / 100, 1.0)])
        else:
            features.extend([2.5, 0.0, 0.0])

        # Metadata
        features.append(1.0 if ex.has_thumbnail else 0.0)
        features.append(min(ex.title_length / 100, 1.0))

        # Content type one-hot
        content_types = ["article", "video", "audio", "paper", "image", "thread", "other"]
        for ct in content_types:
            features.append(1.0 if ex.content_type == ct else 0.0)

        return features

    def predict(self, content: Content) -> dict[str, float]:
        """Predict reward scores for all objectives."""
        if not self.is_trained or not content.embeddings:
            return {obj: 2.5 for obj in OBJECTIVE_TYPES}

        try:
            import numpy as np
        except ImportError:
            return {obj: 2.5 for obj in OBJECTIVE_TYPES}

        # Collect embeddings (handle both Embedding objects and dicts)
        embeddings_by_type = {}
        for emb in content.embeddings:
            emb_type = emb.get("type") if isinstance(emb, dict) else emb.type
            emb_vector = emb.get("vector") if isinstance(emb, dict) else emb.vector
            if emb_type and emb_vector:
                embeddings_by_type[emb_type] = emb_vector

        if not embeddings_by_type:
            return {obj: 2.5 for obj in OBJECTIVE_TYPES}

        # Build features
        ex = MultiObjectiveExample(
            item_id=content.id,
            embeddings_by_type=embeddings_by_type,
            source_id="",
            clicked=False,
            content_type=content.content_type.value,
            has_thumbnail=bool(content.metadata.get("thumbnail")),
            title_length=len(content.title),
        )
        features = self._build_features(ex)
        X = np.array([features])
        X_scaled = self.scaler.transform(X)

        # Predict each objective
        results = {}
        for obj_type in OBJECTIVE_TYPES:
            if obj_type in self.reward_models:
                pred = float(self.reward_models[obj_type].predict(X_scaled)[0])
                results[obj_type] = max(0.0, min(5.0, pred))
            else:
                results[obj_type] = 2.5

        return results

    def predict_click(self, content: Content) -> float:
        """Predict click probability."""
        if not self.is_trained or not content.embeddings or self.click_model is None:
            return 0.5

        try:
            import numpy as np
        except ImportError:
            return 0.5

        embeddings_by_type = {}
        for emb in content.embeddings:
            emb_type = emb.get("type") if isinstance(emb, dict) else emb.type
            emb_vector = emb.get("vector") if isinstance(emb, dict) else emb.vector
            if emb_type and emb_vector:
                embeddings_by_type[emb_type] = emb_vector

        if not embeddings_by_type:
            return 0.5

        ex = MultiObjectiveExample(
            item_id=content.id,
            embeddings_by_type=embeddings_by_type,
            source_id="",
            clicked=False,
            content_type=content.content_type.value,
            has_thumbnail=bool(content.metadata.get("thumbnail")),
            title_length=len(content.title),
        )
        features = self._build_features(ex)
        X = self.scaler.transform([features])

        return float(self.click_model.predict_proba(X)[0, 1])

    def score(self, content: Content, objective: str | None = None) -> float:
        """Compute ranking score for content."""
        click_prob = self.predict_click(content)
        rewards = self.predict(content)

        if objective and objective in rewards:
            expected_reward = rewards[objective]
        else:
            expected_reward = sum(rewards.values()) / len(rewards)

        if self.click_model is not None:
            return click_prob * expected_reward
        return expected_reward

    def save(self, path: Path) -> None:
        """Save model to disk."""
        import pickle

        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "model_type": "multi_objective",
            "click_model": self.click_model,
            "reward_models": self.reward_models,
            "scaler": self.scaler,
            "fusion_layer": self.fusion_layer.get_state(),
            "source_stats": {
                k: {
                    "source_id": v.source_id,
                    "item_count": v.item_count,
                    "avg_reward": v.avg_reward,
                    "click_rate": v.click_rate,
                    "engagement_count": v.engagement_count,
                }
                for k, v in self.source_stats.items()
            },
            "training_counts": self.training_counts,
            "is_trained": self.is_trained,
        }

        with open(path, "wb") as f:
            pickle.dump(data, f)

        logger.info(f"Multi-objective model saved to {path}")

    def load(self, path: Path) -> bool:
        """Load model from disk."""
        import pickle

        if not path.exists():
            return False

        try:
            with open(path, "rb") as f:
                data = pickle.load(f)

            if data.get("model_type") != "multi_objective":
                return False

            self.click_model = data["click_model"]
            self.reward_models = data["reward_models"]
            self.scaler = data["scaler"]

            if "fusion_layer" in data:
                self.fusion_layer.set_state(data["fusion_layer"])

            self.source_stats = {
                k: SourceStats(**v)
                for k, v in data["source_stats"].items()
            }
            self.training_counts = data.get("training_counts", {})
            self.is_trained = data["is_trained"]

            logger.info(f"Multi-objective model loaded from {path}")
            return True
        except Exception as e:
            logger.warning(f"Failed to load multi-objective model: {e}")
            return False


# Default path for multi-objective model
DEFAULT_MULTI_OBJECTIVE_PATH = Path("~/.omnifeed/multi_objective_model.pkl").expanduser()

_multi_objective_model: MultiObjectiveModel | None = None


def get_multi_objective_model() -> MultiObjectiveModel:
    """Get or create the multi-objective model singleton."""
    global _multi_objective_model
    if _multi_objective_model is None:
        _multi_objective_model = MultiObjectiveModel()
        _multi_objective_model.load(DEFAULT_MULTI_OBJECTIVE_PATH)
    return _multi_objective_model
