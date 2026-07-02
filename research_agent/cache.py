"""Dedup cache backed by data/seen.json.

Tracks paper IDs we have already sent so the same paper never shows up twice
across days. The GitHub Actions workflow commits the updated file back to the
repo after each run, giving us free persistent state with no database.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Set

from .config import ROOT

DEFAULT_PATH = ROOT / "data" / "seen.json"
# Keep the cache from growing forever; arXiv IDs are stable so this is plenty.
MAX_IDS = 50000


def _normalize(paper_id: str) -> str:
    """Stable short hash so the file stays compact and source-agnostic."""
    return hashlib.sha1(paper_id.strip().lower().encode("utf-8")).hexdigest()[:16]


class SeenCache:
    def __init__(self, path: Path = DEFAULT_PATH):
        self.path = path
        self._ids: List[str] = []
        self._set: Set[str] = set()
        self.last_run = None
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        self._ids = list(data.get("seen_ids", []))
        self._set = set(self._ids)
        self.last_run = data.get("last_run")

    def is_seen(self, paper_id: str) -> bool:
        return _normalize(paper_id) in self._set

    def mark(self, paper_ids: Iterable[str]) -> None:
        for pid in paper_ids:
            h = _normalize(pid)
            if h not in self._set:
                self._set.add(h)
                self._ids.append(h)

    def save(self) -> None:
        # Trim to the most recent MAX_IDS to bound file size.
        if len(self._ids) > MAX_IDS:
            self._ids = self._ids[-MAX_IDS:]
            self._set = set(self._ids)
        payload = {
            "seen_ids": self._ids,
            "last_run": datetime.now(timezone.utc).isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
