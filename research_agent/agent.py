"""ResearchPulse Agent - Interactive research assistant.

An AI-powered research agent that searches papers, remembers your reading
history, and provides personalized insights.

Usage:
    python -m research_agent              # Interactive mode
    python -m research_agent search "query"  # One-shot search
    research-agent                        # If installed via pip
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import List, Optional

from . import __version__
from .config import load_topics, topics_by_id
from .memory import ResearchMemory
from .models import Paper
from .search import search_papers, search_by_topic, search_all_sources
from .summarize import Summarizer
from .config import load_secrets, load_settings
from .chat import ask_about_paper, ask_research_question, explain_concept, is_llm_available, get_llm_backend
from .compare import compare_papers
from .critique import challenge_hypothesis, refine_hypothesis
from .insights import generate_insights, format_insights
from .recommend import get_recommendations, get_daily_briefing, format_recommendations
from .features import extract_features, format_features

# Try to import rich for nice formatting; fall back to plain text
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.markdown import Markdown
    from rich.text import Text
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


# ── Display Helpers ─────────────────────────────────────────────────────

def _print_plain(text: str) -> None:
    """Print plain text (fallback when rich is not installed)."""
    print(text)


def _display_paper_plain(paper: Paper, index: int = 0) -> None:
    """Display a single paper in plain text."""
    prefix = f"{index}." if index else "-"
    print(f"\n{prefix} [{paper.source}] {paper.title}")
    if paper.authors:
        authors = ", ".join(paper.authors[:3])
        if len(paper.authors) > 3:
            authors += " et al."
        print(f"   Authors: {authors}")
    if paper.venue_line():
        print(f"   Venue: {paper.venue_line()}")
    if paper.score:
        print(f"   Relevance: {paper.score:.2f}")
    if paper.citations:
        print(f"   Citations: {paper.citations}")
    if paper.summary:
        print(f"   Summary: {paper.summary}")
    elif paper.abstract:
        # Show first 200 chars of abstract
        abstract = paper.abstract[:200] + "..." if len(paper.abstract) > 200 else paper.abstract
        print(f"   Abstract: {abstract}")
    print(f"   URL: {paper.url}")


def _display_papers_plain(papers: List[Paper], title: str = "Results") -> None:
    """Display multiple papers in plain text."""
    if not papers:
        print(f"\nNo papers found.")
        return

    print(f"\n{'='*60}")
    print(f"  {title} ({len(papers)} papers)")
    print(f"{'='*60}")

    for i, paper in enumerate(papers, 1):
        _display_paper_plain(paper, i)

    print(f"\n{'='*60}")


# Rich display functions
def _display_paper_rich(console: 'Console', paper: Paper, index: int = 0) -> None:
    """Display a single paper with rich formatting."""
    prefix = f"[bold cyan]{index}.[/bold cyan]" if index else "[bold cyan]-[/bold cyan]"

    console.print(f"\n{prefix} [bold]{paper.title}[/bold]")
    meta = f"   [dim]{paper.source}[/dim]"
    if paper.authors:
        authors = ", ".join(paper.authors[:3])
        if len(paper.authors) > 3:
            authors += " et al."
        meta += f" [dim]· {authors}[/dim]"
    if paper.citations:
        meta += f" [dim]· {paper.citations} citations[/dim]"
    console.print(meta)
    if paper.venue_line():
        console.print(f"   [magenta]{paper.venue_line()}[/magenta]")

    if paper.score:
        console.print(f"   [green]Relevance: {paper.score:.2f}[/green]")

    if paper.summary:
        console.print(f"   {paper.summary}")
    elif paper.abstract:
        abstract = paper.abstract[:250] + "..." if len(paper.abstract) > 250 else paper.abstract
        console.print(f"   [dim]{abstract}[/dim]")

    console.print(f"   [blue]{paper.url}[/blue]")


def _display_papers_rich(console: 'Console', papers: List[Paper], title: str = "Results") -> None:
    """Display multiple papers with rich formatting."""
    if not papers:
        console.print("\n[yellow]No papers found.[/yellow]")
        return

    sep = "-" * 60
    console.print(f"\n[bold]{sep}[/bold]")
    console.print(f"  [bold cyan]{title}[/bold cyan] ({len(papers)} papers)")
    console.print(f"[bold]{sep}[/bold]")

    for i, paper in enumerate(papers, 1):
        _display_paper_rich(console, paper, i)

    console.print(f"\n[bold]{sep}[/bold]")


def display_papers(papers: List[Paper], title: str = "Results") -> None:
    """Display papers using the best available method."""
    if HAS_RICH:
        console = Console()
        _display_papers_rich(console, papers, title)
    else:
        _display_papers_plain(papers, title)


# ── Command Handlers ────────────────────────────────────────────────────

def cmd_search(query: str, memory: ResearchMemory) -> Optional[List[Paper]]:
    """Search for papers by keyword."""
    if not query:
        from . import ui
        ui.warn("Usage: search <query>")
        ui.info("Example: search transformer attention efficiency")
        return None

    from . import ui
    sources = ["arxiv", "openalex", "semanticscholar", "crossref"]
    with ui.quiet_logs(), ui.search_progress(sources, query) as on_source:
        papers = search_papers(query, limit=10, on_source=on_source)

    if papers:
        display_papers(papers, f"Search: {query}")
        # Record in memory
        for p in papers[:3]:  # Record top 3
            memory.record_paper(
                paper_id=p.id,
                title=p.title,
                url=p.url,
                source=p.source,
                tags=[query],
            )
    else:
        print("No papers found. Try a different query or check your internet connection.")

    return papers


def cmd_topic(topic_id: str) -> Optional[List[Paper]]:
    """Search for papers in a specific topic."""
    from . import ui

    if not topic_id:
        ui.warn("Usage: topic <topic_id>")
        ui.info("Run 'topics' to see available topics.")
        return None

    with ui.spinner(f"Fetching papers for {topic_id}"):
        papers = search_by_topic(topic_id, days=7, limit=10)

    if papers:
        display_papers(papers, f"Topic: {topic_id}")
    else:
        print(f"No papers found for topic '{topic_id}'. Check the topic ID with 'topics'.")

    return papers


def cmd_topics() -> None:
    """List available research topics."""
    topics, _ = load_topics()

    if HAS_RICH:
        console = Console()
        table = Table(title="Available Topics")
        table.add_column("ID", style="cyan")
        table.add_column("Label", style="bold")
        table.add_column("Keywords", style="dim")

        for t in topics:
            keywords = ", ".join(t.keywords[:4])
            if len(t.keywords) > 4:
                keywords += "..."
            table.add_row(t.id, t.label, keywords)

        console.print(table)
    else:
        print("\nAvailable Topics:")
        print("-" * 50)
        for t in topics:
            keywords = ", ".join(t.keywords[:3])
            print(f"  {t.id:20s} {t.label}")
            print(f"  {'':20s} Keywords: {keywords}")
        print()


def cmd_summarize(paper_id: str, papers: List[Paper], memory: ResearchMemory) -> None:
    """Summarize a specific paper from recent search results."""
    if not paper_id:
        print("Usage: summarize <number>")
        print("Use the number from a recent search result.")
        return

    try:
        idx = int(paper_id) - 1
        if 0 <= idx < len(papers):
            paper = papers[idx]
            print(f"\nSummarizing: {paper.title}")

            # Use the summarizer if LLM is available
            secrets = load_secrets()
            settings = load_settings()
            summarizer = Summarizer(secrets, settings.abstract_max_chars)

            summary = summarizer.summarize(paper)
            print(f"\nSummary: {summary}")

            # Record in memory
            memory.record_paper(
                paper_id=paper.id,
                title=paper.title,
                url=paper.url,
                source=paper.source,
            )
        else:
            print(f"Invalid number. Use 1-{len(papers)}.")
    except ValueError:
        print("Usage: summarize <number> (e.g., summarize 1)")


def cmd_rate(rating_str: str, paper_id: str, papers: List[Paper], memory: ResearchMemory) -> None:
    """Rate a paper from recent search results."""
    if not rating_str or not paper_id:
        print("Usage: rate <number> <1-5>")
        print("Example: rate 1 4  (rate paper #1 as 4 stars)")
        return

    try:
        idx = int(paper_id) - 1
        rating = int(rating_str)

        if not (1 <= rating <= 5):
            print("Rating must be 1-5.")
            return

        if 0 <= idx < len(papers):
            paper = papers[idx]
            memory.record_paper(
                paper_id=paper.id,
                title=paper.title,
                url=paper.url,
                source=paper.source,
                rating=rating,
            )
            print(f"Rated '{paper.title}' {rating}/5 stars.")
        else:
            print(f"Invalid number. Use 1-{len(papers)}.")
    except ValueError:
        print("Usage: rate <number> <1-5>")


def cmd_memory(args: List[str], memory: ResearchMemory) -> None:
    """View or update memory."""
    if not args:
        print(memory.summary())
        return

    subcmd = args[0]

    if subcmd == "set":
        # memory set name "Alice"
        if len(args) >= 3:
            key = args[1]
            value = " ".join(args[2:]).strip('"')
            if key in ("name", "field", "role"):
                memory.set_profile(**{key: value})
                print(f"Set {key} = {value}")
            elif key == "goal":
                goals = memory.profile.get("goals", [])
                goals.append(value)
                memory.set_profile(goals=goals)
                print(f"Added goal: {value}")
            else:
                print(f"Unknown key: {key}. Use: name, field, role, goal")

    elif subcmd == "add":
        # memory add keyword "transformer"
        if len(args) >= 3:
            itype = args[1]
            value = " ".join(args[2:]).strip('"')
            memory.add_interest(itype, value)
            print(f"Added {itype}: {value}")

    elif subcmd == "question":
        # memory question "Is sparse attention faster?"
        if len(args) >= 2:
            question = " ".join(args[1:]).strip('"')
            memory.add_interest("question", question)
            print(f"Added question: {question}")

    elif subcmd == "papers":
        papers = memory.get_recent_papers(days=30)
        if papers:
            print(f"\nRecent papers ({len(papers)}):")
            for p in papers[:10]:
                stars = "★" * p.rating + "☆" * (5 - p.rating) if p.rating else "unrated"
                print(f"  [{stars}] {p.title}")
        else:
            print("No papers recorded yet. Use 'search' to find papers.")

    elif subcmd == "insights":
        insights = memory.get_recent_insights(days=30)
        if insights:
            print(f"\nRecent insights ({len(insights)}):")
            for i in insights[:10]:
                print(f"  [{i.insight_type}] {i.description}")
        else:
            print("No insights yet. Keep using the agent!")

    else:
        print(f"Unknown subcommand: {subcmd}")
        print("Usage: memory [set|add|question|papers|insights]")


def cmd_profile(memory: ResearchMemory) -> None:
    """Show researcher profile."""
    print("\n" + "="*50)
    print("  Researcher Profile")
    print("="*50)
    print(memory.summary())
    print("="*50)


def cmd_ask(question: str, papers: List[Paper], memory: ResearchMemory) -> None:
    """Ask a question about a paper or general research question."""
    if not question:
        print("Usage: ask <question>")
        print("Example: ask What methodology did they use?")
        return

    if not is_llm_available():
        print("\nLLM not configured. Set GROQ_API_KEY, GEMINI_API_KEY, or OLLAMA_HOST.")
        print("See .env.example for configuration details.")
        return

    # Check if asking about a specific paper (e.g., "ask 1 What methodology?")
    parts = question.split(maxsplit=1)
    if parts and parts[0].isdigit() and len(parts) > 1:
        try:
            idx = int(parts[0]) - 1
            if 0 <= idx < len(papers):
                paper = papers[idx]
                actual_question = parts[1]
                print(f"\nAsking about: {paper.title}")
                answer = ask_about_paper(paper, actual_question)
                if answer:
                    print(f"\nAnswer: {answer}")
                    memory.record_conversation(question, answer)
                else:
                    print("Could not generate an answer.")
                return
        except (ValueError, IndexError):
            pass

    # General research question
    print(f"\nThinking about: {question}")
    answer = ask_research_question(question, papers)
    if answer:
        print(f"\nAnswer: {answer}")
        memory.record_conversation(question, answer)
    else:
        print("Could not generate an answer.")


def cmd_explain(concept: str, papers: List[Paper]) -> None:
    """Explain a research concept."""
    if not concept:
        print("Usage: explain <concept>")
        print("Example: explain transformer attention")
        return

    if not is_llm_available():
        print("\nLLM not configured. Set GROQ_API_KEY, GEMINI_API_KEY, or OLLAMA_HOST.")
        return

    print(f"\nExplaining: {concept}")
    explanation = explain_concept(concept, papers)
    if explanation:
        print(f"\nExplanation: {explanation}")
    else:
        print("Could not generate an explanation.")


def cmd_compare(indices_str: str, papers: List[Paper]) -> None:
    """Compare papers from recent search results."""
    if not indices_str:
        print("Usage: compare <number1> <number2> [number3...]")
        print("Example: compare 1 2 3")
        print("Use numbers from a recent search result.")
        return

    try:
        indices = [int(x.strip()) - 1 for x in indices_str.split()]
        selected = []
        for idx in indices:
            if 0 <= idx < len(papers):
                selected.append(papers[idx])
            else:
                print(f"Invalid number: {idx + 1}. Use 1-{len(papers)}.")
                return

        if len(selected) < 2:
            print("Need at least 2 papers to compare.")
            return

        print(f"\nComparing {len(selected)} papers...")
        comparison = compare_papers(selected)
        print(comparison)

    except ValueError:
        print("Usage: compare <number1> <number2> [number3...]")
        print("Example: compare 1 2")


def cmd_critique(hypothesis: str, papers: List[Paper]) -> None:
    """Challenge a hypothesis with evidence from papers."""
    if not hypothesis:
        print("Usage: critique <hypothesis>")
        print("Example: critique LoRA is always better than full fine-tuning")
        return

    if not papers:
        print("No papers available. Search for relevant papers first.")
        return

    print(f"\nChallenging hypothesis: {hypothesis}")
    critique = challenge_hypothesis(hypothesis, papers)
    print(critique)


def cmd_insights(papers: List[Paper], memory: ResearchMemory) -> None:
    """Generate insights from papers."""
    if not papers:
        print("No papers available. Search for papers first.")
        return

    print(f"\nAnalyzing {len(papers)} papers for insights...")
    insights = generate_insights(papers, memory)
    print(format_insights(insights))


def cmd_recommend(papers: List[Paper], memory: ResearchMemory) -> None:
    """Get personalized recommendations."""
    if not papers:
        print("No papers available. Search for papers first.")
        return

    print(f"\nGenerating recommendations based on your profile...")
    recommendations = get_recommendations(papers, memory)
    print(format_recommendations(recommendations))


def cmd_briefing(papers: List[Paper], memory: ResearchMemory) -> None:
    """Generate a daily research briefing."""
    if not papers:
        print("No papers available. Search for papers first.")
        return

    print(f"\nGenerating daily briefing...")
    briefing = get_daily_briefing(papers, memory)
    print(briefing)


def cmd_features(paper_id: str, papers: List[Paper]) -> None:
    """Extract features from a paper."""
    if not paper_id:
        print("Usage: features <number>")
        print("Use the number from a recent search result.")
        return

    try:
        idx = int(paper_id) - 1
        if 0 <= idx < len(papers):
            paper = papers[idx]
            print(f"\nExtracting features from: {paper.title}")

            features = extract_features(paper)
            print(format_features(features))
        else:
            print(f"Invalid number. Use 1-{len(papers)}.")
    except ValueError:
        print("Usage: features <number> (e.g., features 1)")


def cmd_search_all(query: str, memory: ResearchMemory) -> Optional[List[Paper]]:
    """Search across ALL sources."""
    if not query:
        from . import ui
        ui.warn("Usage: search --all <query>")
        return None

    from . import ui
    sources = ["arxiv", "openalex", "semanticscholar", "crossref", "europepmc"]
    with ui.quiet_logs(), ui.search_progress(sources, query) as on_source:
        papers = search_papers(
            query, sources=sources, limit=10, on_source=on_source
        )

    if papers:
        display_papers(papers, f"Search (All Sources): {query}")
        # Record in memory
        for p in papers[:3]:
            memory.record_paper(
                paper_id=p.id,
                title=p.title,
                url=p.url,
                source=p.source,
                tags=[query],
            )
    else:
        print("No papers found. Try a different query.")

    return papers


def cmd_help() -> None:
    """Show help."""
    help_text = """
