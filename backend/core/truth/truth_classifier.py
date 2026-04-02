"""
truth/truth_classifier.py — CEO truth classification system.

CEO must classify every request before routing.

TRUTH TYPES:
  stable_knowledge  — answered from training data (facts, explanations, code help)
  live_current      — requires a real-time tool (clock, weather API, etc.)
  search_dependent  — requires real web search (latest versions, news, etc.)
  mixed             — part stable + part search-dependent

CRITICAL RULE:
  NO TOOL = NO CURRENT FACT ANSWER.
  If truth_type is live_current or search_dependent and no tool is available,
  CEO must respond with a cannot_verify message — never hallucinate.

EXAMPLES:
  "What is Python?"                 → stable_knowledge
  "What time is it?"                → live_current  (tool: system_clock)
  "What's the weather in London?"   → live_current  (tool: weather_api)
  "Latest version of React?"        → search_dependent
  "What happened in the news today?"→ search_dependent
  "Explain closures in JS"          → stable_knowledge
  "Is FastAPI still maintained?"    → mixed (explain=stable, status=search)
"""

from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger("ceo_router.truth")

# ── Pattern sets ─────────────────────────────────────────────────────────────

_LIVE_CURRENT_PATTERNS = re.compile(
    r"\b("
    r"what time|current time|time right now|time is it|"
    r"today['']?s date|what day|what['']?s the date|"
    r"weather|forecast|temperature|humidity|"
    r"stock price|exchange rate|currency rate|"
    r"is .{0,30} (up|down|live|online|working|available)\?|"
    r"current (status|price|rate|score|standing)|"
    r"right now|at this moment|as of (today|now)"
    r")\b",
    re.IGNORECASE,
)

_SEARCH_DEPENDENT_PATTERNS = re.compile(
    r"\b("
    r"latest|newest|most recent|current version|changelog|release notes|"
    r"just released|just announced|new in|update[ds]? (for|to|of)|"
    r"news|headlines|breaking|happened today|happened this week|"
    r"trending|viral|popular right now|"
    r"who won|results of|outcome of|"
    r"still (maintained|supported|active|developed)|"
    r"recently (added|changed|deprecated|removed)|"
    r"docs for|documentation for|official site for"
    r")\b",
    re.IGNORECASE,
)

_STABLE_KNOWLEDGE_PATTERNS = re.compile(
    r"\b("
    r"what is|what are|explain|how does|how do|define|describe|"
    r"difference between|compare|pros and cons|example of|"
    r"write (a|an|the)|create (a|an)|generate|build|implement|fix|debug|"
    r"refactor|review|test|help me|can you|please|should i|"
    r"best practice|why (is|does|do)|when (should|to)"
    r")\b",
    re.IGNORECASE,
)

# Tools available in the system
_AVAILABLE_TOOLS = {
    "system_clock",   # current time
    "web_search",     # search pipeline (Phase 68)
    # future: weather_api, stock_api, etc.
}


