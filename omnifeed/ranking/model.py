"""Multi-head ranking model for predicting click probability and reward."""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from omnifeed.models import Item, ExplicitFeedback
from omnifeed.ranking.embeddings import get_embedding_by_type
from omnifeed.store.base import Store

logger = logging.getLogger(__name__)


@dataclass
class TrainingExample:
    """A single training example."""
    item_id: str
    embeddings_by_type: dict[str, list[float]]  # All available embeddings
    source_id: str

    # Labels
    clicked: bool
    reward_score: float | None  # From explicit feedback (0-5)

    # Metadata features
    content_type: str
    has_thumbnail: bool
    title_length: int


class EmbeddingFusionLayer:
    """Learns to fuse multiple embedding types into a fixed-size representation.

    Uses learned weights per embedding type with attention-like aggregation.
    Can handle any number of embedding types and missing embeddings.
    """

    def __init__(self, output_dim: int = 128):
        self.output_dim = output_dim
        self.type_projections: dict[str, Any] = {}  # type -> (W, b) projection
        self.type_weights: dict[str, float] = {}  # learned importance weights
        self.seen_types: set[str] = set()
        self._fitted = False

    def fit(self, examples: list[TrainingExample]) -> None:
        """Learn projection matrices and type weights from training data."""
        try:
            import numpy as np
            from sklearn.decomposition import PCA
        except ImportError:
            raise RuntimeError("numpy and scikit-learn required")

        # Collect all embedding types seen
        all_embeddings_by_type: dict[str, list[list[float]]] = {}
        for ex in examples:
            for emb_type, emb in ex.embeddings_by_type.items():
                if emb_type not in all_embeddings_by_type:
                    all_embeddings_by_type[emb_type] = []
                all_embeddings_by_type[emb_type].append(emb)

        self.seen_types = set(all_embeddings_by_type.keys())

        # Learn a PCA projection for each type to output_dim
        for emb_type, embeddings in all_embeddings_by_type.items():
            X = np.array(embeddings)
            input_dim = X.shape[1]

            # Use PCA to project to output_dim
            n_components = min(self.output_dim, input_dim, len(embeddings))
            pca = PCA(n_components=n_components)
            pca.fit(X)

            self.type_projections[emb_type] = pca

            # Initialize weight based on frequency (more common = initially higher weight)
            self.type_weights[emb_type] = len(embeddings) / len(examples)

        # Normalize weights
        total_weight = sum(self.type_weights.values())
        if total_weight > 0:
            self.type_weights = {k: v / total_weight for k, v in self.type_weights.items()}

        self._fitted = True
        logger.info(f"Fusion layer fitted with types: {list(self.seen_types)}")

    def transform(self, embeddings_by_type: dict[str, list[float]]) -> list[float]:
        """Transform multiple embeddings into a single fused vector."""
        import numpy as np

        if not self._fitted:
            # Fallback: just use first available embedding
            for emb in embeddings_by_type.values():
                return emb[:self.output_dim] + [0.0] * max(0, self.output_dim - len(emb))
            return [0.0] * self.output_dim

        # Project and weight each available embedding
        projected = []
        weights = []

        for emb_type, emb in embeddings_by_type.items():
            if emb_type in self.type_projections:
                pca = self.type_projections[emb_type]
                proj = pca.transform([emb])[0]
                # Pad to output_dim if needed
                if len(proj) < self.output_dim:
                    proj = np.concatenate([proj, np.zeros(self.output_dim - len(proj))])
                projected.append(proj)
                weights.append(self.type_weights.get(emb_type, 0.1))

        if not projected:
            return [0.0] * self.output_dim

        # Weighted average of projections
        weights = np.array(weights)
        weights = weights / weights.sum()  # Normalize

        fused = np.zeros(self.output_dim)
        for proj, w in zip(projected, weights):
            fused += w * proj

        return fused.tolist()

    def get_state(self) -> dict:
        """Get serializable state."""
        import pickle
        import base64

        return {
            "output_dim": self.output_dim,
            "type_projections": {
                k: base64.b64encode(pickle.dumps(v)).decode()
                for k, v in self.type_projections.items()
            },
            "type_weights": self.type_weights,
            "seen_types": list(self.seen_types),
            "fitted": self._fitted,
        }

    def set_state(self, state: dict) -> None:
        """Restore from serialized state."""
        import pickle
        import base64

        self.output_dim = state["output_dim"]
        self.type_projections = {
            k: pickle.loads(base64.b64decode(v))
            for k, v in state["type_projections"].items()
        }
        self.type_weights = state["type_weights"]
        self.seen_types = set(state["seen_types"])
        self._fitted = state["fitted"]


