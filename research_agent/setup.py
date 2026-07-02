"""Interactive first-time setup wizard for local users.

Walks the user through picking topics, optionally configuring an LLM key,
and runs a dry-run so they see output immediately.

Usage:
    python -m research_agent setup
"""

from __future__ import annotations

import sys
from pathlib import Path

from .config import ROOT, load_topics


def _prompt(msg: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        value = input(f"{msg}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return value or default


def run_setup() -> int:
    """Interactive setup wizard."""
    topics, _ = load_topics()

    print("\n" + "=" * 56)
    print("  ResearchPulse - First-time setup")
    print("=" * 56)
    print("\nThis wizard will help you configure ResearchPulse for")
    print("local use. You can also run it as a newsletter later.\n")

    # Step 1: pick topics
    print("Available research topics:\n")
    for i, t in enumerate(topics, 1):
        kw = ", ".join(t.keywords[:3])
        print(f"  {i:2d}. {t.label}  ({kw})")

    print(f"\nPick topics by entering their numbers (e.g. 1 3 5).")
    print("Or type 'all' to subscribe to everything.")
    raw = _prompt("Your choices", "all")

    if raw.lower() == "all":
        chosen = [t.id for t in topics]
    else:
        try:
            indices = [int(x) - 1 for x in raw.replace(",", " ").split()]
            chosen = [topics[i].id for i in indices if 0 <= i < len(topics)]
        except (ValueError, IndexError):
            chosen = [topics[0].id]
            print(f"  Couldn't parse input; defaulting to {chosen[0]}.")

    chosen_labels = [t.label for t in topics if t.id in chosen]
    print(f"\n  Selected: {', '.join(chosen_labels)}\n")

    # Step 2: LLM (optional)
    print("ResearchPulse can use a free LLM API for plain-language summaries.")
    print("Without one, it uses paper abstracts (works fine, zero cost).\n")
    print("  1. Skip (use abstracts)")
    print("  2. Enter a Groq API key (free at console.groq.com)")
    print("  3. Enter a Gemini API key (free at aistudio.google.com)")
    print("  4. Use a local Ollama model\n")
    llm_choice = _prompt("Choice", "1")

    env_lines = []
    if llm_choice == "2":
        key = _prompt("Groq API key")
        if key:
            env_lines.append(f"GROQ_API_KEY={key}")
    elif llm_choice == "3":
        key = _prompt("Gemini API key")
        if key:
            env_lines.append(f"GEMINI_API_KEY={key}")
    elif llm_choice == "4":
        host = _prompt("Ollama host", "http://localhost:11434")
        model = _prompt("Ollama model", "llama3.2")
        env_lines.append(f"OLLAMA_HOST={host}")
        env_lines.append(f"OLLAMA_MODEL={model}")

    # Step 3: write .env (merge with existing)
    env_path = ROOT / ".env"
    existing = ""
    if env_path.exists():
        existing = env_path.read_text(encoding="utf-8")

    if env_lines:
        with env_path.open("a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            for line in env_lines:
                f.write(line + "\n")
        print(f"\n  Saved LLM config to {env_path}")

    # Step 4: run a dry-run preview
    print("\n" + "-" * 56)
    print("  Running a preview digest for your chosen topics...")
    print("-" * 56 + "\n")

    from .pipeline import main as pipeline_main
    topic_args = []
    for t in chosen:
        topic_args.extend(["--topics", t])
    topic_args.extend(["--dry-run", "--limit", "1"])

    rc = pipeline_main(topic_args)

    if rc == 0:
        preview_dir = ROOT / "preview"
        previews = sorted(preview_dir.glob("*.html"))
        if previews:
            print(f"\n  Preview written to: {previews[0]}")
            open_it = _prompt("Open in browser? (y/n)", "y")
            if open_it.lower() in ("y", "yes"):
                import webbrowser
                webbrowser.open(previews[0].as_uri())

    print(f"\n{'=' * 56}")
    print("  Setup complete!")
    print(f"{'=' * 56}")
    print(f"\nNext steps:")
    print(f"  - Preview any time:  python -m research_agent digest --topics {' '.join(chosen[:3])} --open")
    print(f"  - Interactive agent: python -m research_agent")
    print(f"  - Search papers:     python -m research_agent search \"your query\"")
    print(f"  - Detect Zotero:     python -m research_agent zotero")
    print(f"  - Full help:         python -m research_agent help\n")

    return 0
