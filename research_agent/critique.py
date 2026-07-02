"""Hypothesis challenger module.

Takes a user's research hypothesis or claim and finds evidence
both supporting and contradicting it from the literature.

Usage:
    from research_agent.critique import challenge_hypothesis
    critique = challenge_hypothesis("LoRA is always better than full fine-tuning", papers)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .chat import _generate, is_llm_available
from .models import Paper


@dataclass
class CritiqueResult:
    """Structured critique of a hypothesis."""
    hypothesis: str
    supporting_evidence: List[str] = field(default_factory=list)
    contradicting_evidence: List[str] = field(default_factory=list)
    nuances: List[str] = field(default_factory=list)
    confidence: str = "unknown"  # "strong", "moderate", "weak", "unknown"
    llm_analysis: Optional[str] = None


# ── Prompts ─────────────────────────────────────────────────────────────

CRITIQUE_PROMPT = """You are a critical research assistant. A researcher has proposed 
a hypothesis or claim. Your job is to:

1. Find evidence that SUPPORTS this claim
2. Find evidence that CONTRADICTS this claim
3. Identify NUANCES or conditions where the claim might be true or false
4. Assess the overall CONFIDENCE level (strong/moderate/weak)

HYPOTHESIS: {hypothesis}

RECENT RESEARCH CONTEXT:
{context}

Provide a balanced, critical analysis. Be specific about which papers support 
or contradict the claim. Identify any limitations or conditions."""

NUANCED_PROMPT = """You are a research assistant helping to refine a hypothesis.
A researcher has made a claim, and you need to help them think about it more precisely.

HYPOTHESIS: {hypothesis}

CONTEXT FROM RESEARCH:
{context}