ResearchPulse Agent v{version}

SEARCH COMMANDS:
  search <query>        Search papers by keyword
  search --all <query>  Search ALL sources (arXiv, OpenAlex, Semantic Scholar, Crossref, Europe PMC)
  topic <topic_id>      Search papers in a specific topic
  topics                List available research topics

PAPER COMMANDS:
  summarize <number>    Summarize a paper from recent results
  rate <number> <1-5>   Rate a paper
  compare <n1> <n2>     Compare two or more papers
  ask <question>        Ask a question about research
  ask <n> <question>    Ask about a specific paper
  explain <concept>     Explain a research concept
  critique <hypothesis> Challenge a hypothesis with evidence
  features <number>     Extract methodology, findings, and contributions

INSIGHT COMMANDS:
  insights              Get insights from recent papers
  recommend             Get personalized recommendations
  briefing              Get daily research briefing

MEMORY COMMANDS:
  memory                View your research memory
  memory set <k> <v>    Set profile (name, field, role)
  memory add <type> <v> Add interest (topic, keyword, author)
  memory question <q>   Add a research question
  memory papers         View recent papers
  memory insights       View recent insights
  profile               Show researcher profile

OTHER:
  web                   Start web UI (browser-based interface)
  help                  Show this help
  quit / exit           Exit the agent

