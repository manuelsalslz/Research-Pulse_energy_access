"""Simple command-line interface for ResearchPulse.

Designed for daily use with minimal setup:

    pip install -r requirements.txt
    research-pulse              # today's digest (opens in browser)
    research-pulse search "query"
    research-pulse topics       # view or change your topics
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from typing import List, Optional

from . import __version__
from .config import ROOT, load_topics, topics_by_id, add_topic, load_settings
from .local_config import (
    clear_papers_per_topic,
    effective_papers_per_topic,
    ensure_ready,
    get_papers_per_topic,
    get_topics,
    save,
    set_papers_per_topic,
    MIN_PAPERS_PER_TOPIC,
    MAX_PAPERS_PER_TOPIC,
)
from . import ui


def _open_preview() -> None:
    previews = sorted((ROOT / "preview").glob("*.html"))
    if previews:
        webbrowser.open(previews[0].as_uri())
        ui.success("Opened preview in browser")
        ui.info(str(previews[0]))
    else:
        ui.warn("No preview generated.")


def cmd_today(open_browser: bool = True) -> int:
    """Fetch and show today's digest using saved topics."""
    ui.banner()
    topics = ensure_ready(force_zotero=True, verbose=False)
    topics_list, _ = load_topics()
    labels = topics_by_id(topics_list)
    names = [labels[t].label if t in labels else t for t in topics]

    if not ui.HAS_RICH:
        ui.info(f"Topics: {', '.join(names)}")

    from .pipeline import run

    with ui.quiet_logs(), ui.digest_progress(names) as on_progress:
        rc = run(dry_run=True, topic_override=topics, on_progress=on_progress)

    if rc == 0:
        ui.success("Digest preview ready")
        if open_browser:
            _open_preview()
        else:
            ui.info(f"Saved to {ROOT / 'preview'}")
    else:
        ui.error("Digest failed — check your connection and try again.")
    return rc


def cmd_search(query: str) -> int:
    if not query.strip():
        ui.warn('Usage: research-pulse search "your query"')
        ui.command_palette()
        return 1

    ui.banner("Search across free open-access sources")
    from .agent import display_papers
    from .search import search_papers

    sources = ["arxiv", "openalex", "semanticscholar", "crossref"]
    with ui.quiet_logs(), ui.search_progress(sources, query) as on_source:
        papers = search_papers(query, limit=10, on_source=on_source)

    if papers:
        display_papers(papers, f"Search · {query}")
        ui.success(f"{len(papers)} papers ranked by relevance")
    else:
        ui.warn("No papers found — try different keywords or check your connection.")
    return 0 if papers else 1


def cmd_topics(args: List[str]) -> int:
    """Show or set topics. No args = interactive picker."""
    topics_list, _ = load_topics()
    by_id = topics_by_id(topics_list)
    current = get_topics() or ensure_ready(verbose=False)

    if args:
        unknown = [a for a in args if a not in by_id]
        if unknown:
            ui.error(f"Unknown topic(s): {', '.join(unknown)}")
            ui.info("Run: research-pulse topics")
            return 1
        save(args, source="manual")
        names = [by_id[t].label for t in args]
        ui.success(f"Saved {len(names)} topic(s)")
        for n in names:
            ui.info(n)
        return 0

    ui.banner("Manage your research topics")
    ui.show_topics(current, topics_list, by_id)
    ui.info("Enter numbers to follow (e.g. 1 3 5), or press Enter to keep current")

    try:
        raw = ui.prompt("Select › ")
    except (EOFError, KeyboardInterrupt):
        print()
        return 0

    if not raw:
        return 0

    try:
        indices = [int(x) - 1 for x in raw.replace(",", " ").split()]
        chosen = [topics_list[i].id for i in indices if 0 <= i < len(topics_list)]
    except (ValueError, IndexError):
        ui.error("Invalid input — use numbers like: 1 3 5")
        return 1

    if not chosen:
        ui.warn("No topics selected.")
        return 1

    save(chosen, source="manual")
    ui.success(f"Following {len(chosen)} topic(s)")
    for tid in chosen:
        ui.info(by_id[tid].label)
    return 0


def cmd_help() -> int:
    ui.show_help()
    return 0


def _slugify(text: str) -> str:
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug[:40] or "topic"


def cmd_follow(args: List[str]) -> int:
    """Follow any research area described in plain English."""
    phrase = " ".join(args).strip().strip('"').strip("'")
    if not phrase:
        ui.warn('Usage: research-pulse follow "your research area"')
        ui.info('Example: research-pulse follow "quantum error correction"')
        return 1

    ui.banner(f'Following · "{phrase}"')

    topics_list, _ = load_topics()
    by_id = topics_by_id(topics_list)

    match = None
    if phrase.lower() in by_id:
        match = phrase.lower()
    else:
        for t in topics_list:
            if t.label.lower() == phrase.lower():
                match = t.id
                break

    if match is None:
        topic_id = _slugify(phrase)
        if topic_id in by_id:
            match = topic_id
        else:
            keywords = [w for w in phrase.split() if len(w) > 2][:6] or [phrase]
            add_topic(
                topic_id,
                phrase.title(),
                keywords,
                arxiv=[],
                biorxiv=[],
                openalex=phrase,
                semanticscholar=phrase,
                europepmc=phrase,
            )
            match = topic_id
            ui.success(f"Created topic: {phrase.title()} ({topic_id})")

    current = get_topics()
    if match not in current:
        current.append(match)
        save(current, source="follow")
    ui.info("Added to your daily digest")

    from .search import search_by_topic
    from .agent import display_papers

    with ui.quiet_logs(), ui.spinner(f"Fetching recent papers for {phrase}"):
        papers = search_by_topic(match, days=30, limit=10)

    if papers:
        display_papers(papers, f"Recent · {phrase}")
        ui.success(f"{len(papers)} papers — they'll also appear in tomorrow's digest")
    else:
        ui.warn("No recent papers yet — check back in your next digest.")
    return 0


