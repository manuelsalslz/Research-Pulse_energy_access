"""Zotero integration: detect local Zotero library and infer research domains.

Zotero stores its library in a SQLite database (zotero.sqlite). This module
finds that database on the user's machine, reads the user's collections and
item tags, and maps them to ResearchPulse topic IDs.

This is entirely local and read-only -- it never modifies the Zotero DB.

Usage:
    python -m research_agent zotero
    # or programmatically:
    from research_agent.zotero import detect_topics
    topics = detect_topics()  # -> ['ai-ml', 'nlp', ...]

Supported platforms: Windows, macOS, Linux.
"""

from __future__ import annotations

import os
import platform
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import load_topics


# ── Locate the Zotero database ──────────────────────────────────────────

def _default_zotero_paths() -> List[Path]:
    """Return candidate paths for zotero.sqlite, platform-aware."""
    home = Path.home()
    system = platform.system()
    candidates: List[Path] = []

    if system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            candidates.append(Path(appdata) / "Zotero" / "Zotero" / "Profiles")
        candidates.append(home / "Zotero")
    elif system == "Darwin":
        candidates.append(home / "Library" / "Application Support" / "Zotero" / "Profiles")
        candidates.append(home / "Zotero")
    else:
        candidates.append(home / ".zotero" / "zotero")
        candidates.append(home / "Zotero")

    # Also check ZOTERO_DATA_DIR env var for custom installations.
    custom = os.environ.get("ZOTERO_DATA_DIR")
    if custom:
        candidates.insert(0, Path(custom))

    return candidates


def find_zotero_db() -> Optional[Path]:
    """Locate the user's zotero.sqlite file. Returns None if not found."""
    for base in _default_zotero_paths():
        if not base.exists():
            continue
        # Direct path
        direct = base / "zotero.sqlite"
        if direct.exists():
            return direct
        # Inside a profile directory (e.g. Profiles/<hash>.default/zotero/zotero.sqlite)
        for db in base.rglob("zotero.sqlite"):
            return db
    return None


# ── Extract data from Zotero SQLite ─────────────────────────────────────

def _read_tags(db_path: Path) -> List[str]:
    """Read all item tags from the Zotero database."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.execute(
            "SELECT t.name FROM tags t "
            "JOIN itemTags it ON t.tagID = it.tagID "
            "GROUP BY t.name ORDER BY COUNT(*) DESC"
        )
        tags = [row[0] for row in cursor.fetchall() if row[0]]
        conn.close()
        return tags
    except sqlite3.Error:
        return []


def _read_collections(db_path: Path) -> List[str]:
    """Read all collection names from the Zotero database."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.execute(
            "SELECT collectionName FROM collections ORDER BY collectionName"
        )
        names = [row[0] for row in cursor.fetchall() if row[0]]
        conn.close()
        return names
    except sqlite3.Error:
        return []


def _read_titles(db_path: Path, limit: int = 200) -> List[str]:
    """Read recent item titles to supplement tag-based detection."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.execute(
            "SELECT iv.value FROM itemDataValues iv "
            "JOIN itemData id ON iv.valueID = id.valueID "
            "JOIN fields f ON id.fieldID = f.fieldID "
            "WHERE f.fieldName = 'title' "
            "ORDER BY id.itemID DESC LIMIT ?",
            (limit,)
        )
        titles = [row[0] for row in cursor.fetchall() if row[0]]
        conn.close()
        return titles
    except sqlite3.Error:
        return []


def _read_item_count(db_path: Path) -> int:
    """Count the total number of items in the library."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.execute("SELECT COUNT(*) FROM items WHERE itemTypeID != 1")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except sqlite3.Error:
        return 0


# ── Map Zotero data to ResearchPulse topics ──────────────────────────────

