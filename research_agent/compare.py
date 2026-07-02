"""Paper comparison module.

Compares two or more papers side-by-side, highlighting similarities,
differences, methodologies, and findings. Uses LLM when available,
falls back to structured comparison.

Usage:
    from research_agent.compare import compare_papers
    comparison = compare_papers([paper1, paper2])
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .chat import _generate, is_llm_available
from .models import Paper


@dataclass
class ComparisonResult:
    """Structured comparison between papers."""
    papers: List[Paper]
    similarities: List[str] = field(default_factory=list)
    differences: List[str] = field(default_factory=list)
    methodologies: List[str] = field(default_factory=list)
    findings: List[str] = field(default_factory=list)
    llm_analysis: Optional[str] = None


# ── Prompts ─────────────────────────────────────────────────────────────

COMPARISON_PROMPT = """You are a research assistant comparing multiple papers. 
Provide a structured comparison covering:

1. **Similarities**: What do these papers have in common?
2. **Differences**: How do they differ in approach, scope, or findings?
3. **Methodologies**: Compare their methods
4. **Key Findings**: What did each paper conclude?

Papers to compare:

{papers_text}

Provide a clear, organized comparison. Be specific about each paper."""


def _format_paper_brief(paper: Paper, index: int) -> str:
    """Format a paper for comparison context."""
    authors = ", ".join(paper.authors[:3])
    if len(paper.authors) > 3:
        authors += " et al."

    return f"""Paper {index}: "{paper.title}"