def cmd_config(args: List[str]) -> int:
    """View or change local preferences (papers per topic, etc.)."""
    default = load_settings().papers_per_topic
    current = effective_papers_per_topic()
    override = get_papers_per_topic()

    if not args or args[0] == "show":
        ui.banner("Local settings")
        ui.info(f"Papers per topic: [bold]{current}[/]" if ui.HAS_RICH else f"Papers per topic: {current}")
        if override is not None:
            ui.info(f"  (your override; default in settings.yaml is {default})")
        else:
            ui.info(f"  (from config/settings.yaml — default {default})")
        ui.info(f"Range: {MIN_PAPERS_PER_TOPIC}–{MAX_PAPERS_PER_TOPIC}")
        ui.info("Set: research-pulse config papers 10")
        return 0

    if args[0] == "papers":
        if len(args) == 1:
            ui.info(f"Papers per topic: {current}")
            return 0
        if args[1].lower() in ("reset", "default", "clear"):
            clear_papers_per_topic()
            ui.success(f"Reset to default ({default} papers per topic)")
            return 0
        try:
            count = int(args[1])
        except ValueError:
            ui.error(f"Usage: research-pulse config papers <{MIN_PAPERS_PER_TOPIC}-{MAX_PAPERS_PER_TOPIC}>")
            ui.info("Or: research-pulse config papers reset")
            return 1
        try:
            set_papers_per_topic(count)
        except ValueError as exc:
            ui.error(str(exc))
            return 1
        ui.success(f"Papers per topic set to {count}")
        ui.info("Applies to your next digest (research-pulse)")
        return 0

    ui.warn(f"Unknown setting: {args[0]}")
    ui.info("Try: research-pulse config")
    return 1


def cmd_add_topic(args: List[str]) -> int:
    """Add a new topic to config/topics.yaml."""
    parser = argparse.ArgumentParser(prog="research-pulse add-topic", add_help=False)
    parser.add_argument("--id", required=True, help="Topic ID (lowercase, no spaces)")
    parser.add_argument("--label", required=True, help="Human-friendly name")
    parser.add_argument("--keywords", required=True, help="Comma-separated keywords")
    parser.add_argument("--arxiv", default="", help="Comma-separated arXiv codes (e.g. cs.AI,cs.LG)")
    parser.add_argument("--biorxiv", default="", help="Comma-separated: biorxiv,medrxiv")
    parser.add_argument("--openalex", default="", help="OpenAlex search query")
    parser.add_argument("--semanticscholar", default="", help="Semantic Scholar search query")
    parser.add_argument("--europepmc", default="", help="Europe PMC search query")

    try:
        opts = parser.parse_args(args)
    except SystemExit:
        ui.warn("Usage: research-pulse add-topic --id ID --label \"Name\" --keywords \"kw1,kw2\"")
        return 1

    topic_id = opts.id.strip().lower().replace(" ", "-")
    label = opts.label.strip()
    keywords = [k.strip() for k in opts.keywords.split(",") if k.strip()]
    arxiv = [a.strip() for a in opts.arxiv.split(",") if a.strip()]
    biorxiv = [b.strip() for b in opts.biorxiv.split(",") if b.strip()]
    openalex = opts.openalex.strip() or None
    semanticscholar = opts.semanticscholar.strip() or None
    europepmc = opts.europepmc.strip() or None

    if not topic_id or not label or not keywords:
        ui.error("--id, --label, and --keywords are required.")
        return 1

    added = add_topic(topic_id, label, keywords, arxiv, biorxiv, openalex,
                      semanticscholar, europepmc)
    if added:
        ui.success(f"Added topic: {label} ({topic_id})")
        ui.info(f"Use it: research-pulse topics {topic_id}")
    else:
        ui.warn(f"Topic '{topic_id}' already exists.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]

    if not argv:
        return cmd_today()

    if argv[0] in ("-h", "--help", "help"):
        return cmd_help()

    if argv[0] in ("-v", "--version", "version"):
        ui.info(f"ResearchPulse v{__version__}")
        return 0

    cmd = argv[0]
    rest = argv[1:]

    if cmd in ("today", "digest", "run"):
        return cmd_today()

    if cmd == "search":
        return cmd_search(" ".join(rest))

    if cmd == "topics":
        return cmd_topics(rest)

    if cmd in ("follow", "add"):
        return cmd_follow(rest)

    if cmd in ("chat", "agent"):
        from .agent import run_agent
        return run_agent()

    if cmd == "setup":
        return cmd_topics([])

    if cmd == "add-topic":
        return cmd_add_topic(rest)

    if cmd in ("config", "papers", "settings"):
        if cmd in ("papers", "settings") and rest:
            return cmd_config(["papers"] + rest)
        if cmd == "papers" and not rest:
            return cmd_config(["papers"])
        return cmd_config(rest)

    if cmd == "commands":
        ui.banner()
        ui.command_palette()
        return 0

    return cmd_search(f"{cmd} {' '.join(rest)}".strip())


if __name__ == "__main__":
    sys.exit(main())
