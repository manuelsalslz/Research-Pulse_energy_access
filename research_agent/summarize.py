"""Plain-language summarization with graceful degradation.

Design goal from the plan: the project must always work with zero API keys.
- Default: a cleaned, trimmed version of the paper's own abstract (no cost).
- Optional: if exactly one LLM backend is configured (Groq / Gemini / Ollama),
  generate a one to two sentence TL;DR instead.

The backend is chosen automatically based on which secret/host is present.
"""

from __future__ import annotations

from typing import List, Optional

import requests

from .config import Secrets
from .log import get as _log
from .models import Paper

log = _log("summarize")

PROMPT = (
    "Summarize this research paper for a busy researcher in 1-2 plain-language "
    "sentences. Avoid jargon and do not add a preamble.\n\n"
    "Title: {title}\n\nAbstract: {abstract}\n\nSummary:"
)


def _trim_abstract(text: str, max_chars: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return cut + "\u2026"


def _groq(title: str, abstract: str, secrets: Secrets) -> Optional[str]:
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {secrets.groq_api_key}"},
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [
                    {"role": "user", "content": PROMPT.format(title=title, abstract=abstract)}
                ],
                "temperature": 0.3,
                "max_tokens": 160,
            },
            timeout=40,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except (requests.RequestException, KeyError, IndexError) as exc:
        log.warning("groq failed, falling back to abstract: %s", exc)
        return None


def _gemini(title: str, abstract: str, secrets: Secrets) -> Optional[str]:
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
                    {"parts": [{"text": PROMPT.format(title=title, abstract=abstract)}]}
                ]
            },
            timeout=40,
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (requests.RequestException, KeyError, IndexError) as exc:
        log.warning("gemini failed, falling back to abstract: %s", exc)
        return None


def _ollama(title: str, abstract: str, secrets: Secrets) -> Optional[str]:
    try:
        resp = requests.post(
            f"{secrets.ollama_host}/api/generate",
            json={
                "model": secrets.ollama_model,
                "prompt": PROMPT.format(title=title, abstract=abstract),
                "stream": False,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except (requests.RequestException, KeyError) as exc:
        log.warning("ollama failed, falling back to abstract: %s", exc)
        return None


class Summarizer:
    """Picks a backend once and applies it to every paper."""

    def __init__(self, secrets: Secrets, abstract_max_chars: int = 360):
        self.secrets = secrets
        self.abstract_max_chars = abstract_max_chars
        if secrets.groq_api_key:
            self.backend = "groq"
        elif secrets.gemini_api_key:
            self.backend = "gemini"
        elif secrets.ollama_host:
            self.backend = "ollama"
        else:
            self.backend = "abstract"

    @property
    def uses_llm(self) -> bool:
        return self.backend != "abstract"

    def _llm_summary(self, title: str, abstract: str) -> Optional[str]:
        if self.backend == "groq":
            return _groq(title, abstract, self.secrets)
        if self.backend == "gemini":
            return _gemini(title, abstract, self.secrets)
        if self.backend == "ollama":
            return _ollama(title, abstract, self.secrets)
        return None

    def summarize(self, paper: Paper) -> str:
        fallback = _trim_abstract(paper.abstract, self.abstract_max_chars)
        if self.backend == "abstract" or not paper.abstract:
            return fallback
        result = self._llm_summary(paper.title, paper.abstract)
        return result or fallback

    def annotate(self, papers: List[Paper]) -> None:
        """Fill `paper.summary` in place for a list of papers."""
        for paper in papers:
            paper.summary = self.summarize(paper)
