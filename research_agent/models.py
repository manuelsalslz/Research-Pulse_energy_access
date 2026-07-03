"""Shared data structures used across fetchers, ranking, and rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Paper:
    """A single research item from any source.

    The same shape is produced by every fetcher (arXiv, bioRxiv, OpenAlex) so
    that ranking, summarizing, and rendering never need to know the origin.
    """

    id: str
    title: str
    abstract: str
    authors: List[str]
    url: str
    source: str
    published: Optional[datetime] = None
    categories: List[str] = field(default_factory=list)
    citations: int = 0
    venue: str = ""
    year: Optional[int] = None
    core_rank: str = ""
    # Filled in later by the summarizer. Falls back to a trimmed abstract.
    summary: str = ""
    # Relevance score assigned during ranking.
    score: float = 0.0

    def author_line(self, limit: int = 3) -> str:
        if not self.authors:
            return ""
        shown = self.authors[:limit]
        suffix = " et al." if len(self.authors) > limit else ""
        return ", ".join(shown) + suffix

    def venue_line(self) -> str:
        """Conference/journal, year, and CORE rank for display."""
        parts: List[str] = []
        if self.venue:
            parts.append(self.venue)
        if self.year and str(self.year) not in self.venue:
            parts.append(str(self.year))
        line = ", ".join(parts)
        if self.core_rank:
            line = f"{line} · CORE {self.core_rank}" if line else f"CORE {self.core_rank}"
        return line


@dataclass
class NewsItem:
    """A research-industry / community news entry pulled from an RSS feed."""

    title: str
    url: str
    source: str
    summary: str = ""
    published: Optional[datetime] = None
