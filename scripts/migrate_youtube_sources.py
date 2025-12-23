#!/usr/bin/env python3
"""Migrate YouTube RSS sources to use the YouTube Data API adapter.

This script converts sources that were added as RSS feeds (15 video limit)
to use the YouTube Data API adapter (50 video limit).

Usage:
    python scripts/migrate_youtube_sources.py
"""

import json
import re
import sqlite3
from pathlib import Path

import httpx

# Load config for API key
config_path = Path("~/.omnifeed/config.json").expanduser()
config = json.loads(config_path.read_text())
API_KEY = config.get("extra", {}).get("youtube_api_key")

if not API_KEY:
    print("ERROR: No youtube_api_key in ~/.omnifeed/config.json")
    exit(1)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
DB_PATH = Path("~/.omnifeed/data.db").expanduser()


def get_channel_info(channel_id: str) -> dict | None:
    """Fetch channel info from YouTube API."""
    params = {
        "key": API_KEY,
        "part": "snippet,contentDetails",
        "id": channel_id,
    }
    response = httpx.get(f"{YOUTUBE_API_BASE}/channels", params=params, timeout=30.0)
    if response.status_code != 200:
        return None
    data = response.json()
    if not data.get("items"):
        return None
    return data["items"][0]


def resolve_username(username: str) -> str | None:
    """Resolve a YouTube username to channel ID."""
    # Try as handle
    params = {
        "key": API_KEY,
        "part": "id",
        "forHandle": f"@{username}" if not username.startswith("@") else username,
    }
    response = httpx.get(f"{YOUTUBE_API_BASE}/channels", params=params, timeout=30.0)
    if response.status_code == 200:
        data = response.json()
        if data.get("items"):
            return data["items"][0]["id"]

    # Try as username
    params = {"key": API_KEY, "part": "id", "forUsername": username}
    response = httpx.get(f"{YOUTUBE_API_BASE}/channels", params=params, timeout=30.0)
    if response.status_code == 200:
        data = response.json()
        if data.get("items"):
            return data["items"][0]["id"]

    return None


def migrate_source(conn: sqlite3.Connection, source_id: str, uri: str, display_name: str) -> bool:
    """Migrate a single YouTube RSS source to use the Data API."""

    # Parse the RSS URL to extract channel/user/playlist ID
    channel_id = None
    is_playlist = False

    # Check for channel_id
    match = re.search(r"channel_id=([^&]+)", uri)
    if match:
        channel_id = match.group(1)

    # Check for user
    if not channel_id:
        match = re.search(r"user=([^&]+)", uri)
        if match:
            username = match.group(1)
            print(f"  Resolving username '{username}'...")
            channel_id = resolve_username(username)
            if not channel_id:
                print(f"  ERROR: Could not resolve username '{username}'")
                return False

    # Check for playlist_id (can't migrate these easily)
    if not channel_id:
        match = re.search(r"playlist_id=([^&]+)", uri)
        if match:
            print(f"  SKIP: '{display_name}' is a playlist, not a channel. Keep as RSS.")
            return False

    if not channel_id:
        print(f"  ERROR: Could not extract channel ID from '{uri}'")
        return False

    # Fetch channel info to get uploads playlist ID
    print(f"  Fetching channel info for {channel_id}...")
    channel_info = get_channel_info(channel_id)
    if not channel_info:
        print(f"  ERROR: Could not fetch channel info for {channel_id}")
        return False

    snippet = channel_info["snippet"]
    content_details = channel_info["contentDetails"]
    uploads_playlist_id = content_details["relatedPlaylists"]["uploads"]

    # Build new metadata
    new_metadata = {
        "channel_id": channel_id,
        "uploads_playlist_id": uploads_playlist_id,
        "description": snippet.get("description"),
        "custom_url": snippet.get("customUrl"),
    }

    # Get avatar
    thumbnails = snippet.get("thumbnails", {})
    avatar_url = (
        thumbnails.get("high", {}).get("url")
        or thumbnails.get("medium", {}).get("url")
        or thumbnails.get("default", {}).get("url")
    )

    # Update the database
    new_uri = f"youtube:channel:{channel_id}"
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE sources
        SET source_type = 'youtube_channel',
            uri = ?,
            metadata = ?,
            avatar_url = COALESCE(avatar_url, ?)
        WHERE id = ?
    """, (new_uri, json.dumps(new_metadata), avatar_url, source_id))

    print(f"  MIGRATED: {display_name} -> youtube_channel")
    return True


def main():
    print("YouTube Source Migration")
    print("=" * 50)
    print()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Find YouTube RSS sources
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, display_name, uri, source_type, metadata
        FROM sources
        WHERE source_type = 'rss' AND uri LIKE '%youtube.com%'
    """)

    sources = cursor.fetchall()

    if not sources:
        print("No YouTube RSS sources found to migrate.")
        return

    print(f"Found {len(sources)} YouTube RSS source(s) to migrate:\n")

    migrated = 0
    skipped = 0
    failed = 0

    for source in sources:
        print(f"Processing: {source['display_name']}")
        print(f"  Current URI: {source['uri']}")

        if migrate_source(conn, source['id'], source['uri'], source['display_name']):
            migrated += 1
        elif "playlist_id" in source['uri']:
            skipped += 1
        else:
            failed += 1
        print()

    conn.commit()
    conn.close()

    print("=" * 50)
    print(f"Migration complete: {migrated} migrated, {skipped} skipped, {failed} failed")
    print("\nRestart the backend to use the new YouTube Data API adapter.")


if __name__ == "__main__":
    main()
