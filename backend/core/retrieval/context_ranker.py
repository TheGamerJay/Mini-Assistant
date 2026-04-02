"""
retrieval/context_ranker.py — Context ranking and auto-pruning.

Called by retrieval_engine after gathering candidates.
Ranks by relevance + category match + recency + repair memory similarity.
Prunes weak matches, redundant entries, and low-score items.

RANKING FACTORS (weighted):
  1. relevance score (pre-set by source loader)     — weight 0.50
  2. source priority for this brain                 — weight 0.25
  3. keyword match with task_description            — weight 0.25

PRUNE IF:
  - combined score < 0.20
  - content is empty or < 10 chars
  - same source+subtype already represented (deduplicate)

LIMITS:
  - repair_memory: max 3 items
  - context_docs: max 2 items
  - logs: max 1 item
  - task_state: max 3 items
  - total: max 8 items per retrieval call
"""

from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger("ceo_router.context_ranker")

# Source priority per brain (higher = more useful for that brain)
_SOURCE_PRIORITY: dict[str, dict[str, float]] = {
    "builder":      {"project_files": 1.0, "task_state": 0.8, "context_docs": 0.5},
    "doctor":       {"repair_memory": 1.0, "logs": 0.9, "project_files": 0.7, "context_docs": 0.4},
    "hands":        {"task_state": 1.0, "test_results": 0.9},
    "vision":       {"task_state": 0.9, "project_files": 0.7},
    "general_chat": {"task_state": 0.9, "context_docs": 0.6},
    "ceo":          {"context_docs": 1.0, "task_state": 0.7},
    "task_assist":  {"task_state": 1.0, "context_docs": 0.5},
    "campaign_lab": {"task_state": 1.0, "context_docs": 0.4},
    "web_search":   {"task_state": 0.8},
}

# Per-source hard limits
_SOURCE_LIMITS: dict[str, int] = {
    "repair_memory": 3,
    "context_docs":  2,
    "logs":          1,
    "task_state":    3,
    "project_files": 2,
    "prior_outputs": 1,
    "test_results":  2,
}

_TOTAL_LIMIT = 8
_MIN_SCORE   = 0.20
_MIN_CONTENT = 10


def rank_and_prune(
    candidates:       list[dict[str, Any]],
    task_description: str,
    brain:            str,
    allowed_sources:  set[str],
) -> list[dict[str, Any]]:
    """
    Rank and prune a list of candidate context items.

    Each candidate must have:
      source   — source type string
      content  — text content
      relevance — float 0.0–1.0

    Returns ordered list of surviving items with added 'score' field.
    """
    if not candidates:
        return []

    keywords = _extract_keywords(task_description)
    priority_map = _SOURCE_PRIORITY.get(brain, {})

    scored: list[dict[str, Any]] = []
    for item in candidates:
        content = item.get("content", "")
        if not content or len(content) < _MIN_CONTENT:
            continue

        relevance_score  = float(item.get("relevance", 0.5))
        source           = item.get("source", "")
        source_priority  = priority_map.get(source, 0.5)
        keyword_score    = _keyword_overlap(content.lower(), keywords)

        combined = (
            relevance_score  * 0.50 +
            source_priority  * 0.25 +
            keyword_score    * 0.25
        )

        if combined < _MIN_SCORE:
            log.debug("ranker: pruned item source=%s score=%.2f (below threshold)", source, combined)
            continue

        scored.append({**item, "score": round(combined, 3)})

    # Sort by score descending
    scored.sort(key=lambda x: -x["score"])

    # Deduplicate: one item per source+subtype
    seen_subtypes: set[str] = set()
    deduplicated: list[dict[str, Any]] = []
    for item in scored:
        key = f"{item.get('source')}:{item.get('subtype', '')}"
        if key in seen_subtypes:
            continue
        seen_subtypes.add(key)
        deduplicated.append(item)

    # Enforce per-source limits
    source_counts: dict[str, int] = {}
    limited: list[dict[str, Any]] = []
    for item in deduplicated:
        source = item.get("source", "")
        count  = source_counts.get(source, 0)
        limit  = _SOURCE_LIMITS.get(source, 2)
        if count >= limit:
            log.debug("ranker: source=%s hit limit=%d, skipping", source, limit)
            continue
        source_counts[source] = count + 1
        limited.append(item)
        if len(limited) >= _TOTAL_LIMIT:
            break

    log.debug(
        "ranker: brain=%s candidates=%d → scored=%d → dedup=%d → final=%d",
        brain, len(candidates), len(scored), len(deduplicated), len(limited),
    )
    return limited


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords (>3 chars, not stopwords)."""
    STOPWORDS = {
        "this", "that", "with", "from", "have", "will", "what", "when", "where",
        "which", "there", "their", "about", "would", "could", "should", "more",
        "into", "than", "then", "some", "your", "does", "just", "been", "also",
        "make", "like", "time", "know", "want", "need", "help", "code", "task",
    }
    words = re.findall(r"[a-z]{4,}", text.lower())
    return {w for w in words if w not in STOPWORDS}


def _keyword_overlap(content: str, keywords: set[str]) -> float:
    """Fraction of task keywords found in content (0.0–1.0)."""
    if not keywords:
        return 0.5
    matches = sum(1 for kw in keywords if kw in content)
    return min(matches / len(keywords), 1.0)
