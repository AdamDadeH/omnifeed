"""Text embedding generation using sentence-transformers."""

from typing import Protocol, Any
import logging

from omnifeed.models import Item

logger = logging.getLogger(__name__)


def make_embedding(
    embedding_type: str,
    model: str,
    vector: list[float],
    **metadata: Any,
) -> dict[str, Any]:
    """Create a typed embedding entry."""
    return {
        "type": embedding_type,
        "model": model,
        "vector": vector,
        **metadata,
    }


def get_embedding_by_type(
    embeddings: list[dict[str, Any]],
    embedding_type: str,
) -> list[float] | None:
    """Get the first embedding of a given type."""
    for emb in embeddings:
        if emb.get("type") == embedding_type:
            return emb.get("vector")
    return None


class EmbeddingModel(Protocol):
    """Protocol for embedding models."""

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Encode texts to embeddings."""
        ...

    @property
    def embedding_dim(self) -> int:
        """Return the embedding dimension."""
        ...


class SentenceTransformerEmbedder:
    """Embedding model using sentence-transformers."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None

    def _load_model(self):
        """Lazy load the model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"Loading embedding model: {self.model_name}")
                self._model = SentenceTransformer(self.model_name)
            except ImportError:
                raise RuntimeError(
                    "sentence-transformers not installed. "
                    "Run: pip install sentence-transformers"
                )
        return self._model

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Encode texts to embeddings."""
        model = self._load_model()
        embeddings = model.encode(texts, convert_to_numpy=True)
        return [emb.tolist() for emb in embeddings]

    @property
    def embedding_dim(self) -> int:
        """Return the embedding dimension."""
        model = self._load_model()
        return model.get_sentence_embedding_dimension()


class EmbeddingService:
    """Service for generating embeddings for items.

    Uses content_text from item metadata if available, falling back to
    title + description. This allows any source adapter to provide rich
    text content (transcripts, article body, etc.) without the embedding
    service needing to know about specific platforms.
    """

    DEFAULT_TEXT_MODEL = "all-MiniLM-L6-v2"

    def __init__(self, model: EmbeddingModel | None = None):
        self.model = model or SentenceTransformerEmbedder()

    def get_item_text(self, item: Item) -> str:
        """Extract text content from item for embedding.

        Priority:
        1. content_text from metadata (transcript, article body, etc.)
        2. description from metadata
        3. title + creator name
        """
        parts = [item.title]

        # Add creator name
        if item.creator_name:
            parts.append(f"by {item.creator_name}")

        # Add content_text if available (transcript, article body, etc.)
        content_text = item.metadata.get("content_text")
        if content_text and isinstance(content_text, str):
            # Truncate to avoid too long texts
            parts.append(content_text[:1000])

        # Fall back to description if no content_text
        description = item.metadata.get("description")
        if description and isinstance(description, str) and not content_text:
            parts.append(description[:500])

        return " ".join(parts)

    def embed_item(self, item: Item) -> dict[str, Any]:
        """Generate text embedding for a single item."""
        text = self.get_item_text(item)
        vectors = self.model.encode([text])
        return make_embedding(
            embedding_type="text",
            model=self.DEFAULT_TEXT_MODEL,
            vector=vectors[0],
        )

    def embed_items(self, items: list[Item]) -> list[dict[str, Any]]:
        """Generate text embeddings for multiple items (batched)."""
        texts = [self.get_item_text(item) for item in items]
        vectors = self.model.encode(texts)
        return [
            make_embedding(
                embedding_type="text",
                model=self.DEFAULT_TEXT_MODEL,
                vector=vec,
            )
            for vec in vectors
        ]

    def embed_items_legacy(self, items: list[Item]) -> list[list[float]]:
        """Generate embeddings for multiple items (legacy format)."""
        texts = [self.get_item_text(item) for item in items]
        return self.model.encode(texts)


# Singleton instance for reuse
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get or create the embedding service singleton."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
