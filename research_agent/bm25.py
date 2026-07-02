"""BM25 Ranking Algorithm.

BM25 (Best Matching 25) is a ranking function used by search engines
to estimate the relevance of documents to a given search query.

This implementation is based on the Okapi BM25 variant used in
FindResearch.online for relevance scoring.

Reference: https://en.wikipedia.org/wiki/Okapi_BM25
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

from .models import Paper


@dataclass
class CorpusStats:
    """Statistics about the document corpus for BM25 calculation."""
    doc_count: int
    avg_doc_length: float
    term_frequency: Dict[str, int]  # How many docs contain each term
    doc_lengths: List[int]


def _tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase words, removing punctuation."""
    # Convert to lowercase and split on non-alphanumeric
    words = re.findall(r'[a-z0-9]+', text.lower())
    # Remove very short words (1-2 chars) and common stop words
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
        'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'can', 'this', 'that', 'these',
        'those', 'it', 'its', 'we', 'our', 'they', 'their', 'i', 'my', 'me',
    }
    return [w for w in words if len(w) > 2 and w not in stop_words]


def _compute_corpus_stats(papers: List[Paper], query_terms: List[str]) -> CorpusStats:
    """Compute corpus statistics for BM25 calculation."""
    doc_count = len(papers)
    total_length = 0
    term_frequency: Dict[str, int] = {term: 0 for term in query_terms}
    doc_lengths = []

    for paper in papers:
        # Combine title and abstract for matching
        doc_text = f"{paper.title} {paper.abstract}"
        tokens = _tokenize(doc_text)
        doc_length = len(tokens)
        doc_lengths.append(doc_length)
        total_length += doc_length

        # Count documents containing each query term
        doc_set = set(tokens)
        for term in query_terms:
            if term in doc_set:
                term_frequency[term] += 1

    avg_doc_length = total_length / doc_count if doc_count > 0 else 0

    return CorpusStats(
        doc_count=doc_count,
        avg_doc_length=avg_doc_length,
        term_frequency=term_frequency,
        doc_lengths=doc_lengths,
    )


def _compute_tf(token: str, doc_tokens: List[str]) -> int:
    """Compute term frequency in a document."""
    return doc_tokens.count(token)


def _compute_idf(term: str, corpus_stats: CorpusStats) -> float:
    """Compute inverse document frequency for a term."""
    n_t = corpus_stats.term_frequency.get(term, 0)
    n = corpus_stats.doc_count

    # BM25 IDF formula (with smoothing to avoid negative values)
    return math.log((n - n_t + 0.5) / (n_t + 0.5) + 1)


def compute_bm25_score(
    paper: Paper,
    query_terms: List[str],
    corpus_stats: CorpusStats,
    k1: float = 1.2,
    b: float = 0.75,
) -> float:
    """Compute BM25 relevance score for a paper against query terms.

    Args:
        paper: The paper to score
        query_terms: Tokenized query terms
        corpus_stats: Corpus statistics
        k1: Term frequency saturation parameter (default 1.2)
        b: Length normalization parameter (default 0.75)

    Returns:
        BM25 relevance score
    """
    if not query_terms or corpus_stats.doc_count == 0:
        return 0.0

    # Tokenize document
    doc_text = f"{paper.title} {paper.abstract}"
    doc_tokens = _tokenize(doc_text)
    doc_length = len(doc_tokens)

    score = 0.0
    for term in query_terms:
        # Term frequency in this document
        tf = _compute_tf(term, doc_tokens)

        # Inverse document frequency
        idf = _compute_idf(term, corpus_stats)

        # BM25 formula
        numerator = tf * (k1 + 1)
        denominator = tf + k1 * (1 - b + b * (doc_length / corpus_stats.avg_doc_length))

        score += idf * (numerator / denominator)

    return score


def normalize_scores(scores: List[float]) -> List[float]:
    """Normalize scores to 0-1 range."""
    if not scores:
        return []

    min_score = min(scores)
    max_score = max(scores)

    if max_score == min_score:
        return [1.0] * len(scores)

    return [(s - min_score) / (max_score - min_score) for s in scores]


def rank_papers_bm25(
    papers: List[Paper],
    query: str,
    title_boost: float = 2.0,
) -> List[Tuple[Paper, float]]:
    """Rank papers using BM25 algorithm.

    Args:
        papers: List of papers to rank
        query: Search query
        title_boost: Multiplier for title matches (default 2.0)

    Returns:
        List of (paper, score) tuples sorted by score descending
    """
    if not papers or not query:
        return [(p, 0.0) for p in papers]

    # Tokenize query
    query_terms = _tokenize(query)
    if not query_terms:
        return [(p, 0.0) for p in papers]

    # Compute corpus statistics
    corpus_stats = _compute_corpus_stats(papers, query_terms)

    # Score each paper
    scores = []
    for i, paper in enumerate(papers):
        # Base BM25 score on abstract
        base_score = compute_bm25_score(paper, query_terms, corpus_stats)

        # Boost for title matches
        title_tokens = _tokenize(paper.title)
        title_matches = sum(1 for term in query_terms if term in title_tokens)
        title_score = title_matches * title_boost

        # Combined score
        total_score = base_score + title_score
        scores.append(total_score)

    # Normalize scores to 0-1
    normalized = normalize_scores(scores)

    # Create (paper, score) pairs
    results = [(paper, score) for paper, score in zip(papers, normalized)]

    # Sort by score descending
    results.sort(key=lambda x: x[1], reverse=True)

    return results


def rank_papers_combined(
    papers: List[Paper],
    query: str,
    bm25_weight: float = 0.4,
    citation_weight: float = 0.3,
    recency_weight: float = 0.2,
    exact_match_weight: float = 0.1,
) -> List[Tuple[Paper, float]]:
    """Rank papers using combined BM25 + citations + recency scoring.

    This is the ranking approach used in FindResearch.online.

    Args:
        papers: List of papers to rank
        query: Search query
        bm25_weight: Weight for BM25 relevance score
        citation_weight: Weight for citation count
        recency_weight: Weight for publication recency
        exact_match_weight: Weight for exact title match

    Returns:
        List of (paper, score) tuples sorted by score descending
    """
    if not papers:
        return []

    # Get BM25 scores
    bm25_results = rank_papers_bm25(papers, query)
    bm25_scores = {id(paper): score for paper, score in bm25_results}

    # Normalize citations (log scale)
    max_citations = max((p.citations for p in papers), default=1)
    citation_norm = math.log(max_citations + 1) if max_citations > 0 else 1

    # Compute combined scores
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    current_year = now.year

    results = []
    for paper in papers:
        # BM25 relevance
        bm25_score = bm25_scores.get(id(paper), 0.0)

        # Citation score (normalized log scale)
        citation_score = math.log(paper.citations + 1) / citation_norm if citation_norm > 0 else 0

        # Recency score (decay over 10 years)
        if paper.published:
            years_old = current_year - paper.published.year
            recency_score = max(0, 1 - years_old / 10)
        else:
            recency_score = 0.5  # Unknown date gets neutral score

        # Exact match bonus
        query_lower = query.lower()
        title_lower = paper.title.lower()
        exact_match = 1.0 if query_lower in title_lower else 0.0

        # Combined score
        combined_score = (
            bm25_score * bm25_weight +
            citation_score * citation_weight +
            recency_score * recency_weight +
            exact_match * exact_match_weight
        )

        results.append((paper, combined_score))

    # Sort by combined score descending
    results.sort(key=lambda x: x[1], reverse=True)

    return results
