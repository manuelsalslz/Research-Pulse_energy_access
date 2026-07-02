"""Insights module for contradiction and gap detection.

Analyzes papers to find contradictions between studies, research gaps,
and emerging trends. Uses keyword analysis and optional LLM for deeper insights.

Usage:
    from research_agent.insights import find_contradictions, find_gaps, analyze_trends
    contradictions = find_contradictions(papers)
    gaps = find_gaps(papers, memory)
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from .chat import _generate, is_llm_available
from .memory import ResearchMemory
from .models import Paper


@dataclass
class Contradiction:
    """A contradiction between two papers."""
    paper1_title: str
    paper2_title: str
    topic: str
    evidence: str
    confidence: float  # 0.0 to 1.0


@dataclass
class ResearchGap:
    """An identified gap in the research."""
    topic: str
    description: str
    related_papers: List[str] = field(default_factory=list)
    opportunity: str = ""


@dataclass
class Trend:
    """An emerging research trend."""
    topic: str
    velocity: float  # How fast it's growing
    papers: List[str] = field(default_factory=list)
    prediction: str = ""


# ── Prompts ─────────────────────────────────────────────────────────────

CONTRADICTION_PROMPT = """You are a research analyst identifying contradictions in the literature.

Papers to analyze:
{papers_text}

Identify any contradictions or conflicting findings between these papers. 
For each contradiction:
1. Which papers contradict each other?
2. What specific claims conflict?
3. What might explain the contradiction (different methods, data, scope)?

Format your response as a structured list of contradictions."""

GAP_PROMPT = """You are a research analyst identifying gaps in the literature.

Research context:
{context}

User's research interests:
{interests}

Identify potential research gaps:
1. What topics are understudied?
2. What questions remain unanswered?
3. What combinations of approaches haven't been tried?
4. What populations or contexts are missing?

Be specific and actionable."""

TREND_PROMPT = """You are a research analyst identifying emerging trends.

Recent papers (last {days} days):
{papers_text}

Identify:
1. What topics are gaining momentum?
2. What new methods or approaches are emerging?
3. What old topics are declining?
4. What cross-disciplinary connections are forming?