def _match_topics(tags: List[str], collections: List[str],
                  titles: List[str]) -> List[Tuple[str, str, float]]:
    """Score each ResearchPulse topic against the user's Zotero data.

    Returns a sorted list of (topic_id, topic_label, confidence) tuples where
    confidence is 0.0-1.0 indicating how well the user's library matches.
    """
    rp_topics, _ = load_topics()

    # Build a combined bag of lowercase terms from the user's Zotero data.
    all_terms = []
    for tag in tags:
        all_terms.extend(tag.lower().split())
    for col in collections:
        all_terms.extend(col.lower().split())
    for title in titles:
        all_terms.extend(title.lower().split())

    term_counts = Counter(all_terms)
    total_terms = max(len(all_terms), 1)

    results: List[Tuple[str, str, float]] = []
    for topic in rp_topics:
        hits = 0
        max_possible = max(len(topic.keywords), 1)
        for kw in topic.keywords:
            kw_parts = kw.lower().split()
            for part in kw_parts:
                if term_counts.get(part, 0) > 0:
                    hits += term_counts[part]
        # Normalize: how many of the topic's keywords were found, weighted by
        # how often they appear.
        score = min(1.0, (hits / max_possible) / 10.0)

        # Boost if a collection name closely matches the topic label.
        for col in collections:
            if topic.id in col.lower() or topic.label.lower() in col.lower():
                score = min(1.0, score + 0.4)

        # Boost if tags directly contain topic keywords.
        tag_set = {t.lower() for t in tags}
        for kw in topic.keywords:
            if kw.lower() in tag_set:
                score = min(1.0, score + 0.25)

        if score > 0.05:
            results.append((topic.id, topic.label, round(score, 2)))

    results.sort(key=lambda x: x[2], reverse=True)
    return results


# ── Public API ───────────────────────────────────────────────────────────

def detect_topics(db_path: Optional[Path] = None) -> List[Tuple[str, str, float]]:
    """Detect the user's research domains from their Zotero library.

    Returns a list of (topic_id, topic_label, confidence) tuples, sorted by
    confidence descending. Returns an empty list if Zotero is not found.
    """
    if db_path is None:
        db_path = find_zotero_db()
    if db_path is None:
        return []

    tags = _read_tags(db_path)
    collections = _read_collections(db_path)
    titles = _read_titles(db_path)

    return _match_topics(tags, collections, titles)


def get_zotero_summary(db_path: Optional[Path] = None) -> Optional[Dict]:
    """Get a summary of the user's Zotero library for display."""
    if db_path is None:
        db_path = find_zotero_db()
    if db_path is None:
        return None

    return {
        "db_path": str(db_path),
        "item_count": _read_item_count(db_path),
        "tag_count": len(_read_tags(db_path)),
        "collection_count": len(_read_collections(db_path)),
        "top_tags": _read_tags(db_path)[:15],
        "collections": _read_collections(db_path),
    }


def detect_and_print() -> int:
    """CLI entry point: detect Zotero and print domain suggestions."""
    print("\nSearching for Zotero on your system...")

    db = find_zotero_db()
    if db is None:
        print("\n  Zotero database not found.")
        print("\n  Expected locations:")
        for p in _default_zotero_paths():
            print(f"    {p}")
        print("\n  If Zotero is installed in a custom location, set:")
        print("    ZOTERO_DATA_DIR=/path/to/your/zotero/data")
        print("\n  You can still use ResearchPulse without Zotero.")
        print("  Run: python -m research_agent setup")
        return 1

    summary = get_zotero_summary(db)
    print(f"\n  Found Zotero: {db}")
    print(f"  Items: {summary['item_count']}")
    print(f"  Tags: {summary['tag_count']}")
    print(f"  Collections: {summary['collection_count']}")

    if summary["top_tags"]:
        print(f"\n  Your top tags: {', '.join(summary['top_tags'][:10])}")
    if summary["collections"]:
        print(f"  Your collections: {', '.join(summary['collections'][:10])}")

    topics = detect_topics(db)
    if topics:
        print("\n  Suggested ResearchPulse topics based on your library:\n")
        for tid, label, conf in topics:
            bar = "#" * int(conf * 20)
            pct = int(conf * 100)
            print(f"    {tid:20s}  {label:40s}  [{bar:<20s}] {pct}%")

        suggested = [t[0] for t in topics if t[2] >= 0.15]
        if suggested:
            print(f"\n  Quick start with your domains:")
            print(f"    python -m research_agent digest --topics {' '.join(suggested)} --open\n")
    else:
        print("\n  Could not match your library to specific topics.")
        print("  Your Zotero library may focus on domains not yet in topics.yaml.")
        print("  Add custom topics to config/topics.yaml.\n")

    return 0
