"""Retriever abstraction for recursive content discovery."""

from omnifeed.retriever.types import (
    Retriever,
    RetrieverKind,
    RetrieverScore,
    RetrievalContext,
    RetrievalResult,
    ResultType,
)
from omnifeed.retriever.registry import (
    HandlerRegistry,
    get_handler_registry,
    get_handler,
    find_handler,
)
from omnifeed.retriever.orchestrator import (
    RetrieverOrchestrator,
    InvocationResult,
)
from omnifeed.retriever.scoring import (
    RetrieverScorer,
    record_content_feedback,
)

__all__ = [
    # Types
    "Retriever",
    "RetrieverKind",
    "RetrieverScore",
    "RetrievalContext",
    "RetrievalResult",
    "ResultType",
    # Registry
    "HandlerRegistry",
    "get_handler_registry",
    "get_handler",
    "find_handler",
    # Orchestrator
    "RetrieverOrchestrator",
    "InvocationResult",
    # Scoring
    "RetrieverScorer",
    "record_content_feedback",
]
