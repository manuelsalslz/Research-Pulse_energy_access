"""Personalized paper recommendations based on user memory.

Analyzes user's reading history, ratings, interests, and open questions
to recommend papers they might find valuable.

Usage:
    from research_agent.recommend import get_recommendations
    recommendations = get_recommendations(papers, memory)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .config import load_topics, topics_by_id
from .memory import PaperMemory, ResearchMemory
from .models import Paper


@dataclass
class Recommendation:
    """A paper recommendation with explanation."""
    paper: Paper
    score: float
    reasons: List[str] = field(default_factory=list)
    category: str = ""  # "interest_match", "question_related", "citation_boost", "trending"


def _calculate_keyword_match(paper: Paper, keywords: List[str]) -> Tuple[float, List[str]]:
    """Calculate how well a paper matches user keywords.

    Returns:
        Tuple of (score, matching_keywords)
    """
    if not keywords:
        return 0.0, []

    paper_text = f"{paper.title} {paper.abstract}".lower()
    matching = []

    for keyword in keywords:
        if keyword.lower() in paper_text:
            matching.append(keyword)

    score = len(matching) / len(keywords) if keywords else 0.0
    return score, matching


def _calculate_topic_match(paper: Paper, topics: List[str]) -> Tuple[float, List[str]]:
    """Calculate how well a paper matches user topics.

    Returns:
        Tuple of (score, matching_topics)
    """
    if not topics:
        return 0.0, []

    # Load topic configurations
    topic_configs, _ = load_topics()
    topic_map = topics_by_id(topic_configs)

    matching = []
    total_score = 0.0

    for topic_id in topics:
        if topic_id in topic_map:
            topic = topic_map[topic_id]
            # Check if paper matches topic keywords
            paper_text = f"{paper.title} {paper.abstract}".lower()
            keyword_hits = 0

            for keyword in topic.keywords:
                if keyword.lower() in paper_text:
                    keyword_hits += 1

            if keyword_hits > 0:
                matching.append(topic.label)
                total_score += keyword_hits / len(topic.keywords)

    return min(total_score, 1.0), matching


def _calculate_question_relevance(paper: Paper, questions: List[str]) -> Tuple[float, List[str]]:
    """Calculate how relevant a paper is to user's open questions.

    Returns:
        Tuple of (score, relevant_questions)
    """
    if not questions:
        return 0.0, []

    paper_text = f"{paper.title} {paper.abstract}".lower()
    relevant = []

    for question in questions:
        # Extract key terms from question
        question_terms = question.lower().split()
        significant_terms = [t for t in question_terms if len(t) > 4]

        # Check if paper mentions these terms
        hits = sum(1 for term in significant_terms if term in paper_text)
        if hits >= 2:  # Must match at least 2 significant terms
            relevant.append(question[:50] + "..." if len(question) > 50 else question)

    score = len(relevant) / len(questions) if questions else 0.0
    return score, relevant


def _calculate_author_match(paper: Paper, followed_authors: List[str]) -> Tuple[float, List[str]]:
    """Calculate if paper is by an author the user follows.

    Returns:
        Tuple of (score, matching_authors)
    """
    if not followed_authors:
        return 0.0, []

    matching = []
    paper_authors_lower = [a.lower() for a in paper.authors]

    for author in followed_authors:
        if author.lower() in paper_authors_lower:
            matching.append(author)

    score = 1.0 if matching else 0.0
    return score, matching


def _calculate_citation_boost(paper: Paper) -> float:
    """Calculate citation-based boost (papers with some citations are often better)."""
    if paper.citations <= 0:
        return 0.0

    # Log-dampened citation boost
    import math
    return min(1.0, math.log10(paper.citations + 1) / 3.0)


def _calculate_recency_boost(paper: Paper) -> float:
    """Calculate recency boost (newer papers are often more relevant)."""
    if not paper.published:
        return 0.3  # Default moderate score

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    age_days = (now - paper.published).days

    # Exponential decay: 1.0 today, 0.5 after 14 days, 0.25 after 28 days
    return max(0.1, 1.0 * (0.5 ** (age_days / 14)))


def _is_already_seen(paper: Paper, memory: ResearchMemory) -> bool:
    """Check if user has already seen this paper."""
    return paper.id in memory.papers


def _calculate_rating_boost(paper: Paper, memory: ResearchMemory) -> float:
    """Boost papers similar to highly-rated ones."""
    if not memory.papers:
        return 0.0

    # Get user's highly rated papers
    highly_rated = [p for p in memory.papers.values() if p.rating >= 4]
    if not highly_rated:
        return 0.0

    # Check similarity with highly rated papers
    paper_text = f"{paper.title} {paper.abstract}".lower()
    similarity_scores = []

    for rated in highly_rated:
        # Simple keyword overlap
        rated_words = set(rated.title.lower().split())
        paper_words = set(paper_text.split())
        overlap = len(rated_words & paper_words)
        similarity_scores.append(overlap)

    if similarity_scores:
        return min(1.0, max(similarity_scores) / 10.0)

    return 0.0


def score_paper_for_user(paper: Paper, memory: ResearchMemory) -> Tuple[float, List[str], str]:
    """Score a paper for a specific user based on their memory.

    Returns:
        Tuple of (total_score, reasons, category)
    """
    reasons = []
    total_score = 0.0
    category = "general"

    # Get user preferences from memory
    keywords = memory.interests.get("keywords", []) + memory.interests.get("topics", [])
    topics = memory.interests.get("topics", [])
    questions = memory.interests.get("questions", [])
    followed_authors = memory.interests.get("authors", [])

    # Calculate various scores
    keyword_score, matching_keywords = _calculate_keyword_match(paper, keywords)
    topic_score, matching_topics = _calculate_topic_match(paper, topics)
    question_score, relevant_questions = _calculate_question_relevance(paper, questions)
    author_score, matching_authors = _calculate_author_match(paper, followed_authors)
    citation_boost = _calculate_citation_boost(paper)
    recency_boost = _calculate_recency_boost(paper)
    rating_boost = _calculate_rating_boost(paper, memory)

    # Weighted combination
    weights = {
        "keyword": 0.25,
        "topic": 0.20,
        "question": 0.25,
        "author": 0.15,
        "citation": 0.05,
        "recency": 0.05,
        "rating": 0.05,
    }

    total_score = (
        keyword_score * weights["keyword"] +
        topic_score * weights["topic"] +
        question_score * weights["question"] +
        author_score * weights["author"] +
        citation_boost * weights["citation"] +
        recency_boost * weights["recency"] +
        rating_boost * weights["rating"]
    )

    # Build reasons
    if matching_keywords:
        reasons.append(f"Matches keywords: {', '.join(matching_keywords[:3])}")
        category = "interest_match"

    if matching_topics:
        reasons.append(f"Matches topics: {', '.join(matching_topics[:2])}")
        category = "interest_match"

    if relevant_questions:
        reasons.append(f"Relevant to your question: {relevant_questions[0]}")
        category = "question_related"

    if matching_authors:
        reasons.append(f"By author you follow: {', '.join(matching_authors)}")
        category = "author_match"

    if citation_boost > 0.3:
        reasons.append(f"Well-cited paper ({paper.citations} citations)")

    if recency_boost > 0.7:
        reasons.append("Recent publication")

    if rating_boost > 0.3:
        reasons.append("Similar to papers you rated highly")

    return total_score, reasons, category


def get_recommendations(papers: List[Paper], memory: ResearchMemory,
                        limit: int = 10, min_score: float = 0.1) -> List[Recommendation]:
    """Get personalized paper recommendations.

    Args:
        papers: List of candidate papers
        memory: User's research memory
        limit: Maximum recommendations to return
        min_score: Minimum score threshold

    Returns:
        List of Recommendation objects sorted by score
    """
    recommendations = []

    for paper in papers:
        # Skip papers user has already seen
        if _is_already_seen(paper, memory):
            continue

        score, reasons, category = score_paper_for_user(paper, memory)

        if score >= min_score:
            recommendations.append(Recommendation(
                paper=paper,
                score=score,
                reasons=reasons,
                category=category,
            ))

    # Sort by score (descending)
    recommendations.sort(key=lambda r: r.score, reverse=True)

    return recommendations[:limit]


def format_recommendations(recommendations: List[Recommendation]) -> str:
    """Format recommendations for display."""
    if not recommendations:
        return "No personalized recommendations found. Try searching for papers first."

    output = []
    output.append("=" * 60)
    output.append("PERSONALIZED RECOMMENDATIONS")
    output.append("=" * 60)

    for i, rec in enumerate(recommendations, 1):
        paper = rec.paper
        output.append(f"\n{i}. [{paper.source}] {paper.title}")
        output.append(f"   Score: {rec.score:.2f} | Category: {rec.category}")

        if paper.authors:
            authors = ", ".join(paper.authors[:3])
            if len(paper.authors) > 3:
                authors += " et al."
            output.append(f"   Authors: {authors}")

        if rec.reasons:
            output.append(f"   Why recommended:")
            for reason in rec.reasons:
                output.append(f"     - {reason}")

        output.append(f"   URL: {paper.url}")

    output.append("\n" + "=" * 60)
    output.append(f"Showing {len(recommendations)} recommendations based on your research profile")
    output.append("=" * 60)

    return "\n".join(output)


def get_daily_briefing(papers: List[Paper], memory: ResearchMemory) -> str:
    """Generate a daily briefing with recommendations and insights.

    Args:
        papers: Today's papers
        memory: User's research memory

    Returns:
        Formatted daily briefing string
    """
    output = []
    output.append("=" * 60)
    output.append("DAILY RESEARCH BRIEFING")
    output.append("=" * 60)

    # Get recommendations
    recommendations = get_recommendations(papers, memory, limit=5)

    if recommendations:
        output.append("\nTOP PAPERS FOR YOU:")
        for i, rec in enumerate(recommendations, 1):
            paper = rec.paper
            output.append(f"\n{i}. {paper.title}")
            output.append(f"   {', '.join(rec.reasons[:2])}")
            output.append(f"   URL: {paper.url}")
    else:
        output.append("\nNo highly relevant papers found today.")

    # Check for papers matching open questions
    questions = memory.interests.get("questions", [])
    if questions:
        output.append("\nRELEVANT TO YOUR QUESTIONS:")
        for question in questions[:3]:
            matching_papers = []
            for paper in papers:
                if question.lower() in paper.abstract.lower():
                    matching_papers.append(paper)

            if matching_papers:
                output.append(f"\n  Q: {question}")
                for p in matching_papers[:2]:
                    output.append(f"    - {p.title}")

    # Suggest papers to rate
    unrated = memory.get_unrated_papers()
    if unrated:
        output.append(f"\nYou have {len(unrated)} papers to rate. Use 'rate <number> <1-5>' to help improve recommendations.")

    output.append("\n" + "=" * 60)
    return "\n".join(output)
