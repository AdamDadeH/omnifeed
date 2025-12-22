"""Store module - persistence layer for OmniFeed."""

from omnifeed.store.base import Store
from omnifeed.store.sqlite import SQLiteStore
from omnifeed.store.file import FileStore
from omnifeed.store.factory import StoreType, create_store

__all__ = ["Store", "SQLiteStore", "FileStore", "StoreType", "create_store"]