Focus on actionable insights for a researcher."""


# ── Contradiction Detection ─────────────────────────────────────────────

def _extract_claims_from_abstract(abstract: str) -> List[str]:
    """Extract key claims from an abstract."""
    sentences = abstract.split(".")
    claims = []

    claim_indicators = [
        "shows", "demonstrates", "proves", "suggests", "indicates", "finds",
        "concludes", "argues", "reports", "observes", "achieves", "outperforms",
        "improves", "reduces", "increases", "decreases", "fails", "succeeds"
    ]

    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) > 30:
            words = sentence.lower().split()
            if any(indicator in words for indicator in claim_indicators):
                claims.append(sentence)

    return claims[:3]


def _find_contradiction_keywords(paper1: Paper, paper2: Paper) -> List[Tuple[str, str]]:
    """Find potential contradictions between two papers using keywords."""
    contradictions = []

    # Extract claims from both papers
    claims1 = _extract_claims_from_abstract(paper1.abstract)
    claims2 = _extract_claims_from_abstract(paper2.abstract)

    # Look for opposing terms
    opposing_pairs = [
        ("increase", "decrease"), ("improve", "worsen"), ("better", "worse"),
        ("superior", "inferior"), ("effective", "ineffective"), ("successful", "failed"),
        ("positive", "negative"), ("significant", "insignificant"),
        ("outperforms", "underperforms"), ("faster", "slower"),
    ]

    for claim1 in claims1:
        for claim2 in claims2:
            claim1_lower = claim1.lower()
            claim2_lower = claim2.lower()

            # Check if claims share context but have opposing terms
            words1 = set(claim1_lower.split())
            words2 = set(claim2_lower.split())

            # Must share at least 2 significant words
            shared = words1 & words2
            significant_shared = [w for w in shared if len(w) > 4]

            if len(significant_shared) >= 2:
                # Check for opposing terms
                for term1, term2 in opposing_pairs:
                    if (term1 in claim1_lower and term2 in claim2_lower) or \
                       (term2 in claim1_lower and term1 in claim2_lower):
                        contradictions.append((claim1, claim2))
                        break

    return contradictions


def find_contradictions(papers: List[Paper], use_llm: bool = False) -> List[Contradiction]:
    """Find contradictions between papers.

    Args:
        papers: List of papers to analyze
        use_llm: Whether to use LLM for deeper analysis

    Returns:
        List of Contradiction objects
    """
    contradictions = []

    # Compare each pair of papers
    for i, paper1 in enumerate(papers):
        for j, paper2 in enumerate(papers):
            if i >= j:
                continue

            # Find keyword-based contradictions
            keyword_contradictions = _find_contradiction_keywords(paper1, paper2)

            for claim1, claim2 in keyword_contradictions:
                # Determine the topic (shared significant words)
                words1 = set(claim1.lower().split())
                words2 = set(claim2.lower().split())
                shared = words1 & words2
                topic_words = [w for w in shared if len(w) > 4]
                topic = ", ".join(topic_words[:3]) if topic_words else "general"

                contradictions.append(Contradiction(
                    paper1_title=paper1.title,
                    paper2_title=paper2.title,
                    topic=topic,
                    evidence=f"Paper 1: {claim1[:100]}...\nPaper 2: {claim2[:100]}...",
                    confidence=0.6,  # Moderate confidence for keyword-based
                ))

    # If LLM is available and requested, do deeper analysis
    if use_llm and is_llm_available() and len(papers) >= 2:
        papers_text = "\n\n".join(
            f"Paper {i+1}: \"{p.title}\"\nAbstract: {p.abstract[:400]}..."
            for i, p in enumerate(papers[:5])
        )

        prompt = CONTRADICTION_PROMPT.format(papers_text=papers_text)
        llm_result = _generate(prompt)

        if llm_result:
            # Add LLM-identified contradictions with higher confidence
            contradictions.append(Contradiction(
                paper1_title="Multiple papers",
                paper2_title="Multiple papers",
                topic="LLM-identified",
                evidence=llm_result[:500],
                confidence=0.8,
            ))

    return contradictions


# ── Gap Detection ───────────────────────────────────────────────────────

def _identify_keyword_gaps(papers: List[Paper], interests: List[str]) -> List[ResearchGap]:
    """Identify research gaps based on keyword analysis."""
    gaps = []

    # Collect all keywords from papers
    paper_keywords: Set[str] = set()
    for paper in papers:
        words = paper.abstract.lower().split()
        for word in words:
            word = word.strip(".,;:!?()[]{}\"'")
            if len(word) > 4:
                paper_keywords.add(word)

    # Check if user's interests are well-covered
    for interest in interests:
        interest_lower = interest.lower()
        interest_words = set(interest_lower.split())

        # Check how many papers mention this interest
        mention_count = 0
        related_papers = []
        for paper in papers:
            if interest_lower in paper.abstract.lower() or interest_lower in paper.title.lower():
                mention_count += 1
                related_papers.append(paper.title)

        # If few papers cover this interest, it might be a gap
        if mention_count <= 2:
            gaps.append(ResearchGap(
                topic=interest,
                description=f"Only {mention_count} papers directly address '{interest}'",
                related_papers=related_papers[:3],
                opportunity=f"Consider exploring {interest} in more depth",
            ))

    # Look for combinations that haven't been explored
    if len(interests) >= 2:
        for i, interest1 in enumerate(interests):
            for j, interest2 in enumerate(interests):
                if i >= j:
                    continue

                # Check if any paper combines both interests
                combined_count = 0
                for paper in papers:
                    abstract_lower = paper.abstract.lower()
                    if interest1.lower() in abstract_lower and interest2.lower() in abstract_lower:
                        combined_count += 1

                if combined_count == 0:
                    gaps.append(ResearchGap(
                        topic=f"{interest1} + {interest2}",
                        description=f"No papers combine '{interest1}' with '{interest2}'",
                        opportunity=f"Cross-disciplinary research opportunity",
                    ))

    return gaps


def find_gaps(papers: List[Paper], memory: ResearchMemory = None,
              use_llm: bool = False) -> List[ResearchGap]:
    """Find research gaps based on papers and user interests.

    Args:
        papers: List of papers to analyze
        memory: User's research memory (for interests)
        use_llm: Whether to use LLM for deeper analysis

    Returns:
        List of ResearchGap objects
    """
    # Get user interests from memory
    interests = []
    if memory:
        interests = memory.interests.get("topics", []) + memory.interests.get("keywords", [])
        interests.extend(memory.interests.get("questions", []))

    if not interests:
        # Default interests if none set
        interests = ["machine learning", "deep learning", "neural networks"]

    gaps = _identify_keyword_gaps(papers, interests)

    # If LLM is available, do deeper gap analysis
    if use_llm and is_llm_available():
        context_parts = []
        for p in papers[:10]:
            context_parts.append(f"- \"{p.title}\": {p.abstract[:200]}...")
        context = "\n".join(context_parts)

        interests_text = "\n".join(f"- {i}" for i in interests[:10])

        prompt = GAP_PROMPT.format(
            context=context,
            interests=interests_text,
        )

        llm_result = _generate(prompt)
        if llm_result:
            gaps.append(ResearchGap(
                topic="LLM-identified gaps",
                description=llm_result[:500],
                opportunity="See LLM analysis for details",
            ))

    return gaps


# ── Trend Detection ─────────────────────────────────────────────────────

def _analyze_keyword_trends(papers: List[Paper]) -> List[Trend]:
    """Analyze trends based on keyword frequency."""
    trends = []

    # Group papers by time periods
    now = datetime.now(timezone.utc)
    recent_papers = []
    older_papers = []

    for paper in papers:
        if paper.published:
            age_days = (now - paper.published).days
            if age_days <= 7:
                recent_papers.append(paper)
            elif age_days <= 30:
                older_papers.append(paper)

    # Count keywords in recent vs older papers
    def count_keywords(paper_list: List[Paper]) -> Counter:
        counter = Counter()
        for paper in paper_list:
            words = paper.abstract.lower().split()
            for word in words:
                word = word.strip(".,;:!?()[]{}\"'")
                if len(word) > 5:  # Only significant words
                    counter[word] += 1
        return counter

    recent_keywords = count_keywords(recent_papers)
    older_keywords = count_keywords(older_papers)

    # Find keywords that are trending up
    trending_up = []
    for keyword, recent_count in recent_keywords.items():
        if recent_count >= 2:  # Must appear at least twice recently
            older_count = older_keywords.get(keyword, 0)
            if older_count == 0 or recent_count > older_count * 1.5:
                trending_up.append((keyword, recent_count))

    # Create Trend objects for top trending keywords
    trending_up.sort(key=lambda x: x[1], reverse=True)
    for keyword, count in trending_up[:5]:
        # Find papers mentioning this keyword
        related_papers = []
        for paper in recent_papers:
            if keyword in paper.abstract.lower():
                related_papers.append(paper.title)

        velocity = count / max(len(recent_papers), 1)  # Papers per day

        trends.append(Trend(
            topic=keyword,
            velocity=velocity,
            papers=related_papers[:3],
            prediction=f"{count} papers in the last 7 days mention '{keyword}'",
        ))

    return trends


def analyze_trends(papers: List[Paper], days: int = 7,
                   use_llm: bool = False) -> List[Trend]:
    """Analyze emerging trends in recent papers.

    Args:
        papers: List of papers to analyze
        days: Time window for trend analysis
        use_llm: Whether to use LLM for deeper analysis

    Returns:
        List of Trend objects
    """
    trends = _analyze_keyword_trends(papers)

    # If LLM is available, do deeper trend analysis
    if use_llm and is_llm_available():
        papers_text = "\n\n".join(
            f"- \"{p.title}\" ({p.source}): {p.abstract[:200]}..."
            for p in papers[:15]
        )

        prompt = TREND_PROMPT.format(
            days=days,
            papers_text=papers_text,
        )

        llm_result = _generate(prompt)
        if llm_result:
            trends.append(Trend(
                topic="LLM-identified trends",
                velocity=1.0,
                papers=[],
                prediction=llm_result[:500],
            ))

    return trends


# ── Unified Insights ────────────────────────────────────────────────────

def generate_insights(papers: List[Paper], memory: ResearchMemory = None,
                      use_llm: bool = False) -> Dict[str, Any]:
    """Generate all insights from papers.

    Args:
        papers: List of papers to analyze
        memory: User's research memory
        use_llm: Whether to use LLM for analysis

    Returns:
        Dictionary with contradictions, gaps, and trends
    """
    contradictions = find_contradictions(papers, use_llm=use_llm)
    gaps = find_gaps(papers, memory, use_llm=use_llm)
    trends = analyze_trends(papers, use_llm=use_llm)

    return {
        "contradictions": contradictions,
        "gaps": gaps,
        "trends": trends,
    }


def format_insights(insights: Dict[str, Any]) -> str:
    """Format insights for display."""
    output = []
    output.append("=" * 60)
    output.append("RESEARCH INSIGHTS")
    output.append("=" * 60)

    # Contradictions
    contradictions = insights.get("contradictions", [])
    if contradictions:
        output.append(f"\nCONTRADICTIONS ({len(contradictions)} found):")
        for c in contradictions[:3]:
            output.append(f"  * {c.topic}")
            output.append(f"    {c.paper1_title[:50]}... vs {c.paper2_title[:50]}...")
    else:
        output.append("\nNo contradictions detected.")

    # Gaps
    gaps = insights.get("gaps", [])
    if gaps:
        output.append(f"\nRESEARCH GAPS ({len(gaps)} found):")
        for g in gaps[:3]:
            output.append(f"  * {g.topic}: {g.description[:100]}...")
    else:
        output.append("\nNo significant gaps detected.")

    # Trends
    trends = insights.get("trends", [])
    if trends:
        output.append(f"\nEMERGING TRENDS ({len(trends)} found):")
        for t in trends[:3]:
            output.append(f"  * {t.topic}: {t.prediction[:100]}...")
    else:
        output.append("\nNo strong trends detected.")

    output.append("\n" + "=" * 60)
    return "\n".join(output)
