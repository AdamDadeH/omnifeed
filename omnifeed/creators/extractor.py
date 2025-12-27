"""Extract creator information from content metadata.

This module provides utilities for extracting creator names and roles
from item descriptions, credits sections, and other metadata.
"""

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ExtractedCreator:
    """A creator extracted from content metadata."""
    name: str
    role: str | None = None  # e.g., "director", "editor", "guest", "featuring"
    external_id: str | None = None  # e.g., YouTube channel ID
    external_id_type: str | None = None  # e.g., "youtube"
    confidence: float = 0.5  # 0-1, how confident we are in this extraction


# Common role patterns in credits - only match at start of line for credits sections
ROLE_PATTERNS = [
    # "Role: Name" or "Role | Name" - must be at start of line (credits format)
    (r"(?:^|\n)\s*(?P<role>director|producer|editor|writer|host|created by|art by|music by|composed by|performed by|vocals? by|directed by|produced by|written by|edited by|animation by|cinematography by|dop|director of photography)[:\s|]+(?P<name>[A-Z][a-zA-Z\s\.\-\']{2,30})(?:\n|$|,|\||&)", re.IGNORECASE | re.MULTILINE),
]

# YouTube channel/handle patterns
YOUTUBE_PATTERNS = [
    # @handle mentions (but not @mentions in middle of text)
    (r"(?:^|\s)@([a-zA-Z0-9_]{3,25})(?:\s|$|[,\.\!\?])", "handle"),
    # youtube.com/@handle or /channel/ID or /c/name
    (r"youtube\.com/@([a-zA-Z0-9_\-]+)", "handle"),
    (r"youtube\.com/channel/(UC[a-zA-Z0-9_\-]{22})", "channel_id"),
    (r"youtube\.com/c/([a-zA-Z0-9_\-]+)", "custom_url"),
]

# "With X" pattern - more restrictive, only in titles, names must look like proper names
# Name must be 2-4 capitalized words, no lowercase-starting words
WITH_PATTERN = re.compile(
    r"\bw(?:ith|/)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})(?:\s*[!,\.\|]|$)",
    re.MULTILINE
)

# "With X and Y" pattern - capture both names separately
WITH_AND_PATTERN = re.compile(
    r"\bw(?:ith|/)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s+and\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})(?:\s*[!,\.\|]|$)",
    re.MULTILINE
)

# "Featuring X" pattern - more restrictive
FEATURING_PATTERN = re.compile(
    r"\b(?:featuring|feat\.?|ft\.?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})(?:\s*[!,\.\|]|$)",
    re.IGNORECASE
)

# "X and Y" as hosts/presenters (common for YouTube collaborations)
# Only single first names like "Griffin and Justin", "Nick and Griffin"
NAME_AND_NAME_PATTERN = re.compile(
    r"^([A-Z][a-z]{2,15})\s+and\s+([A-Z][a-z]{2,15})\b",
    re.MULTILINE
)

# Twitter/social handle patterns that include names
# "Follow Griffin on Twitter: ..." or "twitter.com/griffinmcelroy"
TWITTER_NAME_PATTERN = re.compile(
    r"Follow\s+([A-Z][a-z]+)\s+on\s+Twitter",
    re.IGNORECASE
)


def extract_creators_from_description(
    description: str,
    title: str | None = None,
    source_type: str | None = None,
) -> list[ExtractedCreator]:
    """Extract potential creators from a content description.

    Args:
        description: The content description/body text
        title: Optional title for additional context
        source_type: Source type (e.g., "youtube_channel") for format-specific parsing

    Returns:
        List of extracted creators with roles and confidence scores
    """
    creators: list[ExtractedCreator] = []
    seen_names: set[str] = set()

    # Extract from role patterns (credits sections) - only from description
    for pattern, flags in ROLE_PATTERNS:
        for match in re.finditer(pattern, description, flags):
            name = _clean_name(match.group("name"))
            role = match.group("role").lower().strip()

            if name and name.lower() not in seen_names and _is_valid_name(name):
                seen_names.add(name.lower())
                creators.append(ExtractedCreator(
                    name=name,
                    role=_normalize_role(role),
                    confidence=0.8,  # High confidence for explicit credits
                ))

    # Extract "X and Y" pattern from description (e.g., "Griffin and Justin")
    # These are typically hosts/presenters mentioned at start of sentences
    for match in NAME_AND_NAME_PATTERN.finditer(description):
        for group in [match.group(1), match.group(2)]:
            if group:
                name = _clean_name(group)
                if name and name.lower() not in seen_names and _is_valid_first_name(name):
                    seen_names.add(name.lower())
                    creators.append(ExtractedCreator(
                        name=name,
                        role="host",
                        confidence=0.75,
                    ))

    # Extract names from "Follow X on Twitter" patterns
    for match in TWITTER_NAME_PATTERN.finditer(description):
        name = _clean_name(match.group(1))
        if name and name.lower() not in seen_names and _is_valid_first_name(name):
            seen_names.add(name.lower())
            creators.append(ExtractedCreator(
                name=name,
                role="host",
                confidence=0.8,  # High confidence - explicit credit
            ))

    # Extract "with X and Y" collaborators from title only
    if title:
        # First try "with X and Y" pattern
        for match in WITH_AND_PATTERN.finditer(title):
            for group in [match.group(1), match.group(2)]:
                if group:
                    name = _clean_name(group)
                    if name and name.lower() not in seen_names and _is_valid_name(name):
                        seen_names.add(name.lower())
                        creators.append(ExtractedCreator(
                            name=name,
                            role="guest",
                            confidence=0.75,
                        ))

        # Then try simple "with X" pattern (only if X and Y didn't match)
        if not any(c.role == "guest" for c in creators):
            for match in WITH_PATTERN.finditer(title):
                name = _clean_name(match.group(1))
                if name and name.lower() not in seen_names and _is_valid_name(name):
                    seen_names.add(name.lower())
                    creators.append(ExtractedCreator(
                        name=name,
                        role="guest",
                        confidence=0.7,
                    ))

    # Extract "featuring" mentions from description only
    for match in FEATURING_PATTERN.finditer(description):
        name = _clean_name(match.group(1))
        if name and name.lower() not in seen_names and _is_valid_name(name):
            seen_names.add(name.lower())
            creators.append(ExtractedCreator(
                name=name,
                role="featuring",
                confidence=0.7,
            ))

    return creators


