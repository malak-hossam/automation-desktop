"""
api.py — JSONPlaceholder API client with graceful fallback.
"""
from __future__ import annotations

import logging
from typing import Any

import requests

from src.config import POSTS_API_URL, POSTS_COUNT

logger = logging.getLogger(__name__)

_FALLBACK_POSTS: list[dict[str, Any]] = [
    {
        "userId": 1,
        "id": i,
        "title": f"Sample Post {i}",
        "body": f"This is the body of sample post {i}. "
                f"The API was unavailable so fallback data is used.",
    }
    for i in range(1, POSTS_COUNT + 1)
]


def fetch_posts(n: int = POSTS_COUNT) -> list[dict[str, Any]]:
    """
    Fetch the first *n* posts from JSONPlaceholder.

    Falls back to hard-coded sample data if the request fails, so the
    automation can still proceed during an interview even without internet.
    """
    try:
        resp = requests.get(POSTS_API_URL, params={"limit": n}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # dummyjson wraps posts in {"posts": [...]}, flat list also supported
        posts = data["posts"] if isinstance(data, dict) and "posts" in data else data
        logger.info("Fetched %d posts from %s", len(posts), POSTS_API_URL)
        return posts[:n]
    except requests.RequestException as exc:
        logger.warning(
            "API request failed (%s). Using fallback data for %d posts.", exc, n
        )
        return _FALLBACK_POSTS[:n]


def format_post_content(post: dict[str, Any]) -> str:
    """Return the text to be typed into Notepad for a given post."""
    return f"Title: {post['title']}\n\n{post['body']}"


def post_filename(post: dict[str, Any]) -> str:
    """Return the filename for saving a post."""
    return f"post_{post['id']}.txt"
