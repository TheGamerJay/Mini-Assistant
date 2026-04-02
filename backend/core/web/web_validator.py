"""
web/web_validator.py — Post-retrieval validation for web data.

CEO must validate web data before it is passed to generation modules.
Raw web data is NOT trusted — it must pass relevance, trust, and sanity checks.

Validation checks:
  relevance    — content matches the query intent
  source_trust — domain is not a known low-trust source
  duplication  — results are not near-identical
  sanity       — content is not gibberish or error pages

If validation fails:
  → discard invalid items
  → return only the items that passed
  → if ALL items fail → return ok=False with reason

Rules:
  - never raises — always returns a result
  - does NOT block execution if some results pass
  - validation is CPU-friendly (no LLM calls — keyword overlap only)
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

log = logging.getLogger("ceo_router.web_validator")

# ── Low-trust domain patterns ──────────────────────────────────────────────────
_LOW_TRUST_DOMAINS = re.compile(
    r"\b(pinterest\.com|quora\.com|reddit\.com/r/|facebook\.com|"
    r"twitter\.com|tiktok\.com|instagram\.com|tumblr\.com|"
    r"answers\.yahoo\.com|wikianswers\.com)\b",
    re.IGNORECASE,
)

# ── Error page signals ─────────────────────────────────────────────────────────
_ERROR_PAGE = re.compile(
    r"\b(404 not found|403 forbidden|page not found|access denied|"
    r"this page (doesn.t|does not) exist|error 5\d\d|"
    r"internal server error|gateway timeout)\b",
    re.IGNORECASE,
)

# ── Gibberish/low-quality signals ─────────────────────────────────────────────
_MIN_WORD_COUNT    = 20   # fewer words = suspect
_MIN_AVG_WORD_LEN  = 3.0  # avg word length below this = possible garbage
_DUPLICATION_RATIO = 0.8  # if 80%+ of words overlap with another result, it's a dupe


def validate_web_results(
    query:   str,
    results: list[dict[str, Any]],
    mode:    str = "search",
) -> dict[str, Any]:
    """
    Validate a list of web results against the original query.

    Args:
        query:   the original search query or intent
        results: list of result dicts from web_search / web_scraper / web_crawler
        mode:    "search" | "scraper" | "crawler"

    Returns:
        {
            "ok":             bool,
            "passed":         list[dict],   # validated results only
            "rejected":       list[dict],   # items that failed + reason
            "issues":         list[str],
            "validation_mode": str,
        }
    """
    passed:   list[dict] = []
    rejected: list[dict] = []
    issues:   list[str]  = []

    query_keywords = _tokenize(query)

    seen_fingerprints: list[set[str]] = []

    for item in results:
        text = _get_text(item, mode)
        url  = item.get("url", "")

        # ── Sanity check ────────────────────────────────────────────────────
        if _ERROR_PAGE.search(text):
            rejected.append({**item, "_reject_reason": "error_page"})
            continue

        words = _tokenize(text)
        if len(words) < _MIN_WORD_COUNT:
            rejected.append({**item, "_reject_reason": "too_short"})
            continue

        if words and (sum(len(w) for w in words) / len(words)) < _MIN_AVG_WORD_LEN:
            rejected.append({**item, "_reject_reason": "low_quality_text"})
            continue

        # ── Source trust check ─────────────────────────────────────────────
        if url and _LOW_TRUST_DOMAINS.search(url):
            log.debug("web_validator: low-trust domain skipped: %s", url[:60])
            rejected.append({**item, "_reject_reason": "low_trust_domain"})
            continue

        # ── Relevance check ────────────────────────────────────────────────
        if query_keywords:
            word_set = set(words)
            overlap = len(query_keywords & word_set) / len(query_keywords)
            if overlap < 0.1:
                rejected.append({**item, "_reject_reason": "not_relevant"})
                continue

        # ── Duplication check ──────────────────────────────────────────────
        fp = set(words[:100])  # fingerprint: first 100 words
        if _is_duplicate(fp, seen_fingerprints):
            rejected.append({**item, "_reject_reason": "duplicate"})
            continue
        seen_fingerprints.append(fp)

        passed.append(item)

    if not passed and results:
        issues.append(f"all {len(results)} web results failed validation")
    elif len(rejected) > 0:
        reasons = set(r["_reject_reason"] for r in rejected)
        issues.append(f"{len(rejected)} result(s) rejected: {', '.join(sorted(reasons))}")

    log.info(
        "web_validator: mode=%s query=%r passed=%d rejected=%d",
        mode, query[:60], len(passed), len(rejected),
    )

    return {
        "ok":              len(passed) > 0,
        "passed":          passed,
        "rejected":        rejected,
        "issues":          issues,
        "validation_mode": mode,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_text(item: dict, mode: str) -> str:
    """Extract the primary text field from a result item."""
    if mode == "search":
        return f"{item.get('title', '')} {item.get('snippet', '')}"
    return item.get("text", item.get("summary", ""))


def _tokenize(text: str) -> set[str]:
    """Lowercase word tokens, removing short stop words."""
    STOP = {"the", "a", "an", "is", "in", "of", "to", "and", "or", "for",
            "it", "on", "at", "by", "be", "as", "this", "that", "with"}
    words = re.findall(r"[a-z]{3,}", text.lower())
    return {w for w in words if w not in STOP}


def _is_duplicate(fp: set[str], seen: list[set[str]]) -> bool:
    """Return True if fp overlaps too heavily with any previously seen fingerprint."""
    for existing in seen:
        if not existing:
            continue
        overlap = len(fp & existing) / max(len(fp), len(existing), 1)
        if overlap >= _DUPLICATION_RATIO:
            return True
    return False
