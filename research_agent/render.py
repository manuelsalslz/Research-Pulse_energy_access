"""Render a personalized HTML digest for a subscriber."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlencode

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import TEMPLATE_DIR, Secrets, Settings
from .models import NewsItem, Paper
from .subscribers import Subscriber

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml", "j2"]),
)


def _unsubscribe_url(secrets: Secrets, sub: Subscriber) -> Optional[str]:
    if not secrets.site_url or not sub.token:
        return None
    return f"{secrets.site_url}?" + urlencode(
        {"action": "unsubscribe", "token": sub.token}
    )


def render_digest(
    sub: Subscriber,
    papers_by_topic: Dict[str, List[Paper]],
    topic_labels: Dict[str, str],
    news: List[NewsItem],
    settings: Settings,
    secrets: Secrets,
) -> str:
    """Build the HTML for one subscriber, including only their chosen topics."""
    sections = []
    for topic_id in sub.topics:
        papers = papers_by_topic.get(topic_id, [])
        if not papers:
            continue
        sections.append({"label": topic_labels.get(topic_id, topic_id), "papers": papers})

    template = _env.get_template("email.html.j2")
    return template.render(
        newsletter_name=settings.newsletter_name,
        tagline=settings.newsletter_tagline,
        date=datetime.now().strftime("%A, %B %d, %Y"),
        topic_sections=sections,
        news=news,
        unsubscribe_url=_unsubscribe_url(secrets, sub),
        site_url=secrets.site_url,
    )
