"""RSS news fetcher for the shared "What's happening in research" section."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List

import feedparser

from ..config import NewsFeed
from ..models import NewsItem

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str, limit: int = 240) -> str:
    text = _TAG_RE.sub("", text or "")
    text = " ".join(text.split())
    return text[: limit - 1] + "\u2026" if len(text) > limit else text


def fetch(feeds: List[NewsFeed], per_feed: int = 5) -> List[NewsItem]:
    """Fetch latest entries across all configured feeds."""
    items: List[NewsItem] = []
    for feed in feeds:
        parsed = feedparser.parse(feed.url)
        for entry in parsed.entries[:per_feed]:
            published = None
            if getattr(entry, "published_parsed", None):
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            elif getattr(entry, "updated_parsed", None):
                published = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
            items.append(
                NewsItem(
                    title=" ".join(entry.get("title", "").split()),
                    url=entry.get("link", ""),
                    source=feed.name,
                    summary=_clean(entry.get("summary", "")),
                    published=published,
                )
            )
    # Newest first; undated items sink to the bottom.
    items.sort(key=lambda i: i.published or datetime.min.replace(tzinfo=timezone.utc),
               reverse=True)
    return items