def _is_valid_first_name(name: str) -> bool:
    """Check if a single word looks like a valid first name."""
    if not name or len(name) < 3 or len(name) > 15:
        return False
    # Must be single word
    if " " in name:
        return False
    # Must start with uppercase
    if not name[0].isupper():
        return False
    # Rest should be lowercase
    if not name[1:].islower():
        return False
    # Common false positives for first names
    false_positives = {
        "watch", "subscribe", "like", "follow", "click", "check", "visit",
        "the", "and", "for", "from", "with", "about", "more", "new",
        "warning", "disclaimer", "credits", "thanks", "special",
        "polygon", "vox", "youtube", "twitter", "facebook", "instagram",
        "garfield", "shrek", "batman", "mario", "sonic",  # fictional characters
    }
    if name.lower() in false_positives:
        return False
    return True


def _clean_name(name: str) -> str:
    """Clean up an extracted name."""
    if not name:
        return ""
    # Remove extra whitespace
    name = " ".join(name.split())
    # Remove trailing punctuation
    name = name.rstrip(".,;:")
    # Remove common non-name suffixes
    for suffix in [" and", " &", " featuring", " feat", " ft"]:
        if name.lower().endswith(suffix):
            name = name[:-len(suffix)]
    return name.strip()


def _is_valid_name(name: str) -> bool:
    """Check if extracted text looks like a valid person/entity name."""
    if not name or len(name) < 2:
        return False
    # Too long is suspicious
    if len(name) > 30:
        return False
    # Must have at least one letter
    if not any(c.isalpha() for c in name):
        return False
    # Name should have 1-3 words (first last, or first middle last)
    words = name.split()
    if len(words) > 3:
        return False
    # Each word should start with uppercase (proper name)
    for word in words:
        if word and not word[0].isupper():
            return False
    # Reject if name contains ALL CAPS words (likely role description)
    for word in words:
        if len(word) > 2 and word.isupper():
            return False
    # Reject common false positives and non-name words
    false_positives = {
        "subscribe", "like", "comment", "share", "click", "link",
        "video", "channel", "playlist", "watch", "more", "here",
        "patreon", "twitter", "instagram", "discord", "twitch",
        "credits", "thanks", "special", "support", "episode",
        "official", "audio", "video", "remix", "version",
        "new", "now", "out", "live", "tour", "album", "single",
        "clearance", "starts", "amazon", "lowest", "price",
        "pre-installed", "installed", "aura", "lighting",
        "hub", "world", "open", "explains", "essay", "visual",
        "friday", "monday", "tuesday", "wednesday", "thursday",
        "saturday", "sunday", "polygon", "vox",
        "producer", "director", "editor", "writer", "crew",  # role words
        "executive", "starring", "art",
    }
    name_lower = name.lower()
    if name_lower in false_positives:
        return False
    # Reject if any word is a false positive
    for word in words:
        if word.lower() in false_positives:
            return False
    # Reject URLs
    if "http" in name_lower or ".com" in name_lower:
        return False
    # Reject if it looks like a phrase (contains certain patterns)
    phrase_patterns = ["and the", "on the", "in the", "at the", "for the",
                       "a new", "the new", "out now", "is a"]
    for pattern in phrase_patterns:
        if pattern in name_lower:
            return False
    return True


def _normalize_role(role: str) -> str:
    """Normalize role names to standard forms."""
    role = role.lower().strip()

    role_map = {
        "directed by": "director",
        "produced by": "producer",
        "written by": "writer",
        "edited by": "editor",
        "created by": "creator",
        "animation by": "animator",
        "art by": "artist",
        "music by": "composer",
        "composed by": "composer",
        "performed by": "performer",
        "vocals by": "vocalist",
        "vocal by": "vocalist",
        "cinematography by": "cinematographer",
        "dop": "cinematographer",
        "director of photography": "cinematographer",
        "ft.": "featuring",
        "ft": "featuring",
        "feat.": "featuring",
        "feat": "featuring",
        "with": "guest",
        "by": "creator",
    }

    return role_map.get(role, role)


def extract_from_item(item_metadata: dict[str, Any], title: str, source_type: str) -> list[ExtractedCreator]:
    """Convenience function to extract creators from an Item's metadata.

    Args:
        item_metadata: The item's metadata dict
        title: The item's title
        source_type: The source type

    Returns:
        List of extracted creators
    """
    description = item_metadata.get("content_text", "") or item_metadata.get("content_html", "") or ""
    return extract_creators_from_description(description, title, source_type)
