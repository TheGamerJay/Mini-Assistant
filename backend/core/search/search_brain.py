"""
search/search_brain.py — Search Brain: query rewriting + variant generation.

CEO routes here FIRST when truth_type is search_dependent or mixed.
Search Brain rewrites the query to maximize retrieval quality.

Output:
  {
      "original_query": str,
      "rewritten_query": str,
      "query_variants": [str, ...],   # 2-3 alternative phrasings
      "search_intent":  str,           # what we're actually looking for
      "freshness":      "any" | "recent" | "very_recent",
  }

Rules:
  - no web requests here — this is query planning only
  - CEO decides whether to execute the search
  - variants used if primary query fails
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

log = logging.getLogger("ceo_router.search_brain")

_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"  # fast model for query work


async def plan_search(query: str, context: str = "") -> dict[str, Any]:
    """
    Rewrite and expand a search query for better retrieval.

    Args:
        query:   raw user query
        context: optional conversation context for disambiguation

    Returns:
        {
            original_query, rewritten_query, query_variants,
            search_intent, freshness, ok
        }
    """
    # Fast local rewriting first (no LLM cost for simple cases)
    local = _local_rewrite(query)
    if local["confidence"] >= 0.8:
        log.debug("search_brain: local rewrite sufficient query=%r", query[:60])
        return {**local, "ok": True, "source": "local"}

    # LLM-based rewriting for complex queries
    llm_result = await _llm_rewrite(query, context)
    if llm_result:
        return {**llm_result, "ok": True, "source": "llm"}

    # Fallback to local
    return {**local, "ok": True, "source": "fallback"}


def _local_rewrite(query: str) -> dict[str, Any]:
    """
    Local rule-based query rewriting.
    Handles common patterns without an LLM call.
    """
    q = query.strip()
    intent = _detect_intent(q)
    freshness = _detect_freshness(q)

    # Remove filler words that hurt search
    cleaned = _strip_conversational(q)

    # Build simple variants
    variants = _build_variants(cleaned, intent)

    confidence = 0.7 if len(cleaned) > 10 else 0.4

    return {
        "original_query":  q,
        "rewritten_query": cleaned,
        "query_variants":  variants[:3],
        "search_intent":   intent,
        "freshness":       freshness,
        "confidence":      confidence,
    }


async def _llm_rewrite(query: str, context: str) -> dict[str, Any] | None:
    """Use a fast LLM to produce better query rewrites."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    system = """You are a search query optimizer. Given a user question, output ONLY valid JSON (no markdown):
{
  "rewritten_query": "<cleaned, optimized search query>",
  "query_variants": ["<variant 1>", "<variant 2>"],
  "search_intent": "<one phrase: what the user actually wants to find>",
  "freshness": "any | recent | very_recent"
}
Rules:
- rewritten_query: remove filler words, make it searchable
- query_variants: 2 alternative phrasings (different angle, not synonyms)
- search_intent: what the user actually needs (not just a rephrasing)
- freshness: very_recent if "today/now/latest", recent if "this week/month", else any"""

    user = f"Query: {query}"
    if context:
        user += f"\nContext: {context[:200]}"

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model=_ANTHROPIC_MODEL,
            max_tokens=300,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        raw = resp.content[0].text if resp.content else ""
        import json
        data = json.loads(raw.strip())
        data["original_query"] = query
        data.setdefault("query_variants", [])
        data.setdefault("freshness", "any")
        data.setdefault("confidence", 0.9)
        return data
    except Exception as exc:
        log.debug("search_brain: LLM rewrite failed — %s", exc)
        return None


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------

_FILLER = re.compile(
    r"\b(please|can you|could you|tell me|i want to know|i need|help me|"
    r"what is the|what are the|is there a|do you know|i'm looking for)\b",
    re.IGNORECASE,
)

_FRESHNESS_RECENT  = re.compile(r"\b(latest|newest|recent|current|updated|2024|2025|2026)\b", re.IGNORECASE)
_FRESHNESS_NOW     = re.compile(r"\b(today|right now|this week|this month|just|breaking)\b", re.IGNORECASE)


def _strip_conversational(q: str) -> str:
    cleaned = _FILLER.sub("", q).strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned if len(cleaned) > 5 else q


def _detect_intent(q: str) -> str:
    q_low = q.lower()
    if re.search(r"\b(how to|tutorial|guide|steps|example)\b", q_low):
        return "how_to"
    if re.search(r"\b(what is|what are|define|explain|meaning)\b", q_low):
        return "definition"
    if re.search(r"\b(latest|version|changelog|release|update)\b", q_low):
        return "versioning"
    if re.search(r"\b(news|happened|today|breaking|announcement)\b", q_low):
        return "news"
    if re.search(r"\b(best|top|compare|vs|versus|difference)\b", q_low):
        return "comparison"
    return "general"


def _detect_freshness(q: str) -> str:
    if _FRESHNESS_NOW.search(q):
        return "very_recent"
    if _FRESHNESS_RECENT.search(q):
        return "recent"
    return "any"


def _build_variants(q: str, intent: str) -> list[str]:
    variants = []
    # Add site-specific variant for versioning/docs
    if intent == "versioning":
        variants.append(f"{q} site:github.com OR site:npmjs.com OR site:pypi.org")
    # Add "official" variant for definitions
    if intent == "definition":
        variants.append(f"{q} official documentation")
    # Generic date-restricted variant for news
    if intent == "news":
        variants.append(f"{q} 2026")
    # Always add a plain condensed form
    words = q.split()
    if len(words) > 4:
        variants.append(" ".join(words[:5]))
    return variants
