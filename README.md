# ResearchPulse

**Your daily pulse on research.** A free, open-source agent that emails researchers a
simple morning digest of new papers in their fields, plus what's happening across the
research community.

Works in two modes:
1. **Newsletter** -- People subscribe via email. Every morning a GitHub Actions cron
   sends each subscriber a personalized digest.
2. **Local agent** -- Run on your own machine to search papers, get previews, compare
   papers, track reading history, and generate insights. No account needed.

Runs on 100% free infrastructure. No servers, no database, no paid services required.

## Install from PyPI (recommended)

```bash
pip install research-pulse
research-pulse help
```

That's it — no clone, no setup wizard, no API keys. Data and preferences are stored in
`~/.research-pulse/` (override with `RESEARCHPULSE_HOME`).

Optional extras:

```bash
pip install "research-pulse[web]"   # browser UI (Flask)
```

## Quick start (from source)

```powershell
git clone https://github.com/research-pulse/research-pulse.git
cd research-pulse
pip install -e .

# Run every morning:
research-pulse
```

### Daily commands

| What you want | Command |
|---------------|---------|
| Today's papers | `research-pulse` |
| Search | `research-pulse search "transformer efficiency"` |
| Follow ANY field (plain English) | `research-pulse follow "quantum error correction"` |
| Change topics | `research-pulse topics` |
| Set topics directly | `research-pulse topics ai-ml nlp cv` |
| Set papers per topic | `research-pulse config papers 10` |
| Help | `research-pulse help` |

### Works for every research domain

ResearchPulse ships with **31 built-in domains** spanning computer science, the
life sciences, physics, chemistry, math, engineering, economics, and the social
sciences. Not listed? Just follow it in plain English — no config editing, no
API keys:

```powershell
research-pulse follow "protein folding"
research-pulse follow "behavioral economics"
research-pulse follow "cultural heritage preservation"
```

`follow` creates the topic on the fly, wires it to the keyless open-access
sources (OpenAlex, Europe PMC, Semantic Scholar, arXiv, Crossref), saves it to
your daily digest, and immediately shows recent papers.

Optional: `research-pulse chat` opens the full interactive agent (compare, insights, memory).

## Zotero integration

