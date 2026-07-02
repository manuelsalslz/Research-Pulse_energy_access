"""LLM-powered Q&A about research papers.

Uses the existing summarizer backends (Groq/Gemini/Ollama) to answer
questions about papers. The LLM receives the paper's title, abstract,
and the user's question, then generates a helpful response.

Usage:
    from research_agent.chat import ask_about_paper, ask_research_question
    answer = ask_about_paper(paper, "What methodology did they use?")
"""

from __future__ import annotations

from typing import List, Optional

import requests

from .config import Secrets, load_secrets, load_settings
from .models import Paper


# ── Prompts ─────────────────────────────────────────────────────────────

PAPER_QA_PROMPT = """You are a research assistant helping a researcher understand a paper.

Paper Title: {title}
Authors: {authors}
Source: {source}
Abstract: {abstract}

User Question: {question}

Provide a clear, concise answer based on the paper's abstract. If the abstract
doesn't contain enough information to answer fully, say so. Be specific and
cite relevant details from the abstract."""

RESEARCH_QA_PROMPT = """You are a research assistant helping a researcher with their question.

Research Context:
{context}

User Question: {question}

Provide a helpful, accurate response. If you're unsure about something, say so.
Reference specific papers or findings when relevant."""

CONCEPT_EXPLAIN_PROMPT = """You are a research assistant explaining a concept to a researcher.

Concept: {concept}
Context from recent research:
{context}

Explain this concept clearly and concisely. If there are recent developments
mentioned in the context, highlight them. Keep the explanation accessible but
precise."""


# ── LLM Backends ────────────────────────────────────────────────────────

def _call_groq(prompt: str, secrets: Secrets) -> Optional[str]:
    """Call Groq API for text generation."""
    if not secrets.groq_api_key:
        return None

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {secrets.groq_api_key}"},
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 500,
            },
            timeout=40,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except (requests.RequestException, KeyError, IndexError) as exc:
        print(f"[chat] Groq API error: {exc}")
        return None


def _call_gemini(prompt: str, secrets: Secrets) -> Optional[str]:
    """Call Gemini API for text generation."""
    if not secrets.gemini_api_key:
        return None

    try:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-1.5-flash:generateContent"
        )
        resp = requests.post(
            url,
            params={"key": secrets.gemini_api_key},
            json={
                "contents": [
                    {"parts": [{"text": prompt}]}
                ]
            },
            timeout=40,
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (requests.RequestException, KeyError, IndexError) as exc:
        print(f"[chat] Gemini API error: {exc}")
        return None


def _call_ollama(prompt: str, secrets: Secrets) -> Optional[str]:
    """Call local Ollama model for text generation."""
    if not secrets.ollama_host:
        return None

    try:
        resp = requests.post(
            f"{secrets.ollama_host}/api/generate",
            json={
                "model": secrets.ollama_model,
                "prompt": prompt,
                "stream": False,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except (requests.RequestException, KeyError) as exc:
        print(f"[chat] Ollama error: {exc}")
        return None


def _generate(prompt: str) -> Optional[str]:
    """Generate text using the available LLM backend."""
    secrets = load_secrets()

    # Try each backend in order
    result = _call_groq(prompt, secrets)
    if result:
        return result

    result = _call_gemini(prompt, secrets)
    if result:
        return result

    result = _call_ollama(prompt, secrets)
    if result:
        return result

    return None


# ── Public API ──────────────────────────────────────────────────────────

def ask_about_paper(paper: Paper, question: str) -> Optional[str]:
    """Ask a question about a specific paper.

    Args:
        paper: The paper to ask about
        question: The user's question

    Returns:
        The LLM's answer, or None if no LLM backend is available
    """
    if not question.strip():
        return None

    authors = ", ".join(paper.authors[:5])
    if len(paper.authors) > 5:
        authors += " et al."

    prompt = PAPER_QA_PROMPT.format(
        title=paper.title,
        authors=authors,
        source=paper.source,
        abstract=paper.abstract or "No abstract available",
        question=question,
    )

    return _generate(prompt)


def ask_research_question(question: str, papers: List[Paper] = None) -> Optional[str]:
    """Ask a general research question, optionally with paper context.

    Args:
        question: The user's research question
        papers: Optional list of papers to use as context

    Returns:
        The LLM's answer, or None if no LLM backend is available
    """
    if not question.strip():
        return None

    # Build context from papers
    context_parts = []
    if papers:
        for i, p in enumerate(papers[:5], 1):
            authors = ", ".join(p.authors[:3])
            if len(p.authors) > 3:
                authors += " et al."
            context_parts.append(
                f"{i}. \"{p.title}\" by {authors} ({p.source})\n"
                f"   Abstract: {p.abstract[:300]}..."
            )

    context = "\n\n".join(context_parts) if context_parts else "No specific papers provided as context."

    prompt = RESEARCH_QA_PROMPT.format(
        context=context,
        question=question,
    )

    return _generate(prompt)


def explain_concept(concept: str, papers: List[Paper] = None) -> Optional[str]:
    """Explain a research concept, optionally using papers as context.

    Args:
        concept: The concept to explain
        papers: Optional list of papers that mention the concept

    Returns:
        The LLM's explanation, or None if no LLM backend is available
    """
    if not concept.strip():
        return None

    # Build context from papers
    context_parts = []
    if papers:
        for p in papers[:3]:
            # Find sentences mentioning the concept
            sentences = p.abstract.split(".")
            relevant = [s.strip() for s in sentences if concept.lower() in s.lower()]
            if relevant:
                context_parts.append(f"- \"{p.title}\": {'. '.join(relevant[:2])}.")

    context = "\n".join(context_parts) if context_parts else "No specific context available."

    prompt = CONCEPT_EXPLAIN_PROMPT.format(
        concept=concept,
        context=context,
    )

    return _generate(prompt)


def is_llm_available() -> bool:
    """Check if any LLM backend is configured."""
    secrets = load_secrets()
    return bool(secrets.groq_api_key or secrets.gemini_api_key or secrets.ollama_host)


def get_llm_backend() -> str:
    """Get the name of the available LLM backend."""
    secrets = load_secrets()
    if secrets.groq_api_key:
        return "groq"
    elif secrets.gemini_api_key:
        return "gemini"
    elif secrets.ollama_host:
        return "ollama"
    return "none"
