"""Centralized logging for ResearchPulse.

All modules import `log` from here instead of using bare print() calls.
The log level defaults to INFO; set env RESEARCHPULSE_LOG=DEBUG for verbose.
"""

from __future__ import annotations

import logging
import os
import sys

LOG_LEVEL = os.environ.get("RESEARCHPULSE_LOG", "INFO").upper()

_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))

logger = logging.getLogger("research_agent")
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
logger.propagate = False
if not logger.handlers:
    logger.addHandler(_handler)


def get(name: str) -> logging.Logger:
    """Get a child logger, e.g. `log.get('pipeline')` -> 'research_agent.pipeline'."""
    child = logger.getChild(name)
    child.propagate = True
    return child
