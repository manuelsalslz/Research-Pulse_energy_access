"""bioRxiv / medRxiv fetcher.

Uses the free bioRxiv "details" API which returns JSON for a date range:
    https://api.biorxiv.org/details/<server>/<from>/<to>/<cursor>
No key required.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from ..models import Paper
from .http import get

API_TEMPLATE = "https://api.biorxiv.org/details/{server}/{start}/{end}/0"


def fetch(servers: List[str], lookback_days: int = 2, max_results: int = 50) -> List[Paper]:
    """Fetch recent preprints from the given servers ('biorxiv'/'medrxiv')."""
    if not servers:
        return []

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=max(lookback_days, 1))
    papers: List[Paper] = []

    for server in servers:
        url = API_TEMPLATE.format(
            server=server, start=f"{start:%Y-%m-%d}", end=f"{now:%Y-%m-%d}"
        )
        resp = get(url)
        if resp is None:
            continue
        try:
            data = resp.json()
        except ValueError:
            continue

        for item in data.get("collection", [])[:max_results]:
            doi = item.get("doi", "")
            pub = None
            if item.get("date"):
                try:
                    pub = datetime.strptime(item["date"], "%Y-%m-%d").replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    pub = None
            authors = [
                a.strip()
                for a in item.get("authors", "").split(";")
                if a.strip()
            ]
            papers.append(
                Paper(
                    id=f"doi:{doi}" if doi else item.get("title", ""),
                    title=" ".join(item.get("title", "").split()),
                    abstract=" ".join(item.get("abstract", "").split()),
                    authors=authors,
                    url=f"https://doi.org/{doi}" if doi else "",
                    source=server,
                    published=pub,
                    categories=[item.get("category", "")] if item.get("category") else [],
                )
            )
    return papers