def classify(message: str, tools_available: set[str] = None) -> dict[str, Any]:
    """
    Classify the truth type of a user message.

    Returns:
        {
            truth_type:       "stable_knowledge" | "live_current" | "search_dependent" | "mixed",
            tool_required:    bool,
            tool_name:        str | None,
            can_answer:       bool,    # True if we have the required tool
            confidence:       float,
            cannot_verify_reason: str | None,  # set if can_answer=False
        }
    """
    if tools_available is None:
        tools_available = _AVAILABLE_TOOLS

    msg = message.strip()

    is_live    = bool(_LIVE_CURRENT_PATTERNS.search(msg))
    is_search  = bool(_SEARCH_DEPENDENT_PATTERNS.search(msg))
    is_stable  = bool(_STABLE_KNOWLEDGE_PATTERNS.search(msg))

    # Determine truth type
    if is_live and is_search:
        truth_type = "mixed"
    elif is_live:
        truth_type = "live_current"
    elif is_search:
        truth_type = "search_dependent"
    elif is_stable:
        truth_type = "stable_knowledge"
    else:
        # Default: treat as stable_knowledge with lower confidence
        truth_type = "stable_knowledge"

    # Determine tool requirements
    tool_required, tool_name = _resolve_tool(truth_type, msg)

    can_answer = True
    cannot_verify_reason = None

    if tool_required:
        if tool_name and tool_name not in tools_available:
            can_answer = False
            cannot_verify_reason = (
                f"This question requires real-time information ({tool_name}), "
                f"which is not available. I cannot verify current facts without a tool."
            )
        elif not tool_name:
            # Generic live/search — check if web_search is available
            if "web_search" not in tools_available:
                can_answer = False
                cannot_verify_reason = (
                    "This question requires current information from the web. "
                    "Search is not available in this context."
                )

    # Compute confidence
    matches = sum([is_live, is_search, is_stable])
    confidence = 0.9 if matches == 1 else 0.7 if matches > 1 else 0.5

    result = {
        "truth_type":             truth_type,
        "tool_required":          tool_required,
        "tool_name":              tool_name,
        "can_answer":             can_answer,
        "confidence":             confidence,
        "cannot_verify_reason":   cannot_verify_reason,
    }

    log.debug(
        "truth_classifier: type=%s tool_required=%s can_answer=%s confidence=%.1f",
        truth_type, tool_required, can_answer, confidence,
    )
    return result


def build_cannot_verify_response(classification: dict[str, Any], message: str) -> dict[str, Any]:
    """
    Build a structured cannot_verify response for cases where we cannot
    answer a live/search-dependent question without a tool.
    CEO returns this directly without calling any brain.
    """
    reason = classification.get("cannot_verify_reason", "Cannot verify without a tool.")
    truth_type = classification.get("truth_type", "live_current")

    guidance = {
        "live_current":     "You can check this using your device's clock or a dedicated app.",
        "search_dependent": "You can search for this using a web browser for the most up-to-date answer.",
        "mixed":            "Part of this question can be answered, but the real-time portion requires a tool.",
    }.get(truth_type, "")

    return {
        "type":             "cannot_verify",
        "truth_type":       truth_type,
        "reason":           reason,
        "guidance":         guidance,
        "message":          (
            f"I can't answer this with certainty — {reason.lower()} "
            + (f"\n\n{guidance}" if guidance else "")
        ).strip(),
        "verified_facts":   [],
        "inferences":       [],
    }


def get_current_time() -> dict[str, Any]:
    """
    Tool: system_clock — returns the current UTC time.
    This IS an available tool — CEO may call it for time queries.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    return {
        "tool":       "system_clock",
        "utc_time":   now.isoformat(timespec="seconds"),
        "utc_date":   now.strftime("%Y-%m-%d"),
        "day_of_week": now.strftime("%A"),
        "unix_ts":    int(now.timestamp()),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TIME_PATTERNS = re.compile(
    r"\b(what time|current time|time right now|time is it|"
    r"today['']?s date|what day|what['']?s the date)\b",
    re.IGNORECASE,
)


def _resolve_tool(truth_type: str, message: str = "") -> tuple[bool, str | None]:
    """Return (tool_required, tool_name) for a truth type.

    system_clock is ONLY injected when the query is specifically about time/date.
    All other live_current queries (weather, stocks, uptime) require a tool that
    isn't available, so they surface a cannot_verify response.
    """
    if truth_type == "stable_knowledge":
        return False, None
    if truth_type == "live_current":
        # Only inject clock for actual time/date queries
        if message and _TIME_PATTERNS.search(message):
            return True, "system_clock"
        # All other live queries (weather, stocks, etc.) need unavailable tools
        return True, "live_data_tool"
    if truth_type == "search_dependent":
        return True, "web_search"
    if truth_type == "mixed":
        return True, "web_search"
    return False, None
