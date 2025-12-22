"""Store factory for creating storage backends."""

from enum import Enum

from omnifeed.store.base import Store


class StoreType(Enum):
    """Available storage backend types."""
    SQLITE = "sqlite"
    FILE = "file"


def create_store(store_type: StoreType, path: str) -> Store:
    """Factory to create store by type.

    Args:
        store_type: The type of store to create.
        path: For SQLite, the database file path. For File, the data directory.

    Returns:
        A Store instance.
    """
    # Import here to avoid circular imports
    from omnifeed.store.sqlite import SQLiteStore
    from omnifeed.store.file import FileStore

    match store_type:
        case StoreType.SQLITE:
            return SQLiteStore(path)
        case StoreType.FILE:
            return FileStore(path)
        case _:
            raise ValueError(f"Unknown store type: {store_type}")
