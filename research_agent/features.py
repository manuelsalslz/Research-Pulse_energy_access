"""Feature extraction from research paper abstracts.

Extracts key features like methodology, main outcome, and research
questions from paper abstracts. Uses LLM when available, falls back
to keyword-based extraction.

Inspired by FindResearch.online's approach to extracting structured
information from abstracts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from .chat import _generate, is_llm_available
from .models import Paper


@dataclass
class PaperFeatures:
    """Extracted features from a paper."""
    paper_id: str
    title: str
    methodology: str = ""
    main_outcome: str = ""
    research_questions: List[str] = field(default_factory=list)
    key_findings: List[str] = field(default_factory=list)
    limitations: str = ""
    contributions: List[str] = field(default_factory=list)


# ── Prompts for LLM extraction ──────────────────────────────────────────

FEATURE_EXTRACTION_PROMPT = """Analyze this research paper abstract and extract the following features:

Title: {title}
Abstract: {abstract}

Extract:
1. METHODOLOGY: What method, approach, or technique was used?
2. MAIN OUTCOME: What is the primary finding or contribution?
3. RESEARCH QUESTIONS: What questions does this paper address? (list 1-3)
4. KEY FINDINGS: What are the main results? (list 2-4)
5. LIMITATIONS: What limitations are mentioned or implied?
6. CONTRIBUTIONS: What are the paper's main contributions? (list 1-3)

