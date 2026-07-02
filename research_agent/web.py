"""ResearchPulse Web UI - Interactive research agent interface.

A Flask-based web application that provides a chat-like interface
for the ResearchPulse agent with all Phase 1 and Phase 2 features.

Usage:
    python -m research_agent.web
    # Or: research-agent web
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from flask import Flask, jsonify, render_template, request

from . import __version__
from .chat import ask_about_paper, ask_research_question, explain_concept, is_llm_available, get_llm_backend
from .compare import compare_papers
from .config import ROOT, TEMPLATE_DIR, load_secrets, load_settings, load_topics, topics_by_id
from .critique import challenge_hypothesis
from .insights import generate_insights, format_insights
from .memory import ResearchMemory
from .models import Paper
from .recommend import get_recommendations, get_daily_briefing, format_recommendations
from .search import search_papers, search_by_topic
from .summarize import Summarizer

# Flask app
app = Flask(__name__, template_folder=str(TEMPLATE_DIR), static_folder=str(ROOT / "static"))

# Global state
memory = ResearchMemory()
last_papers: List[Paper] = []
conversation_history: List[Dict] = []


def _paper_to_dict(paper: Paper) -> Dict:
    """Convert Paper object to dictionary for JSON."""
    return {
        "id": paper.id,
        "title": paper.title,
        "abstract": paper.abstract[:500] + "..." if len(paper.abstract) > 500 else paper.abstract,
        "authors": paper.authors[:5],
        "url": paper.url,
        "source": paper.source,
        "published": paper.published.isoformat() if paper.published else None,
        "citations": paper.citations,
        "score": round(paper.score, 3) if paper.score else 0,
        "summary": paper.summary,
    }


def _format_papers_html(papers: List[Paper], title: str = "Results") -> str:
    """Format papers as HTML for display."""
    if not papers:
        return '<div class="no-results">No papers found.</div>'

    html = f'<div class="results-header"><h3>{title}</h3><span class="count">{len(papers)} papers</span></div>'
    html += '<div class="papers-list">'

    for i, paper in enumerate(papers, 1):
        authors = ", ".join(paper.authors[:3])
        if len(paper.authors) > 3:
            authors += " et al."

        score_badge = f'<span class="score-badge">{paper.score:.2f}</span>' if paper.score else ''
        citations = f'<span class="citations">{paper.citations} citations</span>' if paper.citations else ''

        abstract = paper.abstract[:300] + "..." if len(paper.abstract) > 300 else paper.abstract

        html += f'''
        <div class="paper-card" data-index="{i}">
            <div class="paper-header">
                <span class="paper-number">{i}</span>
                <span class="paper-source">{paper.source}</span>
                {score_badge}
            </div>
            <h4 class="paper-title"><a href="{paper.url}" target="_blank">{paper.title}</a></h4>
            <div class="paper-meta">
                <span class="authors">{authors}</span>
                {citations}
            </div>
            <p class="paper-abstract">{abstract}</p>
            <div class="paper-actions">
                <button onclick="summarizePaper({i})" class="btn-small">Summarize</button>
                <button onclick="ratePaper({i})" class="btn-small">Rate</button>
                <button onclick="askAboutPaper({i})" class="btn-small">Ask</button>
            </div>
        </div>'''

    html += '</div>'
    return html


# ── Routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Main page."""
    return render_template("agent.html", version=__version__)


@app.route("/api/search", methods=["POST"])
def api_search():
    """Search for papers."""
    global last_papers

    data = request.json or {}
    query = data.get("query", "").strip()

    if not query:
        return jsonify({"error": "No query provided"}), 400

    papers = search_papers(query, limit=10)
    last_papers = papers

    # Record in memory
    for p in papers[:3]:
        memory.record_paper(
            paper_id=p.id,
            title=p.title,
            url=p.url,
            source=p.source,
            tags=[query],
        )

    papers_data = [_paper_to_dict(p) for p in papers]
    html = _format_papers_html(papers, f"Search: {query}")

    return jsonify({
        "papers": papers_data,
        "html": html,
        "count": len(papers),
    })


@app.route("/api/topic", methods=["POST"])
def api_topic():
    """Search by topic."""
    global last_papers

    data = request.json or {}
    topic_id = data.get("topic", "").strip()

    if not topic_id:
        return jsonify({"error": "No topic provided"}), 400

    papers = search_by_topic(topic_id, days=7, limit=10)
    last_papers = papers

    papers_data = [_paper_to_dict(p) for p in papers]
    html = _format_papers_html(papers, f"Topic: {topic_id}")

    return jsonify({
        "papers": papers_data,
        "html": html,
        "count": len(papers),
    })


