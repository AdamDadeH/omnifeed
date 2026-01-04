"""Featurization module for generating embeddings and features from content.

This module provides:
- Text embeddings using sentence-transformers
- Audio embeddings using CLAP
- Utility functions for working with embeddings
"""

from omnifeed.featurization.text import (
    EmbeddingService,
    SentenceTransformerEmbedder,
    get_embedding_service,
    make_embedding,
    get_embedding_by_type,
)
from omnifeed.featurization.audio import (
    AudioEmbeddingService,
    CLAPEmbedder,
    get_audio_embedding_service,
)

__all__ = [
    # Text embeddings
    "EmbeddingService",
    "SentenceTransformerEmbedder",
    "get_embedding_service",
    "make_embedding",
    "get_embedding_by_type",
    # Audio embeddings
    "AudioEmbeddingService",
    "CLAPEmbedder",
    "get_audio_embedding_service",
]
