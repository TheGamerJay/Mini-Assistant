"""
repair_memory/repair_search.py — Repair Memory Library: retrieval and matching.

Searches the repair memory library for similar past problems.
Returns ranked matches with similarity scores and confidence levels.

Matching algorithm:
  1. Category-first lookup (required — no cross-category search)
  2. Normalize problem_name: lowercase, strip punctuation, trim
  3. Tokenize into keywords
  4. Score token overlap against stored problem_name values
  5. Return top matches sorted by similarity_score DESC, then success_count DESC

Confidence levels:
  0.75+ → HIGH
  0.50–0.74 → MEDIUM
  0.25–0.49 → LOW
  below 0.25 → IGNORE (not returned)

Match result format:
  {
      "problem_name":    str,
      "solution_name":   str,
      "solution_steps":  list[str],
      "similarity_score": float,
      "confidence_level": "HIGH" | "MEDIUM" | "LOW",
      "success_count":   int,
      "_slug":           str,
  }

Rules:
  - matches are REFERENCE ONLY — never auto-apply
  - LOW confidence matches are returned but flagged
  - IGNORE-level matches are excluded entirely
  - failsafe: if no matches, return empty list (caller uses normal diagnosis)
"""

from __future__ import annotations

import logging
import re
import string
from typing import Any

log = logging.getLogger("ceo_router.repair_search")

# Confidence thresholds
_HIGH_THRESHOLD   = 0.75
_MEDIUM_THRESHOLD = 0.50
_LOW_THRESHOLD    = 0.25

# Common stop words to exclude from token comparison
_STOP_WORDS = {
    "the", "a", "an", "is", "in", "of", "to", "and", "or", "for",
    "it", "on", "at", "by", "be", "as", "this", "that", "with",
    "not", "no", "was", "are", "were", "has", "have", "had",
    "when", "after", "before", "during", "while", "from", "into",
}


def search(
    category:    str,
    problem_description: str,
    top_n:       int = 3,
) -> list[dict[str, Any]]:
    """
    Search for similar problems in the given category.

    Returns up to top_n matches with confidence >= LOW.
    Returns empty list if no matches found (caller falls back to normal diagnosis).
    """
    from .repair_store import list_category

    records = list_category(category)
    if not records:
        log.debug("repair_search: no records in category=%s", category)
        return []

    query_tokens = _tokenize(problem_description)
    if not query_tokens:
        log.debug("repair_search: empty query tokens for description=%r", problem_description[:60])
        return []

    scored: list[dict[str, Any]] = []
    for record in records:
        stored_name   = record.get("problem_name", "")
        stored_tokens = _tokenize(stored_name)

        score      = _score(query_tokens, stored_tokens)
        confidence = _confidence_level(score)

        if confidence == "IGNORE":
            continue

        scored.append({
            "problem_name":     stored_name,
            "solution_name":    record.get("solution_name", ""),
            "solution_steps":   record.get("solution_steps", []),
            "similarity_score": round(score, 3),
            "confidence_level": confidence,
            "success_count":    record.get("success_count", 0),
            "_slug":            record.get("_slug", ""),
            "_category":        category,
        })

    # Sort: similarity_score DESC, then success_count DESC
    scored.sort(key=lambda x: (-x["similarity_score"], -x["success_count"]))

    top = scored[:top_n]
    log.info(
        "repair_search: category=%s query=%r matches=%d returned=%d",
        category, problem_description[:60], len(scored), len(top),
    )
    return top


def search_all_categories(
    problem_description: str,
    top_n:               int = 3,
) -> list[dict[str, Any]]:
    """
    Search across all categories. Returns top_n best matches overall.
    Less precise than category-first — use only when category is unknown.
    """
    from .repair_store import ALLOWED_CATEGORIES

    all_matches: list[dict[str, Any]] = []
    for cat in ALLOWED_CATEGORIES:
        matches = search(cat, problem_description, top_n=top_n)
        all_matches.extend(matches)

    all_matches.sort(key=lambda x: (-x["similarity_score"], -x["success_count"]))
    return all_matches[:top_n]


def check_duplicate(
    category:        str,
    problem_name:    str,
    threshold:       float = _HIGH_THRESHOLD,
) -> tuple[bool, list[dict[str, Any]]]:
    """
    Check if a highly similar problem already exists in the category.

    Returns (is_duplicate, matching_records).
    If is_duplicate=True, caller should NOT create a new file.
    """
    matches = search(category, problem_name, top_n=3)
    high_matches = [m for m in matches if m["similarity_score"] >= threshold]
    return bool(high_matches), high_matches


def score_pair(text_a: str, text_b: str) -> float:
    """
    Score similarity between two problem descriptions.
    Useful for direct comparison without a full search.
    """
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    return _score(tokens_a, tokens_b)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    """Lowercase, strip punctuation, tokenize, remove stop words."""
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    tokens = set(text.split())
    return tokens - _STOP_WORDS


def _score(query: set[str], candidate: set[str]) -> float:
    """
    Token overlap similarity score (Jaccard-like, biased toward query coverage).

    Combines:
      - query coverage: how many query tokens appear in candidate
      - Jaccard overlap: intersection / union

    Formula: 0.7 * query_coverage + 0.3 * jaccard
    """
    if not query or not candidate:
        return 0.0

    intersection = query & candidate
    if not intersection:
        return 0.0

    query_coverage = len(intersection) / len(query)
    jaccard        = len(intersection) / len(query | candidate)

    return round(0.7 * query_coverage + 0.3 * jaccard, 4)


def _confidence_level(score: float) -> str:
    if score >= _HIGH_THRESHOLD:
        return "HIGH"
    if score >= _MEDIUM_THRESHOLD:
        return "MEDIUM"
    if score >= _LOW_THRESHOLD:
        return "LOW"
    return "IGNORE"
