"""Conference / journal metadata and CORE ranking lookup.

CORE ranks (A*, A, B, C) are loaded from bundled YAML — free, offline, no API.
Venue names are matched from OpenAlex, Crossref, and arXiv journal-ref fields.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import yaml

from .config import BUNDLED_DIR, CONFIG_DIR
from .models import Paper

CORE_ORDER = {"A*": 4, "A": 3, "B": 2, "C": 1, "": 0, "Unranked": 0}


@lru_cache(maxsize=1)
def _load_catalog() -> Tuple[List[dict], Dict[str, dict]]:
    """Load venue catalog: list of entries + alias -> entry map."""
    for path in (CONFIG_DIR / "core_venues.yaml", BUNDLED_DIR / "config" / "core_venues.yaml"):
        if path.is_file():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            entries = data.get("venues", [])
            alias_map: Dict[str, dict] = {}
            for entry in entries:
                for alias in entry.get("names", []) + [entry.get("id", "")]:
                    if alias:
                        alias_map[_norm(alias)] = entry
            return entries, alias_map
    return [], {}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def lookup_core(venue: str) -> str:
    """Return CORE rank (A*, A, B, C) for a venue name, or empty string."""
    if not venue:
        return ""
    _, aliases = _load_catalog()
    key = _norm(venue)
    if key in aliases:
        return aliases[key].get("core", "")
    # Substring match: "NeurIPS 2024" -> neurips
    for alias_key, entry in aliases.items():
        if len(alias_key) >= 4 and (alias_key in key or key in alias_key):
            return entry.get("core", "")
    return ""


def resolve_venue_id(venue: str) -> Optional[str]:
    """Map a free-text venue to a catalog id (e.g. neurips)."""
    if not venue:
        return None
    _, aliases = _load_catalog()
    key = _norm(venue)
    if key in aliases:
        return aliases[key].get("id")
    for alias_key, entry in aliases.items():
        if len(alias_key) >= 3 and (alias_key in key or key in alias_key):
            return entry.get("id")
    return None


def list_venues(core_min: Optional[str] = None) -> List[dict]:
    """Return catalog entries, optionally filtered by minimum CORE rank."""
    entries, _ = _load_catalog()
    if not core_min:
        return entries
    rank = core_min.strip().upper()
    if rank in ("A_STAR", "ASTAR"):
        rank = "A*"
    min_score = CORE_ORDER.get(rank, 0)
    return [e for e in entries if CORE_ORDER.get(e.get("core", ""), 0) >= min_score]


def enrich_paper(paper: Paper) -> Paper:
    """Fill year and CORE rank from venue / published date."""
    if paper.year is None and paper.published:
        paper.year = paper.published.year
    if paper.venue and not paper.core_rank:
        paper.core_rank = lookup_core(paper.venue)
    return paper


def enrich_papers(papers: List[Paper]) -> List[Paper]:
    for p in papers:
        enrich_paper(p)
    return papers


def matches_venue(paper: Paper, venue_query: str) -> bool:
    """True if paper venue matches a catalog id or free-text name."""
    if not venue_query:
        return True
    q = _norm(venue_query)
    vid = resolve_venue_id(venue_query)
    if vid and paper.venue:
        entry_vid = resolve_venue_id(paper.venue)
        if entry_vid == vid:
            return True
    pv = _norm(paper.venue)
    return q in pv or pv in q or (len(q) >= 4 and q in _norm(paper.title))


def core_meets_min(paper: Paper, core_min: Optional[str]) -> bool:
    """True if paper CORE rank is at least core_min (e.g. A keeps A* and A)."""
    if not core_min:
        return True
    rank = core_min.upper()
    if rank in ("A*", "A_STAR"):
        rank = "A*"
    min_score = CORE_ORDER.get(rank, 0)
    if min_score == 0:
        return True
    paper_rank = paper.core_rank or lookup_core(paper.venue)
    return CORE_ORDER.get(paper_rank, 0) >= min_score


def filter_papers(
    papers: List[Paper],
    venues: Optional[List[str]] = None,
    core_min: Optional[str] = None,
    year: Optional[int] = None,
) -> List[Paper]:
    """Filter papers by conference, CORE rank, and/or year."""
    out: List[Paper] = []
    for p in papers:
        enrich_paper(p)
        if year is not None and p.year != year:
            continue
        if venues:
            if not any(matches_venue(p, v) for v in venues):
                continue
        if not core_meets_min(p, core_min):
            continue
        out.append(p)
    return out
