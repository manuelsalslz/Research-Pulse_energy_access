"""arXiv fetcher.

Uses the public arXiv Atom API (no key required). Queries by category and a
submittedDate window, sorted by most recent. Respects the requested polite
delay between calls.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import feedparser

from ..models import Paper
from .http import get

API_URL = "http://export.arxiv.org/api/query"


def _venue_from_arxiv_text(text: str) -> Tuple[str, Optional[int]]:
    """Best-effort venue/year from arXiv journal-ref or comments."""
    if not text:
        return "", None
    year_match = re.search(r"\b(20\d{2})\b", text)
    year = int(year_match.group(1)) if year_match else None
    cleaned = re.sub(r"(?i)\b(accepted at|to appear in|presented at|published in)\b", "", text)
    cleaned = re.sub(r"\b(20\d{2})\b", "", cleaned).strip(" ,.;")
    return cleaned.strip(), year


def _paper_from_entry(entry) -> Paper:
    published = None
    if getattr(entry, "published_parsed", None):
        published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

    journal_ref = getattr(entry, "arxiv_journal_ref", "") or ""
    comment = getattr(entry, "arxiv_comment", "") or ""
    venue, vyear = _venue_from_arxiv_text(journal_ref or comment)
    year = vyear or (published.year if published else None)

    return Paper(
        id=entry.get("id", entry.get("link", "")),
        title=" ".join(entry.get("title", "").split()),
        abstract=" ".join(entry.get("summary", "").split()),
        authors=[a.get("name", "") for a in entry.get("authors", [])],
        url=entry.get("link", ""),
        source="arXiv",
        published=published,
        categories=[t.get("term", "") for t in entry.get("tags", [])],
        venue=venue,
        year=year,
    )


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
        papers.append(_paper_from_entry(entry))
    return papers