EXAMPLES:
  search "transformer attention efficiency"
  topic ai-ml
  summarize 1
  rate 1 4
  compare 1 2 3
  ask "What methodology did they use?"
  ask 1 "What are the limitations?"
  explain "attention mechanism"
  critique "LoRA is always better than full fine-tuning"
  insights
  recommend
  briefing
  memory set name "Alice"
  memory add keyword "sparse attention"
  memory question "Is sparse attention faster at scale?"

TIPS:
  - The agent remembers what you search and read
  - Rate papers to get better recommendations
  - Add research questions to track open problems
  - Use 'memory' to see your research profile
  - Configure LLM (GROQ_API_KEY, GEMINI_API_KEY, or OLLAMA_HOST) for AI features
""".format(version=__version__)
    print(help_text)


def cmd_quit() -> bool:
    """Exit the agent."""
    print("\nGoodbye! Your research memory has been saved.")
    return True


# ── Main Agent Loop ─────────────────────────────────────────────────────

def run_agent() -> int:
    """Run the interactive agent."""
    from . import ui

    memory = ResearchMemory()
    last_papers: List[Paper] = []

    ui.banner("Interactive research agent")
    ui.agent_palette()

    if memory.profile.get("name"):
        ui.info(f"Welcome back, {memory.profile['name']}!")
        if memory.interests.get("questions"):
            ui.info(f"{len(memory.interests['questions'])} open research questions tracked")

    while True:
        try:
            user_input = ui.agent_prompt()

            if not user_input:
                continue

            # Parse command
            parts = user_input.split(maxsplit=1)
            command = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""

            # Route commands
            if command in ("quit", "exit", "q"):
                cmd_quit()
                break

            elif command in ("help", "h", "?"):
                cmd_help()
                ui.agent_palette()

            elif command == "search":
                # Check for --all flag
                if args.startswith("--all "):
                    query = args[6:].strip()
                    papers = cmd_search_all(query, memory)
                else:
                    papers = cmd_search(args, memory)
                if papers:
                    last_papers = papers

            elif command == "topic":
                papers = cmd_topic(args)
                if papers:
                    last_papers = papers

            elif command == "topics":
                cmd_topics()

            elif command == "summarize":
                cmd_summarize(args, last_papers, memory)

            elif command == "rate":
                parts = args.split(maxsplit=1)
                if len(parts) == 2:
                    cmd_rate(parts[0], parts[1], last_papers, memory)
                else:
                    print("Usage: rate <number> <1-5>")

            elif command == "memory":
                mem_args = args.split() if args else []
                cmd_memory(mem_args, memory)

            elif command == "profile":
                cmd_profile(memory)

            elif command == "ask":
                cmd_ask(args, last_papers, memory)

            elif command == "explain":
                cmd_explain(args, last_papers)

            elif command == "compare":
                cmd_compare(args, last_papers)

            elif command == "critique":
                cmd_critique(args, last_papers)

            elif command == "insights":
                cmd_insights(last_papers, memory)

            elif command == "recommend":
                cmd_recommend(last_papers, memory)

            elif command == "briefing":
                cmd_briefing(last_papers, memory)

            elif command == "features":
                cmd_features(args, last_papers)

            elif command == "web":
                print("Starting web UI...")
                from .web import run_web
                run_web()

            else:
                # Treat unknown commands as a search query
                papers = cmd_search(user_input, memory)
                if papers:
                    last_papers = papers

        except KeyboardInterrupt:
            print("\n\nUse 'quit' to exit.")
            continue
        except EOFError:
            cmd_quit()
            break

    return 0


# ── One-shot Commands ───────────────────────────────────────────────────

def run_search(query: str) -> int:
    """Run a one-shot search."""
    from . import ui

    if not query:
        ui.warn("Usage: research-pulse search <query>")
        return 1

    ui.banner("Search across free open-access sources")
    memory = ResearchMemory()
    sources = ["arxiv", "openalex", "semanticscholar", "crossref"]
    with ui.quiet_logs(), ui.search_progress(sources, query) as on_source:
        papers = search_papers(query, limit=10, on_source=on_source)

    if papers:
        display_papers(papers, f"Search · {query}")
        ui.success(f"{len(papers)} papers ranked by relevance")
        for p in papers[:3]:
            memory.record_paper(
                paper_id=p.id,
                title=p.title,
                url=p.url,
                source=p.source,
                tags=[query],
            )
    else:
        ui.warn("No papers found.")
    return 0 if papers else 1


def run_topics() -> int:
    """List available topics."""
    cmd_topics()
    return 0


def run_memory(args: List[str]) -> int:
    """Handle memory subcommands."""
    memory = ResearchMemory()
    cmd_memory(args, memory)
    return 0


# ── CLI Entry Point ─────────────────────────────────────────────────────

def main() -> int:
    """Main entry point for the agent CLI."""
    args = sys.argv[1:]

    if not args:
        return run_agent()

    command = args[0]

    if command == "search":
        query = " ".join(args[1:]) if len(args) > 1 else ""
        return run_search(query)

    elif command == "topics":
        return run_topics()

    elif command == "memory":
        return run_memory(args[1:])

    elif command in ("help", "--help", "-h"):
        cmd_help()
        return 0

    elif command in ("version", "--version", "-v"):
        print(f"ResearchPulse Agent v{__version__}")
        return 0

    else:
        # Treat as search query
        return run_search(" ".join(args))
