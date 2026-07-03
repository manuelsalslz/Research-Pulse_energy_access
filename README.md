# ResearchPulse

**Your daily pulse on research.** A free, open-source agent that fetches new papers in your fields and opens them in your browser.

## Install

```bash
pip install research-pulse
```

Or with pipx (Mac/Linux):

```bash
pipx install research-pulse
```

## Usage

```bash
research-pulse                          # Today's papers
research-pulse search "query"           # Search papers
research-pulse search "attention" --venue neurips,icml --core A --year 2024
research-pulse conferences              # List CORE-ranked venues
research-pulse conferences --core "A*"  # Top-tier only
research-pulse topics                   # View/change topics
research-pulse topics ai-ml nlp cv      # Set topics directly
research-pulse add-topic --id my-field --label "My Field" --keywords "kw1,kw2"
research-pulse chat                     # Interactive agent
research-pulse help                     # All commands
```

## What it does

- Fetches papers from **arXiv, OpenAlex, Europe PMC, bioRxiv, Crossref, Semantic Scholar**
- **Auto-detects topics** from your Zotero library (if installed)
- Opens a clean HTML digest in your browser
- Tracks your reading history and ratings
- 31 built-in research domains (AI, NLP, medicine, physics, etc.)
- Follow any field: `research-pulse follow "quantum computing"`
- **Conference metadata**: venue name, year, and CORE rank (A*, A, B, C) on each paper
- **Filter by conference**: `--venue neurips`, `--core A`, `--year 2024` on search

## Conference filtering

Each paper shows **venue**, **year**, and **CORE rank** when available (from OpenAlex, Crossref, or arXiv comments).

```bash
research-pulse conferences                    # all ranked venues in catalog
research-pulse search "diffusion models" --venue neurips,icml
research-pulse search "LLM reasoning" --core A --year 2024
```

CORE ranks come from a bundled offline catalog (`config/core_venues.yaml`). Edit or extend it for your field — no CORE API key needed.

## Zotero Integration

If you have [Zotero](https://www.zotero.org/) installed, topics are auto-detected from your library on first run.

```bash
research-pulse zotero    # See detected topics
```

## Interactive Agent

```bash
research-pulse chat
```

Inside the agent:
- `search <query>` — search papers
- `summarize <n>` — summarize paper
- `compare <n1> <n2>` — compare papers
- `rate <n> <1-5>` — rate a paper
- `ask <question>` — ask AI about papers
- `insights` — get research insights
- `memory` — view reading history

## Add Custom Topics

```bash
research-pulse add-topic --id data-science --label "Data Science" --keywords "data,analytics,visualization" --arxiv "stat.ML,cs.DB"
```

## License

MIT — see [LICENSE](LICENSE).
