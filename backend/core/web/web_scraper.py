"""
web/web_scraper.py — Fetch and extract structured content from a specific URL.

Only called when web_decider returns web_mode="scraper".
Strips scripts, styles, navigation clutter — outputs clean structured content.

Rules:
- one URL per call
- 10 second timeout
- no JavaScript rendering (plain HTTP only)
- do not call unless CEO explicitly routed here
- output is summarized before being passed to generation (no raw HTML forward)

Output format:
    {
        "ok":         bool,
        "url":        str,
        "title":      str,
        "summary":    str,
        "key_points": list[str],
        "text":       str,       # full cleaned text (capped)
        "error":      str | None,
    }
"""

from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger("ceo_router.web_scraper")

_TIMEOUT_S  = 10
_MAX_CHARS  = 8000   # total text cap
_SUMMARY_CHARS = 500  # summary cap


async def scrape_url(url: str) -> dict[str, Any]:
    """
    Fetch a URL and return structured extracted content.

    Returns a structured dict — never returns raw HTML.
    """
    try:
        import httpx
    except ImportError:
        return _fail(url, "httpx not installed")

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "Mini-Assistant-Scraper/1.0"},
            )
            resp.raise_for_status()
            html = resp.text

        title     = _extract_title(html)
        text      = _extract_text(html)[:_MAX_CHARS]
        summary   = _make_summary(text)
        key_points = _extract_key_points(text)

        log.info("web_scraper: url=%s chars=%d title=%r", url[:80], len(text), title[:60])
        return {
            "ok":         True,
            "url":        url,
            "title":      title,
            "summary":    summary,
            "key_points": key_points,
            "text":       text,
            "error":      None,
        }

    except Exception as exc:
        log.warning("web_scraper failed: url=%s error=%s", url[:80], exc)
        return _fail(url, str(exc))


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def _extract_title(html: str) -> str:
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Try h1
    h1 = re.search(r"<h1[^>]*>([^<]+)</h1>", html, re.IGNORECASE)
    if h1:
        return h1.group(1).strip()
    return ""


def _extract_text(html: str) -> str:
    """Strip noise elements and collapse whitespace."""
    # Remove noise blocks
    html = re.sub(
        r"<(script|style|nav|footer|header|aside|form|noscript)[^>]*>.*?</\1>",
        " ", html, flags=re.IGNORECASE | re.DOTALL,
    )
    # Strip remaining tags
    html = re.sub(r"<[^>]+>", " ", html)
    # Decode common HTML entities
    for ent, char in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                      ("&nbsp;", " "), ("&quot;", '"'), ("&#39;", "'")]:
        html = html.replace(ent, char)
    return re.sub(r"\s+", " ", html).strip()


def _make_summary(text: str) -> str:
    """Return the first meaningful paragraph as a summary."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    summary = ""
    for s in sentences:
        if len(s) > 30:  # skip very short fragments
            summary += s + " "
        if len(summary) >= _SUMMARY_CHARS:
            break
    return summary.strip()[:_SUMMARY_CHARS]


def _extract_key_points(text: str, max_points: int = 5) -> list[str]:
    """
    Extract up to max_points key points from the text.
    Looks for list-like sentences or distinct paragraph starters.
    """
    # Split on sentence boundaries
    sentences = re.split(r"(?<=[.!?])\s+", text)
    # Filter for substantive sentences (length heuristic)
    candidates = [s.strip() for s in sentences if 40 < len(s.strip()) < 300]
    # Deduplicate preserving order
    seen: set[str] = set()
    points: list[str] = []
    for c in candidates:
        key = c[:60].lower()
        if key not in seen:
            seen.add(key)
            points.append(c)
        if len(points) >= max_points:
            break
    return points


def _fail(url: str, error: str) -> dict[str, Any]:
    return {
        "ok":         False,
        "url":        url,
        "title":      "",
        "summary":    "",
        "key_points": [],
        "text":       "",
        "error":      error,
    }