@dataclass
class SourceStats:
    """Aggregate stats for a source."""
    source_id: str
    item_count: int
    avg_reward: float
    click_rate: float
    engagement_count: int


@dataclass
class TrainingDataStats:
    """Stats about training data collection."""
    total_items: int
    items_with_embeddings: int
    click_events: int
    explicit_feedbacks: int
    engaged_items: int
    examples_built: int
    missing_embeddings: int


def collect_training_data(store: Store) -> tuple[list[TrainingExample], TrainingDataStats]:
    """Collect training examples from items with engagement.

    Returns:
        (examples, stats) - The training examples and diagnostic stats
    """
    examples = []

    # Get all items
    items = store.get_items(limit=10000)
    all_items_by_id = {item.id: item for item in items}

    # Items with any embedding
    items_with_embeddings = {
        item.id: item for item in items
        if item.embeddings  # Has at least one embedding of any type
    }

    # Get engagement events (any engagement implies the item was opened/clicked)
    all_events = store.get_feedback_events(limit=10000)
    engagement_types = {"click", "reading_complete", "watching_complete", "listening_complete"}
    clicked_items = {e.item_id for e in all_events if e.event_type in engagement_types}
    click_events = [e for e in all_events if e.event_type in engagement_types]

    # Get explicit feedback
    explicit_fb = store.get_explicit_feedback(limit=10000)
    fb_by_item: dict[str, ExplicitFeedback] = {}
    for fb in explicit_fb:
        if fb.item_id not in fb_by_item:
            fb_by_item[fb.item_id] = fb

    # Build examples from items that have been clicked or rated
    engaged_items = clicked_items | set(fb_by_item.keys())

    # Track how many are missing embeddings
    missing_embeddings = 0

    for item_id in engaged_items:
        item = items_with_embeddings.get(item_id)
        if not item:
            if item_id in all_items_by_id:
                missing_embeddings += 1
            continue

        fb = fb_by_item.get(item_id)

        # Collect all available embeddings (any type present in the item)
        embeddings_by_type = {}
        for emb_entry in item.embeddings:
            emb_type = emb_entry.get("type")
            emb_vector = emb_entry.get("vector")
            if emb_type and emb_vector:
                embeddings_by_type[emb_type] = emb_vector

        example = TrainingExample(
            item_id=item_id,
            embeddings_by_type=embeddings_by_type,
            source_id=item.source_id,
            clicked=item_id in clicked_items,
            reward_score=fb.reward_score if fb else None,
            content_type=item.content_type.value,
            has_thumbnail=bool(item.metadata.get("thumbnail")),
            title_length=len(item.title),
        )
        examples.append(example)

    stats = TrainingDataStats(
        total_items=len(items),
        items_with_embeddings=len(items_with_embeddings),
        click_events=len(click_events),
        explicit_feedbacks=len(explicit_fb),
        engaged_items=len(engaged_items),
        examples_built=len(examples),
        missing_embeddings=missing_embeddings,
    )

    return examples, stats


def compute_source_stats(store: Store) -> dict[str, SourceStats]:
    """Compute aggregate stats per source."""
    sources = store.list_sources()
    stats: dict[str, SourceStats] = {}

    for source in sources:
        source_id = source.id
        item_count = store.count_items(source_id=source_id)

        # Get feedback for this source's items
        items = store.get_items(source_id=source_id, limit=1000)
        item_ids = {item.id for item in items}

        # Count clicks
        clicks = store.get_feedback_events(event_type="click", limit=10000)
        source_clicks = [c for c in clicks if c.item_id in item_ids]

        # Get rewards
        explicit = store.get_explicit_feedback(limit=10000)
        source_fb = [fb for fb in explicit if fb.item_id in item_ids]
        rewards = [fb.reward_score for fb in source_fb]

        stats[source_id] = SourceStats(
            source_id=source_id,
            item_count=item_count,
            avg_reward=sum(rewards) / len(rewards) if rewards else 2.5,
            click_rate=len(source_clicks) / item_count if item_count > 0 else 0.0,
            engagement_count=len(source_clicks) + len(source_fb),
        )

    return stats


