"""Crossref fetcher.

Crossref is a major scholarly metadata source with millions of records.
It provides citation counts, DOIs, and rich metadata.

API Docs: https://api.crossref.org/swagger-ui/index.html
No API key required (but polite email recommended for rate limiting).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from ..models import Paper
from .http import get

API_URL = "https://api.crossref.org/works"


def _clean_abstract(abstract: str) -> str:
    """Clean Crossref abstract (often contains JATS XML tags)."""
    if not abstract:
        return ""
    # Remove JATS XML tags
    cleaned = re.sub(r'</?jats:\w+(?:\s+[^>]*)?>', '', abstract)
    cleaned = re.sub(r'</?[^>]+(?:>|$)', '', cleaned)
    # Decode HTML entities
    cleaned = cleaned.replace('&nbsp;', ' ')
    cleaned = cleaned.replace('&lt;', '<')
    cleaned = cleaned.replace('&gt;', '>')
    cleaned = cleaned.replace('&amp;', '&')
    cleaned = cleaned.replace('&quot;', '"')
    cleaned = cleaned.replace('&#39;', "'")
    return cleaned.strip()


def _extract_authors(author_list: List[dict]) -> List[str]:
    """Extract author names from Crossref author format."""
    authors = []
    for author in author_list:
        if 'name' in author:
            authors.append(author['name'])
        elif 'given' in author or 'family' in author:
            given = author.get('given', '')
            family = author.get('family', '')
            name = f"{given} {family}".strip()
            if name:
                authors.append(name)
    return authors


def _extract_date(published: dict) -> Optional[datetime]:
    """Extract publication date from Crossref date format."""
    try:
        date_parts = published.get('date-parts', [[]])[0]
        if date_parts and len(date_parts) >= 1:
            year = date_parts[0]
            month = date_parts[1] if len(date_parts) > 1 else 1
            day = date_parts[2] if len(date_parts) > 2 else 1
            return datetime(year, month, day, tzinfo=timezone.utc)
    except (ValueError, IndexError, TypeError):
        pass
    return None


def fetch(query: str, lookback_days: int = 30, max_results: int = 25,
          mailto: str = "") -> List[Paper]:
    """Fetch recent papers from Crossref matching a free-text query.

    Args:
        query: Free-text search query
        lookback_days: How many days back to search
        max_results: Maximum number of results
        mailto: Contact email for polite pool (optional)

    Returns:
        List of Paper objects
    """
    if not query:
        return []

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=max(lookback_days, 1))

    # Build filter for date range and article type
    filters = [
        f"from-pub-date:{start:%Y-%m-%d}",
        "type:journal-article",
    ]

    params = {
        "query": query,
        "rows": min(max_results, 50),
        "sort": "relevance",
        "order": "desc",
        "filter": ",".join(filters),
        "select": "DOI,title,author,container-title,published,abstract,subject,is-referenced-by-count,reference",
    }

    # Add polite email for rate limiting
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
    for item in data.get("message", {}).get("items", []):
        # Skip items without title or abstract
        title_list = item.get("title", [])
        if not title_list:
            continue

        title = title_list[0] if title_list else ""
        abstract = item.get("abstract", "")
        if abstract:
            abstract = _clean_abstract(abstract)

        # Skip items with fig/table DOIs (not real papers)
        doi = item.get("DOI", "")
        if doi and ("/fig-" in doi or "/table-" in doi):
            continue

        authors = _extract_authors(item.get("author", []))
        published = _extract_date(item.get("published", {}))

        journal_list = item.get("container-title", [])
        journal = journal_list[0] if journal_list else "Unknown"

        tags = item.get("subject", [])
        citations = item.get("is-referenced-by-count", 0) or 0

        url = f"https://doi.org/{doi}" if doi else ""

        papers.append(Paper(
            id=doi or url,
            title=title,
            abstract=abstract,
            authors=authors,
            url=url,
            source="Crossref",
            published=published,
            categories=tags[:5],  # Limit tags
            citations=citations,
        ))

    return papers


def fetch_by_doi(doi: str) -> Optional[Paper]:
    """Fetch a single paper by DOI.

    Args:
        doi: The DOI to look up

    Returns:
        Paper object or None if not found
    """
    if not doi:
        return None

    url = f"{API_URL}/{doi}"
    resp = get(url)
    if resp is None:
        return None

    try:
        data = resp.json()
    except ValueError:
        return None

    item = data.get("message", {})
    if not item:
        return None

    title_list = item.get("title", [])
    title = title_list[0] if title_list else ""
    abstract = item.get("abstract", "")
    if abstract:
        abstract = _clean_abstract(abstract)

    authors = _extract_authors(item.get("author", []))
    published = _extract_date(item.get("published", {}))

    journal_list = item.get("container-title", [])
    journal = journal_list[0] if journal_list else "Unknown"

    tags = item.get("subject", [])
    citations = item.get("is-referenced-by-count", 0) or 0

    return Paper(
        id=doi,
        title=title,
        abstract=abstract,
        authors=authors,
        url=f"https://doi.org/{doi}",
        source="Crossref",
        published=published,
        categories=tags[:5],
        citations=citations,
    )
