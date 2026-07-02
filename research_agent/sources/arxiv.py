"""arXiv fetcher.

Uses the public arXiv Atom API (no key required). Queries by category and a
submittedDate window, sorted by most recent. Respects the requested polite
delay between calls.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import List

import feedparser

from ..models import Paper
from .http import get

API_URL = "http://export.arxiv.org/api/query"


def _date_window(lookback_days: int) -> str:
    """Build a `[YYYYMMDDHHMM TO YYYYMMDDHHMM]` window in GMT for submittedDate."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=max(lookback_days, 1))
    return f"[{start:%Y%m%d}0000 TO {now:%Y%m%d}2359]"


def fetch(categories: List[str], lookback_days: int = 2, max_results: int = 50,
          delay: float = 3.0) -> List[Paper]:
    """Fetch recent papers for the given arXiv categories."""
    if not categories:
        return []

    cat_clause = " OR ".join(f"cat:{c}" for c in categories)
    window = _date_window(lookback_days)
    search_query = f"({cat_clause}) AND submittedDate:{window}"

    params = {
        "search_query": search_query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    resp = get(API_URL, params=params)
    # Be polite: arXiv asks for >= 3s between requests.
    time.sleep(delay)
    if resp is None:
        return []

    feed = feedparser.parse(resp.content)
    papers: List[Paper] = []
    for entry in feed.entries:
        published = None
        if getattr(entry, "published_parsed", None):
            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        papers.append(
            Paper(
                id=entry.get("id", entry.get("link", "")),
                title=" ".join(entry.get("title", "").split()),
                abstract=" ".join(entry.get("summary", "").split()),
                authors=[a.get("name", "") for a in entry.get("authors", [])],
                url=entry.get("link", ""),
                source="arXiv",
                published=published,
                categories=[t.get("term", "") for t in entry.get("tags", [])],
            )
        )
    return papers
