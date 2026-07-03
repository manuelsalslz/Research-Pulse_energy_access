"""Relevance ranking and per-topic selection.

No LLM required: papers are scored with a transparent heuristic combining
keyword relevance, recency, and (when available) early citation counts. This
keeps the default pipeline zero-cost while still surfacing the best items.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import List

from .config import Topic
from .models import Paper
from .venues import CORE_ORDER, enrich_paper, lookup_core


def _keyword_score(paper: Paper, keywords: List[str]) -> float:
    if not keywords:
        return 0.0
    haystack = f"{paper.title} {paper.abstract}".lower()
    hits = 0
    for kw in keywords:
        kw_l = kw.lower()
        # Title matches count double; they are stronger relevance signals.
        if kw_l in paper.title.lower():
            hits += 2
        elif kw_l in haystack:
            hits += 1
    return hits / (len(keywords) * 2)


def _recency_score(paper: Paper) -> float:
    if not paper.published:
        return 0.3
    age_days = (datetime.now(timezone.utc) - paper.published).total_seconds() / 86400
    # 1.0 today, decaying gently over a week.
    return max(0.0, 1.0 - (age_days / 7.0))


def _citation_score(paper: Paper) -> float:
    if paper.citations <= 0:
        return 0.0
    # Log-dampened so a few early citations help without dominating.
    return min(1.0, math.log10(paper.citations + 1) / 2.0)


def _core_score(paper: Paper) -> float:
    rank = paper.core_rank or lookup_core(paper.venue)
    return CORE_ORDER.get(rank, 0) / 4.0


def score_paper(paper: Paper, topic: Topic) -> float:
    enrich_paper(paper)
    return (
        0.50 * _keyword_score(paper, topic.keywords)
        + 0.25 * _recency_score(paper)
        + 0.15 * _citation_score(paper)
        + 0.10 * _core_score(paper)
    )


# Sources that are already topically filtered upstream (by category / server)
# and may therefore be kept even with a weak textual keyword match.
_CURATED_SOURCES = {"arxiv", "biorxiv", "medrxiv"}


def _relevant(paper: Paper, topic: Topic) -> bool:
    """Drop obviously off-topic items from broad full-text sources (OpenAlex).

    arXiv/bioRxiv are pre-filtered by category, so they pass through; broad
    sources must contain at least one topic keyword to count.
    """
    if not topic.keywords:
        return True
    if paper.source.lower() in _CURATED_SOURCES:
        return True
    return _keyword_score(paper, topic.keywords) > 0


def rank_for_topic(papers: List[Paper], topic: Topic, limit: int) -> List[Paper]:
    """Filter for relevance, score, sort, and trim papers for a single topic."""
    candidates = [p for p in papers if _relevant(p, topic)]
    for p in candidates:
        p.score = score_paper(p, topic)
    ranked = sorted(candidates, key=lambda p: p.score, reverse=True)
    return ranked[:limit]