@app.route("/api/topics", methods=["GET"])
def api_topics():
    """List available topics."""
    topics, _ = load_topics()
    topics_data = [
        {
            "id": t.id,
            "label": t.label,
            "keywords": t.keywords[:5],
        }
        for t in topics
    ]
    return jsonify({"topics": topics_data})


@app.route("/api/summarize", methods=["POST"])
def api_summarize():
    """Summarize a paper."""
    global last_papers

    data = request.json or {}
    index = data.get("index", 0) - 1

    if not last_papers or index < 0 or index >= len(last_papers):
        return jsonify({"error": "Invalid paper index"}), 400

    paper = last_papers[index]

    # Use summarizer
    secrets = load_secrets()
    settings = load_settings()
    summarizer = Summarizer(secrets, settings.abstract_max_chars)
    summary = summarizer.summarize(paper)

    # Record in memory
    memory.record_paper(
        paper_id=paper.id,
        title=paper.title,
        url=paper.url,
        source=paper.source,
    )

    return jsonify({
        "title": paper.title,
        "summary": summary,
    })


@app.route("/api/rate", methods=["POST"])
def api_rate():
    """Rate a paper."""
    global last_papers

    data = request.json or {}
    index = data.get("index", 0) - 1
    rating = data.get("rating", 0)

    if not last_papers or index < 0 or index >= len(last_papers):
        return jsonify({"error": "Invalid paper index"}), 400

    if not (1 <= rating <= 5):
        return jsonify({"error": "Rating must be 1-5"}), 400

    paper = last_papers[index]
    memory.record_paper(
        paper_id=paper.id,
        title=paper.title,
        url=paper.url,
        source=paper.source,
        rating=rating,
    )

    return jsonify({
        "message": f"Rated '{paper.title}' {rating}/5 stars",
        "title": paper.title,
        "rating": rating,
    })


@app.route("/api/ask", methods=["POST"])
def api_ask():
    """Ask a question about research."""
    global last_papers, conversation_history

    data = request.json or {}
    question = data.get("question", "").strip()
    paper_index = data.get("paper_index")

    if not question:
        return jsonify({"error": "No question provided"}), 400

    if not is_llm_available():
        return jsonify({
            "error": "LLM not configured",
            "message": "Set GROQ_API_KEY, GEMINI_API_KEY, or OLLAMA_HOST in .env"
        }), 400

    # Ask about specific paper
    if paper_index and last_papers:
        idx = paper_index - 1
        if 0 <= idx < len(last_papers):
            paper = last_papers[idx]
            answer = ask_about_paper(paper, question)
            if answer:
                conversation_history.append({"role": "user", "content": question})
                conversation_history.append({"role": "assistant", "content": answer})
                memory.record_conversation(question, answer)
                return jsonify({
                    "answer": answer,
                    "paper": paper.title,
                })

    # General research question
    answer = ask_research_question(question, last_papers)
    if answer:
        conversation_history.append({"role": "user", "content": question})
        conversation_history.append({"role": "assistant", "content": answer})
        memory.record_conversation(question, answer)
        return jsonify({"answer": answer})

    return jsonify({"error": "Could not generate an answer"}), 500


@app.route("/api/explain", methods=["POST"])
def api_explain():
    """Explain a concept."""
    global last_papers

    data = request.json or {}
    concept = data.get("concept", "").strip()

    if not concept:
        return jsonify({"error": "No concept provided"}), 400

    if not is_llm_available():
        return jsonify({
            "error": "LLM not configured",
            "message": "Set GROQ_API_KEY, GEMINI_API_KEY, or OLLAMA_HOST in .env"
        }), 400

    explanation = explain_concept(concept, last_papers)
    if explanation:
        return jsonify({"explanation": explanation, "concept": concept})

    return jsonify({"error": "Could not generate an explanation"}), 500


@app.route("/api/compare", methods=["POST"])
def api_compare():
    """Compare papers."""
    global last_papers

    data = request.json or {}
    indices = data.get("indices", [])

    if len(indices) < 2:
        return jsonify({"error": "Need at least 2 papers to compare"}), 400

    selected = []
    for idx in indices:
        idx = idx - 1
        if 0 <= idx < len(last_papers):
            selected.append(last_papers[idx])

    if len(selected) < 2:
        return jsonify({"error": "Invalid paper indices"}), 400

    comparison = compare_papers(selected)

    return jsonify({
        "comparison": comparison,
        "papers": [p.title for p in selected],
    })


