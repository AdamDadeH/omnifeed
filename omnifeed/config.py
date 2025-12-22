"""Configuration management for OmniFeed."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from omnifeed.store import Store, StoreType, create_store


DEFAULT_CONFIG_PATH = "~/.omnifeed/config.json"
DEFAULT_DATA_PATH = "~/.omnifeed/data.db"


@dataclass
class Config:
    """Application configuration."""

    store_type: StoreType = StoreType.SQLITE
    store_path: str = DEFAULT_DATA_PATH
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str = DEFAULT_CONFIG_PATH) -> "Config":
        """Load config from a JSON file, or return defaults if not found."""
        config_path = Path(path).expanduser()

        if not config_path.exists():
            return cls()

        try:
            data = json.loads(config_path.read_text())
            return cls(
                store_type=StoreType(data.get("store_type", "sqlite")),
                store_path=data.get("store_path", DEFAULT_DATA_PATH),
                extra=data.get("extra", {}),
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return cls()

    def save(self, path: str = DEFAULT_CONFIG_PATH) -> None:
        """Save config to a JSON file."""
        config_path = Path(path).expanduser()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "store_type": self.store_type.value,
            "store_path": self.store_path,
            "extra": self.extra,
        }
        config_path.write_text(json.dumps(data, indent=2))

    def create_store(self) -> Store:
        """Create a store instance from this config."""
        return create_store(self.store_type, self.store_path)
