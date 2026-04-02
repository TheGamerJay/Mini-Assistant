"""
web/web_search.py — Web search wrapper for the CEO pipeline.

Uses Claude's built-in web_search tool (Anthropic beta) when available.
Falls back to a no-op stub with a clear error so callers know search failed.

Rules:
- only called when web_decider returns requires_web=True and web_mode="search"
- results are injected into module context — modules do not call this directly
- max 5 results per call (CPU-friendly)
- never call unless CEO explicitly routed here
"""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger("ceo_router.web_search")

_MAX_RESULTS = 5


async def run_search(query: str) -> dict[str, Any]:
    """
    Run a web search for the given query.

    Returns:
        {
            "ok": bool,
            "results": [ {"title": str, "url": str, "snippet": str}, ... ],
            "error": str | None,
        }
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        log.warning("web_search: ANTHROPIC_API_KEY not set — search unavailable")
        return {"ok": False, "results": [], "error": "API key not configured"}

    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": _MAX_RESULTS}],
            extra_headers={"anthropic-beta": "web-search-2025-03-05"},
            messages=[{"role": "user", "content": query}],
        )

        results = []
        for block in resp.content:
            if hasattr(block, "type") and block.type == "tool_result":
                for item in getattr(block, "content", []):
                    if isinstance(item, dict):
                        results.append({
                            "title":   item.get("title", ""),
                            "url":     item.get("url", ""),
                            "snippet": item.get("snippet", ""),
                        })

        log.info("web_search: query=%r results=%d", query[:80], len(results))
        return {"ok": True, "results": results[:_MAX_RESULTS], "error": None}

    except Exception as exc:
        log.error("web_search failed: %s", exc)
        return {"ok": False, "results": [], "error": str(exc)}
