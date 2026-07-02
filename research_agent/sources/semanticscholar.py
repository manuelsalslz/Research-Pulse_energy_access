"""Semantic Scholar fetcher.

Semantic Scholar (Allen Institute for AI) indexes ~200M papers across ALL
research fields -- computer science, medicine, biology, physics, economics,
social sciences, and more.

The shared keyless pool is heavily rate-limited (frequent HTTP 429), so this
source is treated as an *optional enhancement*: it only runs when a (free)
`S2_API_KEY` is set. Request one at
https://www.semanticscholar.org/product/api#api-key-form. Without a key this
fetcher returns nothing instantly, keeping the keyless experience fast; the
reliable keyless coverage comes from OpenAlex + Crossref + Europe PMC + arXiv.

Docs: https://api.semanticscholar.org/api-docs/graph
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from ..models import Paper
from .http import get

API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

FIELDS = ",".join([
    "title",
    "abstract",
    "authors",
    "url",
    "publicationDate",
    "year",
    "citationCount",
    "externalIds",
    "openAccessPdf",
    "fieldsOfStudy",
])


def _parse_date(item: dict) -> Optional[datetime]:
    raw = item.get("publicationDate")
    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    year = item.get("year")
    if year:
        try:
            return datetime(int(year), 1, 1, tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass
    return None


def _best_url(item: dict) -> str:
    """Prefer an open-access PDF, then DOI, then the S2 page."""
    oa = item.get("openAccessPdf") or {}
    if oa.get("url"):
        return oa["url"]
    ext = item.get("externalIds") or {}
    if ext.get("DOI"):
        return f"https://doi.org/{ext['DOI']}"
    if ext.get("ArXiv"):
        return f"https://arxiv.org/abs/{ext['ArXiv']}"
    return item.get("url", "")


def _stable_id(item: dict) -> str:
    """Use DOI/arXiv ids when available so cross-source dedup works."""
    ext = item.get("externalIds") or {}
    if ext.get("DOI"):
        return ext["DOI"]
    if ext.get("ArXiv"):
        return f"arxiv:{ext['ArXiv']}"
    return item.get("paperId", "") or item.get("url", "")


def fetch(query: str, lookback_days: int = 0, max_results: int = 25) -> List[Paper]:
    """Fetch papers matching a free-text query.

    Args:
        query: Free-text search query.
        lookback_days: If > 0, only return papers published in this window.
        max_results: Maximum number of results (API caps at 100 per page).
    """
    if not query:
        return []

    # Keyless access is rate-limited to the point of being unusable, so skip
    # the network entirely unless the user provides a (free) key.
    api_key = os.environ.get("S2_API_KEY", "").strip()
    if not api_key:
        return []

    params = {
        "query": query,
        "fields": FIELDS,
        "limit": min(max_results, 100),
    }
    if lookback_days > 0:
        start = datetime.now(timezone.utc) - timedelta(days=max(lookback_days, 1))
        # Open-ended range: from start date until now.
        params["publicationDateOrYear"] = f"{start:%Y-%m-%d}:"

    resp = get(API_URL, params=params, headers={"x-api-key": api_key})
    if resp is None:
        return []
    try:
        data = resp.json()
    except ValueError:
        return []

    papers: List[Paper] = []
    for item in data.get("data", []) or []:
        title = " ".join((item.get("title") or "").split())
        if not title:
            continue
        authors = [
            a.get("name", "") for a in (item.get("authors") or []) if a.get("name")
        ]
        papers.append(Paper(
            id=_stable_id(item),
            title=title,
            abstract=" ".join((item.get("abstract") or "").split()),
            authors=authors,
            url=_best_url(item),
            source="Semantic Scholar",
            published=_parse_date(item),
            categories=[f for f in (item.get("fieldsOfStudy") or []) if f],
            citations=int(item.get("citationCount") or 0),
        ))
    return papers[:max_results]
