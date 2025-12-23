"""Transcript-based embeddings for YouTube videos."""

import logging
from typing import Any

from omnifeed.models import Item
from omnifeed.ranking.embeddings import make_embedding, get_embedding_service

logger = logging.getLogger(__name__)


def fetch_youtube_transcript(video_id: str) -> str | None:
    """Fetch transcript for a YouTube video.

    Returns the full transcript text or None if unavailable.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        logger.warning("youtube-transcript-api not installed")
        return None

    try:
        api = YouTubeTranscriptApi()

        # Fetch transcript, preferring English
        transcript = api.fetch(video_id, languages=('en', 'en-US', 'en-GB'))

        # Combine all text segments
        text_parts = [entry.text for entry in transcript]
        full_text = ' '.join(text_parts)

        # Clean up common artifacts
        full_text = full_text.replace('\n', ' ')
        full_text = ' '.join(full_text.split())  # Normalize whitespace

        return full_text

    except Exception as e:
        # Could be TranscriptsDisabled, NoTranscriptFound, etc.
        logger.debug(f"No transcript for {video_id}: {e}")
        return None


def embed_transcript(video_id: str, max_chars: int = 10000) -> dict[str, Any] | None:
    """Generate embedding from YouTube video transcript.

    Args:
        video_id: YouTube video ID
        max_chars: Maximum characters to use for embedding (transcripts can be long)

    Returns:
        Embedding dict or None if transcript unavailable
    """
    transcript = fetch_youtube_transcript(video_id)
    if not transcript:
        return None

    # Truncate if needed (transformers have token limits)
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars]

    # Use the standard embedding service
    service = get_embedding_service()
    vectors = service.model.encode([transcript])

    return make_embedding(
        embedding_type="transcript",
        model=service.DEFAULT_TEXT_MODEL,
        vector=vectors[0],
        source="youtube",
        video_id=video_id,
        transcript_length=len(transcript),
    )


def embed_youtube_items(items: list[Item]) -> dict[str, dict[str, Any]]:
    """Generate transcript embeddings for YouTube items.

    Args:
        items: List of items to process

    Returns:
        Dict mapping item_id -> embedding (only for successful items)
    """
    results = {}

    for item in items:
        # Check if it's a YouTube video
        video_id = item.metadata.get("video_id")
        if not video_id:
            # Try to extract from URL
            video_id = _extract_video_id(item.url)

        if not video_id:
            continue

        embedding = embed_transcript(video_id)
        if embedding:
            results[item.id] = embedding
            logger.info(f"Generated transcript embedding for {item.title[:50]}")
        else:
            logger.debug(f"No transcript available for {item.title[:50]}")

    return results


def _extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from URL."""
    import re

    patterns = [
        r'youtube\.com/watch\?v=([^&]+)',
        r'youtube\.com/embed/([^?]+)',
        r'youtu\.be/([^?]+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None
