"""
search.py – Web Search Tool
────────────────────────────
Supports DuckDuckGo (default, no key required), Tavily, and Brave Search.
Returns a list of {"title", "url", "body"} dicts.
"""

import logging
import os
from typing import Optional

from ..config import SEARCH_ENGINE, TAVILY_API_KEY, BRAVE_API_KEY

logger = logging.getLogger(__name__)


# ─── DuckDuckGo ───────────────────────────────────────────────────────────────

def _ddg_search(query: str, max_results: int) -> list[dict]:
    from ddgs import DDGS
    results = []
    with DDGS(timeout=10) as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append({
                "title": r.get("title", ""),
                "url":   r.get("href",  ""),
                "body":  r.get("body",  ""),
            })
    return results


# ─── Tavily ───────────────────────────────────────────────────────────────────

def _tavily_search(query: str, max_results: int) -> list[dict]:
    import requests
    resp = requests.post(
        "https://api.tavily.com/search",
        json={"api_key": TAVILY_API_KEY, "query": query, "max_results": max_results},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return [
        {"title": r.get("title",""), "url": r.get("url",""), "body": r.get("content","")}
        for r in data.get("results", [])
    ]


# ─── Brave ────────────────────────────────────────────────────────────────────

def _brave_search(query: str, max_results: int) -> list[dict]:
    import requests
    resp = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        headers={"Accept": "application/json", "X-Subscription-Token": BRAVE_API_KEY},
        params={"q": query, "count": max_results},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return [
        {
            "title": r.get("title", ""),
            "url":   r.get("url",   ""),
            "body":  r.get("description", ""),
        }
        for r in data.get("web", {}).get("results", [])
    ]


# ─── Public function ──────────────────────────────────────────────────────────

def web_search(query: str, max_results: int = 5, engine: Optional[str] = None) -> list[dict]:
    """
    Search the web and return a list of result dicts.

    Args:
        query:       Search query string.
        max_results: Number of results to return.
        engine:      Override the default engine ("duckduckgo" | "tavily" | "brave").

    Returns:
        List of {"title", "url", "body"} dicts.
    """
    eng = (engine or SEARCH_ENGINE).lower()
    logger.info("Web search: engine=%s query=%r", eng, query)

    try:
        if eng == "tavily" and TAVILY_API_KEY:
            return _tavily_search(query, max_results)
        elif eng == "brave" and BRAVE_API_KEY:
            return _brave_search(query, max_results)
        else:
            return _ddg_search(query, max_results)
    except Exception as exc:
        logger.warning("Search engine %s failed (%s); trying DuckDuckGo.", eng, exc)
        try:
            return _ddg_search(query, max_results)
        except Exception as fallback_exc:
            logger.error("All search engines failed: %s", fallback_exc)
            return []
