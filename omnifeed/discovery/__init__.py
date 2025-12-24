"""Source discovery using LLM-powered interest extraction."""

from omnifeed.discovery.engine import (
    DiscoveryEngine,
    DiscoveryResult,
    DiscoveryResponse,
    discover_sources,
)
from omnifeed.discovery.interests import (
    Interest,
    InterestProfile,
    build_interest_profile,
    extract_interests_from_items,
    generate_queries_from_prompt,
)
from omnifeed.discovery.llm import (
    LLMBackend,
    OllamaBackend,
    OpenAIBackend,
    AnthropicBackend,
    get_llm_backend,
    set_llm_backend,
    get_llm_status,
)

__all__ = [
    # Engine
    "DiscoveryEngine",
    "DiscoveryResult",
    "DiscoveryResponse",
    "discover_sources",
    # Interests
    "Interest",
    "InterestProfile",
    "build_interest_profile",
    "extract_interests_from_items",
    "generate_queries_from_prompt",
    # LLM
    "LLMBackend",
    "OllamaBackend",
    "OpenAIBackend",
    "AnthropicBackend",
    "get_llm_backend",
    "set_llm_backend",
    "get_llm_status",
]