Format your response as:
METHODOLOGY: <answer>
MAIN_OUTCOME: <answer>
QUESTIONS: <q1>; <q2>; <q3>
FINDINGS: <f1>; <f2>; <f3>
LIMITATIONS: <answer>
CONTRIBUTIONS: <c1>; <c2>; <c3>"""


# ── Keyword-based extraction (fallback) ─────────────────────────────────

_METHOD_KEYWORDS = [
    "propose", "introduce", "present", "develop", "use", "apply",
    "employ", "utilize", "leverage", "adopt", "implement", "design",
    "method", "approach", "technique", "framework", "algorithm",
    "model", "architecture", "system", "pipeline", "methodology",
]

_OUTCOME_KEYWORDS = [
    "achieve", "demonstrate", "show", "prove", "find", "discover",
    "observe", "report", "conclude", "result", "outperform",
    "improve", "reduce", "increase", "decrease", "enhance",
    "superior", "better", "effective", "efficient", "significant",
]

_QUESTION_PATTERNS = [
    r"(?:how|what|why|when|where|which)\s+.{10,80}\?",
    r"(?:investigate|explore|examine|study|address)\s+.{10,80}",
]

_LIMITATION_KEYWORDS = [
    "limitation", "limit", "constraint", "challenge", "drawback",
    "shortcoming", "weakness", "however", "although", "despite",
    "future work", "future research", "further investigation",
]


def _extract_by_keywords(text: str, keywords: List[str], max_sentences: int = 2) -> str:
    """Extract sentences containing specific keywords."""
    sentences = re.split(r'[.!?]+', text)
    relevant = []

    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 20:
            continue

        sentence_lower = sentence.lower()
        if any(kw in sentence_lower for kw in keywords):
            relevant.append(sentence)
            if len(relevant) >= max_sentences:
                break

    return ". ".join(relevant) + "." if relevant else ""


def _extract_questions(text: str) -> List[str]:
    """Extract research questions from text."""
    questions = []

    for pattern in _QUESTION_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches[:2]:
            cleaned = match.strip()
            if len(cleaned) > 15:
                questions.append(cleaned)

    return questions[:3]


def _extract_list_items(text: str, keywords: List[str], max_items: int = 3) -> List[str]:
    """Extract list-like items from text."""
    sentences = re.split(r'[.!?]+', text)
    items = []

    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 15:
            continue

        sentence_lower = sentence.lower()
        if any(kw in sentence_lower for kw in keywords):
            items.append(sentence)
            if len(items) >= max_items:
                break

    return items


def extract_features_keyword(paper: Paper) -> PaperFeatures:
    """Extract features using keyword-based approach (no LLM required).

    Args:
        paper: Paper to extract features from

    Returns:
        PaperFeatures with extracted information
    """
    text = f"{paper.title}. {paper.abstract}"

    features = PaperFeatures(
        paper_id=paper.id,
        title=paper.title,
    )

    # Extract methodology
    features.methodology = _extract_by_keywords(text, _METHOD_KEYWORDS)

    # Extract main outcome
    features.main_outcome = _extract_by_keywords(text, _OUTCOME_KEYWORDS)

    # Extract research questions
    features.research_questions = _extract_questions(text)

    # Extract key findings
    features.key_findings = _extract_list_items(text, _OUTCOME_KEYWORDS)

    # Extract limitations
    features.limitations = _extract_by_keywords(text, _LIMITATION_KEYWORDS)

    # Extract contributions
    features.contributions = _extract_list_items(text, [
        "contribution", "novel", "first", "new", "introduce", "propose"
    ])

    return features


def extract_features_llm(paper: Paper) -> Optional[PaperFeatures]:
    """Extract features using LLM.

    Args:
        paper: Paper to extract features from

    Returns:
        PaperFeatures or None if LLM not available
    """
    if not is_llm_available():
        return None

    prompt = FEATURE_EXTRACTION_PROMPT.format(
        title=paper.title,
        abstract=paper.abstract[:1500],  # Limit abstract length
    )

    response = _generate(prompt)
    if not response:
        return None

    features = PaperFeatures(
        paper_id=paper.id,
        title=paper.title,
    )

    # Parse LLM response
    lines = response.split("\n")
    for line in lines:
        line = line.strip()
        if line.startswith("METHODOLOGY:"):
            features.methodology = line[12:].strip()
        elif line.startswith("MAIN_OUTCOME:"):
            features.main_outcome = line[13:].strip()
        elif line.startswith("QUESTIONS:"):
            questions_str = line[10:].strip()
            features.research_questions = [q.strip() for q in questions_str.split(";") if q.strip()]
        elif line.startswith("FINDINGS:"):
            findings_str = line[9:].strip()
            features.key_findings = [f.strip() for f in findings_str.split(";") if f.strip()]
        elif line.startswith("LIMITATIONS:"):
            features.limitations = line[12:].strip()
        elif line.startswith("CONTRIBUTIONS:"):
            contrib_str = line[14:].strip()
            features.contributions = [c.strip() for c in contrib_str.split(";") if c.strip()]

    return features


def extract_features(paper: Paper, use_llm: bool = True) -> PaperFeatures:
    """Extract features from a paper.

    Tries LLM first, falls back to keyword extraction.

    Args:
        paper: Paper to extract features from
        use_llm: Whether to try LLM extraction

    Returns:
        PaperFeatures with extracted information
    """
    if use_llm:
        llm_features = extract_features_llm(paper)
        if llm_features:
            return llm_features

    return extract_features_keyword(paper)


def format_features(features: PaperFeatures) -> str:
    """Format extracted features for display."""
    lines = []
    lines.append(f"Paper: {features.title}")
    lines.append("-" * 50)

    if features.methodology:
        lines.append(f"Methodology: {features.methodology}")

    if features.main_outcome:
        lines.append(f"Main Outcome: {features.main_outcome}")

    if features.research_questions:
        lines.append("Research Questions:")
        for q in features.research_questions:
            lines.append(f"  - {q}")

    if features.key_findings:
        lines.append("Key Findings:")
        for f in features.key_findings:
            lines.append(f"  - {f}")

    if features.limitations:
        lines.append(f"Limitations: {features.limitations}")

    if features.contributions:
        lines.append("Contributions:")
        for c in features.contributions:
            lines.append(f"  - {c}")

    return "\n".join(lines)


def extract_batch_features(papers: List[Paper], use_llm: bool = True) -> List[PaperFeatures]:
    """Extract features from multiple papers.

    Args:
        papers: List of papers to process
        use_llm: Whether to use LLM (if available)

    Returns:
        List of PaperFeatures
    """
    features_list = []

    for paper in papers:
        features = extract_features(paper, use_llm=use_llm)
        features_list.append(features)

    return features_list
