"""
search/search_pipeline.py — Full search pipeline for grounded answers.

FLOW:
  User → CEO → search_brain (query rewriting)
           → web retrieval (existing web_tools)
           → content extraction + cleaning
           → source ranking (trust + relevance + freshness)
           → context builder (structured context)
           → grounded answer (LLM with context, no hallucination)
           → CEO → User

RULES:
  - no fake search — if search fails, say so
  - no raw HTML passed to LLM
  - no vector DB
  - all grounded answers must cite sources
  - CEO is the only caller of this pipeline

OUTPUT:
  {
      "ok":          bool,
      "answer":      str,     # grounded answer with citations
      "sources":     [...],   # sources used
      "search_plan": {...},   # from search_brain
      "retrieval":   {...},   # raw results from web
      "context_used": str,    # what was passed to LLM
      "grounded":    bool,    # was the answer grounded in retrieved content?
      "search_failed": bool,
      "fail_reason":  str,
  }
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

log = logging.getLogger("ceo_router.search_pipeline")

_ANTHROPIC_MODEL = "claude-sonnet-4-6"


async def run(
    query:      str,
    session_id: Optional[str] = None,
    context:    str = "",
    max_results: int = 5,
) -> dict[str, Any]:
    """
    Full search pipeline. CEO calls this for search_dependent queries.

    Returns a structured grounded answer or a failure response.
    Never hallucates — if search fails, returns search_failed=True.
    """
    log.info("search_pipeline: query=%r session=%s", query[:80], session_id)

    # Step 1: Query rewriting
    from .search_brain import plan_search
    search_plan = await plan_search(query, context)
    log.debug("search_pipeline: plan=%s", search_plan.get("search_intent"))

    # Step 2: Web retrieval
    retrieval = await _retrieve(search_plan, max_results)

    if retrieval["fail"]:
        return _fail_response(
            search_plan=search_plan,
            reason=retrieval["fail_reason"],
        )

    # Step 3: Source ranking
    ranked_sources = _rank_sources(retrieval["results"], query)

    if not ranked_sources:
        return _fail_response(
            search_plan=search_plan,
            reason="All retrieved sources were rejected by quality/trust filters.",
        )

    # Step 4: Context building
    context_block = _build_context(ranked_sources)

    # Step 5: Grounded answer
    answer_result = await _generate_grounded_answer(query, context_block, ranked_sources)

    return {
        "ok":            True,
        "answer":        answer_result["answer"],
        "sources":       [_source_summary(s) for s in ranked_sources[:3]],
        "search_plan":   search_plan,
        "retrieval":     {
            "results_fetched": len(retrieval["results"]),
            "results_used":    len(ranked_sources),
        },
        "context_used":  context_block[:500] + "..." if len(context_block) > 500 else context_block,
        "grounded":      answer_result["grounded"],
        "search_failed": False,
        "fail_reason":   None,
    }


# ---------------------------------------------------------------------------
# Web retrieval
# ---------------------------------------------------------------------------

async def _retrieve(search_plan: dict, max_results: int) -> dict[str, Any]:
    """
    Use existing web tools (web_searcher) to fetch results.
    Returns {fail, fail_reason, results}.
    """
    try:
        from core.web.web_searcher import search as web_search
        query = search_plan.get("rewritten_query", search_plan.get("original_query", ""))
        results = await web_search(query, max_results=max_results)

        if not results:
            # Try first variant
            variants = search_plan.get("query_variants", [])
            if variants:
                results = await web_search(variants[0], max_results=max_results)

        if not results:
            return {"fail": True, "fail_reason": "Web search returned no results.", "results": []}

        return {"fail": False, "fail_reason": None, "results": results}

    except Exception as exc:
        log.warning("search_pipeline: retrieval failed — %s", exc)
        return {"fail": True, "fail_reason": f"Search unavailable: {exc}", "results": []}


# ---------------------------------------------------------------------------
# Source ranking
# ---------------------------------------------------------------------------

_BLOCKED_DOMAINS = {
    "reddit.com", "pinterest.com", "facebook.com", "twitter.com",
    "instagram.com", "tiktok.com", "quora.com", "yahoo.answers.com",
}

_TRUSTED_DOMAINS = {
    "github.com", "stackoverflow.com", "developer.mozilla.org",
    "docs.python.org", "npmjs.com", "pypi.org", "reactjs.org",
    "fastapi.tiangolo.com", "docs.anthropic.com",
}


def _rank_sources(results: list[dict], query: str) -> list[dict]:
    """
    Rank retrieved sources by trust, relevance, and freshness.
    Rejects low-trust and irrelevant sources.
    """
    query_words = set(query.lower().split())
    ranked: list[tuple[float, dict]] = []

    for r in results:
        url     = r.get("url", "")
        title   = r.get("title", "").lower()
        snippet = r.get("snippet", "").lower()
        content = r.get("content", snippet)

        # Trust score
        domain = _extract_domain(url)
        if domain in _BLOCKED_DOMAINS:
            continue
        trust_score = 0.8 if domain in _TRUSTED_DOMAINS else 0.5

        # Relevance score (keyword overlap)
        text = f"{title} {snippet}"
        matches = sum(1 for w in query_words if len(w) > 3 and w in text)
        relevance = min(matches / max(len(query_words), 1), 1.0)
        if relevance < 0.1:
            continue  # completely irrelevant

        # Content quality (avoid empty snippets)
        if len(snippet) < 20:
            continue

        score = trust_score * 0.5 + relevance * 0.5
        ranked.append((score, {**r, "_rank_score": round(score, 3), "_domain": domain}))

    ranked.sort(key=lambda x: -x[0])
    return [item for _, item in ranked[:5]]


def _extract_domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Context building
# ---------------------------------------------------------------------------

def _build_context(sources: list[dict]) -> str:
    """
    Build a clean context block from ranked sources.
    Each source contributes title + snippet/content excerpt.
    No raw HTML. Max ~3000 chars total.
    """
    parts = []
    budget = 3000

    for i, s in enumerate(sources[:4], 1):
        title   = s.get("title", "Untitled")
        url     = s.get("url", "")
        content = s.get("content") or s.get("snippet", "")
        # Strip any residual HTML tags
        import re
        content = re.sub(r"<[^>]+>", " ", content)
        content = re.sub(r"\s+", " ", content).strip()

        excerpt = content[:600]
        part = f"[{i}] {title}\nURL: {url}\n{excerpt}"

        if len(part) > budget:
            part = part[:budget]
            parts.append(part)
            break

        parts.append(part)
        budget -= len(part) + 10

    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Grounded answer generation
# ---------------------------------------------------------------------------

async def _generate_grounded_answer(
    query:    str,
    context:  str,
    sources:  list[dict],
) -> dict[str, Any]:
    """
    Generate an answer grounded in retrieved context.
    No hallucination — answer must be derivable from context.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"answer": _no_api_answer(query, sources), "grounded": False}

    system = """You are an assistant that answers questions ONLY using the provided search results.

RULES:
1. Base your answer ONLY on the provided sources.
2. If the sources don't contain the answer, say "The search results don't directly answer this question."
3. Cite sources using [1], [2], etc. matching the source numbers.
4. Separate verified facts from inferences.
5. Keep the answer concise and factual — no padding.
6. Do not add information from your training beyond what the sources say."""

    user = f"""Question: {query}

Search results:
{context}

Answer the question using the above sources."""

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model=_ANTHROPIC_MODEL,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        answer = resp.content[0].text if resp.content else ""
        grounded = bool(answer and "[" in answer)   # has at least one citation
        return {"answer": answer, "grounded": grounded}
    except Exception as exc:
        log.error("search_pipeline: answer generation failed — %s", exc)
        return {"answer": _no_api_answer(query, sources), "grounded": False}


def _no_api_answer(query: str, sources: list[dict]) -> str:
    """Fallback answer when LLM is unavailable — surface raw source snippets."""
    if not sources:
        return "Search returned results but I cannot generate an answer without the LLM API."
    parts = [f"Search results for: {query}\n"]
    for i, s in enumerate(sources[:3], 1):
        parts.append(f"[{i}] {s.get('title', '')}: {s.get('snippet', '')[:200]}")
    return "\n".join(parts)


def _source_summary(s: dict) -> dict:
    return {
        "title":       s.get("title", ""),
        "url":         s.get("url", ""),
        "domain":      s.get("_domain", ""),
        "rank_score":  s.get("_rank_score", 0),
        "snippet":     s.get("snippet", "")[:200],
    }


def _fail_response(search_plan: dict, reason: str) -> dict[str, Any]:
    return {
        "ok":            False,
        "answer":        (
            f"Search is currently unavailable. {reason}\n\n"
            "I cannot provide a verified current answer without access to search results."
        ),
        "sources":       [],
        "search_plan":   search_plan,
        "retrieval":     {"results_fetched": 0, "results_used": 0},
        "context_used":  "",
        "grounded":      False,
        "search_failed": True,
        "fail_reason":   reason,
    }
