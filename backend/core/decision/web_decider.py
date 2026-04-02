"""
decision/web_decider.py — Decide whether web tools are needed and which mode.

Priority order:
  1. user input (explicit ask)
  2. TR memory (if available and sufficient)
  3. web only if still needed

Web modes:
  search  — standard web search (Claude built-in tool or SerpAPI)
  scraper — fetch and extract a specific URL
  crawler — follow links from a seed URL (limited, CPU-aware)

Rules:
- no unnecessary web calls
- no uncontrolled scraping
- crawler is restricted — use only when search + scraper are insufficient
- must remain CPU-friendly — no infinite crawl loops
"""

from __future__ import annotations

import re
from typing import Optional

# Explicit web request signals
_EXPLICIT_WEB = re.compile(
    r"\b(search (for|the web|online)|look it up|look up|find online|"
    r"check online|check the web|google|bing|search results|"
    r"latest|current|right now|today|live|breaking news|recent news|"
    r"stock price|weather (in|for)|sports score|what happened|"
    r"what('s| is) (happening|new|out)|upcoming|release date|"
    r"who won|who is leading|current standings)\b",
    re.IGNORECASE,
)

# Scrape-specific signals
_SCRAPE_REQUEST = re.compile(
    r"\b(scrape|extract from|pull from|get data from|read (this |the )?(url|link|page|website)|"
    r"fetch (this |the )?(url|link|page)|what does (this |the )?(page|site|url) say)\b",
    re.IGNORECASE,
)

# Crawler signals (rare, restrictive)
_CRAWL_REQUEST = re.compile(
    r"\b(crawl|spider|index|scan (the |this )?(site|domain|website)|"
    r"all pages (on|from|of)|map (the |this )?(site|website))\b",
    re.IGNORECASE,
)


def decide_web(
    message: str,
    intent: str,
    memory_available: bool,
) -> tuple[bool, Optional[str]]:
    """
    Returns:
        (requires_web, web_mode | None)

    web_mode: "search" | "scraper" | "crawler" | None
    """
    # web_intelligence always uses web
    if intent == "web_lookup":
        mode = _pick_mode(message)
        return True, mode

    # Explicit web request overrides memory
    if _EXPLICIT_WEB.search(message):
        mode = _pick_mode(message)
        return True, mode

    # All other intents: no web by default
    return False, None


def _pick_mode(message: str) -> str:
    if _CRAWL_REQUEST.search(message):
        return "crawler"
    if _SCRAPE_REQUEST.search(message):
        return "scraper"
    return "search"
