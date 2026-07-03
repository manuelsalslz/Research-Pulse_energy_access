"""OpenAlex fetcher.

OpenAlex is a free, open catalog of scholarly works (no key required). We use
it for cross-domain coverage and for citation counts that help ranking. We
filter by publication date and a free-text search query.

Docs: https://docs.openalex.org/api-entities/works
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from ..models import Paper
from .http import get

API_URL = "https://api.openalex.org/works"


def _reconstruct_abstract(inverted_index: Optional[dict]) -> str:
    """OpenAlex stores abstracts as an inverted index; rebuild plain text."""
    if not inverted_index:
        return ""
    positions: List[Tuple[int, str]] = []
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort(key=lambda p: p[0])
    return " ".join(word for _, word in positions)


def fetch(query: str, lookback_days: int = 2, max_results: int = 25,
          mailto: str = "", venue: Optional[str] = None) -> List[Paper]:
    """Fetch recent works matching a free-text query."""
    if not query:
        return []

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=max(lookback_days, 1))

    filters = [f"from_publication_date:{start:%Y-%m-%d}"]
    if venue:
        filters.append(f"primary_location.source.display_name.search:{venue}")

    params = {
        "search": query,
        "filter": ",".join(filters),
        "sort": "publication_date:desc",
        "per-page": min(max_results, 50),
    }
    # The "polite pool" just asks for a contact email; entirely optional/free.
    if mailto:
        params["mailto"] = mailto

    resp = get(API_URL, params=params)
    if resp is None:
        return []
    try:
        data = resp.json()
    except ValueError:
        return []

    papers: List[Paper] = []
    for w in data.get("results", []):
        pub = None
        if w.get("publication_date"):
            try:
                pub = datetime.strptime(w["publication_date"], "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                pub = None
        authors = [
            a.get("author", {}).get("display_name", "")
            for a in w.get("authorships", [])
        ]
        url = w.get("doi") or w.get("id", "")
        loc = w.get("primary_location") or {}
        source = loc.get("source") or {}
        venue = source.get("display_name") or ""
        year = w.get("publication_year")
        papers.append(
            Paper(
                id=w.get("id", url),
                title=" ".join((w.get("title") or "").split()),
                abstract=_reconstruct_abstract(w.get("abstract_inverted_index")),
                authors=[a for a in authors if a],
                url=url,
                source="OpenAlex",
                published=pub,
                citations=int(w.get("cited_by_count", 0) or 0),
                venue=venue,
                year=int(year) if year else (pub.year if pub else None),
            )
        )
    return papers
