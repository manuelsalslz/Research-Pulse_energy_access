"""Europe PMC fetcher.

Europe PMC is a free, keyless index of 40M+ life-science and biomedical
publications (including PubMed, PMC, preprints, and Agricola). It gives
strong coverage for medicine, biology, neuroscience, public health,
agriculture, and adjacent fields that arXiv barely touches.

Docs: https://europepmc.org/RestfulWebService
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from ..models import Paper
from .http import get

API_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def _parse_date(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def fetch(query: str, lookback_days: int = 0, max_results: int = 25) -> List[Paper]:
    """Fetch papers matching a free-text query.

    Args:
        query: Free-text search query.
        lookback_days: If > 0, restrict to papers first published in the window.
        max_results: Maximum number of results (API caps at 1000).
    """
    if not query:
        return []

    q = query.strip()
    if lookback_days > 0:
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=max(lookback_days, 1))
        q = f"({q}) AND FIRST_PDATE:[{start:%Y-%m-%d} TO {now:%Y-%m-%d}]"

    params = {
        "query": q,
        "format": "json",
        "resultType": "core",
        "pageSize": min(max_results, 100),
        "sort": "P_PDATE_D desc" if lookback_days > 0 else "",
    }

    resp = get(API_URL, params=params)
    if resp is None:
        return []
    try:
        data = resp.json()
    except ValueError:
        return []

    papers: List[Paper] = []
    for item in data.get("resultList", {}).get("result", []) or []:
        title = " ".join((item.get("title") or "").split()).rstrip(".")
        if not title:
            continue

        doi = item.get("doi", "")
        if doi:
            url = f"https://doi.org/{doi}"
            paper_id = doi
        else:
            pmid = item.get("pmid", "")
            src = item.get("source", "MED")
            item_id = item.get("id", "")
            url = (
                f"https://europepmc.org/article/{src}/{item_id}" if item_id else ""
            )
            paper_id = f"pmid:{pmid}" if pmid else url

        authors = [
            a.strip()
            for a in (item.get("authorString") or "").rstrip(".").split(",")
            if a.strip()
        ]

        papers.append(Paper(
            id=paper_id,
            title=title,
            abstract=" ".join((item.get("abstractText") or "").split()),
            authors=authors,
            url=url,
            source="Europe PMC",
            published=_parse_date(item.get("firstPublicationDate", "")),
            citations=int(item.get("citedByCount") or 0),
        ))
    return papers[:max_results]