Authors: {authors}
Source: {paper.source}
Abstract: {paper.abstract[:500]}..."""


def _extract_keywords(text: str) -> set:
    """Extract significant keywords from text."""
    # Simple keyword extraction - remove common words
    stop_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "can", "this", "that", "these",
        "those", "it", "its", "we", "our", "they", "their", "i", "my", "me",
        "he", "she", "his", "her", "him", "they", "them", "their", "what",
        "which", "who", "whom", "when", "where", "why", "how", "all", "each",
        "every", "both", "few", "more", "most", "other", "some", "such", "no",
        "not", "only", "own", "same", "so", "than", "too", "very", "just",
        "about", "above", "after", "again", "against", "also", "am", "any",
        "because", "before", "below", "between", "both", "but", "by", "can",
        "did", "do", "does", "doing", "down", "during", "each", "few", "for",
        "from", "further", "get", "got", "had", "has", "have", "having", "he",
        "her", "here", "hers", "herself", "him", "himself", "his", "how", "i",
        "if", "in", "into", "is", "it", "its", "itself", "just", "me", "more",
        "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on",
        "once", "one", "only", "or", "other", "our", "ours", "ourselves", "out",
        "over", "own", "re", "same", "she", "so", "some", "such", "t", "than",
        "that", "the", "their", "theirs", "them", "themselves", "then", "there",
        "these", "they", "this", "those", "through", "to", "too", "under",
        "until", "up", "very", "was", "we", "were", "what", "when", "where",
        "which", "while", "who", "whom", "why", "will", "with", "you", "your",
        "yours", "yourself", "yourselves"
    }

    words = text.lower().split()
    keywords = set()
    for word in words:
        # Clean punctuation
        word = word.strip(".,;:!?()[]{}\"'")
        if len(word) > 3 and word not in stop_words:
            keywords.add(word)
    return keywords


def _find_similarities(papers: List[Paper]) -> List[str]:
    """Find similarities between papers based on keywords."""
    if len(papers) < 2:
        return []

    # Extract keywords from each paper
    paper_keywords = []
    for p in papers:
        text = f"{p.title} {p.abstract}"
        paper_keywords.append(_extract_keywords(text))

    # Find common keywords
    common = paper_keywords[0]
    for kw in paper_keywords[1:]:
        common = common.intersection(kw)

    # Convert to meaningful phrases
    similarities = []
    if common:
        # Group related keywords
        keyword_list = sorted(common)[:10]
        similarities.append(f"Common themes: {', '.join(keyword_list)}")

    # Check for same source
    sources = set(p.source for p in papers)
    if len(sources) == 1:
        similarities.append(f"All papers from {sources.pop()}")

    # Check for overlapping authors
    all_authors = set()
    for p in papers:
        for author in p.authors:
            all_authors.add(author.lower())

    # Find author overlaps
    for i, p1 in enumerate(papers):
        for j, p2 in enumerate(papers):
            if i < j:
                common_authors = set(a.lower() for a in p1.authors) & set(a.lower() for a in p2.authors)
                if common_authors:
                    similarities.append(f"Shared authors between papers {i+1} and {j+1}: {', '.join(common_authors)}")

    return similarities


def _find_differences(papers: List[Paper]) -> List[str]:
    """Find differences between papers."""
    differences = []

    # Compare sources
    sources = [p.source for p in papers]
    if len(set(sources)) > 1:
        differences.append(f"Different sources: {', '.join(set(sources))}")

    # Compare citation counts
    citations = [p.citations for p in papers if p.citations > 0]
    if citations:
        max_cite = max(citations)
        min_cite = min(citations)
        if max_cite > min_cite * 2:
            differences.append(f"Citation disparity: {max_cite} vs {min_cite}")

    # Compare publication dates
    dates = [p.published for p in papers if p.published]
    if dates:
        dates.sort()
        time_span = (dates[-1] - dates[0]).days
        if time_span > 365:
            differences.append(f"Time span: {time_span // 365} years between oldest and newest")

    return differences


def _extract_methodology(text: str) -> Optional[str]:
    """Try to extract methodology mentions from abstract."""
    method_keywords = [
        "propose", "introduce", "present", "develop", "use", "apply",
        "method", "approach", "technique", "framework", "algorithm",
        "model", "architecture", "system", "pipeline"
    ]

    sentences = text.split(".")
    for sentence in sentences:
        sentence_lower = sentence.lower()
        if any(kw in sentence_lower for kw in method_keywords):
            return sentence.strip()

    return None


def compare_papers_structured(papers: List[Paper]) -> ComparisonResult:
    """Compare papers using structured analysis (no LLM required).

    Args:
        papers: List of papers to compare (2 or more)

    Returns:
        ComparisonResult with similarities, differences, etc.
    """
    if len(papers) < 2:
        return ComparisonResult(
            papers=papers,
            similarities=["Need at least 2 papers to compare"],
        )

    result = ComparisonResult(papers=papers)
    result.similarities = _find_similarities(papers)
    result.differences = _find_differences(papers)

    # Extract methodologies
    for p in papers:
        method = _extract_methodology(p.abstract)
        if method:
            result.methodologies.append(f"{p.title[:50]}...: {method}")

    return result


def compare_papers_llm(papers: List[Paper]) -> Optional[str]:
    """Compare papers using LLM for detailed analysis.

    Args:
        papers: List of papers to compare

    Returns:
        LLM-generated comparison text, or None if no LLM available
    """
    if len(papers) < 2:
        return "Need at least 2 papers to compare."

    if not is_llm_available():
        return None

    # Format papers for the prompt
    papers_text = "\n\n".join(
        _format_paper_brief(p, i+1) for i, p in enumerate(papers)
    )

    prompt = COMPARISON_PROMPT.format(papers_text=papers_text)
    return _generate(prompt)


def compare_papers(papers: List[Paper], use_llm: bool = True) -> str:
    """Compare papers and return formatted comparison.

    Args:
        papers: List of papers to compare
        use_llm: Whether to use LLM for analysis (if available)

    Returns:
        Formatted comparison string
    """
    if len(papers) < 2:
        return "Need at least 2 papers to compare."

    # Try LLM comparison first
    if use_llm:
        llm_result = compare_papers_llm(papers)
        if llm_result:
            return llm_result

    # Fall back to structured comparison
    result = compare_papers_structured(papers)

    output = []
    output.append("=" * 60)
    output.append("PAPER COMPARISON")
    output.append("=" * 60)

    # List papers
    output.append("\nPapers being compared:")
    for i, p in enumerate(papers, 1):
        authors = ", ".join(p.authors[:2])
        if len(p.authors) > 2:
            authors += " et al."
        output.append(f"  {i}. [{p.source}] {p.title}")
        output.append(f"     Authors: {authors}")

    # Similarities
    if result.similarities:
        output.append("\nSIMILARITIES:")
        for s in result.similarities:
            output.append(f"  + {s}")

    # Differences
    if result.differences:
        output.append("\nDIFFERENCES:")
        for d in result.differences:
            output.append(f"  - {d}")

    # Methodologies
    if result.methodologies:
        output.append("\nMETHODOLOGIES:")
        for m in result.methodologies:
            output.append(f"  * {m}")

    output.append("\n" + "=" * 60)
    output.append("Note: For detailed LLM analysis, configure an API key (GROQ_API_KEY, GEMINI_API_KEY, or OLLAMA_HOST)")
    output.append("=" * 60)

    return "\n".join(output)