If you have [Zotero](https://www.zotero.org/) installed, ResearchPulse can auto-detect
your research domains from your existing library:

```bash
python -m research_agent zotero
```

This reads your local `zotero.sqlite` database (read-only, never modifies it), analyzes
your collections, tags, and recent titles, and suggests which ResearchPulse topics
match your interests. It also gives you a ready-to-paste command:

```
  Suggested ResearchPulse topics based on your library:

    ai-ml        Artificial Intelligence & Machine Learning  [####################] 100%
    nlp          Natural Language Processing                 [#######             ] 36%
    security     Security & Cryptography                    [#                   ] 8%

  Quick start with your domains:
    python -m research_agent digest --topics ai-ml nlp --open
```

Zotero detection works on Windows, macOS, and Linux. If Zotero is in a custom location,
set `ZOTERO_DATA_DIR=/path/to/your/zotero/data`.

## CLI reference

```
python -m research_agent                  # Interactive agent (REPL)
python -m research_agent setup            # First-time setup wizard
python -m research_agent search "query"   # One-shot paper search
python -m research_agent follow "field"   # Follow any research area (plain English)
python -m research_agent topics           # List available topics
python -m research_agent memory           # View research memory
python -m research_agent zotero           # Detect Zotero domains
python -m research_agent digest           # Run daily digest pipeline
python -m research_agent digest --dry-run # Preview without sending
python -m research_agent digest --topics ai-ml nlp --open  # Local preview
python -m research_agent web              # Start web UI (requires flask)
python -m research_agent help             # Full help with all commands
```

### Interactive agent commands

```
SEARCH:      search <query> | search --all <query> | topic <id> | topics
PAPERS:      summarize <n> | rate <n> <1-5> | compare <n1> <n2> | features <n>
AI:          ask <question> | ask <n> <question> | explain <concept>
INSIGHTS:    insights | recommend | briefing | critique <hypothesis>
MEMORY:      memory | memory set name/field/role <value> | memory papers
```

## Newsletter setup (run the public instance)

> Estimated time: ~15 minutes. Everything below is free.

### 1. Fork this repository

Click **Fork**. The daily workflow comes with it.

### 2. Create a free email sender (Brevo)

1. Sign up at [brevo.com](https://www.brevo.com) (free plan: **300 emails/day**, no card).
2. Go to **SMTP & API > SMTP** and note your **login** and **SMTP key**.
3. Verify a sender address under **Senders**.

### 3. Set up the subscriber database (Google Sheet + Apps Script)

1. Create a Google Sheet with this header row:
   `email | topics | confirmed | token | created`
2. Open **Extensions > Apps Script**, paste [apps_script/Code.gs](apps_script/Code.gs),
   and set `SHEET_ID` to your sheet's id (from its URL).
3. **Deploy > New deployment > Web app**: execute as *Me*, access *Anyone*. Copy the
   **web app URL**.
4. **File > Share > Publish to web > CSV** for the sheet. Copy that **CSV URL**.

### 4. Publish the signup page (GitHub Pages)

1. Edit [docs/index.html](docs/index.html): set `APPS_SCRIPT_URL` to your web app URL.
2. In your repo: **Settings > Pages > Source: `main` / `docs`**.

### 5. Add repository secrets

**Settings > Secrets and variables > Actions > New repository secret:**

| Secret | Value |
| --- | --- |
| `SUBSCRIBERS_CSV_URL` | Published CSV URL from step 3.4 |
| `SMTP_HOST` | `smtp-relay.brevo.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | Brevo SMTP login |
| `SMTP_KEY` | Brevo SMTP key |
| `SENDER_EMAIL` | Your verified sender address |
| `SENDER_NAME` | e.g. `ResearchPulse` |
| `SITE_URL` | Your **Apps Script web app URL** (handles unsubscribe links) |
| `GROQ_API_KEY` *(optional)* | Free [Groq](https://console.groq.com) key for LLM summaries |
| `GEMINI_API_KEY` *(optional)* | Free [Gemini](https://aistudio.google.com) key (alternative) |

### 6. Done

The workflow runs every morning at 11:00 UTC. Trigger it manually from the
**Actions** tab (with an optional **dry run**).

## Features

- **Free, open-access sources:** arXiv, OpenAlex (250M+ works, all fields),
  Europe PMC (40M+ life-science papers), Crossref, bioRxiv/medRxiv, optional
  Semantic Scholar, and curated research-news RSS. All keyless and free; sources
  are queried in parallel and one failing never blocks the digest.
- **Every research domain:** 31 built-in topics from AI to agriculture, plus
  `follow "<anything>"` to track fields that aren't listed — no config or keys.
- **Personalized:** each subscriber only gets the topics they chose.
- **Plain-language summaries:** uses the paper abstract by default (zero cost), or an
  LLM TL;DR if you provide a free API key (Groq / Gemini) or run a local model (Ollama).
- **Interactive agent:** search, compare, summarize, critique papers, and get personalized
  insights from the command line. Tracks your reading history.
- **Zotero detection:** auto-detects your research domains from your local Zotero library.
- **Research memory:** remembers papers you read, your ratings, and research questions.
- **BM25 ranking:** papers ranked by relevance using BM25 + keyword + citation scoring.
- **Cross-source dedup:** same paper from arXiv and OpenAlex is shown only once.
- **No duplicates across days:** a committed `data/seen.json` cache prevents repeats.

## Customizing

- **Add a research domain:** the easiest way is `research-pulse follow "<field>"`,
  which appends a ready-to-use entry to [config/topics.yaml](config/topics.yaml)
  automatically. For the hosted newsletter, also add the matching `{ id, label }`
  to [docs/index.html](docs/index.html) so it appears on the signup page.
- **Tune behavior:** [config/settings.yaml](config/settings.yaml) controls papers per
  topic, news items, lookback window, abstract length, and branding.
- **Summaries:** provide one of `GROQ_API_KEY` / `GEMINI_API_KEY` / `OLLAMA_HOST` to
  enable LLM TL;DRs; otherwise abstracts are used.

## Project layout

```
research_agent/
  sources/        arxiv.py, biorxiv.py, openalex.py, crossref.py,
                  semanticscholar.py, europepmc.py, rss.py, http.py
  models.py       Paper / NewsItem data structures
  config.py       YAML + env/.env loading
  log.py          Centralized logging (replaces print())
  subscribers.py  Read confirmed subscribers (published CSV or sample)
  cache.py        data/seen.json dedup state
  rank.py         Relevance ranking + per-topic selection
  bm25.py         BM25 scoring for search
  summarize.py    Abstract default + Groq/Gemini/Ollama backends
  render.py       Jinja2 HTML rendering per subscriber
  mailer.py       SMTP delivery
  pipeline.py     End-to-end digest orchestration
  agent.py        Interactive CLI agent with search/compare/insights
  search.py       On-demand keyword search across all sources
  memory.py       Persistent researcher memory (data/memory.json)
  chat.py         LLM conversation for ask/explain commands
  compare.py      Side-by-side paper comparison
  critique.py     Hypothesis challenging with evidence
  insights.py     Contradiction/gap/trend detection
  recommend.py    Personalized paper recommendations
  features.py     Feature extraction from papers
  setup.py        First-time setup wizard
  zotero.py       Zotero library detection + domain inference
  web.py          Flask web UI
  __main__.py     CLI router
config/           topics.yaml, settings.yaml, subscribers.sample.csv
templates/        email.html.j2
docs/             index.html (GitHub Pages signup)
apps_script/      Code.gs (subscription backend)
.github/workflows/daily.yml
data/             seen.json (dedup), memory.json (reading history)
```

## Limits & scaling (all still free)

- **Brevo free = 300 emails/day**, i.e. ~300 confirmed subscribers on one instance.
- **arXiv** has no hard rate limit but asks for responsible use; we wait 3s between calls
  and poll once daily.
- **OpenAlex / Europe PMC / bioRxiv / Crossref** are free and keyless with generous
  limits, comfortably serving the whole research community from one instance.
- **Semantic Scholar** is optional: its keyless pool is heavily rate-limited, so the
  source only activates when you set a free `S2_API_KEY`. Everything else works
  without it.

## License

MIT -- see [LICENSE](LICENSE). Contributions welcome.