class RankingModel:
    """Multi-head ranking model with embedding fusion."""

    def __init__(self, fusion_dim: int = 128):
        self.fusion_layer = EmbeddingFusionLayer(output_dim=fusion_dim)
        self.click_model = None
        self.reward_model = None
        self.source_stats: dict[str, SourceStats] = {}
        self.is_trained = False

    def train(self, store: Store) -> dict[str, Any]:
        """Train the model on engagement data."""
        try:
            from sklearn.linear_model import LogisticRegression, Ridge
            from sklearn.preprocessing import StandardScaler
            import numpy as np
        except ImportError:
            raise RuntimeError(
                "scikit-learn not installed. Run: pip install scikit-learn"
            )

        # Collect data
        examples, data_stats = collect_training_data(store)
        self.source_stats = compute_source_stats(store)

        if len(examples) == 0:
            logger.warning("No training examples available")
            return {
                "status": "no_data",
                "example_count": 0,
                "total_items": data_stats.total_items,
                "items_with_embeddings": data_stats.items_with_embeddings,
                "click_events": data_stats.click_events,
                "explicit_feedbacks": data_stats.explicit_feedbacks,
                "engaged_items": data_stats.engaged_items,
                "missing_embeddings": data_stats.missing_embeddings,
            }

        logger.info(f"Training on {len(examples)} examples")

        # Train fusion layer on all embeddings
        self.fusion_layer.fit(examples)

        # Build feature matrix
        X = []
        y_click = []
        y_reward = []
        has_reward = []

        for ex in examples:
            features = self._build_features(ex)
            X.append(features)
            y_click.append(1 if ex.clicked else 0)
            if ex.reward_score is not None:
                y_reward.append(ex.reward_score)
                has_reward.append(True)
            else:
                y_reward.append(2.5)  # Placeholder
                has_reward.append(False)

        X = np.array(X)
        y_click = np.array(y_click)
        y_reward = np.array(y_reward)
        has_reward = np.array(has_reward)

        # Standardize features (with floor on std to prevent division by ~0)
        self.scaler = StandardScaler()
        self.scaler.fit(X)
        # Prevent division by near-zero std
        self.scaler.scale_ = np.maximum(self.scaler.scale_, 0.01)
        X_scaled = self.scaler.transform(X)

        # Train click model (skip if all same class - just use default 0.5)
        if len(set(y_click)) > 1:
            self.click_model = LogisticRegression(max_iter=1000)
            self.click_model.fit(X_scaled, y_click)
        else:
            self.click_model = None  # Will use default probability

        # Train reward model (only on items with explicit feedback)
        if has_reward.sum() >= 1:
            X_reward = X_scaled[has_reward]
            y_reward_filtered = y_reward[has_reward]
            self.reward_model = Ridge(alpha=1.0)
            self.reward_model.fit(X_reward, y_reward_filtered)

        self.is_trained = True

        # Log embedding types discovered
        logger.info(f"Embedding types used: {list(self.fusion_layer.seen_types)}")

        return {
            "status": "success",
            "example_count": len(examples),
            "click_examples": int(y_click.sum()),
            "reward_examples": int(has_reward.sum()),
            "embedding_types": list(self.fusion_layer.seen_types),
        }

    def _build_features(self, ex: TrainingExample) -> list[float]:
        """Build feature vector from training example."""
        # Fuse all available embeddings into fixed-size vector
        fused = self.fusion_layer.transform(ex.embeddings_by_type)
        features = list(fused)

        # Source stats
        source = self.source_stats.get(ex.source_id)
        if source:
            features.extend([
                source.avg_reward,
                source.click_rate,
                min(source.engagement_count / 100, 1.0),  # Normalized
            ])
        else:
            features.extend([2.5, 0.0, 0.0])

        # Metadata features
        features.append(1.0 if ex.has_thumbnail else 0.0)
        features.append(min(ex.title_length / 100, 1.0))

        # Content type one-hot
        content_types = ["article", "video", "audio", "paper", "image", "thread", "other"]
        for ct in content_types:
            features.append(1.0 if ex.content_type == ct else 0.0)

        return features

    def predict(self, item: Item) -> tuple[float, float]:
        """Predict click probability and expected reward for an item.

        Returns:
            (click_prob, expected_reward)
        """
        # Check if model is trained and item has embeddings
        if not self.is_trained or not item.embeddings:
            # Return defaults for cold start
            source = self.source_stats.get(item.source_id)
            default_reward = source.avg_reward if source else 2.5
            return 0.5, default_reward

        try:
            import numpy as np
        except ImportError:
            return 0.5, 2.5

        # Collect all embeddings from the item
        embeddings_by_type = {}
        for emb_entry in item.embeddings:
            emb_type = emb_entry.get("type")
            emb_vector = emb_entry.get("vector")
            if emb_type and emb_vector:
                embeddings_by_type[emb_type] = emb_vector

        if not embeddings_by_type:
            source = self.source_stats.get(item.source_id)
            default_reward = source.avg_reward if source else 2.5
            return 0.5, default_reward

        # Build features using fusion layer
        ex = TrainingExample(
            item_id=item.id,
            embeddings_by_type=embeddings_by_type,
            source_id=item.source_id,
            clicked=False,
            reward_score=None,
            content_type=item.content_type.value,
            has_thumbnail=bool(item.metadata.get("thumbnail")),
            title_length=len(item.title),
        )
        features = self._build_features(ex)
        X = np.array([features])
        X_scaled = self.scaler.transform(X)

        # Predict
        if self.click_model is not None:
            click_prob = self.click_model.predict_proba(X_scaled)[0, 1]
        else:
            click_prob = 0.5  # Default when no click model

        if self.reward_model is not None:
            # Check for out-of-distribution features (scaled values too extreme)
            max_abs_scaled = np.abs(X_scaled).max()
            if max_abs_scaled > 10:
                # Features are way outside training distribution, use source prior
                source = self.source_stats.get(item.source_id)
                expected_reward = source.avg_reward if source else 2.5
            else:
                expected_reward = float(self.reward_model.predict(X_scaled)[0])
                expected_reward = max(0.0, min(5.0, expected_reward))  # Clamp
        else:
            source = self.source_stats.get(item.source_id)
            expected_reward = source.avg_reward if source else 2.5

        return float(click_prob), expected_reward

    def score(self, item: Item) -> float:
        """Compute a single ranking score for an item.

        When click model exists: score = click_prob * expected_reward
        Otherwise: score = expected_reward (use reward directly)
        """
        click_prob, expected_reward = self.predict(item)

        # If we have a trained click model, use expected value formula
        if self.click_model is not None:
            return click_prob * expected_reward

        # Otherwise just use expected reward (all examples are engaged anyway)
        return expected_reward

    def save(self, path: Path) -> None:
        """Save model to disk."""
        import pickle

        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "click_model": self.click_model,
            "reward_model": self.reward_model,
            "scaler": self.scaler if hasattr(self, "scaler") else None,
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
            "is_trained": self.is_trained,
        }

        with open(path, "wb") as f:
            pickle.dump(data, f)

        logger.info(f"Model saved to {path}")

    def load(self, path: Path) -> bool:
        """Load model from disk. Returns True if successful."""
        import pickle

        if not path.exists():
            return False

        try:
            with open(path, "rb") as f:
                data = pickle.load(f)

            self.click_model = data["click_model"]
            self.reward_model = data["reward_model"]
            self.scaler = data["scaler"]

            # Load fusion layer if present (backwards compatible)
            if "fusion_layer" in data:
                self.fusion_layer.set_state(data["fusion_layer"])

            self.source_stats = {
                k: SourceStats(**v)
                for k, v in data["source_stats"].items()
            }
            self.is_trained = data["is_trained"]

            logger.info(f"Model loaded from {path}")
            return True
        except Exception as e:
            logger.warning(f"Failed to load model: {e}")
            return False


# Default model path
DEFAULT_MODEL_PATH = Path("~/.omnifeed/ranking_model.pkl").expanduser()

# Singleton
_ranking_model: RankingModel | None = None


def get_ranking_model() -> RankingModel:
    """Get or create the ranking model singleton."""
    global _ranking_model
    if _ranking_model is None:
        _ranking_model = RankingModel()
        _ranking_model.load(DEFAULT_MODEL_PATH)
    return _ranking_model
