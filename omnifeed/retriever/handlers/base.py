"""Abstract base class for retriever handlers."""

from abc import ABC, abstractmethod

from omnifeed.retriever.types import (
    Retriever,
    RetrievalContext,
    RetrievalResult,
)


class RetrieverHandler(ABC):
    """Handler for a specific type of retriever.

    Each handler knows how to:
    1. Identify URIs it can handle (can_handle)
    2. Create a Retriever from a URI (resolve)
    3. Invoke a Retriever to get results (invoke)

    Handlers are registered with the HandlerRegistry and looked up
    by handler_type or URI pattern.
    """

    @property
    @abstractmethod
    def handler_type(self) -> str:
        """Unique identifier for this handler type.

        Used to map Retriever.handler_type to the handler implementation.
        Examples: "source", "exploratory", "rym_chart", "google_search"
        """
        ...

    @abstractmethod
    def can_handle(self, uri: str) -> bool:
        """Check if this handler can process the given URI.

        Args:
            uri: The URI to check (e.g., "rss:https://...", "explore:random")

        Returns:
            True if this handler can process the URI
        """
        ...

    @abstractmethod
    def resolve(self, uri: str, display_name: str | None = None) -> Retriever:
        """Create a Retriever from a URI.

        This performs any necessary lookups to build the Retriever metadata
        but does NOT invoke it to fetch content.

        Args:
            uri: The URI to resolve
            display_name: Optional display name override

        Returns:
            A fully populated Retriever ready for storage/invocation
        """
        ...

    @abstractmethod
    async def invoke(
        self,
        retriever: Retriever,
        context: RetrievalContext,
    ) -> list[RetrievalResult]:
        """Invoke a retriever to get results.

        This is the main entry point for fetching content or sub-retrievers.
        For POLL retrievers, this fetches new content.
        For EXPLORE retrievers, this discovers new sub-retrievers.
        For HYBRID retrievers, this may return both.

        Args:
            retriever: The retriever to invoke
            context: Invocation context (limits, filters, etc.)

        Returns:
            List of results (content or sub-retrievers)
        """
        ...
