"""
Memory Filter — Phase 4

Filters the memory pool to only inject relevant context for a given task.
Prevents noisy prompt injection by scoring and selecting only the most
relevant memory snippets.

DO NOT inject all memory into every task.
Only inject what's relevant to:
  - current mode
  - task type
  - project context
  - current step

This module is called by the orchestrator before every Claude invocation.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_MEMORY_CHARS = 1800  # hard cap on injected memory to protect context window


@dataclass
class MemorySnippet:
    source:    str     # "user_prefs" | "session" | "long_term" | "build_patterns" | "lessons"
    content:   str
    relevance: float   # 0.0 – 1.0
    mode:      str     # which mode this memory applies to


def filter_memory(
    mode:      str,
    task_type: str,
    query:     str,
    all_memory: List[Dict[str, Any]],
    max_chars:  int = MAX_MEMORY_CHARS,
) -> str:
    """
    Select and format the most relevant memory snippets for a task.

    Args:
        mode:       "chat" | "builder" | "image"
        task_type:  "build" | "patch" | "query" | "image" | "chat"
        query:      The user's normalized goal / request.
        all_memory: Raw memory dicts from various sources.
        max_chars:  Hard cap on total injected content.

    Returns:
        Formatted string for injection into the system prompt, or "" if nothing relevant.
    """
    snippets = _score_and_filter(mode, task_type, query, all_memory)

    if not snippets:
        return ""

    # Sort by relevance, descending
    snippets.sort(key=lambda s: s.relevance, reverse=True)

    # Pack up to max_chars
    result_parts: List[str] = []
    total = 0

    for snippet in snippets:
        if snippet.relevance < 0.25:
            break  # below relevance threshold
        if total + len(snippet.content) > max_chars:
            break
        result_parts.append(f"[{snippet.source.upper()}] {snippet.content}")
        total += len(snippet.content)

    if not result_parts:
        return ""

    return "\n\n## Relevant Context\n" + "\n\n".join(result_parts)


def _score_and_filter(
    mode:      str,
    task_type: str,
    query:     str,
    all_memory: List[Dict[str, Any]],
) -> List[MemorySnippet]:
    """Score each memory item and return a filtered list."""
    query_tokens = _tokenize(query)
    results: List[MemorySnippet] = []

    for item in all_memory:
        source  = item.get("source", "unknown")
        content = item.get("content", "")
        item_mode = item.get("mode", "all")

        if not content:
            continue

        # Mode filter: skip items that belong to a different mode
        if item_mode not in ("all", mode):
            continue

        # Task type filter
        item_type = item.get("task_type", "all")
        if item_type not in ("all", task_type):
            continue

        # Relevance scoring
        score = _relevance_score(content, query_tokens, source, mode, task_type)

        results.append(MemorySnippet(
            source=source,
            content=content.strip()[:600],  # truncate per snippet
            relevance=score,
            mode=item_mode,
        ))

    return results


def _relevance_score(
    content:      str,
    query_tokens: List[str],
    source:       str,
    mode:         str,
    task_type:    str,
) -> float:
    """Score 0.0–1.0 how relevant a memory item is for the current task."""
    score = 0.0
    content_lower = content.lower()
    content_tokens = _tokenize(content_lower)

    # Token overlap
    if query_tokens:
        matches = sum(1 for t in query_tokens if t in content_lower)
        score += 0.6 * (matches / max(1, len(query_tokens)))

    # Source affinity — builder tasks prefer build patterns and lessons
    source_boosts = {
        ("builder", "build"):    {"build_patterns": 0.25, "lessons": 0.20},
        ("builder", "patch"):    {"lessons": 0.25, "session": 0.15},
        ("image",   "image"):   {"user_prefs": 0.20},
        ("chat",    "chat"):    {"user_prefs": 0.15, "session": 0.15},
        ("chat",    "query"):   {"long_term": 0.10},
    }
    key = (mode, task_type)
    source_adj = source_boosts.get(key, {})
    score += source_adj.get(source, 0.0)

    # Recency boost (items with a "timestamp" field that's recent)
    # (placeholder — real implementation would parse ISO timestamp)
    if "timestamp" in content_lower:
        score += 0.05

    return min(1.0, score)


_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "be", "to", "of", "and",
    "or", "in", "it", "this", "that", "for", "with", "on", "at",
    "i", "you", "we", "they", "my", "me", "do", "does", "did",
})


def _tokenize(text: str) -> List[str]:
    words = re.findall(r"\b[a-z]{3,}\b", text.lower())
    return [w for w in words if w not in _STOP_WORDS]
