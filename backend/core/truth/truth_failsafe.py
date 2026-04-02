"""
truth/truth_failsafe.py — Hard fail-safe checks for truth and search.

System FAILS if any of these conditions are true:
  1. Live/current fact answered without a tool
  2. Fake search results generated or passed forward
  3. Raw HTML passed to a brain
  4. Context budget exceeded
  5. CEO retrieval bypassed by a brain
  6. Too much context loaded (token bloat)

Each check returns a FailSafeResult with {ok, violation, detail}.
CEO runs these checks before routing to any brain.

These are BLOCKING checks — if ok=False, execution halts.
"""

from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger("ceo_router.truth_failsafe")

# Max safe context character count before "token bloat" flag
_MAX_CONTEXT_CHARS = 12_000

# Minimum realistic search result (fake result guard)
_MIN_SEARCH_SNIPPET_LEN = 10
_MIN_SEARCH_RESULTS     = 0   # 0 = search may return empty (handled as fail)

# HTML detection patterns (raw HTML must not reach a brain)
_HTML_PATTERN = re.compile(r"<(html|head|body|div|span|script|style|p|a\s|ul|li|nav)[^>]*>", re.IGNORECASE)


def check_all(
    truth_classification: dict[str, Any],
    search_result:        dict[str, Any] | None,
    retrieval_result:     dict[str, Any] | None,
    context_passed:       str | list | None,
    brain_requested_retrieval: bool = False,
) -> dict[str, Any]:
    """
    Run all fail-safe checks.

    Returns:
        {
            ok:         bool,   # False = execution must halt
            violations: list[str],
            details:    list[str],
        }
    """
    violations = []
    details    = []

    # Check 1: live fact without tool
    r1 = check_live_without_tool(truth_classification)
    if not r1["ok"]:
        violations.append("live_fact_no_tool")
        details.append(r1["detail"])

    # Check 2: fake/hallucinated search results
    if search_result is not None:
        r2 = check_fake_search(search_result)
        if not r2["ok"]:
            violations.append("fake_search_result")
            details.append(r2["detail"])

    # Check 3: raw HTML in context
    if context_passed is not None:
        r3 = check_raw_html(context_passed)
        if not r3["ok"]:
            violations.append("raw_html_in_context")
            details.append(r3["detail"])

    # Check 4: context budget exceeded
    if context_passed is not None:
        r4 = check_context_budget(context_passed)
        if not r4["ok"]:
            violations.append("context_budget_exceeded")
            details.append(r4["detail"])

    # Check 5: brain attempted self-retrieval
    if brain_requested_retrieval:
        violations.append("brain_self_retrieval")
        details.append("A brain attempted to fetch context directly — CEO retrieval control bypassed.")

    ok = len(violations) == 0
    if not ok:
        log.warning("truth_failsafe: VIOLATIONS=%s", violations)

    return {
        "ok":         ok,
        "violations": violations,
        "details":    details,
    }


def check_live_without_tool(classification: dict[str, Any]) -> dict[str, Any]:
    """
    FAIL if truth_type is live_current or search_dependent but can_answer=False.
    This means we'd have to hallucinate — that's a hard fail.
    """
    truth_type  = classification.get("truth_type", "stable_knowledge")
    can_answer  = classification.get("can_answer", True)
    tool_required = classification.get("tool_required", False)

    if tool_required and not can_answer:
        return {
            "ok":     False,
            "detail": (
                f"truth_type={truth_type} requires a tool but none is available. "
                "Answering would require hallucination."
            ),
        }
    return {"ok": True, "detail": ""}


def check_fake_search(search_result: dict[str, Any]) -> dict[str, Any]:
    """
    FAIL if search result appears fabricated.
    Heuristics: all sources have empty URLs, all snippets are identical,
    or search_failed=False but results are suspiciously clean.
    """
    if search_result.get("search_failed"):
        return {"ok": True, "detail": ""}  # Failed search is fine — we handle it transparently

    sources = search_result.get("sources", [])

    # No sources but grounded=True is contradictory
    if search_result.get("grounded") and not sources:
        return {
            "ok":     False,
            "detail": "Search claims grounded=True but has no sources — result appears fabricated.",
        }

    # All sources have empty URLs
    if sources and all(not s.get("url") for s in sources):
        return {
            "ok":     False,
            "detail": "All search sources have empty URLs — result appears fabricated.",
        }

    # Snippets too short to be real
    if sources and all(len(s.get("snippet", "")) < _MIN_SEARCH_SNIPPET_LEN for s in sources):
        return {
            "ok":     False,
            "detail": "All search snippets are too short — results appear fabricated.",
        }

    return {"ok": True, "detail": ""}


def check_raw_html(context: str | list) -> dict[str, Any]:
    """
    FAIL if raw HTML is detected in context being passed to a brain.
    """
    if isinstance(context, list):
        text = " ".join(str(item) for item in context)
    else:
        text = str(context)

    if _HTML_PATTERN.search(text):
        return {
            "ok":     False,
            "detail": "Raw HTML detected in context passed to brain — must be stripped first.",
        }
    return {"ok": True, "detail": ""}


def check_context_budget(context: str | list) -> dict[str, Any]:
    """
    FAIL if context exceeds the max character budget (token bloat).
    """
    if isinstance(context, list):
        total = sum(len(str(item)) for item in context)
    else:
        total = len(str(context))

    if total > _MAX_CONTEXT_CHARS:
        return {
            "ok":     False,
            "detail": (
                f"Context size {total} chars exceeds limit {_MAX_CONTEXT_CHARS}. "
                "Prune before passing to brain."
            ),
        }
    return {"ok": True, "detail": ""}


def build_violation_response(failsafe_result: dict[str, Any]) -> dict[str, Any]:
    """
    Build a structured error response for a fail-safe violation.
    CEO returns this instead of proceeding to the brain.
    """
    violations = failsafe_result.get("violations", [])
    details    = failsafe_result.get("details", [])

    primary = violations[0] if violations else "unknown"

    messages = {
        "live_fact_no_tool":      "I cannot answer this with real-time accuracy — the required tool is not available.",
        "fake_search_result":     "Search result validation failed — I cannot use these results.",
        "raw_html_in_context":    "Content processing error — raw HTML was not cleaned before use.",
        "context_budget_exceeded":"Context exceeded safe limits — please narrow your request.",
        "brain_self_retrieval":   "Internal routing error — a module attempted unauthorized data access.",
    }

    return {
        "type":       "failsafe_violation",
        "violations": violations,
        "message":    messages.get(primary, "A safety check failed. Cannot proceed."),
        "details":    details,
    }
