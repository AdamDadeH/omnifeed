"""Model registry for managing multiple ranking model implementations.

This provides a flexible abstraction layer between objectives and model implementations.
Models are lazy-loaded and cached. Objectives map to models via configuration.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Any, Callable

from omnifeed.models import Content
from omnifeed.store.base import Store

logger = logging.getLogger(__name__)


class RankerProtocol(Protocol):
    """Protocol that all ranking models must implement."""

    is_trained: bool

    def score(self, content: Content, objective: str | None = None) -> float:
        """Score content. Higher = better."""
        ...

    def train(self, store: Store) -> dict[str, Any]:
        """Train the model on data from store."""
        ...

    def save(self, path: Path) -> None:
        """Save model to disk."""
        ...

    def load(self, path: Path) -> bool:
        """Load model from disk. Returns True on success."""
        ...


@dataclass
class ModelConfig:
    """Configuration for a registered model."""
    name: str
    loader: Callable[[], RankerProtocol]
    path: Path
    supports_objectives: bool = False  # Can this model handle objective param?


class ModelRegistry:
    """Registry for ranking models.

    Models are registered with a name and loader function.
    Objectives can be mapped to specific models.
    """

    def __init__(self):
        self._configs: dict[str, ModelConfig] = {}
        self._instances: dict[str, RankerProtocol | bool] = {}  # bool=False means failed load
        self._objective_mapping: dict[str, str] = {}  # objective -> model_name
        self._default_model: str | None = None

    def register(
        self,
        name: str,
        loader: Callable[[], RankerProtocol],
        path: Path,
        supports_objectives: bool = False,
        is_default: bool = False,
    ) -> None:
        """Register a model.

        Args:
            name: Unique model name
            loader: Function that returns a new model instance
            path: Path where model is saved/loaded
            supports_objectives: Whether model can handle objective param
            is_default: Whether this is the fallback model
        """
        self._configs[name] = ModelConfig(
            name=name,
            loader=loader,
            path=path,
            supports_objectives=supports_objectives,
        )
        if is_default:
            self._default_model = name

    def map_objective(self, objective: str, model_name: str) -> None:
        """Map an objective to a model."""
        if model_name not in self._configs:
            raise ValueError(f"Unknown model: {model_name}")
        self._objective_mapping[objective] = model_name

    def get_model(self, name: str) -> RankerProtocol | None:
        """Get a model by name. Lazy-loads and caches."""
        if name not in self._configs:
            return None

        # Check cache
        if name in self._instances:
            instance = self._instances[name]
            return instance if instance else None

        # Load
        config = self._configs[name]
        try:
            model = config.loader()
            model.load(config.path)
            self._instances[name] = model
            logger.info(f"Loaded model '{name}' from {config.path}")
            return model
        except Exception as e:
            logger.warning(f"Failed to load model '{name}': {e}")
            self._instances[name] = False
            return None

    def get_model_for_objective(self, objective: str | None) -> tuple[RankerProtocol | None, str | None]:
        """Get the appropriate model for an objective.

        Returns:
            (model, model_name) tuple
        """
        if objective and objective in self._objective_mapping:
            model_name = self._objective_mapping[objective]
            model = self.get_model(model_name)
            if model and model.is_trained:
                return model, model_name

        # Fall back to default
        if self._default_model:
            model = self.get_model(self._default_model)
            if model and model.is_trained:
                return model, self._default_model

        return None, None

    def get_default(self) -> RankerProtocol | None:
        """Get the default model."""
        if self._default_model:
            return self.get_model(self._default_model)
        return None

    def list_models(self) -> list[dict[str, Any]]:
        """List all registered models with their status."""
        result = []
        for name, config in self._configs.items():
            model = self._instances.get(name)
            status = "not_loaded"
            if model is False:
                status = "failed"
            elif model:
                status = "trained" if model.is_trained else "loaded"

            result.append({
                "name": name,
                "path": str(config.path),
                "supports_objectives": config.supports_objectives,
                "is_default": name == self._default_model,
                "status": status,
            })
        return result

    def train_model(self, name: str, store: Store) -> dict[str, Any]:
        """Train a specific model."""
        if name not in self._configs:
            return {"status": "error", "message": f"Unknown model: {name}"}

        config = self._configs[name]
        model = config.loader()  # Fresh instance for training
        result = model.train(store)

        if result.get("status") == "success":
            model.save(config.path)
            self._instances[name] = model

        return result

    def clear_cache(self) -> None:
        """Clear cached model instances."""
        self._instances.clear()


# Global registry instance
_registry: ModelRegistry | None = None


def get_model_registry() -> ModelRegistry:
    """Get or create the global model registry."""
    global _registry
    if _registry is None:
        _registry = _create_default_registry()
    return _registry


def _create_default_registry() -> ModelRegistry:
    """Create registry with default model configurations."""
    from pathlib import Path

    registry = ModelRegistry()

    # Register default model
    def load_default():
        from omnifeed.ranking.model import RankingModel
        return RankingModel()

    registry.register(
        name="default",
        loader=load_default,
        path=Path("~/.omnifeed/ranking_model.pkl").expanduser(),
        supports_objectives=False,
        is_default=True,
    )

    # Register multi-objective model
    def load_multi_objective():
        from omnifeed.ranking.multi_objective import MultiObjectiveModel
        return MultiObjectiveModel()

    registry.register(
        name="multi_objective",
        loader=load_multi_objective,
        path=Path("~/.omnifeed/multi_objective_model.pkl").expanduser(),
        supports_objectives=True,
    )

    # Map objectives to multi-objective model
    for objective in ["entertainment", "curiosity", "foundational", "targeted"]:
        registry.map_objective(objective, "multi_objective")

    return registry
