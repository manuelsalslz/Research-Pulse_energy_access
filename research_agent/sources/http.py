"""Small shared HTTP helper with a friendly User-Agent and retries."""

from __future__ import annotations

import time
from typing import Optional

import logging

import requests

log = logging.getLogger("research_agent.http")

USER_AGENT = (
    "ResearchPulse/0.3 (+https://github.com/research-pulse; open-source research digest)"
)

DEFAULT_TIMEOUT = 30


def get(url: str, params: Optional[dict] = None, retries: int = 3,
        backoff: float = 2.0, timeout: int = DEFAULT_TIMEOUT,
        headers: Optional[dict] = None) -> Optional[requests.Response]:
    """GET with simple retry/backoff. Returns None on persistent failure."""
    merged = {"User-Agent": USER_AGENT}
    if headers:
        merged.update(headers)
    headers = merged
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code == 429:
                time.sleep(backoff * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:  # noqa: PERF203
            if attempt == retries - 1:
                log.warning("giving up on %s: %s", url, exc)
                return None
            time.sleep(backoff * (attempt + 1))
    return None
