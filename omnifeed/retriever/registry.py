"""Registry for RetrieverHandler implementations.

Provides lookup of handlers by type or URI pattern.
"""

import logging
from typing import Iterator

from omnifeed.retriever.handlers.base import RetrieverHandler

logger = logging.getLogger(__name__)


class HandlerRegistry:
    """Registry for retriever handlers.

    Handlers are registered and can be looked up by:
    - handler_type: exact match on handler.handler_type
    - uri: first handler where can_handle(uri) returns True
    """

    def __init__(self):
        self._handlers: list[RetrieverHandler] = []
        self._by_type: dict[str, RetrieverHandler] = {}

    def register(self, handler: RetrieverHandler) -> None:
        """Register a handler.

        Args:
            handler: The handler to register.
        """
        self._handlers.append(handler)
        self._by_type[handler.handler_type] = handler
        logger.info(f"Registered retriever handler: {handler.handler_type}")

    def get_by_type(self, handler_type: str) -> RetrieverHandler | None:
        """Get a handler by its type identifier.

        Args:
            handler_type: The handler type (e.g., "source", "exploratory")

        Returns:
            The handler if found, None otherwise.
        """
        return self._by_type.get(handler_type)

    def find_for_uri(self, uri: str) -> RetrieverHandler | None:
        """Find a handler that can handle the given URI.

        Tries handlers in registration order.

        Args:
            uri: The URI to find a handler for.

        Returns:
            The first handler where can_handle(uri) is True, or None.
        """
        for handler in self._handlers:
            if handler.can_handle(uri):
                return handler
        return None

    @property
    def handlers(self) -> list[RetrieverHandler]:
        """All registered handlers."""
        return list(self._handlers)

    def __iter__(self) -> Iterator[RetrieverHandler]:
        return iter(self._handlers)


def create_default_registry() -> HandlerRegistry:
    """Create a registry with default handlers.

    Registers handlers in priority order (more specific first).
    """
    from omnifeed.retriever.handlers.source_wrapper import SourceRetrieverHandler
    from omnifeed.retriever.handlers.exploratory import ExploratoryHandler
    from omnifeed.retriever.handlers.strategy import StrategyHandler

    registry = HandlerRegistry()

    # Register built-in handlers
    # Order matters - more specific handlers should be registered first
    registry.register(StrategyHandler())  # strategy: URIs
    registry.register(ExploratoryHandler())  # explore: URIs (legacy)
    registry.register(SourceRetrieverHandler())  # source: URIs

    return registry


# Singleton registry
_registry: HandlerRegistry | None = None


def get_handler_registry() -> HandlerRegistry:
    """Get or create the default handler registry."""
    global _registry
    if _registry is None:
        _registry = create_default_registry()
    return _registry


def get_handler(handler_type: str) -> RetrieverHandler | None:
    """Get a handler by type from the default registry."""
    return get_handler_registry().get_by_type(handler_type)


def find_handler(uri: str) -> RetrieverHandler | None:
    """Find a handler for a URI from the default registry."""
    return get_handler_registry().find_for_uri(uri)