@app.route("/api/critique", methods=["POST"])
def api_critique():
    """Challenge a hypothesis."""
    global last_papers

    data = request.json or {}
    hypothesis = data.get("hypothesis", "").strip()

    if not hypothesis:
        return jsonify({"error": "No hypothesis provided"}), 400

    if not last_papers:
        return jsonify({"error": "No papers available. Search for papers first."}), 400

    critique = challenge_hypothesis(hypothesis, last_papers)

    return jsonify({
        "critique": critique,
        "hypothesis": hypothesis,
    })


@app.route("/api/insights", methods=["POST"])
def api_insights():
    """Generate insights from papers."""
    global last_papers

    if not last_papers:
        return jsonify({"error": "No papers available. Search for papers first."}), 400

    insights = generate_insights(last_papers, memory)
    formatted = format_insights(insights)

    return jsonify({
        "insights": formatted,
        "contradictions": len(insights.get("contradictions", [])),
        "gaps": len(insights.get("gaps", [])),
        "trends": len(insights.get("trends", [])),
    })


@app.route("/api/recommend", methods=["POST"])
def api_recommend():
    """Get personalized recommendations."""
    global last_papers

    if not last_papers:
        return jsonify({"error": "No papers available. Search for papers first."}), 400

    recommendations = get_recommendations(last_papers, memory)
    formatted = format_recommendations(recommendations)

    return jsonify({
        "recommendations": formatted,
        "count": len(recommendations),
    })


@app.route("/api/briefing", methods=["POST"])
def api_briefing():
    """Generate daily briefing."""
    global last_papers

    if not last_papers:
        return jsonify({"error": "No papers available. Search for papers first."}), 400

    briefing = get_daily_briefing(last_papers, memory)

    return jsonify({"briefing": briefing})


@app.route("/api/memory", methods=["GET"])
def api_memory():
    """Get memory summary."""
    return jsonify({
        "summary": memory.summary(),
        "profile": memory.profile,
        "interests": memory.interests,
        "papers_count": len(memory.papers),
        "insights_count": len(memory.insights),
        "conversations_count": len(memory.conversations),
    })


@app.route("/api/memory/set", methods=["POST"])
def api_memory_set():
    """Set profile information."""
    data = request.json or {}
    key = data.get("key", "")
    value = data.get("value", "")

    if key in ("name", "field", "role"):
        memory.set_profile(**{key: value})
        return jsonify({"message": f"Set {key} = {value}"})
    elif key == "goal":
        goals = memory.profile.get("goals", [])
        goals.append(value)
        memory.set_profile(goals=goals)
        return jsonify({"message": f"Added goal: {value}"})

    return jsonify({"error": f"Unknown key: {key}"}), 400


@app.route("/api/memory/add", methods=["POST"])
def api_memory_add():
    """Add interest."""
    data = request.json or {}
    interest_type = data.get("type", "")
    value = data.get("value", "")

    if interest_type and value:
        memory.add_interest(interest_type, value)
        return jsonify({"message": f"Added {interest_type}: {value}"})

    return jsonify({"error": "Missing type or value"}), 400


@app.route("/api/memory/question", methods=["POST"])
def api_memory_question():
    """Add research question."""
    data = request.json or {}
    question = data.get("question", "")

    if question:
        memory.add_interest("question", question)
        return jsonify({"message": f"Added question: {question}"})

    return jsonify({"error": "Missing question"}), 400


@app.route("/api/memory/papers", methods=["GET"])
def api_memory_papers():
    """Get recent papers from memory."""
    papers = memory.get_recent_papers(days=30)
    papers_data = [
        {
            "title": p.title,
            "url": p.url,
            "rating": p.rating,
            "read_date": p.read_date,
            "notes": p.notes,
        }
        for p in papers
    ]
    return jsonify({"papers": papers_data, "count": len(papers_data)})


@app.route("/api/status", methods=["GET"])
def api_status():
    """Get agent status."""
    return jsonify({
        "version": __version__,
        "llm_available": is_llm_available(),
        "llm_backend": get_llm_backend(),
        "papers_count": len(last_papers),
        "memory": {
            "papers": len(memory.papers),
            "insights": len(memory.insights),
            "conversations": len(memory.conversations),
        },
    })


# ── Main ────────────────────────────────────────────────────────────────

def run_web(host: str = "127.0.0.1", port: int = 5000, debug: bool = False) -> int:
    """Run the web server."""
    print(f"\nResearchPulse Agent v{__version__}")
    print(f"Starting web server at http://{host}:{port}")
    print(f"Open your browser and navigate to the URL above")
    print(f"Press Ctrl+C to stop\n")

    app.run(host=host, port=port, debug=debug)
    return 0


def main() -> int:
    """Main entry point for web server."""
    import argparse

    parser = argparse.ArgumentParser(description="ResearchPulse Web UI")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind to")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()
    return run_web(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    sys.exit(main())