Help refine this hypothesis by:
1. Identifying conditions where it might be true
2. Identifying conditions where it might be false
3. Suggesting a more precise formulation
4. Noting any important caveats or limitations"""


def _extract_claims(text: str) -> List[str]:
    """Extract potential claims or key statements from text."""
    # Look for sentences with strong claim indicators
    claim_indicators = [
        "is", "are", "was", "were", "will", "would", "should", "can", "could",
        "shows", "demonstrates", "proves", "suggests", "indicates", "finds",
        "concludes", "argues", "claims", "reports", "observes"
    ]

    sentences = text.split(".")
    claims = []
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) > 20:  # Skip very short sentences
            words = sentence.lower().split()
            if any(indicator in words for indicator in claim_indicators):
                claims.append(sentence)

    return claims[:5]  # Return top 5 claims


def _find_supporting_keywords(hypothesis: str, paper: Paper) -> List[str]:
    """Find keywords in paper that support the hypothesis."""
    hypothesis_words = set(hypothesis.lower().split())
    abstract_words = set(paper.abstract.lower().split())
    title_words = set(paper.title.lower().split())

    # Find overlapping significant words
    support_keywords = []
    significant_words = hypothesis_words - {"is", "are", "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by"}

    for word in significant_words:
        if word in abstract_words or word in title_words:
            support_keywords.append(word)

    return support_keywords


def _find_contradicting_keywords(hypothesis: str, paper: Paper) -> List[str]:
    """Find keywords in paper that might contradict the hypothesis."""
    # Look for negation or opposing terms
    contradiction_indicators = [
        "however", "but", "although", "despite", "in contrast", "on the other hand",
        "not", "no", "never", "fails", "contrary", "opposite", "unlike", "whereas",
        "while", "nevertheless", "nonetheless", "yet", "still"
    ]

    sentences = paper.abstract.split(".")
    contradictions = []

    for sentence in sentences:
        sentence_lower = sentence.lower()
        if any(indicator in sentence_lower for indicator in contradiction_indicators):
            # Check if the sentence relates to the hypothesis
            hypothesis_words = set(hypothesis.lower().split())
            sentence_words = set(sentence_lower.split())
            if len(hypothesis_words & sentence_words) > 1:
                contradictions.append(sentence.strip())

    return contradictions[:2]


def _analyze_hypothesis_keywords(hypothesis: str, papers: List[Paper]) -> CritiqueResult:
    """Analyze hypothesis using keyword matching (no LLM)."""
    result = CritiqueResult(hypothesis=hypothesis)

    for paper in papers:
        # Find supporting evidence
        support_kw = _find_supporting_keywords(hypothesis, paper)
        if support_kw:
            result.supporting_evidence.append(
                f"[{paper.source}] {paper.title[:60]}... - Keywords: {', '.join(support_kw[:3])}"
            )

        # Find contradicting evidence
        contradictions = _find_contradicting_keywords(hypothesis, paper)
        if contradictions:
            result.contradicting_evidence.append(
                f"[{paper.source}] {paper.title[:60]}... - {contradictions[0][:100]}..."
            )

    # Assess confidence based on evidence balance
    support_count = len(result.supporting_evidence)
    contradict_count = len(result.contradicting_evidence)

    if support_count > contradict_count * 2:
        result.confidence = "strong"
    elif support_count > contradict_count:
        result.confidence = "moderate"
    elif contradict_count > support_count:
        result.confidence = "weak"
    else:
        result.confidence = "uncertain"

    return result


def challenge_hypothesis_llm(hypothesis: str, papers: List[Paper]) -> Optional[str]:
    """Challenge hypothesis using LLM analysis.

    Args:
        hypothesis: The hypothesis to challenge
        papers: List of papers to use as evidence

    Returns:
        LLM-generated critique, or None if no LLM available
    """
    if not is_llm_available():
        return None

    # Build context from papers
    context_parts = []
    for i, p in enumerate(papers[:8], 1):
        authors = ", ".join(p.authors[:2])
        if len(p.authors) > 2:
            authors += " et al."
        context_parts.append(
            f"{i}. \"{p.title}\" by {authors} ({p.source})\n"
            f"   Abstract: {p.abstract[:400]}..."
        )

    context = "\n\n".join(context_parts) if context_parts else "No papers provided as context."

    prompt = CRITIQUE_PROMPT.format(
        hypothesis=hypothesis,
        context=context,
    )

    return _generate(prompt)


def refine_hypothesis(hypothesis: str, papers: List[Paper] = None) -> Optional[str]:
    """Help refine a hypothesis with nuances and conditions.

    Args:
        hypothesis: The hypothesis to refine
        papers: Optional list of papers for context

    Returns:
        Refined hypothesis suggestion, or None if no LLM available
    """
    if not is_llm_available():
        return None

    context = "No specific papers provided."
    if papers:
        context_parts = []
        for p in papers[:5]:
            context_parts.append(f"- \"{p.title}\": {p.abstract[:200]}...")
        context = "\n".join(context_parts)

    prompt = NUANCED_PROMPT.format(
        hypothesis=hypothesis,
        context=context,
    )

    return _generate(prompt)


def challenge_hypothesis(hypothesis: str, papers: List[Paper] = None,
                        use_llm: bool = True) -> str:
    """Challenge a hypothesis and return formatted critique.

    Args:
        hypothesis: The hypothesis to challenge
        papers: List of papers to use as evidence
        use_llm: Whether to use LLM for analysis (if available)

    Returns:
        Formatted critique string
    """
    if not hypothesis.strip():
        return "Please provide a hypothesis to challenge."

    if not papers:
        return "No papers provided as evidence. Search for relevant papers first."

    # Try LLM critique first
    if use_llm:
        llm_result = challenge_hypothesis_llm(hypothesis, papers)
        if llm_result:
            return llm_result

    # Fall back to keyword analysis
    result = _analyze_hypothesis_keywords(hypothesis, papers)

    output = []
    output.append("=" * 60)
    output.append("HYPOTHESIS CRITIQUE")
    output.append("=" * 60)
    output.append(f"\nHypothesis: {hypothesis}")

    # Supporting evidence
    if result.supporting_evidence:
        output.append(f"\nSUPPORTING EVIDENCE ({len(result.supporting_evidence)} papers):")
        for evidence in result.supporting_evidence[:5]:
            output.append(f"  + {evidence}")

    # Contradicting evidence
    if result.contradicting_evidence:
        output.append(f"\nCONTRADICTING EVIDENCE ({len(result.contradicting_evidence)} papers):")
        for evidence in result.contradicting_evidence[:5]:
            output.append(f"  - {evidence}")

    # Confidence assessment
    output.append(f"\nCONFIDENCE: {result.confidence.upper()}")
    output.append(f"  Supporting papers: {len(result.supporting_evidence)}")
    output.append(f"  Contradicting papers: {len(result.contradicting_evidence)}")

    # Nuances
    if result.nuances:
        output.append("\nNUANCES:")
        for nuance in result.nuances:
            output.append(f"  * {nuance}")

    output.append("\n" + "=" * 60)
    output.append("Note: For detailed LLM analysis, configure an API key")
    output.append("=" * 60)

    return "\n".join(output)
