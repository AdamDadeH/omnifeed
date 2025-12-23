"""Audio embedding generation using CLAP (Contrastive Language-Audio Pretraining).

CLAP embeds audio and text into the same latent space, enabling:
- Finding music similar to other music
- Finding music matching text descriptions
- Cross-modal search (describe what you want, find matching audio)
"""

import io
import logging
import tempfile
from pathlib import Path
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class AudioEmbeddingModel(Protocol):
    """Protocol for audio embedding models."""

    def embed_audio(self, audio_path: str) -> list[float]:
        """Embed audio file to vector."""
        ...

    def embed_audio_url(self, url: str) -> list[float]:
        """Download and embed audio from URL."""
        ...

    def embed_text(self, text: str) -> list[float]:
        """Embed text description (for cross-modal search)."""
        ...

    @property
    def embedding_dim(self) -> int:
        """Return the embedding dimension."""
        ...


class CLAPEmbedder:
    """Audio embeddings using CLAP model.

    Uses laion/larger_clap_music_and_speech for music-optimized embeddings.
    """

    def __init__(self, model_name: str = "laion/larger_clap_music_and_speech"):
        self.model_name = model_name
        self._model = None
        self._processor = None

    def _load_model(self):
        """Lazy load the CLAP model."""
        if self._model is None:
            try:
                from transformers import ClapModel, ClapProcessor
                logger.info(f"Loading CLAP model: {self.model_name}")
                self._processor = ClapProcessor.from_pretrained(self.model_name)
                self._model = ClapModel.from_pretrained(self.model_name)
            except ImportError:
                raise RuntimeError(
                    "transformers not installed. "
                    "Run: pip install transformers librosa soundfile"
                )
        return self._model, self._processor

    def _load_audio(self, audio_path: str, target_sr: int = 48000) -> tuple:
        """Load audio file and resample to target sample rate."""
        try:
            import librosa
            audio, sr = librosa.load(audio_path, sr=target_sr, mono=True)
            return audio, sr
        except ImportError:
            raise RuntimeError("librosa not installed. Run: pip install librosa")

    def embed_audio(self, audio_path: str) -> list[float]:
        """Embed audio file to vector."""
        model, processor = self._load_model()

        audio, sr = self._load_audio(audio_path)

        # Process audio
        inputs = processor(
            audios=audio,
            sampling_rate=sr,
            return_tensors="pt",
        )

        # Get embedding
        import torch
        with torch.no_grad():
            audio_features = model.get_audio_features(**inputs)

        # Normalize and convert to list
        embedding = audio_features[0].numpy()
        embedding = embedding / (embedding ** 2).sum() ** 0.5  # L2 normalize
        return embedding.tolist()

    def embed_audio_url(self, url: str) -> list[float]:
        """Download audio from URL and embed it."""
        # Download audio to temp file
        try:
            response = httpx.get(url, follow_redirects=True, timeout=60.0)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise ValueError(f"Failed to download audio: {e}")

        # Write to temp file
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(response.content)
            temp_path = f.name

        try:
            return self.embed_audio(temp_path)
        finally:
            # Cleanup
            Path(temp_path).unlink(missing_ok=True)

    def embed_text(self, text: str) -> list[float]:
        """Embed text description for cross-modal search."""
        model, processor = self._load_model()

        inputs = processor(text=text, return_tensors="pt", padding=True)

        import torch
        with torch.no_grad():
            text_features = model.get_text_features(**inputs)

        embedding = text_features[0].numpy()
        embedding = embedding / (embedding ** 2).sum() ** 0.5
        return embedding.tolist()

    @property
    def embedding_dim(self) -> int:
        """Return the embedding dimension (512 for CLAP)."""
        return 512


class AudioEmbeddingService:
    """Service for generating audio embeddings for items."""

    DEFAULT_MODEL = "laion/larger_clap_music_and_speech"

    def __init__(self, model: AudioEmbeddingModel | None = None):
        self._model = model
        self._model_loaded = False

    @property
    def model(self) -> AudioEmbeddingModel:
        """Lazy load model on first use."""
        if self._model is None:
            self._model = CLAPEmbedder()
        return self._model

    def embed_from_url(self, audio_url: str) -> dict | None:
        """Generate embedding from audio URL."""
        from omnifeed.ranking.embeddings import make_embedding
        try:
            vector = self.model.embed_audio_url(audio_url)
            return make_embedding(
                embedding_type="audio",
                model=self.DEFAULT_MODEL,
                vector=vector,
                source_url=audio_url,
            )
        except Exception as e:
            logger.warning(f"Failed to embed audio from {audio_url}: {e}")
            return None

    def embed_from_file(self, audio_path: str) -> dict | None:
        """Generate embedding from local audio file."""
        from omnifeed.ranking.embeddings import make_embedding
        try:
            vector = self.model.embed_audio(audio_path)
            return make_embedding(
                embedding_type="audio",
                model=self.DEFAULT_MODEL,
                vector=vector,
                source_path=audio_path,
            )
        except Exception as e:
            logger.warning(f"Failed to embed audio from {audio_path}: {e}")
            return None

    def embed_description(self, text: str) -> dict | None:
        """Generate embedding from text description (for cross-modal search)."""
        from omnifeed.ranking.embeddings import make_embedding
        try:
            vector = self.model.embed_text(text)
            return make_embedding(
                embedding_type="audio_text",  # Text in audio embedding space
                model=self.DEFAULT_MODEL,
                vector=vector,
                source_text=text,
            )
        except Exception as e:
            logger.warning(f"Failed to embed text: {e}")
            return None


# Singleton
_audio_embedding_service: AudioEmbeddingService | None = None


def get_audio_embedding_service() -> AudioEmbeddingService:
    """Get or create the audio embedding service singleton."""
    global _audio_embedding_service
    if _audio_embedding_service is None:
        _audio_embedding_service = AudioEmbeddingService()
    return _audio_embedding_service
